"""Tests for durable manual deletion jobs and confirmed preflight plans."""

from __future__ import annotations

import asyncio
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from cleanarr.api.dashboard import ActivityStore
from cleanarr.api.schemas import JellyfinWebhookPayload
from cleanarr.application.deletion_jobs import (
    DeletionExecutionFailure,
    DeletionJobActiveError,
    DeletionJobIdempotencyConflictError,
    DeletionJobIdempotencyRetiredError,
    DeletionPreflightError,
    ManualDeletionJobService,
)
from cleanarr.application.deletion_jobs import plan_hash as _plan_hash
from cleanarr.application.deletion_models import (
    ActionResultResponse,
    ManualDeleteJobPhase,
    ManualDeleteJobStatus,
    ManualDeleteRequest,
    ProcessingResultResponse,
)
from cleanarr.domain import ActionStatus, FailureReason, ItemType, MediaDeletionEvent, MediaFingerprint, OverallStatus
from cleanarr.infrastructure.deletion_repository import SQLiteDeletionRepository


def _event(item_type: ItemType = ItemType.MOVIE) -> MediaDeletionEvent:
    return MediaDeletionEvent(
        notification_type="ItemDeleted",
        item_type=item_type,
        item_id="manual:radarr:1" if item_type is ItemType.MOVIE else "manual:sonarr:99:series",
        name="Movie" if item_type is ItemType.MOVIE else "Series",
        fingerprint=MediaFingerprint(tmdb_id=42, path="/media/item"),
        series_name="Series" if item_type is not ItemType.MOVIE else None,
    )


def _result(event: MediaDeletionEvent, status: OverallStatus = OverallStatus.SUCCESS) -> ProcessingResultResponse:
    return ProcessingResultResponse(
        item_type=event.item_type,
        item_id=event.item_id,
        name=event.name,
        status=status,
        actions=[],
    )


async def _resolver(payload: ManualDeleteRequest) -> MediaDeletionEvent:
    return _event(payload.item_type)


async def _previewer(
    payload: ManualDeleteRequest,
    event: MediaDeletionEvent,
) -> ProcessingResultResponse:
    return _result(event)


async def _runner(
    payload: ManualDeleteRequest,
    event: MediaDeletionEvent,
    report: object,
) -> ProcessingResultResponse:
    return _result(event)


def _job_service(
    resolver: object,
    previewer: object,
    runner: object,
    *,
    db_path: Path,
    **kwargs: object,
) -> ManualDeletionJobService:
    return ManualDeletionJobService(  # type: ignore[arg-type]
        resolver,
        previewer,
        runner,
        repository=SQLiteDeletionRepository(db_path),
        **kwargs,
    )


async def _confirmed_request(
    store: ManualDeletionJobService,
    request: ManualDeleteRequest,
) -> ManualDeleteRequest:
    preview = await store.preview(request)
    return request.model_copy(
        update={"confirmed_plan_hash": preview.plan_hash, "idempotency_key": request.idempotency_key or uuid4()}
    )


async def _wait_for_status(
    store: ManualDeletionJobService,
    job_id: UUID,
    expected: ManualDeleteJobStatus,
) -> None:
    for _ in range(200):
        if store.get(job_id).status is expected:
            return
        await asyncio.sleep(0.01)
    raise AssertionError(f"Job did not reach {expected}")


@pytest.mark.asyncio
async def test_background_deletion_reports_progress_persists_and_dismisses(tmp_path: Path) -> None:
    release = asyncio.Event()
    db_path = tmp_path / "cleanarr.db"

    async def runner(payload, event, report):  # type: ignore[no-untyped-def]
        report(ManualDeleteJobPhase.LOCATING, 25, "Target resolved from persisted identifiers.", event.name)
        await release.wait()
        report(ManualDeleteJobPhase.CLEANING, 70, "Cleaning downstream services.", event.name)
        return _result(event)

    store = _job_service(_resolver, _previewer, runner, db_path=db_path)
    request = await _confirmed_request(
        store,
        ManualDeleteRequest(item_type=ItemType.MOVIE, radarr_movie_id=1),
    )
    queued = await store.submit(request)

    try:
        await _wait_for_status(store, queued.id, ManualDeleteJobStatus.RUNNING)
        running = store.get(queued.id)
        assert running.phase is ManualDeleteJobPhase.LOCATING
        assert running.progress_percent == 25
        assert running.item_name == "Movie"
        assert running.preflight.item_id == "manual:radarr:1"
        with pytest.raises(DeletionJobActiveError):
            store.dismiss(queued.id)

        release.set()
        await _wait_for_status(store, queued.id, ManualDeleteJobStatus.COMPLETED)
        completed = store.get(queued.id)
        assert completed.progress_percent == 100
        assert completed.attempt_count == 1
        assert completed.result is not None
        assert completed.result.status is OverallStatus.SUCCESS

        store.dismiss(queued.id)
        assert store.list_jobs() == []
    finally:
        await store.stop()

    reloaded = _job_service(_resolver, _previewer, runner, db_path=db_path)
    try:
        await reloaded.start()
        assert reloaded.list_jobs() == []
    finally:
        await reloaded.stop()


