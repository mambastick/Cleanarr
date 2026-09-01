"""SQLite persistence adapter for durable deletion workflows.

The adapter owns SQL, transactions, row decoding, and persisted JSON codecs.
It intentionally does not import FastAPI or :mod:`cleanarr.api`.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from cleanarr.application.deletion_models import (
    BatchChildStatus,
    ManualDeleteBatchStatus,
    ManualDeleteJobPhase,
    ManualDeleteJobStatus,
    ManualDeleteRequest,
    ProcessingResultResponse,
)
from cleanarr.application.deletion_persistence import (
    BatchCreationResult,
    DeletionBatchChildRecord,
    DeletionBatchRecord,
    DeletionJobRecord,
    DestructiveIdempotencyRecord,
    display_name_fallback,
)
from cleanarr.domain import ItemType, MediaDeletionEvent, MediaFingerprint
from cleanarr.infrastructure.database import migrate_database
from cleanarr.redaction import redact_sensitive_text

_logger = logging.getLogger("cleanarr")


class SQLiteDeletionRepository:
    """One cohesive SQLite implementation of all deletion persistence ports."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    def initialize(self) -> None:
        migrate_database(self._db_path)

    def load_jobs(self) -> list[DeletionJobRecord]:
        with sqlite3.connect(self._db_path) as connection:
            rows = connection.execute(
                "SELECT id, request_json, event_json, preflight_json, status, phase, progress_percent,"
                " message, item_name, created_at, started_at, completed_at, next_retry_at,"
                " attempt_count, max_attempts, result_json, error, idempotency_key, display_name"
                " FROM manual_delete_jobs ORDER BY created_at DESC"
            ).fetchall()
        jobs: list[DeletionJobRecord] = []
        for row in rows:
            try:
                jobs.append(_job_from_row(row))
            except Exception:  # noqa: BLE001 - corrupt historic records must not block safe startup
                _logger.exception("Ignoring an invalid persisted manual deletion job %s", row[0])
        return jobs

    def load_job(self, job_id: UUID) -> DeletionJobRecord | None:
        with sqlite3.connect(self._db_path) as connection:
            row = connection.execute(
                "SELECT id, request_json, event_json, preflight_json, status, phase, progress_percent,"
                " message, item_name, created_at, started_at, completed_at, next_retry_at,"
                " attempt_count, max_attempts, result_json, error, idempotency_key, display_name"
                " FROM manual_delete_jobs WHERE id = ?",
                (str(job_id),),
            ).fetchone()
        return _job_from_row(row) if row is not None else None

    def save_job(self, job: DeletionJobRecord) -> None:
        with sqlite3.connect(self._db_path) as connection:
            _save_job_in_connection(connection, job)
            connection.commit()

    def delete_job(self, job_id: UUID) -> None:
        with sqlite3.connect(self._db_path) as connection:
            connection.execute("DELETE FROM manual_delete_jobs WHERE id = ?", (str(job_id),))
            connection.commit()

    def load_batches(self) -> list[DeletionBatchRecord]:
        with sqlite3.connect(self._db_path) as connection:
            connection.execute("PRAGMA foreign_keys = ON")
            parent_rows = connection.execute(
                "SELECT id, canonical_request_json, confirmed_batch_hash, status, message, created_at, "
                "started_at, completed_at, error_code, error_message FROM manual_delete_batches"
            ).fetchall()
            child_rows = connection.execute(
                "SELECT id, batch_id, position, mutation_identity, request_json, event_json, preflight_json, "
                "plan_hash, display_name, status, message, blocked_code, error_code, error_message, result_json, "
                "started_at, completed_at FROM manual_delete_batch_children ORDER BY position"
            ).fetchall()
        batches = {UUID(str(row[0])): _batch_from_row(row) for row in parent_rows}
        for row in child_rows:
            try:
                batches[UUID(str(row[1]))].children.append(_batch_child_from_row(row))
            except Exception:  # noqa: BLE001 - one row cannot invalidate an entire durable queue
                _logger.warning("Ignoring an invalid persisted batch child without logging its contents")
        return list(batches.values())

    def load_batch(self, batch_id: UUID) -> DeletionBatchRecord | None:
        with sqlite3.connect(self._db_path) as connection:
            connection.execute("PRAGMA foreign_keys = ON")
            row = connection.execute(
                "SELECT id, canonical_request_json, confirmed_batch_hash, status, message, created_at, "
                "started_at, completed_at, error_code, error_message FROM manual_delete_batches WHERE id = ?",
                (str(batch_id),),
            ).fetchone()
            if row is None:
                return None
            batch = _batch_from_row(row)
            rows = connection.execute(
                "SELECT id, batch_id, position, mutation_identity, request_json, event_json, preflight_json, "
                "plan_hash, display_name, status, message, blocked_code, error_code, error_message, result_json, "
                "started_at, completed_at FROM manual_delete_batch_children WHERE batch_id = ? ORDER BY position",
                (str(batch_id),),
            ).fetchall()
        batch.children = [_batch_child_from_row(child) for child in rows]
        return batch

    def save_batch(self, batch: DeletionBatchRecord) -> None:
        with sqlite3.connect(self._db_path) as connection:
            connection.execute("PRAGMA foreign_keys = ON")
            _save_batch_in_connection(connection, batch)
            connection.commit()

    def delete_batch(self, batch_id: UUID) -> None:
        with sqlite3.connect(self._db_path) as connection:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("DELETE FROM manual_delete_batches WHERE id = ?", (str(batch_id),))
            connection.commit()

    def lookup_destructive_idempotency(self, key: UUID) -> DestructiveIdempotencyRecord | None:
        with sqlite3.connect(self._db_path) as connection:
            row = connection.execute(
                "SELECT request_kind, canonical_request_json, original_request_json, resource_id "
                "FROM destructive_idempotency_ledger WHERE idempotency_key = ?",
                (str(key),),
            ).fetchone()
        return _ledger_from_row(row) if row is not None else None

    def create_job_with_idempotency(
        self,
        job: DeletionJobRecord,
        *,
        canonical_request: str,
        original_request: str,
    ) -> DestructiveIdempotencyRecord | None:
        """Atomically claim a key and save a visible single job when it is new."""

        assert job.idempotency_key is not None
        with sqlite3.connect(self._db_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT request_kind, canonical_request_json, original_request_json, resource_id "
                "FROM destructive_idempotency_ledger WHERE idempotency_key = ?",
                (str(job.idempotency_key),),
            ).fetchone()
            if row is not None:
                return _ledger_from_row(row)
            _save_job_in_connection(connection, job)
            connection.execute(
                "INSERT INTO destructive_idempotency_ledger ("
                "idempotency_key, request_kind, canonical_request_json, original_request_json, resource_id, created_at"
                ") VALUES (?, 'single', ?, ?, ?, ?)",
                (
                    str(job.idempotency_key),
                    canonical_request,
                    original_request,
                    str(job.id),
                    job.created_at.isoformat(),
                ),
            )
            connection.commit()
        return None

    def create_batch_with_idempotency(
        self,
        batch: DeletionBatchRecord,
        *,
        idempotency_key: UUID,
        original_request: str,
        max_pending_parents: int,
    ) -> BatchCreationResult:
        """Atomically claim a batch key while enforcing the durable queue bound."""

        with sqlite3.connect(self._db_path) as connection:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT request_kind, canonical_request_json, original_request_json, resource_id "
                "FROM destructive_idempotency_ledger WHERE idempotency_key = ?",
                (str(idempotency_key),),
            ).fetchone()
            if row is not None:
                return BatchCreationResult(existing=_ledger_from_row(row))
            pending_count = int(
                connection.execute(
                    "SELECT COUNT(*) FROM manual_delete_batches WHERE status IN ('queued', 'running')"
                ).fetchone()[0]
            )
            if pending_count >= max_pending_parents:
                connection.rollback()
                return BatchCreationResult(queue_full=True)
            _save_batch_in_connection(connection, batch)
            connection.execute(
                "INSERT INTO destructive_idempotency_ledger ("
                "idempotency_key, request_kind, canonical_request_json, original_request_json, resource_id, created_at"
                ") VALUES (?, 'batch', ?, ?, ?, ?)",
                (
                    str(idempotency_key),
                    batch.canonical_request,
                    original_request,
                    str(batch.id),
                    batch.created_at.isoformat(),
                ),
            )
            connection.commit()
        return BatchCreationResult()

    def load_completed_webhook(
        self, event_key: str, *, completed_after: datetime
    ) -> tuple[MediaDeletionEvent, ProcessingResultResponse] | None:
        with sqlite3.connect(self._db_path) as connection:
            row = connection.execute(
                "SELECT event_json, result_json FROM processed_webhook_events"
                " WHERE event_key = ? AND completed_at IS NOT NULL AND completed_at >= ?",
                (event_key, completed_after.isoformat()),
            ).fetchone()
        if row is None or row[1] is None:
            return None
        return decode_persisted_event(str(row[0])), ProcessingResultResponse.model_validate_json(str(row[1]))

    def has_incomplete_webhook(self, event_key: str) -> bool:
        with sqlite3.connect(self._db_path) as connection:
            row = connection.execute(
                "SELECT 1 FROM processed_webhook_events WHERE event_key = ? AND completed_at IS NULL",
                (event_key,),
            ).fetchone()
        return row is not None

    def mark_webhook_processing(self, event_key: str, event: MediaDeletionEvent, *, purge_before: datetime) -> None:
        now = datetime.now(UTC).isoformat()
        with sqlite3.connect(self._db_path) as connection:
            connection.execute(
                "DELETE FROM processed_webhook_events WHERE completed_at IS NOT NULL AND completed_at < ?",
                (purge_before.isoformat(),),
            )
            connection.execute(
                "INSERT INTO processed_webhook_events ("
                " event_key, received_at, completed_at, event_json, result_json"
                ") VALUES (?, ?, NULL, ?, NULL)"
                " ON CONFLICT(event_key) DO UPDATE SET"
                " received_at=excluded.received_at, completed_at=NULL,"
                " event_json=excluded.event_json, result_json=NULL",
                (event_key, now, encode_persisted_event(event)),
            )
            connection.commit()

    def mark_webhook_completed(self, event_key: str, result: ProcessingResultResponse) -> None:
        with sqlite3.connect(self._db_path) as connection:
            connection.execute(
                "UPDATE processed_webhook_events SET completed_at = ?, result_json = ? WHERE event_key = ?",
                (datetime.now(UTC).isoformat(), result.model_dump_json(), event_key),
            )
            connection.commit()

    def delete_webhook(self, event_key: str) -> None:
        with sqlite3.connect(self._db_path) as connection:
            connection.execute("DELETE FROM processed_webhook_events WHERE event_key = ?", (event_key,))
            connection.commit()

    def purge_webhooks(self, *, completed_before: datetime) -> None:
        with sqlite3.connect(self._db_path) as connection:
            connection.execute(
                "DELETE FROM processed_webhook_events WHERE completed_at IS NOT NULL AND completed_at < ?",
                (completed_before.isoformat(),),
            )
            connection.commit()


