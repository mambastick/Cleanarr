"""Manual job execution through the real movie deletion strategy."""

from __future__ import annotations

import asyncio
import copy
import logging
from pathlib import Path
from uuid import uuid4

import pytest

from cleanarr.application.deletion_jobs import ManualDeletionJobService
from cleanarr.application.deletion_models import (
    ManualDeleteJobStatus,
    ManualDeleteRequest,
    ProcessingResultResponse,
)
from cleanarr.application.deletion_persistence import DeletionJobRecord
from cleanarr.application.strategies import MovieDeletionStrategy
from cleanarr.domain import (
    DownloaderRemovalResult,
    ExternalServiceError,
    ItemType,
    MediaDeletionEvent,
    MediaFingerprint,
    RadarrHistoryRecord,
    RadarrMovie,
    SeerrMedia,
)
from cleanarr.infrastructure.deletion_repository import SQLiteDeletionRepository
from tests.fakes import FakeRadarrClient, FakeSeerrClient


class _SequencedDownloader:
    """Keep preflight clean, then inject one live execution outcome."""

    def __init__(self, hash_value: str, outcome: str) -> None:
        self.hash_value = hash_value
        self.outcome = outcome
        self.calls = 0
        self.deleted_hashes: list[str] = []

    async def delete_hashes(
        self,
        hashes: list[str],
        *,
        delete_files: bool,
        dry_run: bool = False,
    ) -> list[DownloaderRemovalResult]:
        self.calls += 1
        if self.calls == 4 and self.outcome == "safety":
            return [
                DownloaderRemovalResult(
                    hash_value=hashes[0],
                    existed=True,
                    skip_reason="sibling_scope_unknown",
                )
            ]
        if self.calls == 4 and self.outcome == "transient":
            raise ExternalServiceError("downloader", "temporary downloader failure")
        if not dry_run:
            self.deleted_hashes.extend(hashes)
        return [DownloaderRemovalResult(hash_value=value, existed=True) for value in hashes]


class _CapturingRepository(SQLiteDeletionRepository):
    """Retain durable job snapshots together with externally visible state."""

    def __init__(self, path: Path, probe) -> None:  # type: ignore[no-untyped-def]
        super().__init__(path)
        self.snapshots: list[tuple[DeletionJobRecord, object]] = []
        self._probe = probe

    def save_job(self, job: DeletionJobRecord) -> None:
        self.snapshots.append((copy.deepcopy(job), self._probe()))
        super().save_job(job)


async def _wait_for_terminal(service: ManualDeletionJobService, job_id) -> None:  # type: ignore[no-untyped-def]
    for _ in range(300):
        if service.get(job_id).status in {ManualDeleteJobStatus.COMPLETED, ManualDeleteJobStatus.FAILED}:
            return
        await asyncio.sleep(0.01)
    raise AssertionError("manual deletion job did not finish")


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["safety", "transient"])
async def test_live_movie_strategy_job_rechecks_before_mutation(tmp_path: Path, outcome: str) -> None:
    target_hash = "A" * 40
    radarr = FakeRadarrClient(
        [RadarrMovie(1, "Movie", "/data/movie", 100, None)],
        {1: [RadarrHistoryRecord(1, 1, "grabbed", target_hash, None)]},
    )
    seerr = FakeSeerrClient([SeerrMedia(1, "movie", 100, None, None, None)], [], [])
    downloader = _SequencedDownloader(target_hash, outcome)
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
        seerr=seerr,  # type: ignore[arg-type]
        downloader=downloader,  # type: ignore[arg-type]
    )
    execution_strategy = MovieDeletionStrategy(
        radarr=radarr,
        dry_run=False,
        logger=logging.getLogger("test"),
        seerr=seerr,  # type: ignore[arg-type]
        downloader=downloader,  # type: ignore[arg-type]
    )

    async def resolver(payload: ManualDeleteRequest) -> MediaDeletionEvent:
        return event

    async def previewer(payload: ManualDeleteRequest, resolved: MediaDeletionEvent) -> ProcessingResultResponse:
        return ProcessingResultResponse.from_domain(await preview_strategy.handle(resolved))

    async def runner(payload, resolved, report):  # type: ignore[no-untyped-def]
        return ProcessingResultResponse.from_domain(await execution_strategy.handle(resolved))

    repository = _CapturingRepository(
        tmp_path / f"{outcome}.db",
        lambda: (downloader.calls, tuple(downloader.deleted_hashes), tuple(radarr.deleted_movie_ids)),
    )
    service = ManualDeletionJobService(
        resolver,
        previewer,
        runner,
        repository=repository,
        max_attempts=2,
        retry_delays_seconds=(0,),
    )
    try:
        request = ManualDeleteRequest(item_type=ItemType.MOVIE, radarr_movie_id=1)
        preview = await service.preview(request)
        queued = await service.submit(
            request.model_copy(update={"confirmed_plan_hash": preview.plan_hash, "idempotency_key": uuid4()})
        )
        await _wait_for_terminal(service, queued.id)
        result = service.get(queued.id)
        if outcome == "safety":
            assert result.status is ManualDeleteJobStatus.FAILED
            assert result.error_code == "unsafe_plan"
            assert result.attempt_count == 1
            assert downloader.calls == 4  # preview, submit recheck, worker recheck, live mutation
            assert downloader.deleted_hashes == []
            assert radarr.deleted_movie_ids == []
        else:
            assert result.status is ManualDeleteJobStatus.COMPLETED
            assert result.error_code is None
            assert result.attempt_count == 2
            retry_snapshots = [
                (snapshot, state)
                for snapshot, state in repository.snapshots
                if snapshot.status is ManualDeleteJobStatus.RETRY_WAIT
            ]
            assert retry_snapshots
            retry_snapshot, retry_state = retry_snapshots[-1]
            assert retry_snapshot.error_code == "execution_failed"
            assert retry_state == (4, (), ())
            assert downloader.calls == 6  # failed mutation plus clean retry recheck and mutation
            assert downloader.deleted_hashes == [target_hash]
            assert radarr.deleted_movie_ids == [1]
    finally:
        await service.stop()