@pytest.mark.asyncio
async def test_submit_rejects_missing_or_changed_preflight(tmp_path: Path) -> None:
    async def runner(payload, event, report):  # type: ignore[no-untyped-def]
        return _result(event)

    store = _job_service(_resolver, _previewer, runner, db_path=tmp_path / "cleanarr.db")
    request = ManualDeleteRequest(item_type=ItemType.MOVIE, radarr_movie_id=1, idempotency_key=uuid4())
    try:
        with pytest.raises(DeletionPreflightError, match="Preview"):
            await store.submit(request)
        with pytest.raises(DeletionPreflightError, match="changed"):
            await store.submit(request.model_copy(update={"confirmed_plan_hash": "stale"}))
        assert store.list_jobs() == []
    finally:
        await store.stop()


@pytest.mark.asyncio
async def test_jellyfin_only_job_revalidates_target_before_execution(tmp_path: Path) -> None:
    resolve_calls = 0
    runner_called = False

    async def changing_resolver(payload: ManualDeleteRequest) -> MediaDeletionEvent:
        nonlocal resolve_calls
        resolve_calls += 1
        event = _event(payload.item_type)
        return MediaDeletionEvent(
            notification_type=event.notification_type,
            item_type=event.item_type,
            item_id="manual:jellyfin:jf-direct",
            name="Movie" if resolve_calls < 3 else "Changed movie",
            fingerprint=event.fingerprint,
        )

    async def runner(payload, event, report):  # type: ignore[no-untyped-def]
        nonlocal runner_called
        runner_called = True
        return _result(event)

    store = _job_service(changing_resolver, _previewer, runner, db_path=tmp_path / "cleanarr.db")
    request = await _confirmed_request(
        store,
        ManualDeleteRequest(
            item_type=ItemType.MOVIE,
            jellyfin_item_id="jf-direct",
            jellyfin_only=True,
        ),
    )
    queued = await store.submit(request)

    try:
        await _wait_for_status(store, queued.id, ManualDeleteJobStatus.FAILED)
        failed = store.get(queued.id)
        assert resolve_calls == 3
        assert runner_called is False
        assert failed.error == "The deletion plan changed while the job was queued. Preview it and confirm again."
    finally:
        await store.stop()


@pytest.mark.asyncio
async def test_submit_rejects_preflight_with_downstream_failure(tmp_path: Path) -> None:
    async def failed_previewer(payload, event):  # type: ignore[no-untyped-def]
        return _result(event, OverallStatus.PARTIAL_FAILURE)

    async def runner(payload, event, report):  # type: ignore[no-untyped-def]
        raise AssertionError("unsafe plan must not execute")

    store = _job_service(
        _resolver,
        failed_previewer,
        runner,
        db_path=tmp_path / "cleanarr.db",
    )
    request = ManualDeleteRequest(
        item_type=ItemType.MOVIE,
        radarr_movie_id=1,
        confirmed_plan_hash="any",
        idempotency_key=uuid4(),
    )
    try:
        with pytest.raises(DeletionPreflightError, match="failures"):
            await store.submit(request)
    finally:
        await store.stop()


