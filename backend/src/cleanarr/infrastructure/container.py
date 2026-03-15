"""Composition root and mutable runtime container."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from cleanarr.application.authentication import AuthenticationService
from cleanarr.application.configuration import RuntimeConfigurationService
from cleanarr.application.service import CascadeDeletionService
from cleanarr.application.strategies import DeletionStrategyFactory
from cleanarr.domain.config import (
    JellyseerrServiceConfig,
    QbittorrentServiceConfig,
    RadarrServiceConfig,
    RuntimeConfig,
    SonarrServiceConfig,
)
from cleanarr.infrastructure.auth import InMemorySessionStore, PasswordHasher
from cleanarr.infrastructure.clients import (
    JellyseerrClient,
    NullDownloaderClient,
    NullJellyseerrClient,
    NullRadarrClient,
    NullSonarrClient,
    QbittorrentClient,
    RadarrClient,
    SonarrClient,
)
from cleanarr.infrastructure.config_store import FileConfigStore
from cleanarr.infrastructure.logging import configure_logging
from cleanarr.infrastructure.settings import Settings


@dataclass
class ServiceRuntime:
    """Current live service graph built from saved configuration."""

    config: RuntimeConfig
    service: CascadeDeletionService
    radarr: RadarrClient | NullRadarrClient
    sonarr: SonarrClient | NullSonarrClient
    jellyseerr: JellyseerrClient | NullJellyseerrClient
    downloader: QbittorrentClient | NullDownloaderClient

    async def close(self) -> None:
        """Dispose all HTTP clients."""

        await self.radarr.close()
        await self.sonarr.close()
        await self.jellyseerr.close()
        await self.downloader.close()


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
            store=FileConfigStore(settings.config_state_path),
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
    def radarr(self) -> RadarrClient | NullRadarrClient:
        return self._runtime.radarr

    @property
    def sonarr(self) -> SonarrClient | NullSonarrClient:
        return self._runtime.sonarr

    @property
    def jellyseerr(self) -> JellyseerrClient | NullJellyseerrClient:
        return self._runtime.jellyseerr

    @property
    def downloader(self) -> QbittorrentClient | NullDownloaderClient:
        return self._runtime.downloader

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

        active_radarr = ServiceContainer._pick_active_radarr(config.radarr)
        active_sonarr = ServiceContainer._pick_active_sonarr(config.sonarr)
        active_jellyseerr = ServiceContainer._pick_active_jellyseerr(config.jellyseerr)
        active_downloader = ServiceContainer._pick_active_downloader(config.downloaders)

        radarr = (
            RadarrClient(
                base_url=active_radarr.url,
                api_key=active_radarr.api_key,
                timeout_seconds=general.http_timeout_seconds,
            )
            if active_radarr
            else NullRadarrClient()
        )
        sonarr = (
            SonarrClient(
                base_url=active_sonarr.url,
                api_key=active_sonarr.api_key,
                timeout_seconds=general.http_timeout_seconds,
            )
            if active_sonarr
            else NullSonarrClient()
        )
        jellyseerr = (
            JellyseerrClient(
                base_url=active_jellyseerr.url,
                api_key=active_jellyseerr.api_key,
                timeout_seconds=general.http_timeout_seconds,
            )
            if active_jellyseerr
            else NullJellyseerrClient()
        )
        downloader = (
            QbittorrentClient(
                base_url=active_downloader.url,
                username=active_downloader.username,
                password=active_downloader.password,
                timeout_seconds=general.http_timeout_seconds,
            )
            if active_downloader
            else NullDownloaderClient()
        )

        strategy_factory = DeletionStrategyFactory(
            dry_run=general.dry_run,
            logger=logger,
            radarr=radarr,
            sonarr=sonarr,
            jellyseerr=jellyseerr,
            downloader=downloader,
        )
        return ServiceRuntime(
            config=config,
            service=CascadeDeletionService(strategy_factory),
            radarr=radarr,
            sonarr=sonarr,
            jellyseerr=jellyseerr,
            downloader=downloader,
        )

    @staticmethod
    def _pick_active_radarr(services: list[RadarrServiceConfig]) -> RadarrServiceConfig | None:
        enabled = [service for service in services if service.enabled]
        if not enabled:
            return None
        default = next((service for service in enabled if service.is_default), None)
        return default or enabled[0]

    @staticmethod
    def _pick_active_sonarr(services: list[SonarrServiceConfig]) -> SonarrServiceConfig | None:
        enabled = [service for service in services if service.enabled]
        if not enabled:
            return None
        default = next((service for service in enabled if service.is_default), None)
        return default or enabled[0]

    @staticmethod
    def _pick_active_jellyseerr(
        services: list[JellyseerrServiceConfig],
    ) -> JellyseerrServiceConfig | None:
        enabled = [service for service in services if service.enabled]
        if not enabled:
            return None
        default = next((service for service in enabled if service.is_default), None)
        return default or enabled[0]

    @staticmethod
    def _pick_active_downloader(
        services: list[QbittorrentServiceConfig],
    ) -> QbittorrentServiceConfig | None:
        enabled = [service for service in services if service.enabled]
        if not enabled:
            return None
        default = next((service for service in enabled if service.is_default), None)
        return default or enabled[0]
