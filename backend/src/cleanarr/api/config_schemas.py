"""Schemas for mutable runtime configuration APIs."""

from __future__ import annotations

from pydantic import BaseModel

from cleanarr.application.configuration import ConnectionTestResult
from cleanarr.domain.config import (
    GeneralConfig,
    JellyfinServiceConfig,
    JellyseerrServiceConfig,
    QbittorrentServiceConfig,
    RadarrServiceConfig,
    RuntimeConfig,
    ServiceKind,
    SonarrServiceConfig,
)


class RuntimeConfigResponse(BaseModel):
    """Authorized runtime configuration payload."""

    general: GeneralConfig
    radarr: list[RadarrServiceConfig]
    sonarr: list[SonarrServiceConfig]
    jellyseerr: list[JellyseerrServiceConfig]
    downloaders: list[QbittorrentServiceConfig]
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


class QbittorrentServiceRequest(BaseModel):
    """Create or update a qBittorrent integration."""

    name: str
    url: str
    username: str
    password: str
    enabled: bool = True
    is_default: bool = False

    def to_domain(self, *, service_id: str | None = None) -> QbittorrentServiceConfig:
        payload = self.model_dump()
        if service_id is not None:
            payload["id"] = service_id
        return QbittorrentServiceConfig.model_validate(payload)


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