@pytest.mark.asyncio
async def test_submit_rejects_ignored_attention_plan_before_queueing(tmp_path: Path) -> None:
    async def ignored_previewer(payload, event):  # type: ignore[no-untyped-def]
        return _result(event).model_copy(
            update={
                "actions": [
                    ActionResultResponse(
                        system="downloader",
                        action="ignored",
                        status=ActionStatus.IGNORED,
                        message="Ownership is ambiguous.",
                        details={},
                    )
                ]
            }
        )

    store = _job_service(_resolver, ignored_previewer, _runner, db_path=tmp_path / "cleanarr.db")
    request = ManualDeleteRequest(
        item_type=ItemType.MOVIE,
        radarr_movie_id=1,
        confirmed_plan_hash="any",
        idempotency_key=uuid4(),
    )
    try:
        with pytest.raises(DeletionPreflightError) as raised:
            await store.submit(request)
        assert raised.value.code == "unsafe_plan"
        assert store.list_jobs() == []
    finally:
        await store.stop()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "reason",
    [
        FailureReason.AMBIGUOUS_MATCH,
        FailureReason.NO_MATCH,
        FailureReason.DOWNSTREAM_ERROR,
        FailureReason.AUTHENTICATION_FAILED,
        FailureReason.SOURCE_STILL_PRESENT,
        FailureReason.UNSUPPORTED_EVENT,
        None,
    ],
)
async def test_submit_rejects_unsafe_skipped_reason_before_queueing(
    tmp_path: Path, reason: FailureReason | None
) -> None:
    async def skipped_previewer(payload, event):  # type: ignore[no-untyped-def]
        return _result(event).model_copy(
            update={
                "actions": [
                    ActionResultResponse(
                        system="service",
                        action="skip",
                        status=ActionStatus.SKIPPED,
                        message="private downstream message",
                        reason=reason,
                        details={},
                    )
                ]
            }
        )

    store = _job_service(_resolver, skipped_previewer, _runner, db_path=tmp_path / "cleanarr.db")
    request = ManualDeleteRequest(
        item_type=ItemType.MOVIE, radarr_movie_id=1, confirmed_plan_hash="any", idempotency_key=uuid4()
    )
    try:
        with pytest.raises(DeletionPreflightError) as raised:
            await store.submit(request)
        assert raised.value.code == "unsafe_plan"
        assert store.list_jobs() == []
    finally:
        await store.stop()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "reason",
    [
        FailureReason.PACK_TORRENT,
        FailureReason.SHARED_FILE,
        FailureReason.SEEDING_POLICY,
        FailureReason.PARTIAL_REQUEST_RETAINED,
        FailureReason.NO_PARTIAL_REQUEST_CLEANUP,
    ],
)
async def test_submit_accepts_safe_retained_skipped_reason(tmp_path: Path, reason: FailureReason) -> None:
    async def skipped_previewer(payload, event):  # type: ignore[no-untyped-def]
        plan = _result(event).model_copy(
            update={
                "actions": [
                    ActionResultResponse(
                        system="service",
                        action="retain",
                        status=ActionStatus.SKIPPED,
                        message="retained",
                        reason=reason,
                        details={},
                    )
                ]
            }
        )
        return plan

    store = _job_service(_resolver, skipped_previewer, _runner, db_path=tmp_path / "cleanarr.db")
    request = ManualDeleteRequest(item_type=ItemType.MOVIE, radarr_movie_id=1, idempotency_key=uuid4())
    try:
        request = request.model_copy(update={"confirmed_plan_hash": (await store.preview(request)).plan_hash})
        queued = await store.submit(request)
        assert queued.display_name == "Movie"
    finally:
        await store.stop()


@pytest.mark.asyncio
async def test_background_deletion_exposes_http_error_without_retry(tmp_path: Path) -> None:
    async def runner(payload, event, report):  # type: ignore[no-untyped-def]
        report(ManualDeleteJobPhase.LOCATING, 25, "Target resolved.", None)
        raise DeletionExecutionFailure("Sonarr series 99 not found.")

    store = _job_service(_resolver, _previewer, runner, db_path=tmp_path / "cleanarr.db")
    request = await _confirmed_request(
        store,
        ManualDeleteRequest(item_type=ItemType.SERIES, sonarr_series_id=99),
    )
    queued = await store.submit(request)

    try:
        await _wait_for_status(store, queued.id, ManualDeleteJobStatus.FAILED)
        failed = store.get(queued.id)
        assert failed.phase is ManualDeleteJobPhase.FAILED
        assert failed.progress_percent == 100
        assert failed.attempt_count == 1
        assert failed.error == "Sonarr series 99 not found."
    finally:
        await store.stop()


