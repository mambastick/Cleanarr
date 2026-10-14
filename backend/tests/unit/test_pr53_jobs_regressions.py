"""Focused regressions for durable job error codes and hash-scoped ownership."""

from __future__ import annotations

import asyncio
import logging
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from cleanarr.application.deletion_batches import ManualDeletionBatchService
from cleanarr.application.deletion_jobs import (
    DeletionPreflightError,
    ManualDeletionJobService,
    _execution_result_block_code,
    _OrderedJobWriter,
    _preflight_block_code,
    _preflight_failure_code,
    plan_hash,
    validate_plan_confirmation,
)
from cleanarr.application.deletion_models import (
    ActionResultResponse,
    BatchChildStatus,
    ManualDeleteBatchSubmitRequest,
    ManualDeleteJobPhase,
    ManualDeleteJobStatus,
    ManualDeleteRequest,
    ProcessingResultResponse,
)
from cleanarr.application.deletion_persistence import DeletionJobRecord
from cleanarr.application.results import ActionCollector
from cleanarr.application.strategies import MovieDeletionStrategy
from cleanarr.domain import (
    ActionStatus,
    DownloaderRemovalResult,
    FailureReason,
    ItemType,
    MediaDeletionEvent,
    MediaFingerprint,
    OverallStatus,
    RadarrHistoryRecord,
)
from cleanarr.infrastructure.database import LATEST_SCHEMA_VERSION, MIGRATIONS, migrate_database
from cleanarr.infrastructure.deletion_repository import SQLiteDeletionRepository, encode_persisted_event


def _event() -> MediaDeletionEvent:
    return MediaDeletionEvent(
        notification_type="ItemDeleted",
        item_type=ItemType.MOVIE,
        item_id="manual:radarr:1",
        name="Movie",
        fingerprint=MediaFingerprint(tmdb_id=42, path="/media/movie"),
    )


def _plan(
    event: MediaDeletionEvent,
    *,
    failed: bool = False,
    reason: FailureReason = FailureReason.DOWNSTREAM_ERROR,
    action: str = "verify_download_ownership",
) -> ProcessingResultResponse:
    return ProcessingResultResponse(
        item_type=event.item_type,
        item_id=event.item_id,
        name=event.name,
        status=OverallStatus.PARTIAL_FAILURE if failed else OverallStatus.SUCCESS,
        actions=(
            [
                ActionResultResponse(
                    system="radarr",
                    action=action,
                    status=ActionStatus.FAILED,
                    message="ownership could not be verified",
                    reason=reason,
                    details={},
                )
            ]
            if failed
            else []
        ),
    )


def _job(event: MediaDeletionEvent, *, error_code: str | None = None) -> DeletionJobRecord:
    return DeletionJobRecord(
        id=uuid4(),
        request=ManualDeleteRequest(item_type=ItemType.MOVIE, radarr_movie_id=1),
        event=event,
        preflight=_plan(event),
        status=ManualDeleteJobStatus.FAILED,
        phase=ManualDeleteJobPhase.FAILED,
        progress_percent=100,
        message="failed",
        created_at=datetime.now(UTC),
        max_attempts=1,
        error="The preflight failed.",
        error_code=error_code,
    )


