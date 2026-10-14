"""Regression coverage for dismiss versus a terminal job write."""

from __future__ import annotations

import asyncio
import threading
from pathlib import Path
from uuid import uuid4

import pytest

from cleanarr.application.deletion_jobs import ManualDeletionJobService
from cleanarr.application.deletion_models import (
    ManualDeleteJobStatus,
    ManualDeleteRequest,
    ProcessingResultResponse,
)
from cleanarr.domain import ItemType, MediaDeletionEvent, MediaFingerprint, OverallStatus
from cleanarr.infrastructure.deletion_repository import SQLiteDeletionRepository


def _event() -> MediaDeletionEvent:
    return MediaDeletionEvent(
        notification_type="ItemDeleted",
        item_type=ItemType.MOVIE,
        item_id="manual:radarr:1",
        name="Movie",
        fingerprint=MediaFingerprint(tmdb_id=1, path="/media/movie"),
    )


def _result(event: MediaDeletionEvent) -> ProcessingResultResponse:
    return ProcessingResultResponse(
        item_type=event.item_type,
        item_id=event.item_id,
        name=event.name,
        status=OverallStatus.SUCCESS,
        actions=[],
    )


@pytest.mark.asyncio
async def test_dismiss_waits_for_terminal_save_before_deleting_job(tmp_path: Path) -> None:
    event = _event()
    result = _result(event)
    request = ManualDeleteRequest(
        item_type=ItemType.MOVIE,
        radarr_movie_id=1,
        idempotency_key=uuid4(),
    )
    repository = SQLiteDeletionRepository(tmp_path / "cleanarr.db")
    original_save_job = repository.save_job
    original_delete_job = repository.delete_job
    terminal_save_started = threading.Event()
    release_terminal_save = threading.Event()
    delete_called = threading.Event()

    def gated_save_job(snapshot) -> None:  # type: ignore[no-untyped-def]
        if snapshot.status is ManualDeleteJobStatus.COMPLETED:
            terminal_save_started.set()
            assert release_terminal_save.wait(timeout=5), "terminal save was not released"
        original_save_job(snapshot)

    def recording_delete_job(job_id) -> None:  # type: ignore[no-untyped-def]
        delete_called.set()
        original_delete_job(job_id)

    repository.save_job = gated_save_job  # type: ignore[method-assign]
    repository.delete_job = recording_delete_job  # type: ignore[method-assign]

    async def resolver(_payload: ManualDeleteRequest) -> MediaDeletionEvent:
        return event

    async def previewer(
        _payload: ManualDeleteRequest,
        _event: MediaDeletionEvent,
    ) -> ProcessingResultResponse:
        return result

    async def runner(
        _payload: ManualDeleteRequest,
        _event: MediaDeletionEvent,
        _report,
    ) -> ProcessingResultResponse:  # type: ignore[no-untyped-def]
        return result

    store = ManualDeletionJobService(
        resolver,
        previewer,
        runner,
        repository=repository,
        max_attempts=1,
        retry_delays_seconds=(0,),
    )
    preview = await store.preview(request)
    confirmed = request.model_copy(update={"confirmed_plan_hash": preview.plan_hash})
    queued = await store.submit(confirmed)

    try:
        assert await asyncio.to_thread(terminal_save_started.wait, 5)
        dismiss_task = asyncio.create_task(store.dismiss(queued.id))
        await asyncio.sleep(0.05)

        assert not dismiss_task.done()
        assert not delete_called.is_set()
        persisted = await asyncio.to_thread(repository.load_job, queued.id)
        assert persisted is not None
        assert persisted.status is not ManualDeleteJobStatus.COMPLETED

        release_terminal_save.set()
        await asyncio.wait_for(dismiss_task, timeout=5)
        assert delete_called.is_set()
        assert await asyncio.to_thread(repository.load_job, queued.id) is None
    finally:
        release_terminal_save.set()
        await store.stop()

    reloaded = ManualDeletionJobService(
        resolver,
        previewer,
        runner,
        repository=SQLiteDeletionRepository(tmp_path / "cleanarr.db"),
    )
    try:
        await reloaded.start()
        assert reloaded.list_jobs() == []
    finally:
        await reloaded.stop()
