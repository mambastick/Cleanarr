"""Environment-backed settings."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


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

    radarr_url: str | None = Field(default=None, alias="RADARR_URL")
    radarr_api_key: str | None = Field(default=None, alias="RADARR_API_KEY")

    sonarr_url: str | None = Field(default=None, alias="SONARR_URL")
    sonarr_api_key: str | None = Field(default=None, alias="SONARR_API_KEY")

    jellyseerr_url: str | None = Field(default=None, alias="JELLYSEERR_URL")
    jellyseerr_api_key: str | None = Field(default=None, alias="JELLYSEERR_API_KEY")

    downloader_kind: str = Field(default="qbittorrent", alias="DOWNLOADER_KIND")
    qbittorrent_url: str | None = Field(default=None, alias="QBITTORRENT_URL")
    qbittorrent_username: str | None = Field(default=None, alias="QBITTORRENT_USERNAME")
    qbittorrent_password: str | None = Field(default=None, alias="QBITTORRENT_PASSWORD")