@pytest.mark.asyncio
async def test_preflight_failure_is_retry_terminal_error_code_and_persisted(tmp_path: Path) -> None:
    event = _event()
    calls = 0
    assert _preflight_failure_code(_plan(event, failed=True)) == "preflight_failed"

    async def resolver(payload: ManualDeleteRequest) -> MediaDeletionEvent:
        return event

    async def previewer(payload: ManualDeleteRequest, resolved: MediaDeletionEvent) -> ProcessingResultResponse:
        nonlocal calls
        calls += 1
        # preview(), submit(), then the worker refreshes preflight; only the last
        # call represents a read failure after a durable job was accepted.
        return _plan(resolved, failed=calls == 3, reason=FailureReason.DOWNSTREAM_ERROR)

    runner_called = False

    async def runner(payload, resolved, report):  # type: ignore[no-untyped-def]
        nonlocal runner_called
        runner_called = True
        return _plan(resolved)

    repository = SQLiteDeletionRepository(tmp_path / "jobs.db")
    service = ManualDeletionJobService(
        resolver,
        previewer,
        runner,
        repository=repository,
        max_attempts=1,
        retry_delays_seconds=(0,),
    )
    try:
        preview = await service.preview(ManualDeleteRequest(item_type=ItemType.MOVIE, radarr_movie_id=1))
        request = ManualDeleteRequest(
            item_type=ItemType.MOVIE,
            radarr_movie_id=1,
            confirmed_plan_hash=preview.plan_hash,
            idempotency_key=uuid4(),
        )
        queued = await service.submit(request)
        for _ in range(200):
            current = service.get(queued.id)
            if current.status is ManualDeleteJobStatus.FAILED:
                break
            await asyncio.sleep(0.01)
        current = service.get(queued.id)
        assert current.status is ManualDeleteJobStatus.FAILED
        assert current.error_code == "preflight_failed"
        assert current.error is not None
        assert not runner_called
        persisted = repository.load_job(queued.id)
        assert persisted is not None
        assert persisted.error_code == "preflight_failed"
    finally:
        await service.stop()


@pytest.mark.asyncio
async def test_preflight_failure_retries_then_clears_code_after_one_mutation(tmp_path: Path) -> None:
    event = _event()
    preview_calls = 0
    runner_calls = 0

    async def resolver(payload: ManualDeleteRequest) -> MediaDeletionEvent:
        return event

    async def previewer(payload: ManualDeleteRequest, resolved: MediaDeletionEvent) -> ProcessingResultResponse:
        nonlocal preview_calls
        preview_calls += 1
        # preview(), submit(), and attempt 1 are followed by a clean attempt 2.
        return _plan(resolved, failed=preview_calls == 3, reason=FailureReason.DOWNSTREAM_ERROR)

    async def runner(payload, resolved, report):  # type: ignore[no-untyped-def]
        nonlocal runner_calls
        runner_calls += 1
        return _plan(resolved)

    repository = SQLiteDeletionRepository(tmp_path / "retry.db")
    service = ManualDeletionJobService(
        resolver,
        previewer,
        runner,
        repository=repository,
        max_attempts=2,
        retry_delays_seconds=(0,),
    )
    try:
        preview = await service.preview(ManualDeleteRequest(item_type=ItemType.MOVIE, radarr_movie_id=1))
        request = ManualDeleteRequest(
            item_type=ItemType.MOVIE,
            radarr_movie_id=1,
            confirmed_plan_hash=preview.plan_hash,
            idempotency_key=uuid4(),
        )
        queued = await service.submit(request)
        for _ in range(200):
            if service.get(queued.id).status is ManualDeleteJobStatus.COMPLETED:
                break
            await asyncio.sleep(0.01)
        result = service.get(queued.id)
        assert result.status is ManualDeleteJobStatus.COMPLETED
        assert result.attempt_count == 2
        assert runner_calls == 1
        assert result.error_code is None
        assert repository.load_job(queued.id).error_code is None  # type: ignore[union-attr]
    finally:
        await service.stop()


