"""Persistent webhook idempotency and process-wide deletion serialization."""

from __future__ import annotations

import asyncio
import hashlib
import json
import sqlite3
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cleanarr.api.schemas import JellyfinWebhookPayload, ProcessingResultResponse
from cleanarr.domain import MediaDeletionEvent, OverallStatus, ProcessingResult
from cleanarr.infrastructure.database import migrate_database

EventProcessor = Callable[[MediaDeletionEvent], Awaitable[ProcessingResult]]


class DeletionExecutionCoordinator:
    """Serialize mutations and suppress completed duplicate webhook events."""

    def __init__(
        self,
        db_path: Path,
        *,
        retention: timedelta = timedelta(days=7),
    ) -> None:
        self._db_path = db_path
        self._retention = retention
        self.lock = asyncio.Lock()

    async def initialize(self) -> None:
        """Apply the event-ledger migration and remove expired completions."""

        await asyncio.to_thread(migrate_database, self._db_path)
        await asyncio.to_thread(self._purge_expired_sync)

    async def process_webhook(
        self,
        event: MediaDeletionEvent,
        processor: EventProcessor,
    ) -> tuple[ProcessingResult, bool]:
        """Process once under the global safety lock, returning duplicate state."""

        event_key = _event_key(event)
        async with self.lock:
            cached = await asyncio.to_thread(self._load_completed_sync, event_key)
            if cached is not None:
                return cached, True

            await asyncio.to_thread(self._mark_processing_sync, event_key, event)
            try:
                result = await processor(event)
            except asyncio.CancelledError:
                raise
            except Exception:
                await asyncio.to_thread(self._delete_event_sync, event_key)
                raise

            if result.status is not OverallStatus.SUCCESS:
                await asyncio.to_thread(self._delete_event_sync, event_key)
            else:
                await asyncio.to_thread(self._mark_completed_sync, event_key, result)
            return result, False

    def _load_completed_sync(self, event_key: str) -> ProcessingResult | None:
        cutoff = (datetime.now(UTC) - self._retention).isoformat()
        with sqlite3.connect(self._db_path) as connection:
            row = connection.execute(
                "SELECT event_json, result_json FROM processed_webhook_events"
                " WHERE event_key = ? AND completed_at IS NOT NULL AND completed_at >= ?",
                (event_key, cutoff),
            ).fetchone()
        if row is None or row[1] is None:
            return None
        event = JellyfinWebhookPayload.model_validate_json(str(row[0])).to_domain()
        return ProcessingResultResponse.model_validate_json(str(row[1])).to_domain(event)

    def _mark_processing_sync(self, event_key: str, event: MediaDeletionEvent) -> None:
        now = datetime.now(UTC).isoformat()
        cutoff = (datetime.now(UTC) - self._retention).isoformat()
        event_json = JellyfinWebhookPayload.from_domain(event).model_dump_json()
        with sqlite3.connect(self._db_path) as connection:
            connection.execute(
                "DELETE FROM processed_webhook_events WHERE completed_at IS NOT NULL AND completed_at < ?",
                (cutoff,),
            )
            connection.execute(
                "INSERT INTO processed_webhook_events ("
                " event_key, received_at, completed_at, event_json, result_json"
                ") VALUES (?, ?, NULL, ?, NULL)"
                " ON CONFLICT(event_key) DO UPDATE SET"
                " received_at=excluded.received_at, completed_at=NULL,"
                " event_json=excluded.event_json, result_json=NULL",
                (event_key, now, event_json),
            )
            connection.commit()

    def _mark_completed_sync(self, event_key: str, result: ProcessingResult) -> None:
        with sqlite3.connect(self._db_path) as connection:
            connection.execute(
                "UPDATE processed_webhook_events SET completed_at = ?, result_json = ? WHERE event_key = ?",
                (
                    datetime.now(UTC).isoformat(),
                    ProcessingResultResponse.from_domain(result).model_dump_json(),
                    event_key,
                ),
            )
            connection.commit()

    def _delete_event_sync(self, event_key: str) -> None:
        with sqlite3.connect(self._db_path) as connection:
            connection.execute("DELETE FROM processed_webhook_events WHERE event_key = ?", (event_key,))
            connection.commit()

    def _purge_expired_sync(self) -> None:
        cutoff = (datetime.now(UTC) - self._retention).isoformat()
        with sqlite3.connect(self._db_path) as connection:
            connection.execute(
                "DELETE FROM processed_webhook_events WHERE completed_at IS NULL OR completed_at < ?",
                (cutoff,),
            )
            connection.commit()


def _event_key(event: MediaDeletionEvent) -> str:
    """Return a stable digest for one Jellyfin delivery payload."""

    payload = JellyfinWebhookPayload.from_domain(event).model_dump(mode="json")
    canonical = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
    return hashlib.sha256(canonical).hexdigest()
