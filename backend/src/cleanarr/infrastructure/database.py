"""Ordered SQLite schema migrations shared by all persistent stores."""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DatabaseMigration:
    """One forward-only, transactional schema migration."""

    version: int
    statements: Sequence[str]


MIGRATIONS = (
    DatabaseMigration(
        version=1,
        statements=(
            "CREATE TABLE IF NOT EXISTS config ( id INTEGER PRIMARY KEY CHECK (id = 1), config_json TEXT NOT NULL)",
            "CREATE TABLE IF NOT EXISTS activity ("
            " id INTEGER PRIMARY KEY AUTOINCREMENT,"
            " processed_at TEXT NOT NULL,"
            " result_json TEXT NOT NULL"
            ")",
            "CREATE INDEX IF NOT EXISTS idx_processed_at ON activity(processed_at)",
            "CREATE TABLE IF NOT EXISTS manual_delete_jobs ("
            " id TEXT PRIMARY KEY,"
            " request_json TEXT NOT NULL,"
            " event_json TEXT NOT NULL,"
            " preflight_json TEXT NOT NULL,"
            " status TEXT NOT NULL,"
            " phase TEXT NOT NULL,"
            " progress_percent INTEGER NOT NULL,"
            " message TEXT NOT NULL,"
            " item_name TEXT,"
            " created_at TEXT NOT NULL,"
            " started_at TEXT,"
            " completed_at TEXT,"
            " next_retry_at TEXT,"
            " attempt_count INTEGER NOT NULL,"
            " max_attempts INTEGER NOT NULL,"
            " result_json TEXT,"
            " error TEXT"
            ")",
        ),
    ),
    DatabaseMigration(
        version=2,
        statements=(
            "CREATE TABLE IF NOT EXISTS processed_webhook_events ("
            " event_key TEXT PRIMARY KEY,"
            " received_at TEXT NOT NULL,"
            " completed_at TEXT,"
            " event_json TEXT NOT NULL,"
            " result_json TEXT"
            ")",
            "CREATE INDEX IF NOT EXISTS idx_webhook_event_completed_at ON processed_webhook_events(completed_at)",
        ),
    ),
)

LATEST_SCHEMA_VERSION = MIGRATIONS[-1].version


class UnsupportedDatabaseVersionError(RuntimeError):
    """Raised when a newer database is opened by an older CleanArr build."""


def migrate_database(db_path: Path) -> int:
    """Apply pending migrations in order and return the resulting version."""

    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as connection:
        current_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        if current_version > LATEST_SCHEMA_VERSION:
            raise UnsupportedDatabaseVersionError(
                f"Database schema {current_version} is newer than supported schema {LATEST_SCHEMA_VERSION}."
            )

        try:
            connection.execute("BEGIN IMMEDIATE")
            for migration in MIGRATIONS:
                if migration.version <= current_version:
                    continue
                if migration.version != current_version + 1:
                    raise RuntimeError(f"Database migration chain is not contiguous at version {migration.version}.")
                for statement in migration.statements:
                    connection.execute(statement)
                connection.execute(f"PRAGMA user_version = {migration.version}")
                current_version = migration.version
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    return current_version
