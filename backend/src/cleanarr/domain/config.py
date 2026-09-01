"""Persistent runtime configuration models."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

from pydantic import AliasChoices, BaseModel, Field, field_validator, model_validator

CURRENT_CONFIG_SCHEMA_VERSION: Literal[3] = 3


class ServiceKind(StrEnum):
    """Supported downstream service kinds."""

    RADARR = "radarr"
    SONARR = "sonarr"
    SEERR = "seerr"
    QBITTORRENT = "qbittorrent"
    TRANSMISSION = "transmission"
    DELUGE = "deluge"
    RTORRENT = "rtorrent"
    JELLYFIN = "jellyfin"


class TorrentRemovalPolicy(StrEnum):
    """Policy applied before removing a torrent from a download client."""

    IMMEDIATE = "immediate"
    KEEP = "keep"
    DEFER = "defer"


class SSOAuthMode(StrEnum):
    """Available auth modes for the web UI."""

    PASSWORD_ONLY = "password_only"
    SSO_ONLY = "sso_only"
    BOTH = "both"


class SeedingStopPolicyMode(StrEnum):
    ALL = "all"
    ANY = "any"


class SeedingStopPolicyConfig(BaseModel):
    """Opt-in reversible stop policy; thresholds are deliberately fail-closed."""

    enabled: bool = False
    mode: SeedingStopPolicyMode = SeedingStopPolicyMode.ALL
    min_ratio: float | None = Field(default=None, ge=0)
    min_seeding_minutes: int | None = Field(default=None, ge=1)
    include_categories: list[str] = Field(default_factory=list)
    exclude_categories: list[str] = Field(default_factory=list)
    include_tags: list[str] = Field(default_factory=list)
    exclude_tags: list[str] = Field(default_factory=list)
    interval_seconds: int = Field(default=300, ge=30, le=86_400)
    max_attempts: int = Field(default=1, ge=1, le=5)

    @model_validator(mode="after")
    def validate_thresholds(self) -> SeedingStopPolicyConfig:
        if self.enabled and self.min_ratio is None and self.min_seeding_minutes is None:
            raise ValueError("Enabled seeding stop policy requires a ratio or seeding-time threshold.")
        return self

    @field_validator("include_categories", "exclude_categories", "include_tags", "exclude_tags", mode="before")
    @classmethod
    def normalize_scope(cls, value: object) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            value = value.replace("\n", ",").split(",")
        if not isinstance(value, (list, tuple, set)):
            raise ValueError("Policy scope must be a list or comma-separated string.")
        result: list[str] = []
        seen: set[str] = set()
        for item in value:
            text = str(item).strip()
            folded = text.casefold()
            if text and folded not in seen:
                result.append(text)
                seen.add(folded)
        return result[:100]


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
    sso_allowed_users: list[str] = Field(default_factory=list)
    sso_allowed_groups: list[str] = Field(default_factory=list)
    sso_group_claim: str = "groups"
    sso_required_claim: str | None = None
    sso_required_value: str | None = None
    seeding_stop_policy: SeedingStopPolicyConfig = Field(default_factory=SeedingStopPolicyConfig)

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

    @field_validator("sso_allowed_users", "sso_allowed_groups", mode="before")
    @classmethod
    def normalize_sso_allowlist(cls, value: object) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            entries = value.replace("\n", ",").split(",")
        elif isinstance(value, (list, tuple, set)):
            entries = list(value)
        else:
            raise ValueError("SSO allowlists must be a list or comma-separated string.")
        normalized: list[str] = []
        seen: set[str] = set()
        for entry in entries:
            candidate = str(entry).strip()
            folded = candidate.casefold()
            if not candidate or folded in seen:
                continue
            seen.add(folded)
            normalized.append(candidate)
        return normalized

    @field_validator("sso_group_claim", mode="before")
    @classmethod
    def normalize_sso_group_claim(cls, value: str | None) -> str:
        return str(value or "groups").strip() or "groups"

    @field_validator("sso_required_claim", "sso_required_value", mode="before")
    @classmethod
    def normalize_optional_sso_policy_value(cls, value: str | None) -> str | None:
        candidate = str(value).strip() if value is not None else ""
        return candidate or None

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

    @model_validator(mode="after")
    def validate_sso_access_policy(self) -> GeneralConfig:
        if bool(self.sso_required_claim) != bool(self.sso_required_value):
            raise ValueError("SSO required claim and value must be configured together.")
        return self

    def local_auth_enabled(self) -> bool:
        return self.sso_mode in (SSOAuthMode.PASSWORD_ONLY, SSOAuthMode.BOTH)

    def sso_auth_enabled(self) -> bool:
        return self.sso_mode in (SSOAuthMode.SSO_ONLY, SSOAuthMode.BOTH)

    def has_sso_access_policy(self) -> bool:
        return bool(self.sso_allowed_users or self.sso_allowed_groups or self.sso_required_claim)


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


class BaseDownloaderServiceConfig(BaseServiceConfig):
    """Shared torrent-removal policy for all supported download clients."""

    seeding_policy: TorrentRemovalPolicy = TorrentRemovalPolicy.IMMEDIATE
    min_seed_ratio: float | None = Field(default=None, ge=0)
    min_seed_time_minutes: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_seeding_policy(self) -> BaseDownloaderServiceConfig:
        if (
            self.seeding_policy is TorrentRemovalPolicy.DEFER
            and self.min_seed_ratio is None
            and self.min_seed_time_minutes is None
        ):
            raise ValueError("Deferred torrent removal requires a minimum seed ratio or time.")
        return self


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


class SeerrServiceConfig(BaseServiceConfig):
    """Seerr integration settings, including migrated Jellyseerr profiles."""

    kind: Literal[ServiceKind.SEERR] = ServiceKind.SEERR
    api_key: str

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_kind(cls, values: object) -> object:
        if not isinstance(values, dict) or values.get("kind") != "jellyseerr":
            return values
        migrated = dict(values)
        migrated["kind"] = ServiceKind.SEERR.value
        return migrated

    @field_validator("url", mode="before")
    @classmethod
    def normalize_seerr_url(cls, value: str) -> str:
        return _normalize_api_service_url(value, expected_suffix="/api/v1")


class QbittorrentServiceConfig(BaseDownloaderServiceConfig):
    """qBittorrent integration settings."""

    kind: Literal[ServiceKind.QBITTORRENT] = ServiceKind.QBITTORRENT
    username: str = ""
    password: str = ""
    api_key: str | None = None

    @field_validator("url", mode="before")
    @classmethod
    def normalize_qbittorrent_url(cls, value: str) -> str:
        return _normalize_qbittorrent_url(value)


class TransmissionServiceConfig(BaseDownloaderServiceConfig):
    """Transmission RPC integration settings."""

    kind: Literal[ServiceKind.TRANSMISSION] = ServiceKind.TRANSMISSION
    username: str = ""
    password: str = ""

    @field_validator("url", mode="before")
    @classmethod
    def normalize_transmission_url(cls, value: str) -> str:
        return _normalize_service_path(value, default_path="/transmission/rpc")


class DelugeServiceConfig(BaseDownloaderServiceConfig):
    """Deluge Web JSON-RPC integration settings."""

    kind: Literal[ServiceKind.DELUGE] = ServiceKind.DELUGE
    password: str

    @field_validator("url", mode="before")
    @classmethod
    def normalize_deluge_url(cls, value: str) -> str:
        return _normalize_service_path(value, default_path="/json")


class RTorrentServiceConfig(BaseDownloaderServiceConfig):
    """rTorrent HTTP XML-RPC integration settings."""

    kind: Literal[ServiceKind.RTORRENT] = ServiceKind.RTORRENT
    username: str = ""
    password: str = ""

    @field_validator("url", mode="before")
    @classmethod
    def normalize_rtorrent_url(cls, value: str) -> str:
        return _normalize_service_path(value, default_path="/RPC2")


DownloaderServiceConfig = Annotated[
    QbittorrentServiceConfig | TransmissionServiceConfig | DelugeServiceConfig | RTorrentServiceConfig,
    Field(discriminator="kind"),
]


class JellyfinServiceConfig(BaseServiceConfig):
    """Jellyfin media server integration settings."""

    kind: ServiceKind = ServiceKind.JELLYFIN
    api_key: str


class RuntimeConfig(BaseModel):
    """Complete persisted CleanArr runtime configuration."""

    config_schema_version: Literal[3] = CURRENT_CONFIG_SCHEMA_VERSION
    admin: AdminAccountConfig = Field(default_factory=AdminAccountConfig)
    general: GeneralConfig = Field(default_factory=GeneralConfig)
    radarr: list[RadarrServiceConfig] = Field(default_factory=list)
    sonarr: list[SonarrServiceConfig] = Field(default_factory=list)
    seerr: list[SeerrServiceConfig] = Field(
        default_factory=list,
        validation_alias=AliasChoices("seerr", "jellyseerr"),
    )
    downloaders: list[DownloaderServiceConfig] = Field(default_factory=list)
    jellyfin: list[JellyfinServiceConfig] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def merge_legacy_seerr_profiles(cls, values: object) -> object:
        """Accept mixed upgrade payloads without dropping either profile set."""

        if not isinstance(values, dict) or "jellyseerr" not in values:
            return values
        canonical = values.get("seerr")
        legacy = values.get("jellyseerr")
        canonical_profiles = list(canonical) if isinstance(canonical, list) else []
        legacy_profiles = list(legacy) if isinstance(legacy, list) else []
        known_ids = {
            profile.get("id")
            for profile in canonical_profiles
            if isinstance(profile, dict) and profile.get("id") is not None
        }
        migrated = dict(values)
        migrated["seerr"] = [
            *canonical_profiles,
            *[
                profile
                for profile in legacy_profiles
                if not isinstance(profile, dict) or profile.get("id") not in known_ids
            ],
        ]
        migrated.pop("jellyseerr", None)
        return migrated


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


def _normalize_service_path(value: str, *, default_path: str) -> str:
    candidate = value.strip()
    parsed = urlsplit(candidate)
    path = parsed.path.rstrip("/") or default_path
    return urlunsplit((parsed.scheme, parsed.netloc, path, parsed.query, parsed.fragment)).rstrip("/")


def _strip_known_api_suffix(path: str) -> str:
    stripped = path.rstrip("/")
    for suffix in ("/api/v3", "/api/3", "/api/v1", "/api/1", "/api"):
        if stripped.endswith(suffix):
            return stripped[: -len(suffix)].rstrip("/")
    return stripped
