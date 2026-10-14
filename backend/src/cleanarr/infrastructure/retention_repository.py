"""SQLite persistence for durable seeding-policy retention evidence."""

from __future__ import annotations

import asyncio
import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from cleanarr.domain.retention import RetainedTorrent
from cleanarr.infrastructure.database import migrate_database


def _parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(UTC)


class SqliteRetentionRepository:
    """Short-lived SQLite operations for records that outlive activity pruning."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        migrate_database(db_path)

    async def record_retention(self, record: RetainedTorrent) -> None:
        """Persist one retained torrent before dependent Arr mutations run."""

        await asyncio.to_thread(self._record_sync, record)

    def _record_sync(self, record: RetainedTorrent) -> None:
        with closing(sqlite3.connect(self.db_path)) as db:
            db.execute(
                "INSERT INTO retained_torrents ("
                "client_id, info_hash, policy, correlation_id, provider_ids_json, item_scope, retained_at, "
                "min_seed_ratio, min_seed_time_minutes"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(client_id, info_hash) DO UPDATE SET "
                "policy=excluded.policy, correlation_id=excluded.correlation_id, "
                "provider_ids_json=excluded.provider_ids_json, item_scope=excluded.item_scope, "
                "retained_at=excluded.retained_at, min_seed_ratio=excluded.min_seed_ratio, "
                "min_seed_time_minutes=excluded.min_seed_time_minutes",
                (
                    record.client_id,
                    record.info_hash.upper(),
                    record.policy.value,
                    record.correlation_id,
                    json.dumps(record.provider_ids, sort_keys=True, separators=(",", ":")),
                    record.item_scope,
                    record.retained_at.astimezone(UTC).isoformat(),
                    record.min_seed_ratio,
                    record.min_seed_time_minutes,
                ),
            )
            db.commit()

    def latest_retention_projections(self, keys: set[tuple[str, str]]) -> dict[tuple[str, str], dict[str, object]]:
        """Return safe UI fields joined by downloader client and hash."""

        if not keys:
            return {}
        normalized = {(client_id, info_hash.upper()) for client_id, info_hash in keys}
        clauses = " OR ".join("(client_id=? AND info_hash=?)" for _ in normalized)
        params = [value for key in sorted(normalized) for value in key]
        with closing(sqlite3.connect(self.db_path)) as db:
            rows = db.execute(
                "SELECT client_id, info_hash, policy, correlation_id, retained_at, min_seed_ratio, "
                f"min_seed_time_minutes FROM retained_torrents WHERE {clauses}",
                params,
            ).fetchall()
        return {
            (str(client_id), str(info_hash)): {
                "policy": str(policy),
                "retained_at": _parse_datetime(str(retained_at)),
                "correlation_id": str(correlation_id),
                "min_seed_ratio": min_seed_ratio,
                "min_seed_time_minutes": min_seed_time_minutes,
            }
            for client_id, info_hash, policy, correlation_id, retained_at, min_seed_ratio, min_seed_time_minutes in rows
        }
