"""Schemas for mutable runtime configuration APIs."""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from cleanarr.application.configuration import ConnectionTestResult
from cleanarr.domain.config import (
    DelugeServiceConfig,
    DownloaderServiceConfig,
    GeneralConfig,
    JellyfinServiceConfig,
    JellyseerrServiceConfig,
    QbittorrentServiceConfig,
    RadarrServiceConfig,
    RTorrentServiceConfig,
    RuntimeConfig,
    ServiceKind,
    SonarrServiceConfig,
    TorrentRemovalPolicy,
    TransmissionServiceConfig,
)


class RuntimeConfigResponse(BaseModel):
    """Authorized runtime configuration payload."""

    general: GeneralConfig
    radarr: list[RadarrServiceConfig]
    sonarr: list[SonarrServiceConfig]
    jellyseerr: list[JellyseerrServiceConfig]
    downloaders: list[DownloaderServiceConfig]
    jellyfin: list[JellyfinServiceConfig]
    admin_token_configured: bool

    @classmethod
    def from_config(cls, config: RuntimeConfig, *, admin_token_configured: bool) -> RuntimeConfigResponse:
        return cls(
            general=config.general,
            radarr=config.radarr,
            sonarr=config.sonarr,
            jellyseerr=config.jellyseerr,
            downloaders=config.downloaders,
            jellyfin=config.jellyfin,
            admin_token_configured=admin_token_configured,
        )


class GeneralConfigRequest(BaseModel):
    """PUT request for mutable app settings."""

    dry_run: bool
    log_level: str
    webhook_shared_token: str | None = None
    http_timeout_seconds: float
    activity_retention_days: int = 30
    jellyfin_language: str = "en"
    ui_language: str = "en"
    sso_enabled: bool = False
    sso_mode: str = "password_only"
    sso_issuer_url: str | None = None
    sso_client_id: str | None = None
    sso_client_secret: str | None = None
    sso_redirect_uri: str | None = None
    sso_scopes: str = "openid profile email"

    def to_domain(self) -> GeneralConfig:
        return GeneralConfig.model_validate(self.model_dump())


class RadarrServiceRequest(BaseModel):
    """Create or update a Radarr integration."""

    name: str
    url: str
    api_key: str
    enabled: bool = True
    is_default: bool = False

    def to_domain(self, *, service_id: str | None = None) -> RadarrServiceConfig:
        payload = self.model_dump()
        if service_id is not None:
            payload["id"] = service_id
        return RadarrServiceConfig.model_validate(payload)


class SonarrServiceRequest(BaseModel):
    """Create or update a Sonarr integration."""

    name: str
    url: str
    api_key: str
    enabled: bool = True
    is_default: bool = False

    def to_domain(self, *, service_id: str | None = None) -> SonarrServiceConfig:
        payload = self.model_dump()
        if service_id is not None:
            payload["id"] = service_id
        return SonarrServiceConfig.model_validate(payload)


class JellyseerrServiceRequest(BaseModel):
    """Create or update a Jellyseerr integration."""

    name: str
    url: str
    api_key: str
    enabled: bool = True
    is_default: bool = False

    def to_domain(self, *, service_id: str | None = None) -> JellyseerrServiceConfig:
        payload = self.model_dump()
        if service_id is not None:
            payload["id"] = service_id
        return JellyseerrServiceConfig.model_validate(payload)


class BaseDownloaderServiceRequest(BaseModel):
    """Fields shared by all torrent-client requests."""

    name: str
    url: str
    enabled: bool = True
    is_default: bool = False
    seeding_policy: TorrentRemovalPolicy = TorrentRemovalPolicy.IMMEDIATE
    min_seed_ratio: float | None = Field(default=None, ge=0)
    min_seed_time_minutes: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_seeding_policy(self) -> BaseDownloaderServiceRequest:
        if (
            self.seeding_policy is TorrentRemovalPolicy.DEFER
            and self.min_seed_ratio is None
            and self.min_seed_time_minutes is None
        ):
            raise ValueError("Deferred torrent removal requires a minimum seed ratio or time.")
        return self


class QbittorrentServiceRequest(BaseDownloaderServiceRequest):
    """Create or update a qBittorrent integration."""

    username: str = ""
    password: str = ""
    api_key: str | None = None

    def to_domain(self, *, service_id: str | None = None) -> QbittorrentServiceConfig:
        payload = self.model_dump()
        if service_id is not None:
            payload["id"] = service_id
        return QbittorrentServiceConfig.model_validate(payload)


class TransmissionServiceRequest(BaseDownloaderServiceRequest):
    """Create or update a Transmission integration."""

    username: str = ""
    password: str = ""

    def to_domain(self, *, service_id: str | None = None) -> TransmissionServiceConfig:
        payload = self.model_dump()
        if service_id is not None:
            payload["id"] = service_id
        return TransmissionServiceConfig.model_validate(payload)


class DelugeServiceRequest(BaseDownloaderServiceRequest):
    """Create or update a Deluge integration."""

    password: str

    def to_domain(self, *, service_id: str | None = None) -> DelugeServiceConfig:
        payload = self.model_dump()
        if service_id is not None:
            payload["id"] = service_id
        return DelugeServiceConfig.model_validate(payload)


class RTorrentServiceRequest(BaseDownloaderServiceRequest):
    """Create or update an rTorrent integration."""

    username: str = ""
    password: str = ""

    def to_domain(self, *, service_id: str | None = None) -> RTorrentServiceConfig:
        payload = self.model_dump()
        if service_id is not None:
            payload["id"] = service_id
        return RTorrentServiceConfig.model_validate(payload)


class JellyfinServiceRequest(BaseModel):
    """Create or update a Jellyfin server integration."""

    name: str
    url: str
    api_key: str
    enabled: bool = True
    is_default: bool = False

    def to_domain(self, *, service_id: str | None = None) -> JellyfinServiceConfig:
        payload = self.model_dump()
        if service_id is not None:
            payload["id"] = service_id
        return JellyfinServiceConfig.model_validate(payload)


class ConnectionTestResponse(BaseModel):
    """Serialized connection test result."""

    ok: bool
    message: str

    @classmethod
    def from_domain(cls, result: ConnectionTestResult) -> ConnectionTestResponse:
        return cls(ok=result.ok, message=result.message)


SERVICE_KIND_VALUES = {kind.value for kind in ServiceKind}
