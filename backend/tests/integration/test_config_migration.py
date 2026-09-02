"""Persisted runtime configuration migration tests."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from cleanarr.application.configuration import RuntimeConfigurationService
from cleanarr.domain.config import CURRENT_CONFIG_SCHEMA_VERSION
from cleanarr.infrastructure.config_migrations import UnsupportedConfigSchemaVersionError
from cleanarr.infrastructure.config_store import FileConfigStore, SqliteConfigStore, config_v3_backup_path
from cleanarr.infrastructure.database import MIGRATIONS
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
    backup_path = config_v3_backup_path(db_path)
    restored_path = tmp_path / "cleanarr-restored.db"
    store = SqliteConfigStore(str(db_path))
    stable_payload = {
        "config_schema_version": 3,
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

    service = RuntimeConfigurationService(store=store, settings=Settings.model_construct())
    config = service.get_config()

    assert config.config_schema_version == CURRENT_CONFIG_SCHEMA_VERSION
    assert config.admin.username == "existing-admin"
    assert config.general.sso_client_id == "cleanarr"
    assert config.general.sso_allowed_users == []
    assert config.general.sso_allowed_groups == []
    assert config.general.has_sso_access_policy() is False
    assert config.general.seeding_stop_policy.enabled is False
    assert config.general.storage_warning_free_percent == 15.0
    assert config.general.storage_critical_free_percent == 5.0
    with sqlite3.connect(db_path) as connection:
        migrated = json.loads(connection.execute("SELECT config_json FROM config WHERE id = 1").fetchone()[0])
    assert migrated["config_schema_version"] == CURRENT_CONFIG_SCHEMA_VERSION
    assert migrated["general"]["sso_client_secret"] == "existing-secret"
    assert migrated["general"]["seeding_stop_policy"]["enabled"] is False

    assert backup_path.exists()
    original_backup = backup_path.read_bytes()
    with sqlite3.connect(backup_path) as backup:
        assert backup.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        backup_payload = json.loads(backup.execute("SELECT config_json FROM config WHERE id = 1").fetchone()[0])
    assert backup_payload["config_schema_version"] == 3
    assert "storage_warning_free_percent" not in backup_payload["general"]

    # Normalized persistence and later loads must never overwrite the one
    # rollback artifact captured before the first v3 -> v4 rewrite.
    assert store.load() is not None
    assert backup_path.read_bytes() == original_backup

    with sqlite3.connect(backup_path) as backup, sqlite3.connect(restored_path) as restored:
        backup.backup(restored)
    with sqlite3.connect(restored_path) as restored:
        restored_payload = json.loads(restored.execute("SELECT config_json FROM config WHERE id = 1").fetchone()[0])
    assert restored_payload["config_schema_version"] == 3
    assert restored_payload["admin"]["username"] == "existing-admin"


def test_file_config_v3_upgrade_creates_one_restorable_sidecar(tmp_path: Path) -> None:
    config_path = tmp_path / "runtime-config.json"
    payload = {"config_schema_version": 3, "general": {"dry_run": True}}
    config_path.write_text(json.dumps(payload), encoding="utf-8")
    store = FileConfigStore(str(config_path))

    config = store.load()

    assert config is not None and config.config_schema_version == CURRENT_CONFIG_SCHEMA_VERSION
    backup_path = config_v3_backup_path(config_path)
    assert json.loads(backup_path.read_text(encoding="utf-8")) == payload
    original_backup = backup_path.read_bytes()
    store.save(config)
    assert store.load() is not None
    assert backup_path.read_bytes() == original_backup


def test_file_config_v3_upgrade_refuses_to_overwrite_a_conflicting_backup(tmp_path: Path) -> None:
    config_path = tmp_path / "runtime-config.json"
    payload = {"config_schema_version": 3, "general": {"dry_run": True}}
    config_path.write_text(json.dumps(payload), encoding="utf-8")
    backup_path = config_v3_backup_path(config_path)
    backup_path.write_text(
        json.dumps({"config_schema_version": 3, "general": {"dry_run": False}}),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="does not match"):
        FileConfigStore(str(config_path)).load()

    assert json.loads(config_path.read_text(encoding="utf-8")) == payload
    assert json.loads(backup_path.read_text(encoding="utf-8"))["general"]["dry_run"] is False


def test_file_config_v3_upgrade_rejects_symlink_backup_alias(tmp_path: Path) -> None:
    config_path = tmp_path / "runtime-config.json"
    payload = {"config_schema_version": 3, "general": {"dry_run": True}}
    config_path.write_text(json.dumps(payload), encoding="utf-8")
    backup_path = config_v3_backup_path(config_path)
    backup_path.symlink_to(config_path)

    with pytest.raises(RuntimeError, match="independent regular file"):
        FileConfigStore(str(config_path)).load()

    assert json.loads(config_path.read_text(encoding="utf-8")) == payload
    assert backup_path.is_symlink()


def test_sqlite_v3_upgrade_fails_closed_when_existing_backup_is_corrupt(tmp_path: Path) -> None:
    db_path = tmp_path / "cleanarr.db"
    store = SqliteConfigStore(str(db_path))
    payload = {"config_schema_version": 3, "general": {"dry_run": True}}
    serialized = json.dumps(payload)
    with sqlite3.connect(db_path) as connection:
        connection.execute("INSERT INTO config (id, config_json) VALUES (1, ?)", (serialized,))
        connection.commit()
    backup_path = config_v3_backup_path(db_path)
    backup_path.write_bytes(b"not-a-sqlite-database")

    with pytest.raises(RuntimeError, match="not a valid CleanArr SQLite database"):
        RuntimeConfigurationService(store=store, settings=Settings.model_construct())

    with sqlite3.connect(db_path) as connection:
        assert json.loads(connection.execute("SELECT config_json FROM config WHERE id = 1").fetchone()[0]) == payload
    assert backup_path.read_bytes() == b"not-a-sqlite-database"


def test_sqlite_v3_upgrade_rejects_hardlinked_backup_alias(tmp_path: Path) -> None:
    db_path = tmp_path / "cleanarr.db"
    store = SqliteConfigStore(str(db_path))
    payload = {"config_schema_version": 3, "general": {"dry_run": True}}
    with sqlite3.connect(db_path) as connection:
        connection.execute("INSERT INTO config (id, config_json) VALUES (1, ?)", (json.dumps(payload),))
        connection.commit()
    backup_path = config_v3_backup_path(db_path)
    backup_path.hardlink_to(db_path)

    with pytest.raises(RuntimeError, match="independent regular file"):
        store.load()

    with sqlite3.connect(db_path) as connection:
        persisted = json.loads(connection.execute("SELECT config_json FROM config WHERE id = 1").fetchone()[0])
    assert persisted == payload


def test_sqlite_v3_upgrade_rejects_backup_with_different_database_state(tmp_path: Path) -> None:
    db_path = tmp_path / "cleanarr.db"
    store = SqliteConfigStore(str(db_path))
    payload = {"config_schema_version": 3, "general": {"dry_run": True}}
    with sqlite3.connect(db_path) as connection:
        connection.execute("INSERT INTO config (id, config_json) VALUES (1, ?)", (json.dumps(payload),))
        connection.execute(
            "INSERT INTO activity (processed_at, result_json) VALUES (?, ?)",
            ("2026-09-01T00:00:00+00:00", '{"name":"source"}'),
        )
        connection.commit()
    backup_path = config_v3_backup_path(db_path)
    with sqlite3.connect(db_path) as source, sqlite3.connect(backup_path) as backup:
        source.backup(backup)
    with sqlite3.connect(backup_path) as backup:
        backup.execute("UPDATE activity SET result_json = ?", ('{"name":"different"}',))
        backup.commit()

    with pytest.raises(RuntimeError, match="does not match"):
        store.load()


def test_sqlite_v3_backup_precedes_database_migrations_and_keeps_seeded_activity(tmp_path: Path) -> None:
    db_path = tmp_path / "cleanarr.db"
    payload = {"config_schema_version": 3, "general": {"dry_run": True}}
    with sqlite3.connect(db_path) as connection:
        for migration in MIGRATIONS[:2]:
            for statement in migration.statements:
                connection.execute(statement)
        connection.execute("PRAGMA user_version = 2")
        connection.execute("INSERT INTO config (id, config_json) VALUES (1, ?)", (json.dumps(payload),))
        connection.execute(
            "INSERT INTO activity (processed_at, result_json) VALUES (?, ?)",
            ("2026-09-01T00:00:00+00:00", '{"name":"before-upgrade"}'),
        )
        connection.commit()

    store = SqliteConfigStore(str(db_path))
    config = store.load()

    assert config is not None and config.config_schema_version == CURRENT_CONFIG_SCHEMA_VERSION
    backup_path = config_v3_backup_path(db_path)
    with sqlite3.connect(backup_path) as backup:
        assert backup.execute("PRAGMA user_version").fetchone() == (2,)
        assert backup.execute("SELECT result_json FROM activity").fetchone() == ('{"name":"before-upgrade"}',)


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
    assert not config_v3_backup_path(db_path).exists()


def test_future_config_schema_blocks_database_migration_before_any_rewrite(tmp_path: Path) -> None:
    db_path = tmp_path / "old-future.db"
    future_payload = {"config_schema_version": CURRENT_CONFIG_SCHEMA_VERSION + 1, "general": {"dry_run": True}}
    serialized = json.dumps(future_payload)
    with sqlite3.connect(db_path) as connection:
        for statement in MIGRATIONS[0].statements:
            connection.execute(statement)
        connection.execute("PRAGMA user_version = 1")
        connection.execute("INSERT INTO config (id, config_json) VALUES (1, ?)", (serialized,))
        connection.commit()

    with pytest.raises(UnsupportedConfigSchemaVersionError, match="newer than supported"):
        SqliteConfigStore(str(db_path))

    with sqlite3.connect(db_path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone() == (1,)
        assert connection.execute("SELECT config_json FROM config WHERE id = 1").fetchone() == (serialized,)
        assert (
            connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'download_observations'"
            ).fetchone()
            is None
        )
    assert not config_v3_backup_path(db_path).exists()


def test_future_legacy_file_blocks_sqlite_creation_before_any_rewrite(tmp_path: Path) -> None:
    db_path = tmp_path / "not-created.db"
    config_path = tmp_path / "runtime-config.json"
    future_payload = {"config_schema_version": CURRENT_CONFIG_SCHEMA_VERSION + 1, "general": {"dry_run": True}}
    serialized = json.dumps(future_payload)
    config_path.write_text(serialized, encoding="utf-8")

    with pytest.raises(UnsupportedConfigSchemaVersionError, match="newer than supported"):
        SqliteConfigStore(str(db_path), migrate_from=str(config_path))

    assert not db_path.exists()
    assert config_path.read_text(encoding="utf-8") == serialized
    assert not config_v3_backup_path(config_path).exists()
