"""Jellyfin dependency outcomes remain bound to real manual cleanup flows."""

from __future__ import annotations

import asyncio
import copy
import logging
from pathlib import Path
from uuid import uuid4

import pytest

from cleanarr.application.deletion_batches import ManualDeletionBatchService
from cleanarr.application.deletion_jobs import ManualDeletionJobService, _execution_result_block_code
from cleanarr.application.deletion_models import (
    BatchChildStatus,
    ManualDeleteBatchSubmitRequest,
    ManualDeleteJobStatus,
    ManualDeleteRequest,
)
from cleanarr.application.deletion_persistence import DeletionJobRecord
from cleanarr.application.manual_deletion import ManualDeletionService
from cleanarr.application.strategies import DeletionStrategyFactory
from cleanarr.domain import (
    DownloaderRemovalResult,
    ExternalServiceError,
    ItemType,
    JellyfinItem,
    LibraryMediaType,
    RadarrHistoryRecord,
    RadarrMovie,
    SeerrMedia,
    SonarrEpisode,
    SonarrEpisodeFile,
    SonarrHistoryRecord,
    SonarrSeries,
    encode_library_resource,
)
from cleanarr.domain.config import RuntimeConfig, SonarrServiceConfig
from cleanarr.infrastructure.deletion_repository import SQLiteDeletionRepository
from tests.fakes import FakeRadarrClient, FakeSeerrClient, FakeSonarrClient


class _SequencedDownloader:
    def __init__(self, hash_value: str, outcome: str) -> None:
        self.outcome = outcome
        self.hash_value = hash_value
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
        if self.calls == 4 and self.outcome in {"sibling_scope_unknown", "shared_path"}:
            return [
                DownloaderRemovalResult(
                    hash_value=hashes[0],
                    existed=True,
                    skip_reason=self.outcome,
                )
            ]
        if self.calls == 4 and self.outcome == "transient":
            raise ExternalServiceError("downloader", "temporary downloader failure")
        if not dry_run:
            self.deleted_hashes.extend(hashes)
        return [DownloaderRemovalResult(hash_value=value, existed=True) for value in hashes]


class _JellyfinFake:
    def __init__(self, items: list[JellyfinItem]) -> None:
        self.items = items
        self.deleted_items: list[str] = []

    async def list_items(self, *, include_types: list[str]) -> list[JellyfinItem]:
        return [item for item in self.items if item.type in include_types]

    async def delete_item(self, item_id: str) -> None:
        self.deleted_items.append(item_id)


class _ActivityRecorder:
    def __init__(self) -> None:
        self.records: list[object] = []

    async def record(self, result: object, *, display_name: str | None = None) -> None:
        self.records.append(result)


class _CapturingRepository(SQLiteDeletionRepository):
    def __init__(self, path: Path, probe) -> None:  # type: ignore[no-untyped-def]
        super().__init__(path)
        self.snapshots: list[tuple[DeletionJobRecord, object]] = []
        self.batch_states: list[object] = []
        self._probe = probe

    def save_job(self, job: DeletionJobRecord) -> None:
        self.snapshots.append((copy.deepcopy(job), self._probe()))
        super().save_job(job)

    def save_batch(self, batch) -> None:  # type: ignore[no-untyped-def]
        self.batch_states.append(self._probe())
        super().save_batch(batch)


def _sonarr_state(
    sonarr: FakeSonarrClient,
) -> tuple[tuple[int, ...], tuple[tuple[int, int], ...], tuple[int, ...], tuple[int, ...]]:
    return (
        tuple(sonarr.unmonitored_episode_ids),
        tuple(sonarr.unmonitored_seasons),
        tuple(sonarr.deleted_episode_file_ids),
        tuple(sonarr.deleted_series_ids),
    )


