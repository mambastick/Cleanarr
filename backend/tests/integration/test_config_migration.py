"""Persisted runtime configuration migration tests."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from cleanarr.application.configuration import RuntimeConfigurationService
from cleanarr.domain.config import CURRENT_CONFIG_SCHEMA_VERSION
from cleanarr.infrastructure.config_migrations import UnsupportedConfigSchemaVersionError
from cleanarr.infrastructure.config_store import SqliteConfigStore
from cleanarr.infrastructure.settings import Settings


def test_v030_sqlite_config_migrates_jellyseerr_to_canonical_seerr(tmp_path: Path) -> None:
    db_path = tmp_path / "cleanarr.db"
    store = SqliteConfigStore(str(db_path))
    legacy_payload = {
        "jellyseerr": [
            {
                "id": "legacy-seerr",
                "kind": "jellyseerr",
                "name": "Existing Seerr profile",
                "url": "https://seerr.example.com/api/v1",
                "api_key": "existing-key",
                "enabled": True,
                "is_default": True,
            }
        ]
    }
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "INSERT INTO config (id, config_json) VALUES (1, ?)",
            (json.dumps(legacy_payload),),
        )
        connection.commit()

    service = RuntimeConfigurationService(store=store, settings=Settings.model_construct())

    config = service.get_config()
    assert len(config.seerr) == 1
    assert config.seerr[0].id == "legacy-seerr"
    assert config.seerr[0].kind.value == "seerr"

    with sqlite3.connect(db_path) as connection:
        row = connection.execute("SELECT config_json FROM config WHERE id = 1").fetchone()
    assert row is not None
    persisted = json.loads(row[0])
    assert "jellyseerr" not in persisted
    assert persisted["seerr"][0]["id"] == "legacy-seerr"
    assert persisted["seerr"][0]["kind"] == "seerr"


def test_mixed_upgrade_payload_merges_unique_legacy_and_canonical_profiles(tmp_path: Path) -> None:
    db_path = tmp_path / "cleanarr.db"
    store = SqliteConfigStore(str(db_path))
    mixed_payload = {
        "seerr": [
            {
                "id": "canonical",
                "kind": "seerr",
                "name": "Canonical profile",
                "url": "https://canonical.example.com/api/v1",
                "api_key": "canonical-key",
            }
        ],
        "jellyseerr": [
            {
                "id": "canonical",
                "kind": "jellyseerr",
                "name": "Stale duplicate",
                "url": "https://stale.example.com/api/v1",
                "api_key": "stale-key",
            },
            {
                "id": "legacy-only",
                "kind": "jellyseerr",
                "name": "Legacy-only profile",
                "url": "https://legacy.example.com/api/v1",
                "api_key": "legacy-key",
            },
        ],
    }
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "INSERT INTO config (id, config_json) VALUES (1, ?)",
            (json.dumps(mixed_payload),),
        )
        connection.commit()

    service = RuntimeConfigurationService(store=store, settings=Settings.model_construct())

    profiles = service.get_config().seerr
    assert [profile.id for profile in profiles] == ["canonical", "legacy-only"]
    assert profiles[0].name == "Canonical profile"


def test_v040_config_upgrade_is_versioned_fail_closed_and_rollback_safe(tmp_path: Path) -> None:
    db_path = tmp_path / "cleanarr.db"
    backup_path = tmp_path / "cleanarr-v0.4.0.backup.db"
    restored_path = tmp_path / "cleanarr-restored.db"
    store = SqliteConfigStore(str(db_path))
    stable_payload = {
        "admin": {
            "username": "existing-admin",
            "password_salt": "00" * 16,
            "password_hash": "11" * 64,
        },
        "general": {
            "dry_run": True,
            "sso_mode": "both",
            "sso_issuer_url": "https://id.example/realms/cleanarr",
            "sso_client_id": "cleanarr",
            "sso_client_secret": "existing-secret",
            "sso_redirect_uri": "https://cleanarr.example/api/auth/sso/callback",
        },
        "seerr": [],
    }
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "INSERT INTO config (id, config_json) VALUES (1, ?)",
            (json.dumps(stable_payload),),
        )
        connection.commit()
    with sqlite3.connect(db_path) as source, sqlite3.connect(backup_path) as backup:
        source.backup(backup)
    with sqlite3.connect(backup_path) as backup:
        assert backup.execute("PRAGMA integrity_check").fetchone() == ("ok",)

    service = RuntimeConfigurationService(store=store, settings=Settings.model_construct())
    config = service.get_config()

    assert config.config_schema_version == CURRENT_CONFIG_SCHEMA_VERSION
    assert config.admin.username == "existing-admin"
    assert config.general.sso_client_id == "cleanarr"
    assert config.general.sso_allowed_users == []
    assert config.general.sso_allowed_groups == []
    assert config.general.has_sso_access_policy() is False
    with sqlite3.connect(db_path) as connection:
        migrated = json.loads(connection.execute("SELECT config_json FROM config WHERE id = 1").fetchone()[0])
    assert migrated["config_schema_version"] == CURRENT_CONFIG_SCHEMA_VERSION
    assert migrated["general"]["sso_client_secret"] == "existing-secret"

    with sqlite3.connect(backup_path) as backup, sqlite3.connect(restored_path) as restored:
        backup.backup(restored)
    with sqlite3.connect(restored_path) as restored:
        restored_payload = json.loads(restored.execute("SELECT config_json FROM config WHERE id = 1").fetchone()[0])
    assert "config_schema_version" not in restored_payload
    assert restored_payload["admin"]["username"] == "existing-admin"


def test_future_config_schema_is_rejected_without_rewrite(tmp_path: Path) -> None:
    db_path = tmp_path / "future.db"
    store = SqliteConfigStore(str(db_path))
    future_payload = {"config_schema_version": CURRENT_CONFIG_SCHEMA_VERSION + 1, "general": {"dry_run": True}}
    serialized = json.dumps(future_payload)
    with sqlite3.connect(db_path) as connection:
        connection.execute("INSERT INTO config (id, config_json) VALUES (1, ?)", (serialized,))
        connection.commit()

    with pytest.raises(UnsupportedConfigSchemaVersionError, match="newer than supported"):
        store.load()

    with sqlite3.connect(db_path) as connection:
        assert connection.execute("SELECT config_json FROM config WHERE id = 1").fetchone() == (serialized,)