def encode_persisted_event(event: MediaDeletionEvent) -> str:
    """Encode an event with the established webhook JSON key order and shape."""

    return json.dumps(
        {
            "notification_type": event.notification_type,
            "item_type": event.item_type.value,
            "item_id": event.item_id,
            "name": event.name,
            "path": event.fingerprint.path,
            "tmdb_id": event.fingerprint.tmdb_id,
            "tvdb_id": event.fingerprint.tvdb_id,
            "imdb_id": event.fingerprint.imdb_id,
            "series_name": event.series_name,
            "series_id": event.series_id,
            "season_number": event.season_number,
            "episode_number": event.episode_number,
            "episode_end_number": event.episode_end_number,
            "occurred_at": _json_datetime(event.occurred_at),
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )


def decode_persisted_event(value: str) -> MediaDeletionEvent:
    """Decode a legacy-compatible persisted event without relying on API schemas."""

    payload = json.loads(value)
    occurred_at = payload.get("occurred_at")
    return MediaDeletionEvent(
        notification_type=str(payload["notification_type"]),
        item_type=ItemType(str(payload["item_type"])),
        item_id=str(payload["item_id"]),
        name=str(payload["name"]),
        fingerprint=MediaFingerprint(
            tmdb_id=payload.get("tmdb_id"),
            tvdb_id=payload.get("tvdb_id"),
            imdb_id=payload.get("imdb_id"),
            path=payload.get("path"),
        ),
        series_name=payload.get("series_name"),
        series_id=payload.get("series_id"),
        season_number=payload.get("season_number"),
        episode_number=payload.get("episode_number"),
        episode_end_number=payload.get("episode_end_number"),
        occurred_at=datetime.fromisoformat(occurred_at) if occurred_at is not None else None,
    )


def _json_datetime(value: datetime | None) -> str | None:
    """Match the established Pydantic webhook JSON encoding for UTC timestamps."""

    if value is None:
        return None
    encoded = value.isoformat()
    return f"{encoded[:-6]}Z" if encoded.endswith("+00:00") else encoded


def _save_job_in_connection(connection: sqlite3.Connection, job: DeletionJobRecord) -> None:
    connection.execute(
        "INSERT INTO manual_delete_jobs ("
        " id, request_json, event_json, preflight_json, status, phase, progress_percent,"
        " message, item_name, created_at, started_at, completed_at, next_retry_at,"
        " attempt_count, max_attempts, result_json, error, idempotency_key, display_name"
        ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
        " ON CONFLICT(id) DO UPDATE SET"
        " request_json=excluded.request_json, event_json=excluded.event_json,"
        " preflight_json=excluded.preflight_json, status=excluded.status, phase=excluded.phase,"
        " progress_percent=excluded.progress_percent, message=excluded.message,"
        " item_name=excluded.item_name, created_at=excluded.created_at,"
        " started_at=excluded.started_at, completed_at=excluded.completed_at,"
        " next_retry_at=excluded.next_retry_at, attempt_count=excluded.attempt_count,"
        " max_attempts=excluded.max_attempts, result_json=excluded.result_json, error=excluded.error,"
        " idempotency_key=excluded.idempotency_key, display_name=excluded.display_name",
        (
            str(job.id),
            job.request.model_dump_json(),
            encode_persisted_event(job.event),
            job.preflight.model_dump_json(),
            job.status.value,
            job.phase.value,
            job.progress_percent,
            job.message,
            job.item_name,
            job.created_at.isoformat(),
            _datetime_to_text(job.started_at),
            _datetime_to_text(job.completed_at),
            _datetime_to_text(job.next_retry_at),
            job.attempt_count,
            job.max_attempts,
            job.result.model_dump_json() if job.result is not None else None,
            job.error,
            str(job.idempotency_key) if job.idempotency_key is not None else None,
            job.display_name,
        ),
    )


def _job_from_row(row: tuple[object, ...]) -> DeletionJobRecord:
    event = decode_persisted_event(str(row[2]))
    item_name = str(row[8]) if row[8] is not None else None
    return DeletionJobRecord(
        id=UUID(str(row[0])),
        request=ManualDeleteRequest.model_validate_json(str(row[1])),
        event=event,
        preflight=ProcessingResultResponse.model_validate_json(str(row[3])),
        status=ManualDeleteJobStatus(str(row[4])),
        phase=ManualDeleteJobPhase(str(row[5])),
        progress_percent=int(str(row[6])),
        message=redact_sensitive_text(str(row[7])),
        item_name=item_name,
        idempotency_key=UUID(str(row[17])) if row[17] is not None else None,
        display_name=(
            str(row[18])
            if row[18] is not None
            else display_name_fallback(item_name=item_name, result_name=event.name, item_type=event.item_type)
        ),
        created_at=datetime.fromisoformat(str(row[9])),
        started_at=_datetime_from_value(row[10]),
        completed_at=_datetime_from_value(row[11]),
        next_retry_at=_datetime_from_value(row[12]),
        attempt_count=int(str(row[13])),
        max_attempts=int(str(row[14])),
        result=ProcessingResultResponse.model_validate_json(str(row[15])) if row[15] is not None else None,
        error=redact_sensitive_text(str(row[16])) if row[16] is not None else None,
    )


def _save_batch_in_connection(connection: sqlite3.Connection, batch: DeletionBatchRecord) -> None:
    connection.execute(
        "INSERT INTO manual_delete_batches ("
        "id, canonical_request_json, confirmed_batch_hash, status, message, "
        "created_at, started_at, completed_at, error_code, error_message"
        ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(id) DO UPDATE SET "
        "status=excluded.status, message=excluded.message, "
        "started_at=excluded.started_at, completed_at=excluded.completed_at, "
        "error_code=excluded.error_code, error_message=excluded.error_message",
        (
            str(batch.id),
            batch.canonical_request,
            batch.confirmed_batch_hash,
            batch.status.value,
            batch.message,
            batch.created_at.isoformat(),
            _datetime_to_text(batch.started_at),
            _datetime_to_text(batch.completed_at),
            batch.error_code,
            batch.error_message,
        ),
    )
    for child in batch.children:
        connection.execute(
            "INSERT INTO manual_delete_batch_children ("
            "id, batch_id, position, mutation_identity, request_json, event_json, "
            "preflight_json, plan_hash, display_name, status, message, blocked_code, "
            "error_code, error_message, result_json, started_at, completed_at"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET "
            "status=excluded.status, message=excluded.message, "
            "blocked_code=excluded.blocked_code, error_code=excluded.error_code, "
            "error_message=excluded.error_message, result_json=excluded.result_json, "
            "started_at=excluded.started_at, completed_at=excluded.completed_at",
            (
                str(child.id),
                str(batch.id),
                child.position,
                child.mutation_identity,
                child.request.model_dump_json(),
                encode_persisted_event(child.event) if child.event is not None else None,
                child.preflight.model_dump_json() if child.preflight is not None else None,
                child.plan_hash,
                child.display_name,
                child.status.value,
                child.message,
                child.blocked_code,
                child.error_code,
                child.error_message,
                child.result.model_dump_json() if child.result is not None else None,
                _datetime_to_text(child.started_at),
                _datetime_to_text(child.completed_at),
            ),
        )


def _batch_from_row(row: tuple[object, ...]) -> DeletionBatchRecord:
    return DeletionBatchRecord(
        id=UUID(str(row[0])),
        canonical_request=str(row[1]),
        confirmed_batch_hash=str(row[2]),
        status=ManualDeleteBatchStatus(str(row[3])),
        message=redact_sensitive_text(str(row[4])),
        created_at=datetime.fromisoformat(str(row[5])),
        started_at=_datetime_from_value(row[6]),
        completed_at=_datetime_from_value(row[7]),
        error_code=str(row[8]) if row[8] is not None else None,
        error_message=redact_sensitive_text(str(row[9])) if row[9] is not None else None,
    )


def _batch_child_from_row(row: tuple[object, ...]) -> DeletionBatchChildRecord:
    return DeletionBatchChildRecord(
        id=UUID(str(row[0])),
        position=int(str(row[2])),
        mutation_identity=str(row[3]),
        request=ManualDeleteRequest.model_validate_json(str(row[4])),
        event=decode_persisted_event(str(row[5])) if row[5] is not None else None,
        preflight=ProcessingResultResponse.model_validate_json(str(row[6])) if row[6] is not None else None,
        plan_hash=str(row[7]) if row[7] is not None else None,
        display_name=str(row[8]),
        status=BatchChildStatus(str(row[9])),
        message=redact_sensitive_text(str(row[10])),
        blocked_code=str(row[11]) if row[11] is not None else None,
        error_code=str(row[12]) if row[12] is not None else None,
        error_message=redact_sensitive_text(str(row[13])) if row[13] is not None else None,
        result=ProcessingResultResponse.model_validate_json(str(row[14])) if row[14] is not None else None,
        started_at=_datetime_from_value(row[15]),
        completed_at=_datetime_from_value(row[16]),
    )


def _ledger_from_row(row: tuple[object, ...]) -> DestructiveIdempotencyRecord:
    return DestructiveIdempotencyRecord(
        request_kind=str(row[0]),
        canonical_request_json=str(row[1]),
        original_request_json=str(row[2]),
        resource_id=UUID(str(row[3])),
    )


def _datetime_to_text(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _datetime_from_value(value: object) -> datetime | None:
    return datetime.fromisoformat(str(value)) if value is not None else None