def _services(tmp_path: Path, outcome: str, item_type: ItemType = ItemType.MOVIE):
    hash_value = "A" * 40
    if item_type is ItemType.MOVIE:
        radarr = FakeRadarrClient(
            [RadarrMovie(1, "Movie", "/data/movie", 100, None)],
            {1: [RadarrHistoryRecord(1, 1, "grabbed", hash_value, None)]},
        )
        sonarr = FakeSonarrClient([], {}, {}, {})
        jellyfin_items = [JellyfinItem("jf-movie", "Movie", "Movie", tmdb_id=100)]
        config = RuntimeConfig()
    else:
        radarr = FakeRadarrClient([], {})
        sonarr = FakeSonarrClient(
            [SonarrSeries(1, "Series", "/data/series", 44, 100, None, service_id="sonarr-one")],
            {1: [SonarrHistoryRecord(1, 1, 10, "grabbed", hash_value, None, None)]},
            {1: [SonarrEpisode(10, 1, 1, 1, 7, True, True)]},
            {1: [SonarrEpisodeFile(7, "/data/series/S01E01.mkv", "S01E01.mkv", 1, 100)]},
        )
        jellyfin_items = [
            JellyfinItem("jf-series", "Series", "Series", tvdb_id=44),
            JellyfinItem("jf-season-1", "Season 1", "Season", parent_id="jf-series", season_number=1),
        ]
        config = RuntimeConfig(
            sonarr=[SonarrServiceConfig(id="sonarr-one", name="Sonarr", url="http://sonarr/api", api_key="key")]
        )
    media_type = "movie" if item_type is ItemType.MOVIE else "tv"
    seerr = FakeSeerrClient([SeerrMedia(1, media_type, 100, None, None, None)], [], [])
    downloader = _SequencedDownloader(hash_value, outcome)
    jellyfin = _JellyfinFake(jellyfin_items)
    recorder = _ActivityRecorder()
    factory = DeletionStrategyFactory(
        dry_run=False,
        logger=logging.getLogger("test"),
        radarr=radarr,
        sonarr=sonarr,
        seerr=seerr,
        downloader=downloader,  # type: ignore[arg-type]
    )
    manual = ManualDeletionService(
        radarr=lambda: radarr,
        sonarr=lambda: sonarr,
        jellyfin=lambda: jellyfin,
        strategy_factory=lambda: factory,
        is_dry_run=lambda: False,
        activity_recorder=recorder,
        config=lambda: config,
    )
    repository = _CapturingRepository(
        tmp_path / f"{outcome}.db",
        lambda: (
            downloader.calls,
            tuple(downloader.deleted_hashes),
            tuple(radarr.deleted_movie_ids),
            tuple(jellyfin.deleted_items),
            _sonarr_state(sonarr),
        ),
    )
    return manual, repository, downloader, radarr, jellyfin, recorder


def _request(item_type: ItemType = ItemType.MOVIE) -> ManualDeleteRequest:
    if item_type is ItemType.MOVIE:
        return ManualDeleteRequest(item_type=item_type, radarr_movie_id=1, jellyfin_item_id="jf-movie")
    return ManualDeleteRequest(
        item_type=item_type,
        sonarr_series_id=1,
        season_number=1 if item_type is ItemType.SEASON else None,
        jellyfin_item_id="jf-season-1" if item_type is ItemType.SEASON else "jf-series",
        library_resource_id=encode_library_resource(LibraryMediaType.SERIES, "sonarr-one", 1),
    )


async def _wait_job(service: ManualDeletionJobService, job_id) -> None:  # type: ignore[no-untyped-def]
    for _ in range(300):
        if service.get(job_id).status in {ManualDeleteJobStatus.COMPLETED, ManualDeleteJobStatus.FAILED}:
            return
        await asyncio.sleep(0.01)
    raise AssertionError("manual job did not finish")


async def _wait_batch(service: ManualDeletionBatchService, batch_id) -> None:  # type: ignore[no-untyped-def]
    for _ in range(300):
        if service.get(batch_id).status.value not in {"queued", "running"}:
            return
        await asyncio.sleep(0.01)
    raise AssertionError("manual batch did not finish")


