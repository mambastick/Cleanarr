"""Runtime configuration service."""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import Protocol, TypeVar

from cleanarr.domain.config import (
    BaseServiceConfig,
    DelugeServiceConfig,
    GeneralConfig,
    JellyfinServiceConfig,
    QbittorrentServiceConfig,
    RadarrServiceConfig,
    RTorrentServiceConfig,
    RuntimeConfig,
    SeerrServiceConfig,
    ServiceKind,
    SonarrServiceConfig,
    SSOAuthMode,
    TransmissionServiceConfig,
)

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


class RuntimeBootstrapSettings(Protocol):
    """Settings values required to create the first persisted runtime config."""

    dry_run: bool
    log_level: str
    webhook_shared_token: str | None
    http_timeout_seconds: float
    jellyfin_language: str
    ui_language: str
    sso_mode: SSOAuthMode
    sso_enabled: bool
    sso_issuer_url: str | None
    sso_client_id: str | None
    sso_client_secret: str | None
    sso_redirect_uri: str | None
    sso_scopes: str
    sso_allowed_users: str
    sso_allowed_groups: str
    sso_group_claim: str
    sso_required_claim: str | None
    sso_required_value: str | None


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


class ServiceConnectionTesterPort(Protocol):
    """Infrastructure-owned downstream connection test adapter."""

    async def test(self, payload: AnyServiceConfig, *, timeout_seconds: float) -> ConnectionTestResult: ...


class RuntimeConfigurationService:
    """Own persisted runtime settings and service definitions."""

    def __init__(
        self,
        *,
        store: RuntimeConfigStore,
        settings: RuntimeBootstrapSettings,
        connection_tester: ServiceConnectionTesterPort | None = None,
    ) -> None:
        self._store = store
        self._connection_tester = connection_tester
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

    def replace_config(self, config: RuntimeConfig) -> RuntimeConfig:
        """Persist a fully validated configuration assembled by a trusted workflow."""

        self._config = config
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

        if self._connection_tester is None:
            return ConnectionTestResult(ok=False, message="Connection testing is unavailable.")
        return await self._connection_tester.test(
            payload,
            timeout_seconds=self._config.general.http_timeout_seconds,
        )

    def _bootstrap_general_from_settings(self, settings: RuntimeBootstrapSettings) -> RuntimeConfig:
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
