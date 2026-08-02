"""Persistent runtime configuration models."""

from __future__ import annotations

from enum import StrEnum
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator


class ServiceKind(StrEnum):
    """Supported downstream service kinds."""

    RADARR = "radarr"
    SONARR = "sonarr"
    JELLYSEERR = "jellyseerr"
    QBITTORRENT = "qbittorrent"
    JELLYFIN = "jellyfin"


class SSOAuthMode(StrEnum):
    """Available auth modes for the web UI."""

    PASSWORD_ONLY = "password_only"
    SSO_ONLY = "sso_only"
    BOTH = "both"


def _normalize_sso_mode_value(value: object) -> SSOAuthMode:
    if isinstance(value, SSOAuthMode):
        return value

    if isinstance(value, bool):
        return SSOAuthMode.BOTH if value else SSOAuthMode.PASSWORD_ONLY

    if value is None:
        return SSOAuthMode.PASSWORD_ONLY

    if isinstance(value, str):
        normalized = value.strip().lower().replace("-", "_")
        if not normalized:
            return SSOAuthMode.PASSWORD_ONLY
        try:
            return SSOAuthMode(normalized)
        except ValueError:
            if normalized in {"true", "1", "on", "yes", "both", "all"}:
                return SSOAuthMode.BOTH
            if normalized in {"password", "passwordonly", "local", "local_only"}:
                return SSOAuthMode.PASSWORD_ONLY
            if normalized in {"sso", "ssoonly", "oidc"}:
                return SSOAuthMode.SSO_ONLY
    return SSOAuthMode.PASSWORD_ONLY


class GeneralConfig(BaseModel):
    """Mutable runtime settings controlled from the UI."""

    dry_run: bool = True
    log_level: str = "INFO"
    webhook_shared_token: str | None = None
    http_timeout_seconds: float = 15.0
    activity_retention_days: int = 30
    jellyfin_language: str = "en"
    ui_language: str = "en"
    sso_enabled: bool = False
    sso_mode: SSOAuthMode = SSOAuthMode.PASSWORD_ONLY
    sso_issuer_url: str | None = None
    sso_client_id: str | None = None
    sso_client_secret: str | None = None
    sso_redirect_uri: str | None = None
    sso_scopes: str = "openid profile email"

    @field_validator("log_level", mode="before")
    @classmethod
    def normalize_log_level(cls, value: str) -> str:
        return value.upper()

    @field_validator("jellyfin_language", mode="before")
    @classmethod
    def normalize_jellyfin_language(cls, value: str | None) -> str:
        if not value:
            return "en"
        normalized = value.strip().replace("_", "-").lower()
        normalized = normalized.split(",", 1)[0].strip()
        if ";" in normalized:
            normalized = normalized.split(";", 1)[0].strip()
        if not normalized:
            return "en"
        return normalized

    @field_validator("ui_language", mode="before")
    @classmethod
    def normalize_ui_language(cls, value: str | None) -> str:
        if not value:
            return "en"
        normalized = value.strip().replace("_", "-").lower()
        normalized = normalized.split(",", 1)[0].strip()
        if ";" in normalized:
            normalized = normalized.split(";", 1)[0].strip()
        return normalized or "en"

    @field_validator("sso_scopes", mode="before")
    @classmethod
    def normalize_sso_scopes(cls, value: str | None) -> str:
        if not value:
            return "openid profile email"
        scopes = " ".join(part.strip() for part in str(value).split() if part.strip())
        return scopes or "openid profile email"

    @model_validator(mode="before")
    @classmethod
    def normalize_sso_fields(cls, values: object) -> object:
        if not isinstance(values, dict):
            return values
        raw_mode = values.get("sso_mode")
        if raw_mode is None and "sso_enabled" in values:
            legacy_enabled = values.get("sso_enabled")
            if isinstance(legacy_enabled, str):
                legacy_enabled = legacy_enabled.strip().lower() in {"1", "true", "yes", "on"}
            raw_mode = bool(legacy_enabled)

        normalized_mode = _normalize_sso_mode_value(raw_mode)
        values["sso_mode"] = normalized_mode.value
        values["sso_enabled"] = normalized_mode is not SSOAuthMode.PASSWORD_ONLY
        return values

    def local_auth_enabled(self) -> bool:
        return self.sso_mode in (SSOAuthMode.PASSWORD_ONLY, SSOAuthMode.BOTH)

    def sso_auth_enabled(self) -> bool:
        return self.sso_mode in (SSOAuthMode.SSO_ONLY, SSOAuthMode.BOTH)


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
