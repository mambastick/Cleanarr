"""Runtime configuration service."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypeVar

from cleanarr.domain.config import (
    BaseServiceConfig,
    GeneralConfig,
    JellyseerrServiceConfig,
    QbittorrentServiceConfig,
    RadarrServiceConfig,
    RuntimeConfig,
    ServiceKind,
    SonarrServiceConfig,
)
from cleanarr.domain.errors import ExternalServiceError
from cleanarr.infrastructure.clients import JellyseerrClient, QbittorrentClient, RadarrClient, SonarrClient
from cleanarr.infrastructure.config_store import FileConfigStore
from cleanarr.infrastructure.settings import Settings

AnyServiceConfig = (
    RadarrServiceConfig | SonarrServiceConfig | JellyseerrServiceConfig | QbittorrentServiceConfig
)
TService = TypeVar("TService", bound=BaseServiceConfig)


@dataclass(frozen=True)
class ConnectionTestResult:
    """Result of a downstream connectivity test."""

    ok: bool
    message: str


class RuntimeConfigurationService:
    """Own persisted runtime settings and service definitions."""

    def __init__(self, *, store: FileConfigStore, settings: Settings) -> None:
        self._store = store
        self._config = self._normalize(
            self._store.load() or self._bootstrap_general_from_settings(settings),
        )
        self._store.save(self._config)

    def get_config(self) -> RuntimeConfig:
        """Return the in-memory runtime configuration."""

        return self._config.model_copy(deep=True)

    def update_general(self, general: GeneralConfig) -> RuntimeConfig:
        """Replace mutable runtime settings."""

        self._config = self._config.model_copy(update={"general": general})
        self._persist()
        return self.get_config()

    def set_admin_credentials(
        self,
        *,
        username: str,
        password_salt: str,
        password_hash: str,
    ) -> RuntimeConfig:
        """Persist the UI admin account."""

        self._config = self._config.model_copy(
            update={
                "admin": self._config.admin.model_copy(
                    update={
                        "username": username,
                        "password_salt": password_salt,
                        "password_hash": password_hash,
                    }
                )
            }
        )
        self._persist()
        return self.get_config()

    def add_service(
        self,
        kind: ServiceKind,
        payload: AnyServiceConfig,
    ) -> RuntimeConfig:
        """Append a new service definition."""

        if kind is ServiceKind.RADARR and isinstance(payload, RadarrServiceConfig):
            self._config = self._config.model_copy(update={"radarr": [*self._config.radarr, payload]})
        elif kind is ServiceKind.SONARR and isinstance(payload, SonarrServiceConfig):
            self._config = self._config.model_copy(update={"sonarr": [*self._config.sonarr, payload]})
        elif kind is ServiceKind.JELLYSEERR and isinstance(payload, JellyseerrServiceConfig):
            self._config = self._config.model_copy(update={"jellyseerr": [*self._config.jellyseerr, payload]})
        elif kind is ServiceKind.QBITTORRENT and isinstance(payload, QbittorrentServiceConfig):
            self._config = self._config.model_copy(update={"downloaders": [*self._config.downloaders, payload]})
        else:
            raise TypeError(f"Payload {type(payload).__name__} does not match {kind.value}.")
        self._persist()
        return self.get_config()

    def update_service(
        self,
        kind: ServiceKind,
        service_id: str,
        payload: AnyServiceConfig,
    ) -> RuntimeConfig:
        """Replace an existing service definition."""

        if not self._contains_service(kind, service_id):
            raise KeyError(service_id)
        if kind is ServiceKind.RADARR and isinstance(payload, RadarrServiceConfig):
            self._config = self._config.model_copy(
                update={
                    "radarr": [
                        payload if service.id == service_id else service
                        for service in self._config.radarr
                    ]
                }
            )
        elif kind is ServiceKind.SONARR and isinstance(payload, SonarrServiceConfig):
            self._config = self._config.model_copy(
                update={
                    "sonarr": [
                        payload if service.id == service_id else service
                        for service in self._config.sonarr
                    ]
                }
            )
        elif kind is ServiceKind.JELLYSEERR and isinstance(payload, JellyseerrServiceConfig):
            self._config = self._config.model_copy(
                update={
                    "jellyseerr": [
                        payload if service.id == service_id else service
                        for service in self._config.jellyseerr
                    ]
                }
            )
        elif kind is ServiceKind.QBITTORRENT and isinstance(payload, QbittorrentServiceConfig):
            self._config = self._config.model_copy(
                update={
                    "downloaders": [
                        payload if service.id == service_id else service
                        for service in self._config.downloaders
                    ]
                }
            )
        else:
            raise TypeError(f"Payload {type(payload).__name__} does not match {kind.value}.")
        self._persist()
        return self.get_config()

    def delete_service(self, kind: ServiceKind, service_id: str) -> RuntimeConfig:
        """Remove a persisted service definition."""

        if not self._contains_service(kind, service_id):
            raise KeyError(service_id)
        if kind is ServiceKind.RADARR:
            self._config = self._config.model_copy(
                update={"radarr": [service for service in self._config.radarr if service.id != service_id]}
            )
        elif kind is ServiceKind.SONARR:
            self._config = self._config.model_copy(
                update={"sonarr": [service for service in self._config.sonarr if service.id != service_id]}
            )
        elif kind is ServiceKind.JELLYSEERR:
            self._config = self._config.model_copy(
                update={"jellyseerr": [service for service in self._config.jellyseerr if service.id != service_id]}
            )
        else:
            self._config = self._config.model_copy(
                update={"downloaders": [service for service in self._config.downloaders if service.id != service_id]}
            )
        self._persist()
        return self.get_config()

    async def test_service(
        self,
        payload: AnyServiceConfig,
    ) -> ConnectionTestResult:
        """Run a minimal connectivity test for a single service definition."""

        timeout = self._config.general.http_timeout_seconds
        try:
            if isinstance(payload, RadarrServiceConfig):
                radarr_client = RadarrClient(
                    base_url=payload.url,
                    api_key=payload.api_key,
                    timeout_seconds=timeout,
                )
                try:
                    await radarr_client.list_movies()
                finally:
                    await radarr_client.close()
                return ConnectionTestResult(ok=True, message="Radarr responded successfully.")

            if isinstance(payload, SonarrServiceConfig):
                sonarr_client = SonarrClient(
                    base_url=payload.url,
                    api_key=payload.api_key,
                    timeout_seconds=timeout,
                )
                try:
                    await sonarr_client.list_series()
                finally:
                    await sonarr_client.close()
                return ConnectionTestResult(ok=True, message="Sonarr responded successfully.")

            if isinstance(payload, JellyseerrServiceConfig):
                jellyseerr_client = JellyseerrClient(
                    base_url=payload.url,
                    api_key=payload.api_key,
                    timeout_seconds=timeout,
                )
                try:
                    await jellyseerr_client.list_media()
                finally:
                    await jellyseerr_client.close()
                return ConnectionTestResult(ok=True, message="Jellyseerr responded successfully.")

            qbittorrent_client = QbittorrentClient(
                base_url=payload.url,
                username=payload.username,
                password=payload.password,
                timeout_seconds=timeout,
            )
            try:
                await qbittorrent_client.ping()
            finally:
                await qbittorrent_client.close()
            return ConnectionTestResult(ok=True, message="qBittorrent responded successfully.")
        except ExternalServiceError as exc:
            return ConnectionTestResult(ok=False, message=exc.message)
        except Exception as exc:  # pragma: no cover
            return ConnectionTestResult(ok=False, message=f"Unexpected connection test error: {exc}")

    def _bootstrap_general_from_settings(self, settings: Settings) -> RuntimeConfig:
        return RuntimeConfig(
            general=GeneralConfig(
                dry_run=settings.dry_run,
                log_level=settings.log_level,
                webhook_shared_token=settings.webhook_shared_token,
                http_timeout_seconds=settings.http_timeout_seconds,
            )
        )

    @staticmethod
    def _normalize(config: RuntimeConfig) -> RuntimeConfig:
        return config.model_copy(
            update={
                "radarr": RuntimeConfigurationService._normalize_defaults(config.radarr),
                "sonarr": RuntimeConfigurationService._normalize_defaults(config.sonarr),
                "jellyseerr": RuntimeConfigurationService._normalize_defaults(config.jellyseerr),
                "downloaders": RuntimeConfigurationService._normalize_defaults(config.downloaders),
            }
        )

    @staticmethod
    def _normalize_defaults(services: list[TService]) -> list[TService]:
        if not services:
            return []

        enabled = [service for service in services if bool(getattr(service, "enabled", False))]
        active_id = next((service.id for service in services if bool(getattr(service, "is_default", False))), None)
        if active_id is None and enabled:
            active_id = enabled[0].id
        elif active_id is None:
            active_id = services[0].id

        normalized: list[TService] = []
        for service in services:
            normalized.append(service.model_copy(update={"is_default": service.id == active_id}))
        return normalized

    def _persist(self) -> None:
        self._config = self._normalize(self._config)
        self._store.save(self._config)

    def _contains_service(self, kind: ServiceKind, service_id: str) -> bool:
        if kind is ServiceKind.RADARR:
            return any(service.id == service_id for service in self._config.radarr)
        if kind is ServiceKind.SONARR:
            return any(service.id == service_id for service in self._config.sonarr)
        if kind is ServiceKind.JELLYSEERR:
            return any(service.id == service_id for service in self._config.jellyseerr)
        return any(service.id == service_id for service in self._config.downloaders)