@pytest.mark.asyncio
async def test_safety_preflight_is_terminal_without_plan_changed_or_mutation(tmp_path: Path) -> None:
    event = _event()
    preview_calls = 0
    runner_calls = 0

    async def resolver(payload: ManualDeleteRequest) -> MediaDeletionEvent:
        return event

    async def previewer(payload: ManualDeleteRequest, resolved: MediaDeletionEvent) -> ProcessingResultResponse:
        nonlocal preview_calls
        preview_calls += 1
        if preview_calls != 3:
            return _plan(resolved)
        return _plan(resolved).model_copy(
            update={
                "status": OverallStatus.PARTIAL_FAILURE,
                "actions": (
                    ActionResultResponse(
                        system="radarr",
                        action="verify_download_ownership",
                        status=ActionStatus.SKIPPED,
                        message="ownership could not be verified",
                        reason=FailureReason.OWNERSHIP_UNVERIFIABLE,
                        details={},
                    ),
                ),
            }
        )

    async def runner(payload, resolved, report):  # type: ignore[no-untyped-def]
        nonlocal runner_calls
        runner_calls += 1
        return _plan(resolved)

    repository = SQLiteDeletionRepository(tmp_path / "safety.db")
    service = ManualDeletionJobService(
        resolver,
        previewer,
        runner,
        repository=repository,
        max_attempts=2,
        retry_delays_seconds=(0,),
    )
    try:
        preview = await service.preview(ManualDeleteRequest(item_type=ItemType.MOVIE, radarr_movie_id=1))
        queued = await service.submit(
            ManualDeleteRequest(
                item_type=ItemType.MOVIE,
                radarr_movie_id=1,
                confirmed_plan_hash=preview.plan_hash,
                idempotency_key=uuid4(),
            )
        )
        for _ in range(200):
            if service.get(queued.id).status is ManualDeleteJobStatus.FAILED:
                break
            await asyncio.sleep(0.01)
        result = service.get(queued.id)
        assert result.status is ManualDeleteJobStatus.FAILED
        assert result.attempt_count == 1
        assert result.error_code == "unsafe_plan"
        assert runner_calls == 0
        persisted = repository.load_job(queued.id)
        assert persisted is not None
        assert persisted.error_code == "unsafe_plan"
    finally:
        await service.stop()


def test_mixed_transient_and_safety_preflight_prefers_unsafe_plan() -> None:
    event = _event()
    transient = _plan(event, failed=True, reason=FailureReason.DOWNSTREAM_ERROR).actions[0]
    safety = ActionResultResponse(
        system="radarr",
        action="verify_source",
        status=ActionStatus.FAILED,
        message="ownership could not be verified",
        reason=FailureReason.SHARED_PATH,
        details={},
    )
    plan = _plan(event, failed=True).model_copy(
        update={"actions": (transient, safety)},
    )
    assert _preflight_failure_code(plan) == "unsafe_plan"
    deleted = ActionResultResponse(
        system="downloader",
        action="delete_torrent",
        status=ActionStatus.DELETED,
        message="already mutated",
        reason=None,
        details={},
    )
    assert _preflight_block_code(_plan(event).model_copy(update={"actions": (deleted,)})) == "unsafe_plan"
    assert _execution_result_block_code(_plan(event).model_copy(update={"actions": (deleted,)})) is None
    assert _execution_result_block_code(_plan(event, failed=True)) == "execution_failed"
    assert _execution_result_block_code(_plan(event, failed=True, action="delete_hash")) == "unsafe_result"
    mutated_plan = _plan(event).model_copy(update={"actions": [deleted]})
    with pytest.raises(DeletionPreflightError) as error:
        validate_plan_confirmation(
            ManualDeleteRequest(
                item_type=ItemType.MOVIE, radarr_movie_id=1, confirmed_plan_hash=plan_hash(mutated_plan)
            ),
            mutated_plan,
        )
    assert error.value.code == "unsafe_plan"
    assert (
        _execution_result_block_code(
            _plan(event).model_copy(update={"actions": (safety.model_copy(update={"status": ActionStatus.SKIPPED}),)})
        )
        == "unsafe_result"
    )
    skipped_safety = safety.model_copy(update={"status": ActionStatus.SKIPPED})
    assert (
        _preflight_failure_code(_plan(event).model_copy(update={"actions": (transient, skipped_safety)}))
        == "unsafe_plan"
    )


