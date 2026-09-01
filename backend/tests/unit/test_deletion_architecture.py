"""Architecture and persistence-contract evidence for durable deletion flows."""

from __future__ import annotations

import ast
import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from cleanarr.api.schemas import JellyfinWebhookPayload
from cleanarr.application.deletion_events import event_key_for
from cleanarr.application.deletion_models import (
    BatchChildStatus,
    ManualDeleteBatchStatus,
    ManualDeleteJobPhase,
    ManualDeleteJobStatus,
    ManualDeleteRequest,
    ProcessingResultResponse,
)
from cleanarr.application.deletion_persistence import (
    DeletionBatchChildRecord,
    DeletionBatchRecord,
    DeletionJobRecord,
)
from cleanarr.domain import ItemType, MediaDeletionEvent, MediaFingerprint, OverallStatus
from cleanarr.infrastructure.deletion_repository import (
    SQLiteDeletionRepository,
    decode_persisted_event,
    encode_persisted_event,
)


def _event() -> MediaDeletionEvent:
    return MediaDeletionEvent(
        notification_type="ItemDeleted",
        item_type=ItemType.MOVIE,
        item_id="manual:radarr:42",
        name="Кино",
        fingerprint=MediaFingerprint(tmdb_id=42, imdb_id="tt0042", path="/media/кино"),
        occurred_at=datetime(2026, 9, 1, 9, 30, tzinfo=UTC),
    )


def _plan(event: MediaDeletionEvent) -> ProcessingResultResponse:
    return ProcessingResultResponse(
        item_type=event.item_type,
        item_id=event.item_id,
        name=event.name,
        status=OverallStatus.SUCCESS,
        actions=[],
    )


def test_application_and_infrastructure_import_boundaries() -> None:
    root = Path(__file__).resolve().parents[2] / "src" / "cleanarr"
    forbidden_application_prefixes = ("cleanarr.api", "cleanarr.infrastructure")
    forbidden_application_modules = {"fastapi", "sqlite3"}

    for package in ("application", "domain"):
        for source in (root / package).rglob("*.py"):
            imported = _imported_modules(source)
            assert not any(module.startswith(forbidden_application_prefixes) for module in imported), source
            assert not any(module == forbidden for module in imported for forbidden in forbidden_application_modules), (
                source
            )

    for source in (root / "infrastructure").rglob("*.py"):
        assert not any(module.startswith("cleanarr.api") for module in _imported_modules(source)), source


