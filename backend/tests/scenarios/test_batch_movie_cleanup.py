"""End-to-end batch execution through the real movie deletion strategy."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from uuid import uuid4

import pytest

from cleanarr.application.deletion_batches import ManualDeletionBatchService
from cleanarr.application.deletion_models import (
    ActionResultResponse,
    BatchChildStatus,
    ManualDeleteBatchSubmitRequest,
    ManualDeleteRequest,
    ProcessingResultResponse,
)
from cleanarr.application.strategies import MovieDeletionStrategy
from cleanarr.domain import (
    ActionStatus,
    ExternalServiceError,
    FailureReason,
    ItemType,
    MediaDeletionEvent,
    MediaFingerprint,
    OverallStatus,
    RadarrHistoryRecord,
    RadarrMovie,
    SeerrMedia,
)
from cleanarr.infrastructure.deletion_repository import SQLiteDeletionRepository
from tests.fakes import FakeDownloaderClient, FakeRadarrClient, FakeSeerrClient


async def _wait_for_terminal(service: ManualDeletionBatchService, batch_id) -> None:  # type: ignore[no-untyped-def]
    for _ in range(200):
        if service.get(batch_id).status.value not in {"queued", "running"}:
            return
        await asyncio.sleep(0.01)
    raise AssertionError("batch did not finish")


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["success", "late_error", "safety_skip", "safety_failed", "retained", "absent"])
async def test_live_movie_strategy_preserves_deleted_batch_outcome(tmp_path: Path, outcome: str) -> None:
    target_hash = "A" * 40
    radarr = FakeRadarrClient(
        [RadarrMovie(1, "Movie", "/data/movie", 100, None)],
        {1: [RadarrHistoryRecord(1, 1, "grabbed", target_hash, None)]},
    )
    downloader = FakeDownloaderClient({target_hash})
    seerr = FakeSeerrClient([SeerrMedia(1, "movie", 100, None, None, None)], [], [])
    event = MediaDeletionEvent(
        "ItemDeleted",
        ItemType.MOVIE,
        "source-id",
        "Movie",
        MediaFingerprint(tmdb_id=100, path="/data/movie"),
    )
    preview_strategy = MovieDeletionStrategy(
        radarr=radarr,
        dry_run=True,
        logger=logging.getLogger("test"),
        seerr=seerr,
        downloader=downloader,
    )
    execution_strategy = MovieDeletionStrategy(
        radarr=radarr,
        dry_run=False,
        logger=logging.getLogger("test"),
        seerr=seerr,
        downloader=downloader,
    )

    async def resolver(payload: ManualDeleteRequest) -> MediaDeletionEvent:
        return event

    async def previewer(payload: ManualDeleteRequest, resolved: MediaDeletionEvent) -> ProcessingResultResponse:
        return ProcessingResultResponse.from_domain(await preview_strategy.handle(resolved))

    async def runner(payload, resolved, report):  # type: ignore[no-untyped-def]
        if outcome in {"retained", "absent"}:
            return (await previewer(payload, resolved)).model_copy(
                update={
                    "status": OverallStatus.IGNORED,
                    "actions": [
                        ActionResultResponse(
                            system="qbittorrent",
                            action="delete_hash",
                            status=ActionStatus.SKIPPED if outcome == "retained" else ActionStatus.ALREADY_ABSENT,
                            reason=FailureReason.SEEDING_POLICY if outcome == "retained" else None,
                            message="Intentionally retained or already absent",
                            details={},
                        )
                    ],
                }
            )
        if outcome.startswith("safety_"):
            return (await previewer(payload, resolved)).model_copy(
                update={
                    "status": OverallStatus.PARTIAL_FAILURE,
                    "actions": [
                        ActionResultResponse(
                            system="qbittorrent",
                            action="delete_hash",
                            status=ActionStatus.SKIPPED if outcome == "safety_skip" else ActionStatus.FAILED,
                            reason=FailureReason.OWNERSHIP_UNVERIFIABLE,
                            message="Synthetic unverified ownership",
                            details={},
                        ),
                    ],
                }
            )
        if outcome == "late_error":

            async def fail():
                raise ExternalServiceError("seerr", "Synthetic late read failure")

            seerr.list_media = fail
        return ProcessingResultResponse.from_domain(await execution_strategy.handle(resolved))

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
        assert preview.ready_count == 1
        submitted = await service.submit(
            ManualDeleteBatchSubmitRequest(
                children=[request],
                idempotency_key=uuid4(),
                confirmed_batch_hash=preview.batch_hash,
                confirmed_item_count=1,
            )
        )
        await _wait_for_terminal(service, submitted.id)
        result = service.get(submitted.id)
        completed = outcome in {"success", "retained", "absent"}
        assert result.status.value == ("completed" if completed else "failed")
        child = result.children[0]
        assert child.status is (BatchChildStatus.COMPLETED if completed else BatchChildStatus.FAILED)
        assert child.error_code == (
            "partial_result" if outcome == "late_error" else "unsafe_result" if outcome.startswith("safety_") else None
        )
        assert child.result is not None
        if outcome.startswith("safety_") or outcome in {"retained", "absent"}:
            assert radarr.deleted_movie_ids == downloader.deleted_hashes == []
            return
        assert {action.action for action in child.result.actions if action.status is ActionStatus.DELETED} >= {
            "delete_hash",
            "delete_movie",
        }
        assert radarr.deleted_movie_ids == [1]
        assert downloader.deleted_hashes == [target_hash]
    finally:
        await service.stop()