@pytest.mark.parametrize(
    "reason",
    [FailureReason.DOWNSTREAM_ERROR, FailureReason.AUTHENTICATION_FAILED],
)
def test_read_preflight_transient_reasons_are_retryable(reason: FailureReason) -> None:
    assert _preflight_failure_code(_plan(_event(), failed=True, reason=reason)) == "preflight_failed"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failed_action,expected_code", [("record_retention", "execution_failed"), ("delete_hash", "unsafe_plan")]
)
async def test_durable_or_mutation_failure_is_terminal_and_not_retried(
    tmp_path: Path, failed_action: str, expected_code: str
) -> None:
    event = _event()
    runner_calls = 0

    async def resolver(payload: ManualDeleteRequest) -> MediaDeletionEvent:
        return event

    async def previewer(payload: ManualDeleteRequest, resolved: MediaDeletionEvent) -> ProcessingResultResponse:
        return _plan(resolved)

    async def runner(payload, resolved, report):  # type: ignore[no-untyped-def]
        nonlocal runner_calls
        runner_calls += 1
        return ProcessingResultResponse(
            item_type=resolved.item_type,
            item_id=resolved.item_id,
            name=resolved.name,
            status=OverallStatus.PARTIAL_FAILURE,
            actions=(
                ActionResultResponse(
                    system="cleanarr",
                    action=failed_action,
                    status=ActionStatus.FAILED,
                    message="retention write failed",
                    reason=FailureReason.DOWNSTREAM_ERROR,
                    details={"error": "retention write failed"},
                ),
            ),
        )

    repository = SQLiteDeletionRepository(tmp_path / "retention.db")
    service = ManualDeletionJobService(
        resolver,
        previewer,
        runner,
        repository=repository,
        max_attempts=2,
        retry_delays_seconds=(0,),
    )
    try:
        preview = await service.preview(ManualDeleteRequest(item_type=ItemType.MOVIE, radarr_movie_id=1))
        queued = await service.submit(
            ManualDeleteRequest(
                item_type=ItemType.MOVIE,
                radarr_movie_id=1,
                confirmed_plan_hash=preview.plan_hash,
                idempotency_key=uuid4(),
            )
        )
        for _ in range(200):
            if service.get(queued.id).status is ManualDeleteJobStatus.FAILED:
                break
            await asyncio.sleep(0.01)
        result = service.get(queued.id)
        assert result.status is ManualDeleteJobStatus.FAILED
        assert result.attempt_count == 1
        assert result.error_code == expected_code
        assert runner_calls == 1
    finally:
        await service.stop()


@pytest.mark.asyncio
async def test_record_retention_failure_after_read_failure_is_still_terminal(tmp_path: Path) -> None:
    event = _event()
    runner_calls = 0

    async def resolver(payload: ManualDeleteRequest) -> MediaDeletionEvent:
        return event

    async def previewer(payload: ManualDeleteRequest, resolved: MediaDeletionEvent) -> ProcessingResultResponse:
        return _plan(resolved)

    async def runner(payload, resolved, report):  # type: ignore[no-untyped-def]
        nonlocal runner_calls
        runner_calls += 1
        return ProcessingResultResponse(
            item_type=resolved.item_type,
            item_id=resolved.item_id,
            name=resolved.name,
            status=OverallStatus.PARTIAL_FAILURE,
            actions=(
                ActionResultResponse(
                    system="radarr",
                    action="verify_download_ownership",
                    status=ActionStatus.FAILED,
                    message="ownership lookup failed",
                    reason=FailureReason.DOWNSTREAM_ERROR,
                    details={"error": "ownership lookup failed"},
                ),
                ActionResultResponse(
                    system="cleanarr",
                    action="record_retention",
                    status=ActionStatus.FAILED,
                    message="retention write failed",
                    reason=FailureReason.DOWNSTREAM_ERROR,
                    details={"error": "retention write failed"},
                ),
            ),
        )

    service = ManualDeletionJobService(
        resolver,
        previewer,
        runner,
        repository=SQLiteDeletionRepository(tmp_path / "retention-order.db"),
        max_attempts=2,
        retry_delays_seconds=(0,),
    )
    try:
        preview = await service.preview(ManualDeleteRequest(item_type=ItemType.MOVIE, radarr_movie_id=1))
        queued = await service.submit(
            ManualDeleteRequest(
                item_type=ItemType.MOVIE,
                radarr_movie_id=1,
                confirmed_plan_hash=preview.plan_hash,
                idempotency_key=uuid4(),
            )
        )
        for _ in range(200):
            if service.get(queued.id).status is ManualDeleteJobStatus.FAILED:
                break
            await asyncio.sleep(0.01)
        result = service.get(queued.id)
        assert result.status is ManualDeleteJobStatus.FAILED
        assert result.attempt_count == 1
        assert result.error_code == "execution_failed"
        assert runner_calls == 1
    finally:
        await service.stop()


