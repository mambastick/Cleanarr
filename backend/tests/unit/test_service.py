"""Tests for the top-level service."""

import pytest

from cleanarr.application.service import CascadeDeletionService
from cleanarr.application.strategies import DeletionStrategyFactory
from cleanarr.domain import (
    ActionStatus,
    ExternalServiceError,
    FailureReason,
    ItemType,
    MediaDeletionEvent,
    MediaFingerprint,
)
from tests.fakes import FakeDownloaderClient, FakeJellyseerrClient, FakeRadarrClient, FakeSonarrClient


@pytest.mark.asyncio
async def test_service_ignores_non_item_deleted_events() -> None:
    strategy_factory = DeletionStrategyFactory(
        dry_run=False,
        logger=__import__("logging").getLogger("test"),
        radarr=FakeRadarrClient(movies=[], history_by_movie={}),
        sonarr=FakeSonarrClient(series=[], history_by_series={}, episodes_by_series={}, episode_files_by_series={}),
        jellyseerr=FakeJellyseerrClient(media=[], requests=[], issues=[]),
        downloader=FakeDownloaderClient(existing_hashes=set()),
    )
    service = CascadeDeletionService(strategy_factory)

    result = await service.process(
        MediaDeletionEvent(
            notification_type="ItemAdded",
            item_type=ItemType.MOVIE,
            item_id="abc",
            name="Movie",
            fingerprint=MediaFingerprint(tmdb_id=1),
        )
    )

    assert result.status.value == "ignored"
    assert result.actions[0].status == ActionStatus.IGNORED


class _FailingStrategy:
    async def handle(self, event: MediaDeletionEvent):  # type: ignore[no-untyped-def]
        raise ExternalServiceError("jellyseerr", "downstream exploded")


class _FailingStrategyFactory:
    def for_item_type(self, item_type: ItemType) -> _FailingStrategy:
        return _FailingStrategy()


@pytest.mark.asyncio
async def test_service_turns_downstream_errors_into_partial_failure() -> None:
    service = CascadeDeletionService(_FailingStrategyFactory())  # type: ignore[arg-type]

    result = await service.process(
        MediaDeletionEvent(
            notification_type="ItemDeleted",
            item_type=ItemType.MOVIE,
            item_id="abc",
            name="Movie",
            fingerprint=MediaFingerprint(tmdb_id=1),
        )
    )

    assert result.status.value == "partial_failure"
    assert result.actions[0].status == ActionStatus.FAILED
    assert result.actions[0].reason == FailureReason.DOWNSTREAM_ERROR
