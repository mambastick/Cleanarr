"""Tests for the in-memory manual deletion queue."""

from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

from cleanarr.api.deletion_jobs import DeletionJobActiveError, ManualDeletionJobStore
from cleanarr.api.library_schemas import (
    ManualDeleteJobPhase,
    ManualDeleteJobStatus,
    ManualDeleteRequest,
)
from cleanarr.api.schemas import ProcessingResultResponse
from cleanarr.domain import ItemType, OverallStatus


async def _wait_for_status(
    store: ManualDeletionJobStore,
    job_id,  # type: ignore[no-untyped-def]
    expected: ManualDeleteJobStatus,
) -> None:
    for _ in range(100):
        if store.get(job_id).status is expected:
            return
        await asyncio.sleep(0.01)
    raise AssertionError(f"Job did not reach {expected}")


@pytest.mark.asyncio
async def test_background_deletion_reports_progress_and_result() -> None:
    release = asyncio.Event()

    async def runner(payload, report):  # type: ignore[no-untyped-def]
        report(ManualDeleteJobPhase.LOCATING, 10, "Looking up the movie in Radarr.", "Movie")
        await release.wait()
        report(ManualDeleteJobPhase.CLEANING, 70, "Cleaning downstream services.", "Movie")
        return ProcessingResultResponse(
            item_type=payload.item_type,
            item_id="manual",
            name="Movie",
            status=OverallStatus.SUCCESS,
            actions=[],
        )

    store = ManualDeletionJobStore(runner)
    queued = await store.submit(ManualDeleteRequest(item_type=ItemType.MOVIE, radarr_movie_id=1))

    try:
        await _wait_for_status(store, queued.id, ManualDeleteJobStatus.RUNNING)
        running = store.get(queued.id)
        assert running.phase is ManualDeleteJobPhase.LOCATING
        assert running.progress_percent == 10
        assert running.item_name == "Movie"
        with pytest.raises(DeletionJobActiveError):
            store.dismiss(queued.id)

        release.set()
        await _wait_for_status(store, queued.id, ManualDeleteJobStatus.COMPLETED)
        completed = store.get(queued.id)
        assert completed.progress_percent == 100
        assert completed.result is not None
        assert completed.result.status is OverallStatus.SUCCESS

        store.dismiss(queued.id)
        assert store.list_jobs() == []
    finally:
        await store.stop()


@pytest.mark.asyncio
async def test_background_deletion_exposes_http_error() -> None:
    async def runner(payload, report):  # type: ignore[no-untyped-def]
        report(ManualDeleteJobPhase.LOCATING, 10, "Looking up the series in Sonarr.", None)
        raise HTTPException(status_code=404, detail="Sonarr series 99 not found.")

    store = ManualDeletionJobStore(runner)
    queued = await store.submit(ManualDeleteRequest(item_type=ItemType.SERIES, sonarr_series_id=99))

    try:
        await _wait_for_status(store, queued.id, ManualDeleteJobStatus.FAILED)
        failed = store.get(queued.id)
        assert failed.phase is ManualDeleteJobPhase.FAILED
        assert failed.progress_percent == 100
        assert failed.error == "Sonarr series 99 not found."
    finally:
        await store.stop()