@pytest.mark.asyncio
async def test_partial_failure_replans_and_retries_to_completion(tmp_path: Path) -> None:
    attempts = 0

    async def runner(payload, event, report):  # type: ignore[no-untyped-def]
        nonlocal attempts
        attempts += 1
        return _result(
            event,
            OverallStatus.PARTIAL_FAILURE if attempts == 1 else OverallStatus.SUCCESS,
        )

    store = _job_service(
        _resolver,
        _previewer,
        runner,
        db_path=tmp_path / "cleanarr.db",
        retry_delays_seconds=(0.01,),
    )
    request = await _confirmed_request(
        store,
        ManualDeleteRequest(item_type=ItemType.MOVIE, radarr_movie_id=1),
    )
    queued = await store.submit(request)

    try:
        await _wait_for_status(store, queued.id, ManualDeleteJobStatus.COMPLETED)
        completed = store.get(queued.id)
        assert attempts == 2
        assert completed.attempt_count == 2
        assert completed.result is not None
        assert completed.result.status is OverallStatus.SUCCESS
    finally:
        await store.stop()


@pytest.mark.asyncio
async def test_retry_requires_the_persisted_confirmation_plan_on_every_attempt(tmp_path: Path) -> None:
    runner_calls = 0
    plan_changed_after_first_run = False

    async def previewer(payload, event):  # type: ignore[no-untyped-def]
        plan = _result(event)
        if plan_changed_after_first_run:
            return plan.model_copy(update={"name": "Changed after the first attempt"})
        return plan

    async def runner(payload, event, report):  # type: ignore[no-untyped-def]
        nonlocal runner_calls, plan_changed_after_first_run
        runner_calls += 1
        plan_changed_after_first_run = True
        return _result(event, OverallStatus.PARTIAL_FAILURE)

    store = _job_service(
        _resolver,
        previewer,
        runner,
        db_path=tmp_path / "cleanarr.db",
        retry_delays_seconds=(0.0,),
    )
    request = await _confirmed_request(
        store,
        ManualDeleteRequest(item_type=ItemType.MOVIE, radarr_movie_id=1),
    )
    queued = await store.submit(request)

    try:
        await _wait_for_status(store, queued.id, ManualDeleteJobStatus.FAILED)
        failed = store.get(queued.id)
        assert runner_calls == 1
        assert failed.attempt_count == 2
        assert failed.error is not None
        assert "plan changed" in failed.error.lower()
    finally:
        await store.stop()


@pytest.mark.asyncio
async def test_manual_job_uses_shared_execution_lock(tmp_path: Path) -> None:
    execution_lock = asyncio.Lock()
    await execution_lock.acquire()
    runner_started = asyncio.Event()

    async def runner(payload, event, report):  # type: ignore[no-untyped-def]
        runner_started.set()
        return _result(event)

    store = _job_service(
        _resolver,
        _previewer,
        runner,
        db_path=tmp_path / "cleanarr.db",
        execution_lock=execution_lock,
    )
    request = await _confirmed_request(
        store,
        ManualDeleteRequest(item_type=ItemType.MOVIE, radarr_movie_id=1),
    )
    queued = await store.submit(request)

    try:
        await _wait_for_status(store, queued.id, ManualDeleteJobStatus.RUNNING)
        await asyncio.sleep(0.02)
        assert runner_started.is_set() is False
        execution_lock.release()
        await _wait_for_status(store, queued.id, ManualDeleteJobStatus.COMPLETED)
        assert runner_started.is_set() is True
    finally:
        if execution_lock.locked():
            execution_lock.release()
        await store.stop()


