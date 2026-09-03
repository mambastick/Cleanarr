"""Upgrade and rollback evidence for the shared SQLite schema."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from cleanarr.domain.downloads import (
    DownloadActionStatus,
    DownloadControlAction,
    ListingFreshness,
    TorrentOwnership,
    TorrentSnapshot,
    TorrentState,
)
from cleanarr.infrastructure.database import (
    LATEST_SCHEMA_VERSION,
    MIGRATIONS,
    UnsupportedDatabaseVersionError,
    migrate_database,
)
from cleanarr.infrastructure.downloads_repository import DownloadsRepository


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


def test_v1_manual_job_schema_upgrades_to_event_ledger_without_data_loss(tmp_path: Path) -> None:
    db_path = tmp_path / "v1.db"
    with sqlite3.connect(db_path) as connection:
        for statement in MIGRATIONS[0].statements:
            connection.execute(statement)
        connection.execute("PRAGMA user_version = 1")
        connection.execute(
            "INSERT INTO config (id, config_json) VALUES (1, ?)",
            ('{"general":{"dry_run":true}}',),
        )
        connection.commit()

    assert migrate_database(db_path) == LATEST_SCHEMA_VERSION

    with sqlite3.connect(db_path) as connection:
        assert connection.execute("SELECT config_json FROM config WHERE id = 1").fetchone() == (
            '{"general":{"dry_run":true}}',
        )
    assert {"manual_delete_jobs", "processed_webhook_events"} <= _table_names(db_path)


def test_v2_jobs_upgrade_to_v4_idempotency_batch_tables_and_rollback_backup(tmp_path: Path) -> None:
    db_path = tmp_path / "v2.db"
    backup_path = tmp_path / "v2.backup.db"
    restored_path = tmp_path / "v2-restored.db"
    with sqlite3.connect(db_path) as connection:
        for migration in MIGRATIONS[:2]:
            for statement in migration.statements:
                connection.execute(statement)
        connection.execute("PRAGMA user_version = 2")
        connection.execute(
            "INSERT INTO activity (processed_at, result_json) VALUES (?, ?)",
            ("2026-09-01T00:00:00+00:00", '{"item_type":"Movie","name":"Old activity"}'),
        )
        connection.execute(
            "INSERT INTO manual_delete_jobs ("
            "id, request_json, event_json, preflight_json, status, phase, progress_percent, message, item_name, "
            "created_at, attempt_count, max_attempts"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "old-job",
                "{}",
                "{}",
                "{}",
                "completed",
                "completed",
                100,
                "Old job",
                "Old library title",
                "2026-09-01T00:00:00+00:00",
                1,
                3,
            ),
        )
        connection.commit()

    with sqlite3.connect(db_path) as source, sqlite3.connect(backup_path) as backup:
        source.backup(backup)
    with sqlite3.connect(backup_path) as backup:
        assert backup.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert backup.execute("PRAGMA user_version").fetchone() == (2,)

    assert migrate_database(db_path) == LATEST_SCHEMA_VERSION
    assert migrate_database(db_path) == LATEST_SCHEMA_VERSION
    with sqlite3.connect(db_path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone() == (LATEST_SCHEMA_VERSION,)
        assert connection.execute(
            "SELECT item_name, idempotency_key, display_name FROM manual_delete_jobs WHERE id = 'old-job'"
        ).fetchone() == ("Old library title", None, None)
        assert connection.execute("SELECT result_json FROM activity").fetchone() == (
            '{"item_type":"Movie","name":"Old activity"}',
        )
        indexes = {row[1] for row in connection.execute("PRAGMA index_list(manual_delete_jobs)").fetchall()}
        assert "idx_manual_delete_jobs_idempotency_key" in indexes
        assert {
            "destructive_idempotency_ledger",
            "manual_delete_batches",
            "manual_delete_batch_children",
            "download_observations",
            "download_actions",
            "policy_evaluations",
        } <= _table_names(db_path)
        connection.execute(
            "INSERT INTO download_actions("
            "id,idempotency_key,canonical_request_json,client_id,info_hash,action,status,created_at,updated_at) "
            "VALUES ('download-action','00000000-0000-0000-0000-000000000000','{}','client','AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA','pause','queued','now','now')"
        )
        connection.commit()
    assert migrate_database(db_path) == LATEST_SCHEMA_VERSION
    with sqlite3.connect(db_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM download_actions").fetchone() == (1,)

    with sqlite3.connect(backup_path) as backup, sqlite3.connect(restored_path) as restored:
        backup.backup(restored)
    with sqlite3.connect(restored_path) as restored:
        assert restored.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert restored.execute("PRAGMA user_version").fetchone() == (2,)
        columns = {row[1] for row in restored.execute("PRAGMA table_info(manual_delete_jobs)").fetchall()}
        assert "idempotency_key" not in columns
        assert not ({"download_observations", "download_actions", "policy_evaluations"} & _table_names(restored_path))
        assert "display_name" not in columns


def test_v3_idempotency_keys_are_backfilled_into_the_v4_ledger(tmp_path: Path) -> None:
    db_path = tmp_path / "v3.db"
    with sqlite3.connect(db_path) as connection:
        for migration in MIGRATIONS[:3]:
            for statement in migration.statements:
                connection.execute(statement)
        connection.execute("PRAGMA user_version = 3")
        connection.execute(
            "INSERT INTO manual_delete_jobs ("
            "id, request_json, event_json, preflight_json, status, phase, progress_percent, message, created_at, "
            "attempt_count, max_attempts, idempotency_key"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "v3-job",
                '{"item_type":"movie","radarr_movie_id":1,"confirmed_plan_hash":"confirmed"}',
                "{}",
                "{}",
                "completed",
                "completed",
                100,
                "done",
                "2026-09-01T00:00:00+00:00",
                1,
                1,
                "10000000-0000-4000-8000-000000000001",
            ),
        )
        connection.commit()

    assert migrate_database(db_path) == LATEST_SCHEMA_VERSION
    assert migrate_database(db_path) == LATEST_SCHEMA_VERSION
    with sqlite3.connect(db_path) as connection:
        assert connection.execute(
            "SELECT request_kind, resource_id FROM destructive_idempotency_ledger WHERE idempotency_key = ?",
            ("10000000-0000-4000-8000-000000000001",),
        ).fetchone() == ("single", "v3-job")


def test_populated_v4_upgrades_to_v5_and_backup_restores_exactly(tmp_path: Path) -> None:
    db_path = tmp_path / "v4.db"
    backup_path = tmp_path / "v4.backup.db"
    restored_path = tmp_path / "v4.restored.db"
    with sqlite3.connect(db_path) as connection:
        for migration in MIGRATIONS[:4]:
            for statement in migration.statements:
                connection.execute(statement)
        connection.execute("PRAGMA user_version = 4")
        connection.execute(
            "INSERT INTO manual_delete_jobs(id,request_json,event_json,preflight_json,status,phase,progress_percent,"
            "message,created_at,attempt_count,max_attempts) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            ("v4-job", "{}", "{}", "{}", "completed", "completed", 100, "done", "now", 1, 1),
        )
        connection.execute(
            "INSERT INTO destructive_idempotency_ledger(idempotency_key,request_kind,canonical_request_json,"
            "original_request_json,resource_id,created_at) VALUES(?,?,?,?,?,?)",
            ("v4-key", "single", "{}", "{}", "v4-job", "now"),
        )
        connection.execute(
            "INSERT INTO manual_delete_batches(id,canonical_request_json,confirmed_batch_hash,status,message,created_at) "
            "VALUES(?,?,?,?,?,?)",
            ("v4-batch", "{}", "batch-hash", "completed", "done", "now"),
        )
        connection.commit()
    with sqlite3.connect(db_path) as source, sqlite3.connect(backup_path) as backup:
        source.backup(backup)

    assert migrate_database(db_path) == LATEST_SCHEMA_VERSION
    assert migrate_database(db_path) == LATEST_SCHEMA_VERSION
    with sqlite3.connect(db_path) as connection:
        assert connection.execute("SELECT id FROM manual_delete_jobs").fetchone() == ("v4-job",)
        assert connection.execute("SELECT resource_id FROM destructive_idempotency_ledger").fetchone() == ("v4-job",)
        assert connection.execute("SELECT id FROM manual_delete_batches").fetchone() == ("v4-batch",)
        assert {"download_observations", "download_actions", "policy_evaluations"} <= _table_names(db_path)
        assert "idx_download_observations_order" in {
            row[1] for row in connection.execute("PRAGMA index_list(download_observations)").fetchall()
        }
        assert "idx_download_actions_updated" in {
            row[1] for row in connection.execute("PRAGMA index_list(download_actions)").fetchall()
        }
        assert "idx_policy_evaluations_revision_observation" in {
            row[1] for row in connection.execute("PRAGMA index_list(policy_evaluations)").fetchall()
        }

    snapshot = TorrentSnapshot(
        client_id="client-a",
        client_name="Client A",
        client_kind="qbittorrent",
        info_hash="A" * 40,
        display_name="Torrent",
        state=TorrentState.SEEDING,
        observed_at=datetime.now(UTC),
        freshness=ListingFreshness.FRESH,
        ownership=TorrentOwnership.MANAGED,
        ratio=2.0,
    )
    repository = DownloadsRepository(db_path)
    repository.save_listing((snapshot,), {"client-a"})
    claim = repository.claim_action(
        idempotency_key="00000000-0000-0000-0000-000000000004",
        canonical_request="{}",
        client_id="client-a",
        info_hash=snapshot.info_hash,
        action=DownloadControlAction.PAUSE,
        max_attempts=2,
        source="policy",
    )
    repository.update_action(
        claim.action_id,
        DownloadActionStatus.SUCCEEDED,
        code="applied",
        result={"outcome": "applied", "before_state": "seeding", "after_state": "stopped"},
    )
    repository.record_policy_evaluation(
        revision="revision",
        snapshot=snapshot,
        facts={"ratio": 2.0},
        reason_code="thresholds_met",
        decision="eligible",
    )
    assert repository.get_snapshot("client-a", snapshot.info_hash) == snapshot
    assert (
        repository.latest_action_projections({("client-a", snapshot.info_hash)})[("client-a", snapshot.info_hash)][
            "source"
        ]
        == "policy"
    )
    assert repository.latest_policy_evaluations()[("client-a", snapshot.info_hash)]["decision"] == "eligible"

    with sqlite3.connect(backup_path) as backup, sqlite3.connect(restored_path) as restored:
        backup.backup(restored)
    with sqlite3.connect(restored_path) as restored:
        assert restored.execute("PRAGMA user_version").fetchone() == (4,)
        assert restored.execute("SELECT id FROM manual_delete_jobs").fetchone() == ("v4-job",)
        assert restored.execute("SELECT resource_id FROM destructive_idempotency_ledger").fetchone() == ("v4-job",)
        assert restored.execute("SELECT id FROM manual_delete_batches").fetchone() == ("v4-batch",)
        assert not ({"download_observations", "download_actions", "policy_evaluations"} & _table_names(restored_path))


def test_populated_v5_upgrades_to_user_registry_and_backup_restores(tmp_path: Path) -> None:
    db_path = tmp_path / "v5.db"
    backup_path = tmp_path / "v5.backup.db"
    restored_path = tmp_path / "v5.restored.db"
    with sqlite3.connect(db_path) as connection:
        for migration in MIGRATIONS[:5]:
            for statement in migration.statements:
                connection.execute(statement)
        connection.execute("PRAGMA user_version = 5")
        connection.execute("INSERT INTO config(id,config_json) VALUES(1,?)", ('{"general":{"dry_run":true}}',))
        connection.commit()
    with sqlite3.connect(db_path) as source, sqlite3.connect(backup_path) as backup:
        source.backup(backup)

    assert migrate_database(db_path) == LATEST_SCHEMA_VERSION
    assert migrate_database(db_path) == LATEST_SCHEMA_VERSION
    with sqlite3.connect(db_path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone() == (LATEST_SCHEMA_VERSION,)
        assert connection.execute("SELECT config_json FROM config").fetchone() == ('{"general":{"dry_run":true}}',)
        columns = {row[1] for row in connection.execute("PRAGMA table_info(user_accounts)").fetchall()}
        assert {"username_key", "username", "role", "auth_source", "last_seen_at"} <= columns

    with sqlite3.connect(backup_path) as backup, sqlite3.connect(restored_path) as restored:
        backup.backup(restored)
    with sqlite3.connect(restored_path) as restored:
        assert restored.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert restored.execute("PRAGMA user_version").fetchone() == (5,)
        assert restored.execute("SELECT config_json FROM config").fetchone() == ('{"general":{"dry_run":true}}',)
        assert "user_accounts" not in _table_names(restored_path)
