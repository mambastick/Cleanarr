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
    DatabaseMigration(
        version=3,
        statements=(
            "ALTER TABLE manual_delete_jobs ADD COLUMN idempotency_key TEXT",
            "ALTER TABLE manual_delete_jobs ADD COLUMN display_name TEXT",
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_manual_delete_jobs_idempotency_key "
            "ON manual_delete_jobs(idempotency_key) WHERE idempotency_key IS NOT NULL",
        ),
    ),
    DatabaseMigration(
        version=4,
        statements=(
            "CREATE TABLE IF NOT EXISTS destructive_idempotency_ledger ("
            " idempotency_key TEXT PRIMARY KEY,"
            " request_kind TEXT NOT NULL CHECK (request_kind IN ('single', 'batch')),"
            " canonical_request_json TEXT NOT NULL,"
            " original_request_json TEXT NOT NULL,"
            " resource_id TEXT NOT NULL,"
            " created_at TEXT NOT NULL"
            ")",
            "CREATE TABLE IF NOT EXISTS manual_delete_batches ("
            " id TEXT PRIMARY KEY,"
            " canonical_request_json TEXT NOT NULL,"
            " confirmed_batch_hash TEXT NOT NULL,"
            " status TEXT NOT NULL,"
            " message TEXT NOT NULL,"
            " created_at TEXT NOT NULL,"
            " started_at TEXT,"
            " completed_at TEXT,"
            " error_code TEXT,"
            " error_message TEXT"
            ")",
            "CREATE TABLE IF NOT EXISTS manual_delete_batch_children ("
            " id TEXT PRIMARY KEY,"
            " batch_id TEXT NOT NULL REFERENCES manual_delete_batches(id) ON DELETE CASCADE,"
            " position INTEGER NOT NULL,"
            " mutation_identity TEXT NOT NULL,"
            " request_json TEXT NOT NULL,"
            " event_json TEXT,"
            " preflight_json TEXT,"
            " plan_hash TEXT,"
            " display_name TEXT NOT NULL,"
            " status TEXT NOT NULL,"
            " message TEXT NOT NULL,"
            " blocked_code TEXT,"
            " error_code TEXT,"
            " error_message TEXT,"
            " result_json TEXT,"
            " started_at TEXT,"
            " completed_at TEXT,"
            " UNIQUE(batch_id, position),"
            " UNIQUE(batch_id, mutation_identity)"
            ")",
            "CREATE INDEX IF NOT EXISTS idx_manual_delete_batches_created_at ON manual_delete_batches(created_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_manual_delete_batch_children_batch_position "
            "ON manual_delete_batch_children(batch_id, position)",
        ),
    ),
    DatabaseMigration(
        version=5,
        statements=(
            "CREATE TABLE IF NOT EXISTS download_observations ("
            " client_id TEXT NOT NULL, info_hash TEXT NOT NULL, snapshot_json TEXT NOT NULL,"
            " observed_at TEXT NOT NULL, freshness TEXT NOT NULL, PRIMARY KEY(client_id, info_hash)"
            ")",
            "CREATE INDEX IF NOT EXISTS idx_download_observations_order ON download_observations(client_id, info_hash)",
            "CREATE TABLE IF NOT EXISTS download_actions ("
            " id TEXT PRIMARY KEY, idempotency_key TEXT NOT NULL UNIQUE, canonical_request_json TEXT NOT NULL,"
            " client_id TEXT NOT NULL, info_hash TEXT NOT NULL, action TEXT NOT NULL,"
            " source TEXT NOT NULL DEFAULT 'manual', status TEXT NOT NULL,"
            " code TEXT, result_json TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,"
            " attempt_count INTEGER NOT NULL DEFAULT 0, max_attempts INTEGER NOT NULL DEFAULT 1"
            ")",
            "CREATE INDEX IF NOT EXISTS idx_download_actions_updated ON download_actions(updated_at DESC)",
            "CREATE TABLE IF NOT EXISTS policy_evaluations ("
            " id INTEGER PRIMARY KEY AUTOINCREMENT, policy_revision TEXT NOT NULL, client_id TEXT NOT NULL,"
            " info_hash TEXT NOT NULL, observation_key TEXT NOT NULL, facts_json TEXT NOT NULL,"
            " reason_code TEXT NOT NULL, decision TEXT NOT NULL, evaluated_at TEXT NOT NULL"
            ")",
            "CREATE INDEX IF NOT EXISTS idx_policy_evaluations_evaluated ON policy_evaluations(evaluated_at DESC)",
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_policy_evaluations_revision_observation "
            "ON policy_evaluations(policy_revision, observation_key)",
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
            if current_version >= 4:
                _backfill_v3_single_idempotency_ledger(connection)
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    return current_version


def _backfill_v3_single_idempotency_ledger(connection: sqlite3.Connection) -> None:
    """Retain v3 manual-job keys even when their visible jobs are later pruned.

    The v3 request JSON is retained as the original request.  The job store
    canonicalizes it before comparing a future duplicate, so an old row cannot
    accidentally be treated as a new destructive request.
    """

    rows = connection.execute(
        "SELECT id, request_json, idempotency_key, created_at FROM manual_delete_jobs WHERE idempotency_key IS NOT NULL"
    ).fetchall()
    for job_id, request_json, key, created_at in rows:
        connection.execute(
            "INSERT OR IGNORE INTO destructive_idempotency_ledger ("
            "idempotency_key, request_kind, canonical_request_json, original_request_json, resource_id, created_at"
            ") VALUES (?, 'single', ?, ?, ?, ?)",
            (str(key), str(request_json), str(request_json), str(job_id), str(created_at)),
        )
