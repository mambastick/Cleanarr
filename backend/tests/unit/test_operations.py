"""Tests for redacted configuration transfer safeguards."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from cleanarr.api.operations import (
    RedactedConfigExport,
    RedactedGeneralConfig,
    RedactedServiceConfig,
    export_redacted_config,
    import_redacted_config,
)
from cleanarr.domain.config import (
    AdminAccountConfig,
    DelugeServiceConfig,
    GeneralConfig,
    QbittorrentServiceConfig,
    RadarrServiceConfig,
    RuntimeConfig,
    ServiceKind,
    SonarrServiceConfig,
)


def test_redacted_export_omits_credentials_and_url_secrets() -> None:
    config = _sensitive_config()

    exported = export_redacted_config(config)
    serialized = exported.model_dump_json()

    for secret in (
        "webhook-secret",
        "oidc-secret",
        "password-hash",
        "radarr-secret",
        "sonarr-secret",
        "qbt-user",
        "qbt-password",
        "qbt-token",
        "url-password",
        "query-secret",
    ):
        assert secret not in serialized
    radarr = next(service for service in exported.services if service.kind is ServiceKind.RADARR)
    assert radarr.url == "https://radarr.example/base/api/v3"


def test_redacted_import_preserves_auth_and_credentials_but_forces_safe_state() -> None:
    current = _sensitive_config()
    document = RedactedConfigExport(
        exported_at=datetime.now(UTC),
        safety_notice="redacted",
        general=RedactedGeneralConfig(
            log_level="debug",
            http_timeout_seconds=9,
            activity_retention_days=14,
            jellyfin_language="ru",
            ui_language="ru",
        ),
        services=[
            RedactedServiceConfig(
                id="radarr-one",
                kind=ServiceKind.RADARR,
                name="Imported Radarr",
                url="https://new-radarr.example/api/v3",
                enabled=True,
                is_default=True,
            ),
            RedactedServiceConfig(
                id="new-deluge",
                kind=ServiceKind.DELUGE,
                name="Imported Deluge",
                url="https://deluge.example/json",
                enabled=True,
                is_default=True,
            ),
        ],
    )

    merged, result = import_redacted_config(current, document)

    assert merged.general.dry_run is True
    assert merged.general.webhook_shared_token == "webhook-secret"
    assert merged.general.sso_client_secret == "oidc-secret"
    assert merged.admin == current.admin
    assert merged.radarr[0].api_key == "radarr-secret"
    assert merged.radarr[0].name == "Imported Radarr"
    assert merged.radarr[0].enabled is False
    assert merged.sonarr[0].api_key == "sonarr-secret"
    imported_deluge = next(service for service in merged.downloaders if service.id == "new-deluge")
    assert isinstance(imported_deluge, DelugeServiceConfig)
    assert imported_deluge.password == ""
    assert imported_deluge.enabled is False
    assert result.updated_profiles == 1
    assert result.added_profiles == 1
    assert result.all_imported_profiles_disabled is True


def test_redacted_import_rejects_unknown_future_schema() -> None:
    payload = export_redacted_config(_sensitive_config()).model_dump(mode="json")
    payload["export_schema_version"] = 2

    with pytest.raises(ValidationError):
        RedactedConfigExport.model_validate(json.loads(json.dumps(payload, default=str)))


def _sensitive_config() -> RuntimeConfig:
    return RuntimeConfig(
        admin=AdminAccountConfig(
            username="admin",
            password_salt="password-salt",
            password_hash="password-hash",
        ),
        general=GeneralConfig(
            dry_run=False,
            webhook_shared_token="webhook-secret",
            sso_client_secret="oidc-secret",
        ),
        radarr=[
            RadarrServiceConfig(
                id="radarr-one",
                name="Radarr",
                url="https://url-user:url-password@radarr.example/base?token=query-secret",
                api_key="radarr-secret",
            )
        ],
        sonarr=[
            SonarrServiceConfig(
                id="sonarr-one",
                name="Sonarr",
                url="https://sonarr.example",
                api_key="sonarr-secret",
            )
        ],
        downloaders=[
            QbittorrentServiceConfig(
                id="qbt-one",
                name="qBittorrent",
                url="https://qbt.example",
                username="qbt-user",
                password="qbt-password",
                api_key="qbt-token",
            )
        ],
    )