@pytest.mark.asyncio
async def test_process_restart_after_cleaning_fails_without_replaying_the_runner(tmp_path: Path) -> None:
    db_path = tmp_path / "cleanarr.db"
    runner_started = asyncio.Event()
    never_release = asyncio.Event()
    resumed_runner_calls = 0

    async def interrupted_runner(payload, event, report):  # type: ignore[no-untyped-def]
        report(ManualDeleteJobPhase.CLEANING, 30, "Cleanup started.", event.name)
        runner_started.set()
        await never_release.wait()
        return _result(event)

    first_store = _job_service(_resolver, _previewer, interrupted_runner, db_path=db_path)
    request = await _confirmed_request(
        first_store,
        ManualDeleteRequest(item_type=ItemType.MOVIE, radarr_movie_id=1),
    )
    queued = await first_store.submit(request)
    await runner_started.wait()
    await _wait_for_status(first_store, queued.id, ManualDeleteJobStatus.RUNNING)
    await first_store.stop()

    async def resumed_runner(payload, event, report):  # type: ignore[no-untyped-def]
        nonlocal resumed_runner_calls
        resumed_runner_calls += 1
        return _result(event)

    resumed_store = _job_service(
        _resolver,
        _previewer,
        resumed_runner,
        db_path=db_path,
        retry_delays_seconds=(0.0,),
    )
    try:
        await resumed_store.start()
        failed = resumed_store.get(queued.id)
        assert failed.status is ManualDeleteJobStatus.FAILED
        assert failed.phase is ManualDeleteJobPhase.FAILED
        assert failed.error is not None
        assert failed.error.startswith("interrupted_unknown:")
        assert resumed_runner_calls == 0
    finally:
        await resumed_store.stop()


@pytest.mark.asyncio
async def test_restart_during_planning_rechecks_original_confirmation(tmp_path: Path) -> None:
    db_path = tmp_path / "cleanarr.db"
    planning_started = asyncio.Event()
    never_release = asyncio.Event()
    preview_calls = 0

    async def interrupted_previewer(payload, event):  # type: ignore[no-untyped-def]
        nonlocal preview_calls
        preview_calls += 1
        if preview_calls >= 3:
            planning_started.set()
            await never_release.wait()
        return _result(event)

    async def runner_must_not_start(payload, event, report):  # type: ignore[no-untyped-def]
        raise AssertionError("execution must not start before planning finishes")

    first_store = _job_service(
        _resolver,
        interrupted_previewer,
        runner_must_not_start,
        db_path=db_path,
    )
    request = await _confirmed_request(
        first_store,
        ManualDeleteRequest(item_type=ItemType.MOVIE, radarr_movie_id=1),
    )
    queued = await first_store.submit(request)
    await planning_started.wait()
    await first_store.stop()

    async def changed_previewer(payload, event):  # type: ignore[no-untyped-def]
        changed = _result(event)
        return changed.model_copy(update={"name": "Changed plan"})

    resumed_store = _job_service(
        _resolver,
        changed_previewer,
        runner_must_not_start,
        db_path=db_path,
    )
    try:
        await resumed_store.start()
        await _wait_for_status(resumed_store, queued.id, ManualDeleteJobStatus.FAILED)
        failed = resumed_store.get(queued.id)
        assert failed.attempt_count == 1
        assert failed.error is not None
        assert "plan changed" in failed.error.lower()
    finally:
        await resumed_store.stop()


@pytest.mark.asyncio
async def test_restart_before_mutation_rechecks_and_resumes_the_persisted_event(tmp_path: Path) -> None:
    db_path = tmp_path / "cleanarr.db"
    planning_started = asyncio.Event()
    never_release = asyncio.Event()
    preview_calls = 0
    resumed_runner_calls = 0

    async def interrupted_previewer(payload, event):  # type: ignore[no-untyped-def]
        nonlocal preview_calls
        preview_calls += 1
        if preview_calls >= 3:
            planning_started.set()
            await never_release.wait()
        return _result(event)

    async def runner_must_not_start(payload, event, report):  # type: ignore[no-untyped-def]
        raise AssertionError("execution must not start before planning finishes")

    first_store = _job_service(_resolver, interrupted_previewer, runner_must_not_start, db_path=db_path)
    request = await _confirmed_request(
        first_store,
        ManualDeleteRequest(item_type=ItemType.MOVIE, radarr_movie_id=1),
    )
    queued = await first_store.submit(request)
    await planning_started.wait()
    await first_store.stop()

    async def resumed_runner(payload, event, report):  # type: ignore[no-untyped-def]
        nonlocal resumed_runner_calls
        resumed_runner_calls += 1
        return _result(event)

    resumed_store = _job_service(
        _resolver,
        _previewer,
        resumed_runner,
        db_path=db_path,
        retry_delays_seconds=(0.0,),
    )
    try:
        await resumed_store.start()
        await _wait_for_status(resumed_store, queued.id, ManualDeleteJobStatus.COMPLETED)
        completed = resumed_store.get(queued.id)
        assert completed.attempt_count == 1
        assert completed.result is not None
        assert completed.result.item_id == "manual:radarr:1"
        assert resumed_runner_calls == 1
    finally:
        await resumed_store.stop()


