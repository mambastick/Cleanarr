"""Deletion-plan metadata propagation tests."""

from __future__ import annotations

import logging

import pytest

from cleanarr.application.deletion_jobs import plan_hash
from cleanarr.application.deletion_models import ProcessingResultResponse
from cleanarr.application.results import ActionCollector
from cleanarr.application.strategies import BaseDeletionStrategy
from cleanarr.domain import (
    ActionStatus,
    DownloaderRemovalResult,
    ItemType,
    MediaDeletionEvent,
    MediaFingerprint,
    ProcessingResult,
)
from tests.fakes import FakeSeerrClient


class _MetadataDownloader:
    def __init__(self, result: DownloaderRemovalResult) -> None:
        self._result = result
        self.calls: list[tuple[list[str], bool, bool]] = []

    async def delete_hashes(
        self,
        hashes: list[str],
        *,
        delete_files: bool,
        dry_run: bool = False,
    ) -> list[DownloaderRemovalResult]:
        self.calls.append((hashes, delete_files, dry_run))
        return [self._result]


class _MetadataStrategy(BaseDeletionStrategy):
    async def handle(self, event: MediaDeletionEvent) -> ProcessingResult:
        raise NotImplementedError


def _strategy(*, dry_run: bool, downloader: _MetadataDownloader) -> _MetadataStrategy:
    return _MetadataStrategy(
        dry_run=dry_run,
        logger=logging.getLogger("tests.deletion-plan-metadata"),
        seerr=FakeSeerrClient(media=[], requests=[], issues=[]),
        downloader=downloader,
    )


def _collector() -> ActionCollector:
    return ActionCollector(
        MediaDeletionEvent(
            notification_type="ItemDeleted",
            item_type=ItemType.MOVIE,
            item_id="movie-1",
            name="Movie",
            fingerprint=MediaFingerprint(tmdb_id=1),
        )
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("dry_run", "expected_status"),
    [(False, ActionStatus.DELETED), (True, ActionStatus.DRY_RUN)],
)
async def test_cleanup_hashes_propagates_metadata_for_success_and_dry_run(
    dry_run: bool, expected_status: ActionStatus
) -> None:
    downloader = _MetadataDownloader(
        DownloaderRemovalResult(
            hash_value="A" * 40,
            existed=True,
            client_kind="qbittorrent",
            torrent_name="Example release",
            content_path="/downloads/Example release",
            delete_files=True,
        )
    )
    collector = _collector()

    ready = await _strategy(dry_run=dry_run, downloader=downloader)._cleanup_hashes(collector, {"A" * 40})

    assert ready is True
    assert downloader.calls == [(["A" * 40], True, dry_run)]
    action = collector.build().actions[0]
    assert action.status is expected_status
    assert action.details["torrent_name"] == "Example release"
    assert action.details["content_path"] == "/downloads/Example release"
    assert action.details["download_directory"] is None
    assert action.details["delete_files"] is True


@pytest.mark.asyncio
async def test_cleanup_hashes_propagates_retained_and_failed_metadata() -> None:
    retained = _MetadataDownloader(
        DownloaderRemovalResult(
            hash_value="B" * 40,
            existed=True,
            client_kind="transmission",
            skip_reason="Torrent retained by the configured keep policy.",
            torrent_name="Retained release",
            download_directory="/downloads/retained",
            delete_files=False,
        )
    )
    retained_collector = _collector()

    assert await _strategy(dry_run=False, downloader=retained)._cleanup_hashes(retained_collector, {"B" * 40})
    retained_action = retained_collector.build().actions[0]
    assert retained_action.status is ActionStatus.SKIPPED
    assert retained_action.details["torrent_name"] == "Retained release"
    assert retained_action.details["content_path"] is None
    assert retained_action.details["download_directory"] == "/downloads/retained"
    assert retained_action.details["delete_files"] is False

    failed = _MetadataDownloader(
        DownloaderRemovalResult(
            hash_value="C" * 40,
            existed=True,
            client_kind="rtorrent",
            error="rTorrent remove failed",
            torrent_name="Failed release",
            content_path="/downloads/failed",
            delete_files=None,
        )
    )
    failed_collector = _collector()

    assert not await _strategy(dry_run=False, downloader=failed)._cleanup_hashes(failed_collector, {"C" * 40})
    failed_action = failed_collector.build().actions[0]
    assert failed_action.status is ActionStatus.FAILED
    assert failed_action.details["torrent_name"] == "Failed release"
    assert failed_action.details["content_path"] == "/downloads/failed"
    assert failed_action.details["download_directory"] is None
    assert failed_action.details["delete_files"] is None


def test_metadata_round_trips_and_remains_part_of_the_plan_hash() -> None:
    collector = _collector()
    collector.add(
        "qbittorrent",
        "delete_hash",
        ActionStatus.DELETED,
        "Deleted torrent hash.",
        hash="A" * 40,
        torrent_name="Example release",
        content_path="/downloads/Example release",
        download_directory=None,
        delete_files=True,
    )
    result = collector.build()
    response = ProcessingResultResponse.from_domain(result)

    restored = response.to_domain(result.event)
    assert restored.actions[0].details["torrent_name"] == "Example release"
    assert restored.actions[0].details["content_path"] == "/downloads/Example release"
    assert restored.actions[0].details["download_directory"] is None
    assert restored.actions[0].details["delete_files"] is True

    original_hash = plan_hash(response)
    changed_path = response.model_copy(deep=True)
    changed_path.actions[0].details["content_path"] = "/downloads/changed"
    changed_file_effect = response.model_copy(deep=True)
    changed_file_effect.actions[0].details["delete_files"] = False

    assert plan_hash(changed_path) != original_hash
    assert plan_hash(changed_file_effect) != original_hash