@pytest.mark.asyncio
async def test_batch_failed_safety_plan_is_persisted_as_unsafe_plan(tmp_path: Path) -> None:
    event = _event()

    async def resolver(payload: ManualDeleteRequest) -> MediaDeletionEvent:
        return event

    async def previewer(payload: ManualDeleteRequest, resolved: MediaDeletionEvent) -> ProcessingResultResponse:
        return _plan(resolved, failed=True, reason=FailureReason.OWNERSHIP_UNVERIFIABLE)

    async def runner(payload, resolved, report):  # type: ignore[no-untyped-def]
        raise AssertionError("a failed preflight must never reach the runner")

    service = ManualDeletionBatchService(
        resolver,
        previewer,
        runner,
        repository=SQLiteDeletionRepository(tmp_path / "batch.db"),
        execution_lock=asyncio.Lock(),
    )
    request = ManualDeleteRequest(item_type=ItemType.MOVIE, radarr_movie_id=1)
    try:
        preview = await service.preview([request])
        assert preview.children[0].blocked_code == "unsafe_plan"
        submitted = await service.submit(
            ManualDeleteBatchSubmitRequest(
                children=[request],
                idempotency_key=uuid4(),
                confirmed_batch_hash=preview.batch_hash,
                confirmed_item_count=1,
            )
        )
        assert submitted.children[0].blocked_code == "unsafe_plan"
        assert submitted.children[0].status is BatchChildStatus.BLOCKED
    finally:
        await service.stop()