def test_plan_hash_excludes_presentation_display_name() -> None:
    event = _event()
    plan = _result(event)

    assert _plan_hash(plan.model_copy(update={"display_name": "Jellyfin title"})) == _plan_hash(
        plan.model_copy(update={"display_name": "Localized title"})
    )
    assert _plan_hash(plan.model_copy(update={"item_id": "different-owned-item"})) != _plan_hash(plan)


def test_display_name_is_trimmed_bounded_and_rejects_control_characters() -> None:
    request = ManualDeleteRequest(item_type=ItemType.MOVIE, radarr_movie_id=1, display_name="  Library title  ")

    assert request.display_name == "Library title"
    with pytest.raises(ValidationError, match="control characters"):
        ManualDeleteRequest(item_type=ItemType.MOVIE, radarr_movie_id=1, display_name="bad\nname")
    with pytest.raises(ValidationError, match="control characters"):
        ManualDeleteRequest(item_type=ItemType.MOVIE, radarr_movie_id=1, display_name="bad\u0085name")
    with pytest.raises(ValidationError, match="256"):
        ManualDeleteRequest(item_type=ItemType.MOVIE, radarr_movie_id=1, display_name="x" * 257)


@pytest.mark.asyncio
async def test_idempotency_returns_one_job_rejects_conflicts_and_runs_once(tmp_path: Path) -> None:
    runner_calls = 0

    async def runner(payload, event, report):  # type: ignore[no-untyped-def]
        nonlocal runner_calls
        runner_calls += 1
        report(ManualDeleteJobPhase.CLEANING, 50, "Arr title must not replace the library title.", "Arr title")
        return _result(event)

    store = _job_service(_resolver, _previewer, runner, db_path=tmp_path / "cleanarr.db")
    key = uuid4()
    request = await _confirmed_request(
        store,
        ManualDeleteRequest(
            item_type=ItemType.MOVIE,
            radarr_movie_id=1,
            idempotency_key=key,
            display_name="  Jellyfin library title  ",
        ),
    )
    try:
        first, duplicate = await asyncio.gather(store.submit(request), store.submit(request))
        assert first.id == duplicate.id
        assert first.display_name == "Jellyfin library title"
        await _wait_for_status(store, first.id, ManualDeleteJobStatus.COMPLETED)
        completed = store.get(first.id)
        assert completed.display_name == "Jellyfin library title"
        assert completed.result is not None
        assert completed.result.display_name == "Jellyfin library title"
        assert runner_calls == 1
        assert len(store.list_jobs()) == 1

        with pytest.raises(DeletionJobIdempotencyConflictError):
            await store.submit(request.model_copy(update={"radarr_movie_id": 2}))
    finally:
        await store.stop()

    reloaded_store = _job_service(_resolver, _previewer, runner, db_path=tmp_path / "cleanarr.db")
    try:
        await reloaded_store.start()
        reloaded_duplicate = await reloaded_store.submit(request)
        assert reloaded_duplicate.id == first.id
        assert len(reloaded_store.list_jobs()) == 1
        await asyncio.sleep(0)
        assert runner_calls == 1
        with sqlite3.connect(tmp_path / "cleanarr.db") as connection:
            assert connection.execute("SELECT COUNT(*) FROM manual_delete_jobs").fetchone() == (1,)
    finally:
        await reloaded_store.stop()


