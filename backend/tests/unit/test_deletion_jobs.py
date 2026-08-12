"""Tests for durable manual deletion jobs and confirmed preflight plans."""

from __future__ import annotations

import asyncio
from pathlib import Path
from uuid import UUID

import pytest
from fastapi import HTTPException

from cleanarr.api.deletion_jobs import (
    DeletionJobActiveError,
    DeletionPreflightError,
    ManualDeletionJobStore,
)
from cleanarr.api.library_schemas import (
    ManualDeleteJobPhase,
    ManualDeleteJobStatus,
    ManualDeleteRequest,
)
from cleanarr.api.schemas import ProcessingResultResponse
from cleanarr.domain import ItemType, MediaDeletionEvent, MediaFingerprint, OverallStatus


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


async def _confirmed_request(
    store: ManualDeletionJobStore,
    request: ManualDeleteRequest,
) -> ManualDeleteRequest:
    preview = await store.preview(request)
    return request.model_copy(update={"confirmed_plan_hash": preview.plan_hash})


async def _wait_for_status(
    store: ManualDeletionJobStore,
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

    store = ManualDeletionJobStore(_resolver, _previewer, runner, db_path=db_path)
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

    reloaded = ManualDeletionJobStore(_resolver, _previewer, runner, db_path=db_path)
    try:
        await reloaded.start()
        assert reloaded.list_jobs() == []
    finally:
        await reloaded.stop()


@pytest.mark.asyncio
async def test_submit_rejects_missing_or_changed_preflight(tmp_path: Path) -> None:
    async def runner(payload, event, report):  # type: ignore[no-untyped-def]
        return _result(event)

    store = ManualDeletionJobStore(_resolver, _previewer, runner, db_path=tmp_path / "cleanarr.db")
    request = ManualDeleteRequest(item_type=ItemType.MOVIE, radarr_movie_id=1)
    try:
        with pytest.raises(DeletionPreflightError, match="Preview"):
            await store.submit(request)
        with pytest.raises(DeletionPreflightError, match="changed"):
            await store.submit(request.model_copy(update={"confirmed_plan_hash": "stale"}))
        assert store.list_jobs() == []
    finally:
        await store.stop()


@pytest.mark.asyncio
async def test_submit_rejects_preflight_with_downstream_failure(tmp_path: Path) -> None:
    async def failed_previewer(payload, event):  # type: ignore[no-untyped-def]
        return _result(event, OverallStatus.PARTIAL_FAILURE)

    async def runner(payload, event, report):  # type: ignore[no-untyped-def]
        raise AssertionError("unsafe plan must not execute")

    store = ManualDeletionJobStore(
        _resolver,
        failed_previewer,
        runner,
        db_path=tmp_path / "cleanarr.db",
    )
    request = ManualDeleteRequest(
        item_type=ItemType.MOVIE,
        radarr_movie_id=1,
        confirmed_plan_hash="any",
    )
    try:
        with pytest.raises(DeletionPreflightError, match="downstream failures"):
            await store.submit(request)
    finally:
        await store.stop()


@pytest.mark.asyncio
async def test_background_deletion_exposes_http_error_without_retry(tmp_path: Path) -> None:
    async def runner(payload, event, report):  # type: ignore[no-untyped-def]
        report(ManualDeleteJobPhase.LOCATING, 25, "Target resolved.", None)
        raise HTTPException(status_code=404, detail="Sonarr series 99 not found.")

    store = ManualDeletionJobStore(_resolver, _previewer, runner, db_path=tmp_path / "cleanarr.db")
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

    store = ManualDeletionJobStore(
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
async def test_manual_job_uses_shared_execution_lock(tmp_path: Path) -> None:
    execution_lock = asyncio.Lock()
    await execution_lock.acquire()
    runner_started = asyncio.Event()

    async def runner(payload, event, report):  # type: ignore[no-untyped-def]
        runner_started.set()
        return _result(event)

    store = ManualDeletionJobStore(
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
async def test_process_restart_resumes_from_persisted_event(tmp_path: Path) -> None:
    db_path = tmp_path / "cleanarr.db"
    runner_started = asyncio.Event()
    never_release = asyncio.Event()

    async def interrupted_runner(payload, event, report):  # type: ignore[no-untyped-def]
        report(ManualDeleteJobPhase.CLEANING, 30, "Cleanup started.", event.name)
        runner_started.set()
        await never_release.wait()
        return _result(event)

    first_store = ManualDeletionJobStore(_resolver, _previewer, interrupted_runner, db_path=db_path)
    request = await _confirmed_request(
        first_store,
        ManualDeleteRequest(item_type=ItemType.MOVIE, radarr_movie_id=1),
    )
    queued = await first_store.submit(request)
    await runner_started.wait()
    await _wait_for_status(first_store, queued.id, ManualDeleteJobStatus.RUNNING)
    await first_store.stop()

    async def resolver_must_not_run(payload: ManualDeleteRequest) -> MediaDeletionEvent:
        raise AssertionError("restart must use the persisted event")

    async def resumed_runner(payload, event, report):  # type: ignore[no-untyped-def]
        return _result(event)

    resumed_store = ManualDeletionJobStore(
        resolver_must_not_run,
        _previewer,
        resumed_runner,
        db_path=db_path,
        retry_delays_seconds=(0.0,),
    )
    try:
        await resumed_store.start()
        await _wait_for_status(resumed_store, queued.id, ManualDeleteJobStatus.COMPLETED)
        completed = resumed_store.get(queued.id)
        assert completed.attempt_count == 2
        assert completed.result is not None
        assert completed.result.item_id == "manual:radarr:1"
        assert completed.preflight.item_id == "manual:radarr:1"
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

    first_store = ManualDeletionJobStore(
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

    resumed_store = ManualDeletionJobStore(
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
