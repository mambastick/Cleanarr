"""Environment-backed settings."""

from __future__ import annotations

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from cleanarr.domain.config import SSOAuthMode


class Settings(BaseSettings):
    """Runtime configuration."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    db_path: str = Field(default="/config/cleanarr.db", alias="DB_PATH")
    config_state_path: str = Field(default="/config/runtime-config.json", alias="CONFIG_STATE_PATH")
    admin_shared_token: str | None = Field(default=None, alias="ADMIN_SHARED_TOKEN")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    dry_run: bool = Field(default=True, alias="DRY_RUN")
    webhook_shared_token: str | None = Field(default=None, alias="WEBHOOK_SHARED_TOKEN")
    http_timeout_seconds: float = Field(default=15.0, alias="HTTP_TIMEOUT_SECONDS")
    jellyfin_language: str = Field(default="en", alias="JELLYFIN_LANGUAGE")
    ui_language: str = Field(default="en", alias="UI_LANGUAGE")
    sso_mode: SSOAuthMode = Field(default=SSOAuthMode.PASSWORD_ONLY, alias="SSO_MODE")
    sso_enabled: bool = Field(default=False, alias="SSO_ENABLED")
    sso_issuer_url: str | None = Field(default=None, alias="SSO_ISSUER_URL")
    sso_client_id: str | None = Field(default=None, alias="SSO_CLIENT_ID")
    sso_client_secret: str | None = Field(default=None, alias="SSO_CLIENT_SECRET")
    sso_redirect_uri: str | None = Field(default=None, alias="SSO_REDIRECT_URI")
    sso_scopes: str = Field(default="openid profile email", alias="SSO_SCOPES")

    radarr_url: str | None = Field(default=None, alias="RADARR_URL")
    radarr_api_key: str | None = Field(default=None, alias="RADARR_API_KEY")

    sonarr_url: str | None = Field(default=None, alias="SONARR_URL")
    sonarr_api_key: str | None = Field(default=None, alias="SONARR_API_KEY")

    seerr_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("SEERR_URL", "JELLYSEERR_URL"),
    )
    seerr_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("SEERR_API_KEY", "JELLYSEERR_API_KEY"),
    )

    downloader_kind: str = Field(default="qbittorrent", alias="DOWNLOADER_KIND")
    qbittorrent_url: str | None = Field(default=None, alias="QBITTORRENT_URL")
    qbittorrent_username: str | None = Field(default=None, alias="QBITTORRENT_USERNAME")
    qbittorrent_password: str | None = Field(default=None, alias="QBITTORRENT_PASSWORD")