def test_populated_schema7_upgrade_adds_error_code_and_backup_restores(tmp_path: Path) -> None:
    db_path = tmp_path / "schema7.db"
    backup_path = tmp_path / "schema7.backup.db"
    restored_path = tmp_path / "schema7.restored.db"
    event = _event()
    legacy = _job(event)
    with sqlite3.connect(db_path) as connection:
        for migration in MIGRATIONS[:7]:
            for statement in migration.statements:
                connection.execute(statement)
        connection.execute("PRAGMA user_version = 7")
        connection.execute("INSERT INTO config(id, config_json) VALUES(1, ?)", ('{"general":{"dry_run":true}}',))
        connection.execute(
            "INSERT INTO manual_delete_jobs VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                str(legacy.id),
                legacy.request.model_dump_json(),
                encode_persisted_event(legacy.event),
                legacy.preflight.model_dump_json(),
                legacy.status.value,
                legacy.phase.value,
                legacy.progress_percent,
                legacy.message,
                legacy.item_name,
                legacy.created_at.isoformat(),
                None,
                None,
                None,
                legacy.attempt_count,
                legacy.max_attempts,
                None,
                legacy.error,
                None,
                legacy.display_name,
            ),
        )
        connection.commit()
    with sqlite3.connect(db_path) as source, sqlite3.connect(backup_path) as backup:
        source.backup(backup)

    assert migrate_database(db_path) == LATEST_SCHEMA_VERSION
    assert migrate_database(db_path) == LATEST_SCHEMA_VERSION
    with sqlite3.connect(db_path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone() == (8,)
        assert connection.execute("SELECT error_code FROM manual_delete_jobs").fetchone() == (None,)
        assert connection.execute("SELECT config_json FROM config").fetchone() == ('{"general":{"dry_run":true}}',)

    with sqlite3.connect(backup_path) as backup, sqlite3.connect(restored_path) as restored:
        backup.backup(restored)
    with sqlite3.connect(restored_path) as restored:
        assert restored.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert restored.execute("PRAGMA user_version").fetchone() == (7,)
        assert "error_code" not in {row[1] for row in restored.execute("PRAGMA table_info(manual_delete_jobs)")}


def test_job_error_code_round_trips_and_legacy_null_is_supported(tmp_path: Path) -> None:
    repository = SQLiteDeletionRepository(tmp_path / "jobs.db")
    repository.initialize()
    assert LATEST_SCHEMA_VERSION == 8
    event = _event()
    failed = _job(event, error_code="plan_changed")
    repository.save_job(failed)
    loaded = repository.load_job(failed.id)
    assert loaded is not None
    assert loaded.error_code == "plan_changed"

    legacy = _job(event)
    repository.save_job(legacy)
    assert repository.load_job(legacy.id).error_code is None  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_ordered_writer_preserves_first_failure_for_later_submits() -> None:
    calls = 0

    def save(snapshot: object) -> None:
        nonlocal calls
        calls += 1
        raise RuntimeError("sqlite write failed")

    repository = SimpleNamespace(save_job=save)
    writer = _OrderedJobWriter(repository)  # type: ignore[arg-type]
    first = SimpleNamespace(phase=ManualDeleteJobPhase.LOCATING)
    writer.submit(first)
    with pytest.raises(RuntimeError, match="sqlite write failed"):
        await writer.flush()
    writer.submit(SimpleNamespace(phase=ManualDeleteJobPhase.CLEANING))
    with pytest.raises(RuntimeError, match="sqlite write failed"):
        await writer.flush()
    assert calls == 1


class _HashScopedRadarr:
    def __init__(self, records: dict[str, list[RadarrHistoryRecord]]) -> None:
        self.records = records
        self.calls: list[str] = []

    async def list_download_history(self, download_id: str) -> list[RadarrHistoryRecord]:
        self.calls.append(download_id)
        await asyncio.sleep(0)
        return self.records[download_id]


class _UnknownExistenceDownloader:
    async def delete_hashes(self, hashes, *, delete_files, dry_run):  # type: ignore[no-untyped-def]
        return [DownloaderRemovalResult(hash_value=hashes[0], existed=None)]


@pytest.mark.asyncio
async def test_movie_ownership_checks_each_hash_once_and_ignores_target_history() -> None:
    event = _event()
    radarr = _HashScopedRadarr(
        {
            "AAA": [RadarrHistoryRecord(1, 1, " grabbed", "aaa", "/movie.mkv")],
            "BBB": [RadarrHistoryRecord(2, 1, "grabbed", "BBB", "/movie2.mkv")],
        }
    )
    strategy = MovieDeletionStrategy(
        radarr=radarr,  # type: ignore[arg-type]
        dry_run=True,
        logger=logging.getLogger("test"),
        seerr=None,  # type: ignore[arg-type]
        downloader=None,  # type: ignore[arg-type]
    )
    collector = ActionCollector(event)

    assert await strategy._movie_hashes_exclusive(collector, 1, [SimpleNamespace()] * 1001, {"aaa", "BBB"})
    assert radarr.calls == ["AAA", "BBB"]
    assert collector.build().actions == ()


@pytest.mark.asyncio
async def test_movie_ownership_blocks_hash_referenced_by_another_movie() -> None:
    event = _event()
    radarr = _HashScopedRadarr(
        {
            "AAA": [
                RadarrHistoryRecord(1, 1, "grabbed", "aaa", "/movie.mkv"),
                RadarrHistoryRecord(2, 2, "grabbed", "AAA", "/pack.mkv"),
            ]
        }
    )
    strategy = MovieDeletionStrategy(
        radarr=radarr,  # type: ignore[arg-type]
        dry_run=True,
        logger=logging.getLogger("test"),
        seerr=None,  # type: ignore[arg-type]
        downloader=None,  # type: ignore[arg-type]
    )
    collector = ActionCollector(event)

    assert not await strategy._movie_hashes_exclusive(collector, 1, (), {"aaa"})
    action = collector.build().actions[0]
    assert action.reason is FailureReason.PACK_TORRENT
    assert action.details["hashes"] == ["AAA"]


@pytest.mark.asyncio
async def test_unknown_downloader_existence_blocks_cascade_even_without_skip_reason() -> None:
    event = _event()
    strategy = MovieDeletionStrategy(
        radarr=_HashScopedRadarr({}),  # type: ignore[arg-type]
        dry_run=False,
        logger=logging.getLogger("test"),
        seerr=None,  # type: ignore[arg-type]
        downloader=_UnknownExistenceDownloader(),  # type: ignore[arg-type]
    )
    collector = ActionCollector(event)

    assert not await strategy._cleanup_hashes(collector, {"AAA"}, event=event)
    action = collector.build().actions[0]
    assert action.status is ActionStatus.FAILED
    assert action.reason is FailureReason.OWNERSHIP_UNVERIFIABLE
