"""Composition root and mutable runtime container."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from cleanarr.application.authentication import AuthenticationService
from cleanarr.application.configuration import RuntimeConfigurationService, build_downloader_client
from cleanarr.application.service import CascadeDeletionService
from cleanarr.application.strategies import DeletionStrategyFactory
from cleanarr.domain.config import (
    JellyfinServiceConfig,
    RuntimeConfig,
    SeerrServiceConfig,
)
from cleanarr.infrastructure.auth import InMemorySessionStore, PasswordHasher
from cleanarr.infrastructure.clients import (
    JellyfinServerClient,
    NullDownloaderClient,
    NullJellyfinServerClient,
    NullRadarrClient,
    NullSeerrClient,
    NullSonarrClient,
    RadarrClient,
    SeerrClient,
    SonarrClient,
)
from cleanarr.infrastructure.config_store import SqliteConfigStore
from cleanarr.infrastructure.downloaders import (
    DownloaderTarget,
    MultiDownloaderClient,
)
from cleanarr.infrastructure.logging import configure_logging
from cleanarr.infrastructure.routers import MultiRadarrClient, MultiSonarrClient, RadarrTarget, SonarrTarget
from cleanarr.infrastructure.settings import Settings


@dataclass
class ServiceRuntime:
    """Current live service graph built from saved configuration."""

    config: RuntimeConfig
    service: CascadeDeletionService
    strategy_factory: DeletionStrategyFactory
    radarr: RoutedRadarrClient
    sonarr: RoutedSonarrClient
    seerr: SeerrClient | NullSeerrClient
    downloader: DownloaderClient
    jellyfin_server: JellyfinServerClient | NullJellyfinServerClient

    async def close(self) -> None:
        """Dispose all HTTP clients."""

        await self.radarr.close()
        await self.sonarr.close()
        await self.seerr.close()
        await self.downloader.close()
        await self.jellyfin_server.close()


class ServiceContainer:
    """Own mutable runtime state plus config CRUD helpers."""

    def __init__(
        self,
        *,
        settings: Settings,
        config_service: RuntimeConfigurationService,
        auth_service: AuthenticationService,
        runtime: ServiceRuntime,
    ) -> None:
        self.settings = settings
        self.config_service = config_service
        self.auth_service = auth_service
        self._runtime = runtime
        self._runtime_lock = asyncio.Lock()

    @classmethod
    def from_settings(cls, settings: Settings) -> ServiceContainer:
        config_service = RuntimeConfigurationService(
            store=SqliteConfigStore(
                settings.db_path,
                migrate_from=settings.config_state_path,
            ),
            settings=settings,
        )
        auth_service = AuthenticationService(
            config_service=config_service,
            password_hasher=PasswordHasher(),
            session_store=InMemorySessionStore(),
        )
        runtime = cls._build_runtime(settings=settings, config=config_service.get_config())
        return cls(
            settings=settings,
            config_service=config_service,
            auth_service=auth_service,
            runtime=runtime,
        )

    @property
    def config(self) -> RuntimeConfig:
        """Return a snapshot of the live runtime configuration."""

        return self._runtime.config

    @property
    def service(self) -> CascadeDeletionService:
        """Return the current cascade deletion service."""

        return self._runtime.service

    @property
    def radarr(self) -> RoutedRadarrClient:
        return self._runtime.radarr

    @property
    def sonarr(self) -> RoutedSonarrClient:
        return self._runtime.sonarr

    @property
    def seerr(self) -> SeerrClient | NullSeerrClient:
        return self._runtime.seerr

    @property
    def downloader(self) -> DownloaderClient:
        return self._runtime.downloader

    @property
    def jellyfin_server(self) -> JellyfinServerClient | NullJellyfinServerClient:
        return self._runtime.jellyfin_server

    @property
    def strategy_factory(self) -> DeletionStrategyFactory:
        return self._runtime.strategy_factory

    @property
    def webhook_shared_token(self) -> str | None:
        """Return the currently active webhook token."""

        return self._runtime.config.general.webhook_shared_token

    @property
    def admin_shared_token(self) -> str | None:
        """Return the static admin token used for config mutations."""

        return self.settings.admin_shared_token

    async def refresh_runtime(self) -> None:
        """Rebuild the live service graph from persisted config."""

        async with self._runtime_lock:
            new_runtime = self._build_runtime(settings=self.settings, config=self.config_service.get_config())
            old_runtime = self._runtime
            self._runtime = new_runtime
        await old_runtime.close()

    async def close(self) -> None:
        """Dispose all underlying HTTP clients."""

        await self._runtime.close()

    @staticmethod
    def _build_runtime(*, settings: Settings, config: RuntimeConfig) -> ServiceRuntime:
        logger = logging.getLogger("cleanarr")
        general = config.general
        configure_logging(general.log_level)

        active_radarr = [service for service in config.radarr if service.enabled]
        active_sonarr = [service for service in config.sonarr if service.enabled]
        active_seerr = ServiceContainer._pick_active_seerr(config.seerr)
        active_downloaders = [service for service in config.downloaders if service.enabled]
        active_jellyfin = ServiceContainer._pick_active_jellyfin(config.jellyfin)

        radarr: RoutedRadarrClient = (
            MultiRadarrClient(
                [
                    RadarrTarget(
                        id=service.id,
                        name=service.name,
                        client=RadarrClient(
                            base_url=service.url,
                            api_key=service.api_key,
                            timeout_seconds=general.http_timeout_seconds,
                        ),
                    )
                    for service in active_radarr
                ]
            )
            if active_radarr
            else NullRadarrClient()
        )
        sonarr: RoutedSonarrClient = (
            MultiSonarrClient(
                [
                    SonarrTarget(
                        id=service.id,
                        name=service.name,
                        client=SonarrClient(
                            base_url=service.url,
                            api_key=service.api_key,
                            timeout_seconds=general.http_timeout_seconds,
                        ),
                    )
                    for service in active_sonarr
                ]
            )
            if active_sonarr
            else NullSonarrClient()
        )
        seerr = (
            SeerrClient(
                base_url=active_seerr.url,
                api_key=active_seerr.api_key,
                timeout_seconds=general.http_timeout_seconds,
            )
            if active_seerr
            else NullSeerrClient()
        )
        downloader: DownloaderClient = (
            MultiDownloaderClient(
                [
                    DownloaderTarget(
                        id=service.id,
                        name=service.name,
                        kind=service.kind.value,
                        client=build_downloader_client(
                            service,
                            timeout_seconds=general.http_timeout_seconds,
                        ),
                    )
                    for service in active_downloaders
                ]
            )
            if active_downloaders
            else NullDownloaderClient()
        )
        jellyfin_server = (
            JellyfinServerClient(
                base_url=active_jellyfin.url,
                api_key=active_jellyfin.api_key,
                timeout_seconds=general.http_timeout_seconds,
            )
            if active_jellyfin
            else NullJellyfinServerClient()
        )

        strategy_factory = DeletionStrategyFactory(
            dry_run=general.dry_run,
            logger=logger,
            radarr=radarr,
            sonarr=sonarr,
            seerr=seerr,
            downloader=downloader,
        )
        return ServiceRuntime(
            config=config,
            service=CascadeDeletionService(strategy_factory, jellyfin=jellyfin_server),
            strategy_factory=strategy_factory,
            radarr=radarr,
            sonarr=sonarr,
            seerr=seerr,
            downloader=downloader,
            jellyfin_server=jellyfin_server,
        )

    @staticmethod
    def _pick_active_seerr(
        services: list[SeerrServiceConfig],
    ) -> SeerrServiceConfig | None:
        enabled = [service for service in services if service.enabled]
        if not enabled:
            return None
        default = next((service for service in enabled if service.is_default), None)
        return default or enabled[0]

    @staticmethod
    def _pick_active_jellyfin(
        services: list[JellyfinServiceConfig],
    ) -> JellyfinServiceConfig | None:
        enabled = [service for service in services if service.enabled]
        if not enabled:
            return None
        default = next((service for service in enabled if service.is_default), None)
        return default or enabled[0]


DownloaderClient = MultiDownloaderClient | NullDownloaderClient
RoutedRadarrClient = MultiRadarrClient | NullRadarrClient
RoutedSonarrClient = MultiSonarrClient | NullSonarrClient
