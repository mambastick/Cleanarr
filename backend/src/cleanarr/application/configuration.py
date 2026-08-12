"""Runtime configuration service."""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import Protocol, TypeVar

from cleanarr.domain.config import (
    BaseServiceConfig,
    DelugeServiceConfig,
    DownloaderServiceConfig,
    GeneralConfig,
    JellyfinServiceConfig,
    QbittorrentServiceConfig,
    RadarrServiceConfig,
    RTorrentServiceConfig,
    RuntimeConfig,
    SeerrServiceConfig,
    ServiceKind,
    SonarrServiceConfig,
    TransmissionServiceConfig,
)
from cleanarr.domain.errors import ExternalServiceError
from cleanarr.infrastructure.clients import (
    JellyfinServerClient,
    QbittorrentClient,
    RadarrClient,
    SeerrClient,
    SonarrClient,
)
from cleanarr.infrastructure.downloaders import DelugeClient, RTorrentClient, TransmissionClient
from cleanarr.infrastructure.settings import Settings

AnyServiceConfig = (
    RadarrServiceConfig
    | SonarrServiceConfig
    | SeerrServiceConfig
    | QbittorrentServiceConfig
    | TransmissionServiceConfig
    | DelugeServiceConfig
    | RTorrentServiceConfig
    | JellyfinServiceConfig
)
TService = TypeVar("TService", bound=BaseServiceConfig)


class RuntimeConfigStore(Protocol):
    """Persistence contract shared by file-backed and SQLite stores."""

    def load(self) -> RuntimeConfig | None:
        """Load the current runtime configuration when one exists."""

    def save(self, config: RuntimeConfig) -> None:
        """Persist the current runtime configuration."""


@dataclass(frozen=True)
class ConnectionTestResult:
    """Result of a downstream connectivity test."""

    ok: bool
    message: str