@pytest.mark.asyncio
@pytest.mark.parametrize("item_type", [ItemType.MOVIE, ItemType.SERIES, ItemType.SEASON])
async def test_manual_service_jellyfin_dependency_retries_after_transient_downloader_failure(
    tmp_path: Path,
    item_type: ItemType,
) -> None:
    manual, repository, downloader, radarr, jellyfin, recorder = _services(tmp_path, "transient", item_type)
    jobs = ManualDeletionJobService(
        manual.resolve,
        manual.preview,
        manual.execute,
        repository=repository,
        max_attempts=2,
        retry_delays_seconds=(0,),
    )
    try:
        request = _request(item_type)
        preview = await jobs.preview(request)
        queued = await jobs.submit(
            request.model_copy(update={"confirmed_plan_hash": preview.plan_hash, "idempotency_key": uuid4()})
        )
        await _wait_job(jobs, queued.id)
        result = jobs.get(queued.id)
        assert result.status is ManualDeleteJobStatus.COMPLETED
        assert result.attempt_count == 2
        retry_snapshots = [
            (snapshot, state)
            for snapshot, state in repository.snapshots
            if snapshot.status is ManualDeleteJobStatus.RETRY_WAIT
        ]
        assert retry_snapshots
        retry_snapshot, retry_state = retry_snapshots[-1]
        assert retry_snapshot.error_code == "execution_failed"
        assert retry_snapshot.result is not None
        assert any(
            action.action == "delete_item"
            and action.status.value == "skipped"
            and action.reason is not None
            and action.reason.value == "downstream_error"
            for action in retry_snapshot.result.actions
        )
        assert retry_state == (4, (), (), (), ((), (), (), ()))
        assert downloader.calls == 6
        assert downloader.deleted_hashes == ["A" * 40]
        assert radarr.deleted_movie_ids == ([1] if item_type is ItemType.MOVIE else [])
        if item_type is ItemType.SERIES:
            assert repository.snapshots[-1][1][-1] == ((), (), (), (1,))
        elif item_type is ItemType.SEASON:
            assert repository.snapshots[-1][1][-1] == ((10,), ((1, 1),), (7,), ())
        expected_jellyfin_id = (
            "jf-movie"
            if item_type is ItemType.MOVIE
            else "jf-series"
            if item_type is ItemType.SERIES
            else "jf-season-1"
        )
        assert jellyfin.deleted_items == [expected_jellyfin_id]
        assert len(recorder.records) == 2
    finally:
        await jobs.stop()


@pytest.mark.asyncio
@pytest.mark.parametrize("reason", ["sibling_scope_unknown", "shared_path"])
@pytest.mark.parametrize("item_type", [ItemType.MOVIE, ItemType.SERIES, ItemType.SEASON])
async def test_manual_service_jellyfin_dependency_safety_is_terminal(
    tmp_path: Path, reason: str, item_type: ItemType
) -> None:
    manual, repository, downloader, radarr, jellyfin, _ = _services(tmp_path, reason, item_type)
    jobs = ManualDeletionJobService(
        manual.resolve,
        manual.preview,
        manual.execute,
        repository=repository,
        max_attempts=2,
        retry_delays_seconds=(0,),
    )
    try:
        request = _request(item_type)
        preview = await jobs.preview(request)
        queued = await jobs.submit(
            request.model_copy(update={"confirmed_plan_hash": preview.plan_hash, "idempotency_key": uuid4()})
        )
        await _wait_job(jobs, queued.id)
        result = jobs.get(queued.id)
        assert result.status is ManualDeleteJobStatus.FAILED
        assert result.error_code == "unsafe_plan"
        assert result.attempt_count == 1
        assert downloader.calls == 4
        assert downloader.deleted_hashes == []
        assert radarr.deleted_movie_ids == []
        assert jellyfin.deleted_items == []
        assert repository.snapshots[-1][1][-1] == ((), (), (), ())
        assert result.result is not None
        assert any(
            action.action == "delete_item" and action.status.value == "skipped" for action in result.result.actions
        )
    finally:
        await jobs.stop()


