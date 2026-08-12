"""Upgrade and rollback evidence for the shared SQLite schema."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from cleanarr.infrastructure.database import (
    LATEST_SCHEMA_VERSION,
    UnsupportedDatabaseVersionError,
    migrate_database,
)


def _create_latest_stable_database(db_path: Path) -> None:
    """Create the unversioned config/activity layout shipped by v0.3.0."""

    with sqlite3.connect(db_path) as connection:
        connection.execute("CREATE TABLE config ( id INTEGER PRIMARY KEY CHECK (id = 1), config_json TEXT NOT NULL)")
        connection.execute(
            "CREATE TABLE activity ("
            " id INTEGER PRIMARY KEY AUTOINCREMENT,"
            " processed_at TEXT NOT NULL,"
            " result_json TEXT NOT NULL"
            ")"
        )
        connection.execute(
            "INSERT INTO config (id, config_json) VALUES (1, ?)",
            ('{"general":{"dry_run":true}}',),
        )
        connection.execute(
            "INSERT INTO activity (processed_at, result_json) VALUES (?, ?)",
            ("2026-08-12T00:00:00+00:00", '{"name":"preserved"}'),
        )
        connection.commit()


def _table_names(db_path: Path) -> set[str]:
    with sqlite3.connect(db_path) as connection:
        return {
            str(row[0]) for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
        }


def test_v030_upgrade_is_versioned_additive_and_rollback_backup_restores(tmp_path: Path) -> None:
    db_path = tmp_path / "cleanarr.db"
    backup_path = tmp_path / "cleanarr-v0.3.0.backup.db"
    restored_path = tmp_path / "cleanarr-restored.db"
    _create_latest_stable_database(db_path)

    with sqlite3.connect(db_path) as source, sqlite3.connect(backup_path) as backup:
        source.backup(backup)
    with sqlite3.connect(backup_path) as backup:
        assert backup.execute("PRAGMA integrity_check").fetchone() == ("ok",)

    assert migrate_database(db_path) == LATEST_SCHEMA_VERSION
    assert migrate_database(db_path) == LATEST_SCHEMA_VERSION

    with sqlite3.connect(db_path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone() == (LATEST_SCHEMA_VERSION,)
        assert connection.execute("SELECT config_json FROM config WHERE id = 1").fetchone() == (
            '{"general":{"dry_run":true}}',
        )
        assert connection.execute("SELECT result_json FROM activity").fetchone() == ('{"name":"preserved"}',)
    assert "manual_delete_jobs" in _table_names(db_path)

    with sqlite3.connect(backup_path) as backup, sqlite3.connect(restored_path) as restored:
        backup.backup(restored)
    with sqlite3.connect(restored_path) as restored:
        assert restored.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert restored.execute("PRAGMA user_version").fetchone() == (0,)
        assert restored.execute("SELECT config_json FROM config WHERE id = 1").fetchone() == (
            '{"general":{"dry_run":true}}',
        )
    assert "manual_delete_jobs" not in _table_names(restored_path)


def test_newer_schema_is_rejected_without_mutation(tmp_path: Path) -> None:
    db_path = tmp_path / "future.db"
    with sqlite3.connect(db_path) as connection:
        connection.execute(f"PRAGMA user_version = {LATEST_SCHEMA_VERSION + 1}")
        connection.commit()

    with pytest.raises(UnsupportedDatabaseVersionError, match="newer than supported"):
        migrate_database(db_path)

    with sqlite3.connect(db_path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone() == (LATEST_SCHEMA_VERSION + 1,)
