"""Tests for the top-level service."""

from dataclasses import dataclass

import pytest

from cleanarr.application.service import CascadeDeletionService
from cleanarr.application.strategies import DeletionStrategyFactory
from cleanarr.domain import (
    ActionStatus,
    ExternalServiceError,
    FailureReason,
    ItemType,
    JellyfinItem,
    MediaDeletionEvent,
    MediaFingerprint,
)
from tests.fakes import FakeDownloaderClient, FakeJellyseerrClient, FakeRadarrClient, FakeSonarrClient


@dataclass
class _FakeJellyfinClient:
    items: list[JellyfinItem]
    error: Exception | None = None

    async def list_items(self, *, include_types: list[str]) -> list[JellyfinItem]:
        if self.error is not None:
            raise self.error
        return [item for item in self.items if item.type in include_types]


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


@pytest.mark.asyncio
async def test_service_blocks_series_cascade_when_item_reappears_after_move() -> None:
    sonarr = FakeSonarrClient(
        series=[],
        history_by_series={},
        episodes_by_series={},
        episode_files_by_series={},
    )
    jellyseerr = FakeJellyseerrClient(media=[], requests=[], issues=[])
    downloader = FakeDownloaderClient(existing_hashes=set())
    strategy_factory = DeletionStrategyFactory(
        dry_run=False,
        logger=__import__("logging").getLogger("test"),
        radarr=FakeRadarrClient(movies=[], history_by_movie={}),
        sonarr=sonarr,
        jellyseerr=jellyseerr,
        downloader=downloader,
    )
    service = CascadeDeletionService(
        strategy_factory,
        jellyfin=_FakeJellyfinClient(
            items=[
                JellyfinItem(
                    id="new-jellyfin-id",
                    name="Scooby-Doo! Mystery Incorporated",
                    type="Series",
                    tvdb_id=174681,
                    tmdb_id=18123,
                    imdb_id="tt1660055",
                )
            ]
        ),
    )

    result = await service.process(
        MediaDeletionEvent(
            notification_type="ItemDeleted",
            item_type=ItemType.SERIES,
            item_id="old-jellyfin-id",
            name="Scooby-Doo! Mystery Incorporated",
            fingerprint=MediaFingerprint(
                tvdb_id=174681,
                tmdb_id=18123,
                imdb_id="tt1660055",
                path="/data/media/series/Scooby-Doo! Mystery Incorporated (2010) [tvdbid-174681]",
            ),
        )
    )

    assert result.status.value == "ignored"
    assert result.actions[0].action == "confirm_deletion"
    assert result.actions[0].reason == FailureReason.SOURCE_STILL_PRESENT
    assert sonarr.deleted_series_ids == []
    assert jellyseerr.deleted_request_ids == []
    assert jellyseerr.deleted_media_ids == []
    assert downloader.deleted_hashes == []


@pytest.mark.asyncio
async def test_service_fails_closed_when_jellyfin_presence_check_fails() -> None:
    service = CascadeDeletionService(
        _FailingStrategyFactory(),  # type: ignore[arg-type]
        jellyfin=_FakeJellyfinClient(
            items=[],
            error=ExternalServiceError("jellyfin", "temporarily unavailable"),
        ),
    )

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
    assert result.actions[0].action == "confirm_deletion"
    assert result.actions[0].status == ActionStatus.FAILED
    assert result.actions[0].reason == FailureReason.DOWNSTREAM_ERROR