def test_sqlite_deletion_repository_preserves_legacy_rows_and_persisted_codecs(tmp_path: Path) -> None:
    db_path = tmp_path / "cleanarr.db"
    repository = SQLiteDeletionRepository(db_path)
    repository.initialize()
    event = _event()
    plan = _plan(event)

    expected_event_json = JellyfinWebhookPayload.from_domain(event).model_dump_json()
    assert encode_persisted_event(event) == expected_event_json
    assert decode_persisted_event(expected_event_json) == event
    canonical_payload = JellyfinWebhookPayload.from_domain(event).model_dump(mode="json")
    expected_event_key = hashlib.sha256(
        json.dumps(canonical_payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
    ).hexdigest()
    assert event_key_for(event) == expected_event_key

    request = ManualDeleteRequest(item_type=ItemType.MOVIE, radarr_movie_id=42)
    job = DeletionJobRecord(
        id=uuid4(),
        request=request,
        event=event,
        preflight=plan,
        status=ManualDeleteJobStatus.COMPLETED,
        phase=ManualDeleteJobPhase.COMPLETED,
        progress_percent=100,
        message="completed",
        created_at=datetime.now(UTC),
        max_attempts=3,
        item_name=None,
        display_name=None,
        result=plan,
    )
    repository.save_job(job)
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "UPDATE manual_delete_jobs SET request_json = ?, event_json = ?, preflight_json = ?, result_json = ? "
            "WHERE id = ?",
            (
                request.model_dump_json(),
                expected_event_json,
                plan.model_dump_json(),
                plan.model_dump_json(),
                str(job.id),
            ),
        )
        connection.commit()
    loaded_job = repository.load_job(job.id)
    assert loaded_job is not None
    assert loaded_job.event == event
    assert loaded_job.preflight.model_dump_json() == plan.model_dump_json()
    assert loaded_job.display_name == "Кино"

    child = DeletionBatchChildRecord(
        id=uuid4(),
        position=0,
        mutation_identity='{"item_type":"Movie","radarr_movie_id":42}',
        request=request,
        display_name="Кино",
        status=BatchChildStatus.COMPLETED,
        message="completed",
        event=event,
        preflight=plan,
        plan_hash="plan-hash",
        result=plan,
        completed_at=datetime.now(UTC),
    )
    batch = DeletionBatchRecord(
        id=uuid4(),
        canonical_request='{"children":[]}',
        confirmed_batch_hash="batch-hash",
        status=ManualDeleteBatchStatus.COMPLETED,
        message="completed",
        created_at=datetime.now(UTC),
        children=[child],
        completed_at=datetime.now(UTC),
    )
    repository.save_batch(batch)
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "UPDATE manual_delete_batch_children SET request_json = ?, event_json = ?, preflight_json = ?, result_json = ? "
            "WHERE id = ?",
            (
                request.model_dump_json(),
                expected_event_json,
                plan.model_dump_json(),
                plan.model_dump_json(),
                str(child.id),
            ),
        )
        connection.execute(
            "UPDATE manual_delete_batches SET canonical_request_json = ?, confirmed_batch_hash = ? WHERE id = ?",
            ('{"children":[]}', "batch-hash", str(batch.id)),
        )
        connection.commit()
    loaded_batch = repository.load_batch(batch.id)
    assert loaded_batch is not None
    assert loaded_batch.children[0].event == event
    assert loaded_batch.children[0].preflight is not None
    assert loaded_batch.children[0].preflight.model_dump_json() == plan.model_dump_json()

    ledger_job = DeletionJobRecord(
        id=uuid4(),
        request=request,
        event=event,
        preflight=plan,
        status=ManualDeleteJobStatus.QUEUED,
        phase=ManualDeleteJobPhase.QUEUED,
        progress_percent=0,
        message="queued",
        created_at=datetime.now(UTC),
        max_attempts=3,
        idempotency_key=uuid4(),
    )
    assert ledger_job.idempotency_key is not None
    asserted_canonical = '{"confirmed_plan_hash":null,"item_type":"Movie"}'
    assert (
        repository.create_job_with_idempotency(
            ledger_job,
            canonical_request=asserted_canonical,
            original_request=ledger_job.request.model_dump_json(),
        )
        is None
    )
    ledger = repository.lookup_destructive_idempotency(ledger_job.idempotency_key)
    assert ledger is not None
    assert ledger.request_kind == "single"
    assert ledger.canonical_request_json == asserted_canonical
    assert ledger.resource_id == ledger_job.id

    legacy_ledger_key = uuid4()
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "INSERT INTO destructive_idempotency_ledger "
            "(idempotency_key, request_kind, canonical_request_json, original_request_json, resource_id, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                str(legacy_ledger_key),
                "batch",
                '{"children":[]}',
                '{"children":[]}',
                str(batch.id),
                datetime.now(UTC).isoformat(),
            ),
        )
        connection.execute(
            "INSERT INTO processed_webhook_events (event_key, received_at, completed_at, event_json, result_json) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                "event-key",
                datetime.now(UTC).isoformat(),
                datetime.now(UTC).isoformat(),
                expected_event_json,
                plan.model_dump_json(),
            ),
        )
        connection.commit()
    legacy_ledger = repository.lookup_destructive_idempotency(legacy_ledger_key)
    assert legacy_ledger is not None
    assert legacy_ledger.request_kind == "batch"
    assert legacy_ledger.resource_id == batch.id

    cached = repository.load_completed_webhook("event-key", completed_after=datetime(2026, 8, 25, tzinfo=UTC))
    assert cached is not None
    cached_event, cached_result = cached
    assert cached_event == event
    assert cached_result.model_dump_json() == plan.model_dump_json()

    incomplete_key = "incomplete-event-key"
    repository.mark_webhook_processing(incomplete_key, event, purge_before=datetime(2026, 8, 25, tzinfo=UTC))
    repository.purge_webhooks(completed_before=datetime(2026, 9, 2, tzinfo=UTC))
    assert repository.has_incomplete_webhook(incomplete_key)


def _imported_modules(source: Path) -> set[str]:
    tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.add(node.module)
    return imported