@pytest.mark.asyncio
@pytest.mark.parametrize("item_type", [ItemType.MOVIE, ItemType.SERIES, ItemType.SEASON])
async def test_new_hash_confirmed_batch_retries_transient_jellyfin_dependency(
    tmp_path: Path, item_type: ItemType
) -> None:
    manual, repository, downloader, radarr, jellyfin, _ = _services(tmp_path, "transient", item_type)
    batches = ManualDeletionBatchService(
        manual.resolve,
        manual.preview,
        manual.execute,
        repository=repository,
        execution_lock=asyncio.Lock(),
    )
    try:
        request = _request(item_type)
        first_preview = await batches.preview([request])
        first = await batches.submit(
            ManualDeleteBatchSubmitRequest(
                children=[request],
                idempotency_key=uuid4(),
                confirmed_batch_hash=first_preview.batch_hash,
                confirmed_item_count=1,
            )
        )
        await _wait_batch(batches, first.id)
        first_result = batches.get(first.id)
        assert first_result.status.value == "failed"
        assert first_result.children[0].status is BatchChildStatus.FAILED
        assert first_result.children[0].error_code == "partial_result"
        assert first_result.children[0].result is not None
        assert _execution_result_block_code(first_result.children[0].result) == "execution_failed"
        assert any(
            action.action == "delete_item"
            and action.status.value == "skipped"
            and action.reason is not None
            and action.reason.value == "downstream_error"
            for action in first_result.children[0].result.actions
        )
        assert downloader.calls == 4
        assert downloader.deleted_hashes == []
        assert radarr.deleted_movie_ids == []
        assert jellyfin.deleted_items == []
        assert repository.batch_states[-1][-1] == ((), (), (), ())

        second_preview = await batches.preview([request])
        second = await batches.submit(
            ManualDeleteBatchSubmitRequest(
                children=[request],
                idempotency_key=uuid4(),
                confirmed_batch_hash=second_preview.batch_hash,
                confirmed_item_count=1,
            )
        )
        await _wait_batch(batches, second.id)
        second_result = batches.get(second.id)
        assert second_result.status.value == "completed"
        assert second_result.children[0].status is BatchChildStatus.COMPLETED
        assert downloader.calls == 8
        assert downloader.deleted_hashes == ["A" * 40]
        assert radarr.deleted_movie_ids == ([1] if item_type is ItemType.MOVIE else [])
        if item_type is ItemType.SERIES:
            assert repository.batch_states[-1][-1] == ((), (), (), (1,))
        elif item_type is ItemType.SEASON:
            assert repository.batch_states[-1][-1] == ((10,), ((1, 1),), (7,), ())
        expected_jellyfin_id = (
            "jf-movie"
            if item_type is ItemType.MOVIE
            else "jf-series"
            if item_type is ItemType.SERIES
            else "jf-season-1"
        )
        assert jellyfin.deleted_items == [expected_jellyfin_id]
    finally:
        await batches.stop()


@pytest.mark.asyncio
@pytest.mark.parametrize("reason", ["sibling_scope_unknown", "shared_path"])
@pytest.mark.parametrize("item_type", [ItemType.MOVIE, ItemType.SERIES, ItemType.SEASON])
async def test_safety_dependency_is_terminal_for_batch_without_mutation(
    tmp_path: Path, reason: str, item_type: ItemType
) -> None:
    manual, repository, downloader, radarr, jellyfin, _ = _services(tmp_path, reason, item_type)
    batches = ManualDeletionBatchService(
        manual.resolve,
        manual.preview,
        manual.execute,
        repository=repository,
        execution_lock=asyncio.Lock(),
    )
    try:
        request = _request(item_type)
        preview = await batches.preview([request])
        queued = await batches.submit(
            ManualDeleteBatchSubmitRequest(
                children=[request],
                idempotency_key=uuid4(),
                confirmed_batch_hash=preview.batch_hash,
                confirmed_item_count=1,
            )
        )
        await _wait_batch(batches, queued.id)
        result = batches.get(queued.id)
        child = result.children[0]
        assert child.status is BatchChildStatus.FAILED
        assert child.error_code == "unsafe_result"
        assert child.result is not None
        assert _execution_result_block_code(child.result) == "unsafe_result"
        assert any(
            action.action == "delete_item" and action.status.value == "skipped" for action in child.result.actions
        )
        assert downloader.calls == 4
        assert downloader.deleted_hashes == []
        assert radarr.deleted_movie_ids == []
        assert jellyfin.deleted_items == []
        assert repository.batch_states[-1][-1] == ((), (), (), ())
    finally:
        await batches.stop()