class RuntimeConfigurationService:
    """Own persisted runtime settings and service definitions."""

    def __init__(self, *, store: RuntimeConfigStore, settings: Settings) -> None:
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
        elif kind is ServiceKind.SEERR and isinstance(payload, SeerrServiceConfig):
            self._config = self._config.model_copy(update={"seerr": [*self._config.seerr, payload]})
        elif _is_downloader_payload(kind, payload):
            self._config = self._config.model_copy(update={"downloaders": [*self._config.downloaders, payload]})
        elif kind is ServiceKind.JELLYFIN and isinstance(payload, JellyfinServiceConfig):
            self._config = self._config.model_copy(update={"jellyfin": [*self._config.jellyfin, payload]})
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
                update={"radarr": [payload if service.id == service_id else service for service in self._config.radarr]}
            )
        elif kind is ServiceKind.SONARR and isinstance(payload, SonarrServiceConfig):
            self._config = self._config.model_copy(
                update={"sonarr": [payload if service.id == service_id else service for service in self._config.sonarr]}
            )
        elif kind is ServiceKind.SEERR and isinstance(payload, SeerrServiceConfig):
            self._config = self._config.model_copy(
                update={"seerr": [payload if service.id == service_id else service for service in self._config.seerr]}
            )
        elif _is_downloader_payload(kind, payload):
            self._config = self._config.model_copy(
                update={
                    "downloaders": [
                        payload if service.id == service_id else service for service in self._config.downloaders
                    ]
                }
            )
        elif kind is ServiceKind.JELLYFIN and isinstance(payload, JellyfinServiceConfig):
            self._config = self._config.model_copy(
                update={
                    "jellyfin": [payload if service.id == service_id else service for service in self._config.jellyfin]
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
        elif kind is ServiceKind.SEERR:
            self._config = self._config.model_copy(
                update={"seerr": [service for service in self._config.seerr if service.id != service_id]}
            )
        elif kind in DOWNLOADER_SERVICE_KINDS:
            self._config = self._config.model_copy(
                update={"downloaders": [service for service in self._config.downloaders if service.id != service_id]}
            )
        else:
            self._config = self._config.model_copy(
                update={"jellyfin": [service for service in self._config.jellyfin if service.id != service_id]}
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

            if isinstance(payload, SeerrServiceConfig):
                seerr_client = SeerrClient(
                    base_url=payload.url,
                    api_key=payload.api_key,
                    timeout_seconds=timeout,
                )
                try:
                    await seerr_client.list_media()
                finally:
                    await seerr_client.close()
                return ConnectionTestResult(ok=True, message="Seerr responded successfully.")

            if isinstance(payload, JellyfinServiceConfig):
                jellyfin_client = JellyfinServerClient(
                    base_url=payload.url,
                    api_key=payload.api_key,
                    timeout_seconds=timeout,
                )
                try:
                    await jellyfin_client.ping()
                finally:
                    await jellyfin_client.close()
                return ConnectionTestResult(ok=True, message="Jellyfin responded successfully.")

            downloader_client = build_downloader_client(payload, timeout_seconds=timeout)
            try:
                version = await downloader_client.get_version()
            finally:
                await downloader_client.close()
            return ConnectionTestResult(
                ok=True,
                message=f"{payload.name} responded successfully (version {version}).",
            )
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
                jellyfin_language=settings.jellyfin_language,
                ui_language=settings.ui_language,
                sso_mode=settings.sso_mode,
                sso_enabled=settings.sso_enabled,
                sso_issuer_url=settings.sso_issuer_url,
                sso_client_id=settings.sso_client_id,
                sso_client_secret=settings.sso_client_secret,
                sso_redirect_uri=settings.sso_redirect_uri,
                sso_scopes=settings.sso_scopes,
                sso_allowed_users=_split_comma_separated(settings.sso_allowed_users),
                sso_allowed_groups=_split_comma_separated(settings.sso_allowed_groups),
                sso_group_claim=settings.sso_group_claim,
                sso_required_claim=settings.sso_required_claim,
                sso_required_value=settings.sso_required_value,
            )
        )

    @staticmethod
    def _normalize(config: RuntimeConfig) -> RuntimeConfig:
        general = config.general
        if not general.webhook_shared_token:
            general = general.model_copy(update={"webhook_shared_token": secrets.token_hex(24)})
        return config.model_copy(
            update={
                "general": general,
                "radarr": RuntimeConfigurationService._normalize_defaults(config.radarr),
                "sonarr": RuntimeConfigurationService._normalize_defaults(config.sonarr),
                "seerr": RuntimeConfigurationService._normalize_defaults(config.seerr),
                "downloaders": RuntimeConfigurationService._normalize_defaults(config.downloaders),
                "jellyfin": RuntimeConfigurationService._normalize_defaults(config.jellyfin),
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
        if kind is ServiceKind.SEERR:
            return any(service.id == service_id for service in self._config.seerr)
        if kind is ServiceKind.JELLYFIN:
            return any(service.id == service_id for service in self._config.jellyfin)
        if kind in DOWNLOADER_SERVICE_KINDS:
            return any(service.id == service_id and service.kind is kind for service in self._config.downloaders)
        return False


DOWNLOADER_SERVICE_KINDS = {
    ServiceKind.QBITTORRENT,
    ServiceKind.TRANSMISSION,
    ServiceKind.DELUGE,
    ServiceKind.RTORRENT,
}


def _split_comma_separated(value: str) -> list[str]:
    return [entry.strip() for entry in value.replace("\n", ",").split(",") if entry.strip()]


def _is_downloader_payload(kind: ServiceKind, payload: AnyServiceConfig) -> bool:
    return (
        kind in DOWNLOADER_SERVICE_KINDS
        and isinstance(
            payload,
            (QbittorrentServiceConfig, TransmissionServiceConfig, DelugeServiceConfig, RTorrentServiceConfig),
        )
        and payload.kind is kind
    )


def build_downloader_client(
    payload: DownloaderServiceConfig,
    *,
    timeout_seconds: float,
) -> QbittorrentClient | TransmissionClient | DelugeClient | RTorrentClient:
    if isinstance(payload, QbittorrentServiceConfig):
        return QbittorrentClient(
            base_url=payload.url,
            timeout_seconds=timeout_seconds,
            service_id=payload.id,
            service_name=payload.name,
            username=payload.username,
            password=payload.password,
            api_key=payload.api_key,
            seeding_policy=payload.seeding_policy,
            min_seed_ratio=payload.min_seed_ratio,
            min_seed_time_minutes=payload.min_seed_time_minutes,
        )
    if isinstance(payload, TransmissionServiceConfig):
        return TransmissionClient(
            base_url=payload.url,
            timeout_seconds=timeout_seconds,
            service_id=payload.id,
            service_name=payload.name,
            username=payload.username,
            password=payload.password,
            seeding_policy=payload.seeding_policy,
            min_seed_ratio=payload.min_seed_ratio,
            min_seed_time_minutes=payload.min_seed_time_minutes,
        )
    if isinstance(payload, DelugeServiceConfig):
        return DelugeClient(
            base_url=payload.url,
            timeout_seconds=timeout_seconds,
            service_id=payload.id,
            service_name=payload.name,
            password=payload.password,
            seeding_policy=payload.seeding_policy,
            min_seed_ratio=payload.min_seed_ratio,
            min_seed_time_minutes=payload.min_seed_time_minutes,
        )
    return RTorrentClient(
        base_url=payload.url,
        timeout_seconds=timeout_seconds,
        service_id=payload.id,
        service_name=payload.name,
        username=payload.username,
        password=payload.password,
        seeding_policy=payload.seeding_policy,
        min_seed_ratio=payload.min_seed_ratio,
        min_seed_time_minutes=payload.min_seed_time_minutes,
    )
