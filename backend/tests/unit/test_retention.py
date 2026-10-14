"""Retention evidence tests for the bounded deletion path."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

import pytest

from cleanarr.application.results import ActionCollector
from cleanarr.application.strategies import BaseDeletionStrategy, MovieDeletionStrategy
from cleanarr.domain import (
    ActionStatus,
    DownloaderRemovalResult,
    ItemType,
    MediaDeletionEvent,
    MediaFingerprint,
    RadarrHistoryRecord,
    RadarrMovie,
    RetainedTorrent,
)
from cleanarr.domain.config import TorrentRemovalPolicy
from cleanarr.infrastructure.retention_repository import SqliteRetentionRepository
from tests.fakes import FakeRadarrClient, FakeSeerrClient


class _Downloader:
    def __init__(self, result: DownloaderRemovalResult) -> None:
        self.result = result
        self.calls: list[bool] = []

    async def delete_hashes(self, hashes: list[str], *, delete_files: bool, dry_run: bool = False):  # type: ignore[no-untyped-def]
        self.calls.append(dry_run)
        return [self.result]


class _Recorder:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.records: list[RetainedTorrent] = []

    async def record_retention(self, record: RetainedTorrent) -> None:
        if self.error:
            raise self.error
        self.records.append(record)


class _Strategy(BaseDeletionStrategy):
    async def _handle(self, event: MediaDeletionEvent, collector: ActionCollector):  # type: ignore[no-untyped-def]
        return collector.build()


def _event() -> MediaDeletionEvent:
    return MediaDeletionEvent(
        notification_type="ItemDeleted",
        item_type=ItemType.MOVIE,
        item_id="jellyfin-1",
        name="Movie",
        fingerprint=MediaFingerprint(tmdb_id=42, imdb_id="TT123"),
    )


def _collector() -> ActionCollector:
    return ActionCollector(_event(), correlation_id="corr-1")


def _strategy(downloader: _Downloader, recorder: _Recorder | None, *, dry_run: bool = False) -> _Strategy:
    return _Strategy(
        dry_run=dry_run,
        logger=logging.getLogger("tests.retention"),
        seerr=FakeSeerrClient(media=[], requests=[], issues=[]),
        downloader=downloader,
        retention=recorder,
        retention_thresholds={"client-a": (1.5, 90)},
    )


@pytest.mark.asyncio
async def test_dry_run_does_not_create_retention_record() -> None:
    recorder = _Recorder()
    downloader = _Downloader(
        DownloaderRemovalResult(
            hash_value="A" * 40,
            existed=True,
            client_id="client-a",
            client_kind="qbittorrent",
            skip_reason="retained",
            seeding_policy="keep",
        )
    )

    ready = await _strategy(downloader, recorder, dry_run=True)._cleanup_hashes(
        _collector(), {"A" * 40}, event=_event()
    )

    assert ready is True
    assert recorder.records == []
    assert downloader.calls == [True]


@pytest.mark.asyncio
async def test_retention_is_persisted_before_cascade_can_continue() -> None:
    recorder = _Recorder()
    downloader = _Downloader(
        DownloaderRemovalResult(
            hash_value="B" * 40,
            existed=True,
            client_id="client-a",
            client_kind="transmission",
            skip_reason="deferred",
            seeding_policy="defer",
        )
    )
    collector = _collector()

    assert await _strategy(downloader, recorder)._cleanup_hashes(collector, {"B" * 40}, event=_event())
    assert recorder.records[0].policy is TorrentRemovalPolicy.DEFER
    assert recorder.records[0].provider_ids == {"tmdb_id": 42, "imdb_id": "TT123"}
    assert recorder.records[0].min_seed_ratio == 1.5
    assert recorder.records[0].min_seed_time_minutes == 90
    assert collector.build().actions[-1].status is ActionStatus.SKIPPED


@pytest.mark.asyncio
async def test_retention_failure_blocks_dependent_cleanup() -> None:
    recorder = _Recorder(RuntimeError("database unavailable"))
    downloader = _Downloader(
        DownloaderRemovalResult(
            hash_value="C" * 40,
            existed=True,
            client_id="client-a",
            client_kind="deluge",
            skip_reason="deferred",
            seeding_policy="defer",
        )
    )
    collector = _collector()

    assert not await _strategy(downloader, recorder)._cleanup_hashes(collector, {"C" * 40}, event=_event())
    action = collector.build().actions[0]
    assert action.action == "record_retention"
    assert action.status is ActionStatus.FAILED


@pytest.mark.asyncio
async def test_retention_failure_blocks_arr_removal() -> None:
    radarr = FakeRadarrClient(
        movies=[RadarrMovie(id=1, title="Movie", path="/movies/movie", tmdb_id=42, imdb_id=None)],
        history_by_movie={
            1: [
                RadarrHistoryRecord(
                    id=1,
                    movie_id=1,
                    event_type="grabbed",
                    download_id="E" * 40,
                    imported_path="/movies/movie/file.mkv",
                )
            ]
        },
    )
    downloader = _Downloader(
        DownloaderRemovalResult(
            hash_value="E" * 40,
            existed=True,
            client_id="client-a",
            client_kind="qbittorrent",
            skip_reason="deferred",
            seeding_policy="defer",
        )
    )
    strategy = MovieDeletionStrategy(
        dry_run=False,
        logger=logging.getLogger("tests.retention.cascade"),
        radarr=radarr,
        seerr=FakeSeerrClient(media=[], requests=[], issues=[]),
        downloader=downloader,
        retention=_Recorder(RuntimeError("database unavailable")),
    )

    result = await strategy.handle(_event())

    assert result.status.value == "partial_failure"
    assert radarr.deleted_movie_ids == []


@pytest.mark.asyncio
async def test_retention_repository_survives_restart(tmp_path: Path) -> None:
    path = tmp_path / "cleanarr.db"
    record = RetainedTorrent(
        client_id="client-a",
        info_hash="D" * 40,
        policy=TorrentRemovalPolicy.KEEP,
        correlation_id="corr-2",
        provider_ids={"tvdb_id": 7},
        item_scope="Series:season:2",
        retained_at=datetime.now(UTC),
        min_seed_ratio=None,
        min_seed_time_minutes=120,
    )
    await SqliteRetentionRepository(path).record_retention(record)
    projection = SqliteRetentionRepository(path).latest_retention_projections({("client-a", "D" * 40)})

    assert projection[("client-a", "D" * 40)]["policy"] == "keep"
    assert projection[("client-a", "D" * 40)]["correlation_id"] == "corr-2"
    assert projection[("client-a", "D" * 40)]["min_seed_time_minutes"] == 120