@pytest.mark.asyncio
async def test_idempotency_tombstone_blocks_reexecution_after_dismissal_and_pruning(tmp_path: Path) -> None:
    runner_calls = 0

    async def runner(payload, event, report):  # type: ignore[no-untyped-def]
        nonlocal runner_calls
        runner_calls += 1
        return _result(event)

    db_path = tmp_path / "cleanarr.db"
    store = _job_service(_resolver, _previewer, runner, db_path=db_path, history_limit=1)
    first = await _confirmed_request(
        store, ManualDeleteRequest(item_type=ItemType.MOVIE, radarr_movie_id=1, idempotency_key=uuid4())
    )
    try:
        first_job = await store.submit(first)
        await _wait_for_status(store, first_job.id, ManualDeleteJobStatus.COMPLETED)
        store.dismiss(first_job.id)
        with pytest.raises(DeletionJobIdempotencyRetiredError):
            await store.submit(first)

        second = await _confirmed_request(
            store, ManualDeleteRequest(item_type=ItemType.MOVIE, radarr_movie_id=2, idempotency_key=uuid4())
        )
        second_job = await store.submit(second)
        await _wait_for_status(store, second_job.id, ManualDeleteJobStatus.COMPLETED)
        third = await _confirmed_request(
            store, ManualDeleteRequest(item_type=ItemType.MOVIE, radarr_movie_id=3, idempotency_key=uuid4())
        )
        third_job = await store.submit(third)
        await _wait_for_status(store, third_job.id, ManualDeleteJobStatus.COMPLETED)
        with pytest.raises(DeletionJobIdempotencyRetiredError):
            await store.submit(second)
        assert runner_calls == 3
    finally:
        await store.stop()


@pytest.mark.asyncio
async def test_display_name_survives_retry_and_restart(tmp_path: Path) -> None:
    db_path = tmp_path / "cleanarr.db"
    attempts = 0

    async def retrying_runner(payload, event, report):  # type: ignore[no-untyped-def]
        nonlocal attempts
        attempts += 1
        report(ManualDeleteJobPhase.CLEANING, 40, "Using canonical Arr name.", "Canonical Arr name")
        return _result(event, OverallStatus.PARTIAL_FAILURE)

    first_store = _job_service(
        _resolver,
        _previewer,
        retrying_runner,
        db_path=db_path,
        retry_delays_seconds=(60.0,),
    )
    request = await _confirmed_request(
        first_store,
        ManualDeleteRequest(
            item_type=ItemType.MOVIE,
            radarr_movie_id=1,
            display_name="Selected library title",
        ),
    )
    preview = await first_store.preview(request)
    queued = await first_store.submit(request)
    await _wait_for_status(first_store, queued.id, ManualDeleteJobStatus.RETRY_WAIT)
    assert preview.plan.display_name == "Selected library title"
    assert first_store.get(queued.id).display_name == "Selected library title"
    await first_store.stop()

    async def successful_runner(payload, event, report):  # type: ignore[no-untyped-def]
        return _result(event)

    resumed_store = _job_service(
        _resolver,
        _previewer,
        successful_runner,
        db_path=db_path,
        retry_delays_seconds=(0.0,),
    )
    try:
        await resumed_store.start()
        resumed = resumed_store.get(queued.id)
        assert resumed.display_name == "Selected library title"
        assert resumed.preflight.display_name == "Selected library title"
    finally:
        await resumed_store.stop()


@pytest.mark.asyncio
async def test_old_persisted_job_and_activity_rows_fall_back_to_safe_display_names(tmp_path: Path) -> None:
    db_path = tmp_path / "cleanarr.db"
    bootstrap_store = _job_service(_resolver, _previewer, _runner, db_path=db_path)
    await bootstrap_store.start()
    await bootstrap_store.stop()
    event = _event()
    old_job_id = uuid4()
    now = datetime.now(UTC).isoformat()
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "INSERT INTO manual_delete_jobs ("
            "id, request_json, event_json, preflight_json, status, phase, progress_percent, message, item_name, "
            "created_at, attempt_count, max_attempts, idempotency_key, display_name"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                str(old_job_id),
                ManualDeleteRequest(item_type=ItemType.MOVIE, radarr_movie_id=1).model_dump_json(),
                JellyfinWebhookPayload.from_domain(event).model_dump_json(),
                _result(event).model_dump_json(exclude={"display_name"}),
                "completed",
                "completed",
                100,
                "Old job completed.",
                "Legacy library title",
                now,
                1,
                3,
                None,
                None,
            ),
        )
        connection.execute(
            "INSERT INTO activity (processed_at, result_json) VALUES (?, ?)",
            (now, _result(event).model_dump_json(exclude={"display_name"})),
        )
        connection.commit()

    reloaded_store = _job_service(_resolver, _previewer, _runner, db_path=db_path)
    try:
        await reloaded_store.start()
        assert reloaded_store.get(old_job_id).display_name == "Legacy library title"
    finally:
        await reloaded_store.stop()

    activity_store = ActivityStore(db_path)
    await activity_store.initialize()
    records = await activity_store.snapshot()
    assert records[0].result.display_name == "Movie"
