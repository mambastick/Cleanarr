"""Persistent runtime configuration models."""

from __future__ import annotations

from enum import StrEnum
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


class ServiceKind(StrEnum):
    """Supported downstream service kinds."""

    RADARR = "radarr"
    SONARR = "sonarr"
    JELLYSEERR = "jellyseerr"
    QBITTORRENT = "qbittorrent"
    JELLYFIN = "jellyfin"


class GeneralConfig(BaseModel):
    """Mutable runtime settings controlled from the UI."""

    dry_run: bool = True
    log_level: str = "INFO"
    webhook_shared_token: str | None = None
    http_timeout_seconds: float = 15.0
    activity_retention_days: int = 30

    @field_validator("log_level", mode="before")
    @classmethod
    def normalize_log_level(cls, value: str) -> str:
        return value.upper()


class AdminAccountConfig(BaseModel):
    """Persisted admin credentials for UI auth."""

    username: str | None = None
    password_salt: str | None = None
    password_hash: str | None = None

    @property
    def configured(self) -> bool:
        return bool(self.username and self.password_salt and self.password_hash)


class BaseServiceConfig(BaseModel):
    """Shared fields for downstream services."""

    id: str = Field(default_factory=lambda: uuid4().hex)
    name: str
    url: str
    enabled: bool = True
    is_default: bool = False

    @field_validator("url", mode="before")
    @classmethod
    def normalize_url(cls, value: str) -> str:
        return value.strip().rstrip("/")


class RadarrServiceConfig(BaseServiceConfig):
    """Radarr integration settings."""

    kind: ServiceKind = ServiceKind.RADARR
    api_key: str

    @field_validator("url", mode="before")
    @classmethod
    def normalize_radarr_url(cls, value: str) -> str:
        return _normalize_api_service_url(value, expected_suffix="/api/v3")


class SonarrServiceConfig(BaseServiceConfig):
    """Sonarr integration settings."""

    kind: ServiceKind = ServiceKind.SONARR
    api_key: str

    @field_validator("url", mode="before")
    @classmethod
    def normalize_sonarr_url(cls, value: str) -> str:
        return _normalize_api_service_url(value, expected_suffix="/api/v3")


class JellyseerrServiceConfig(BaseServiceConfig):
    """Jellyseerr integration settings."""

    kind: ServiceKind = ServiceKind.JELLYSEERR
    api_key: str

    @field_validator("url", mode="before")
    @classmethod
    def normalize_jellyseerr_url(cls, value: str) -> str:
        return _normalize_api_service_url(value, expected_suffix="/api/v1")


class QbittorrentServiceConfig(BaseServiceConfig):
    """qBittorrent integration settings."""

    kind: ServiceKind = ServiceKind.QBITTORRENT
    username: str
    password: str

    @field_validator("url", mode="before")
    @classmethod
    def normalize_qbittorrent_url(cls, value: str) -> str:
        return _normalize_qbittorrent_url(value)


class JellyfinServiceConfig(BaseServiceConfig):
    """Jellyfin media server integration settings."""

    kind: ServiceKind = ServiceKind.JELLYFIN
    api_key: str


class RuntimeConfig(BaseModel):
    """Complete persisted CleanArr runtime configuration."""

    admin: AdminAccountConfig = Field(default_factory=AdminAccountConfig)
    general: GeneralConfig = Field(default_factory=GeneralConfig)
    radarr: list[RadarrServiceConfig] = Field(default_factory=list)
    sonarr: list[SonarrServiceConfig] = Field(default_factory=list)
    jellyseerr: list[JellyseerrServiceConfig] = Field(default_factory=list)
    downloaders: list[QbittorrentServiceConfig] = Field(default_factory=list)
    jellyfin: list[JellyfinServiceConfig] = Field(default_factory=list)


def _normalize_api_service_url(value: str, *, expected_suffix: str) -> str:
    candidate = value.strip()
    parsed = urlsplit(candidate)
    path = parsed.path.rstrip("/")
    path_without_api = _strip_known_api_suffix(path)
    normalized_path = f"{path_without_api}{expected_suffix}" if path_without_api else expected_suffix
    return urlunsplit((parsed.scheme, parsed.netloc, normalized_path, parsed.query, parsed.fragment)).rstrip("/")


def _normalize_qbittorrent_url(value: str) -> str:
    candidate = value.strip()
    parsed = urlsplit(candidate)
    path = parsed.path.rstrip("/")
    if path.endswith("/api/v2"):
        path = path[: -len("/api/v2")]
    return urlunsplit((parsed.scheme, parsed.netloc, path, parsed.query, parsed.fragment)).rstrip("/")


def _strip_known_api_suffix(path: str) -> str:
    stripped = path.rstrip("/")
    for suffix in ("/api/v3", "/api/3", "/api/v1", "/api/1", "/api"):
        if stripped.endswith(suffix):
            return stripped[: -len(suffix)].rstrip("/")
    return stripped
