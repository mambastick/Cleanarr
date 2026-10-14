"""The production router's negative identities remain valid through cleanup."""

import logging

import pytest

from cleanarr.application.strategies import MovieDeletionStrategy
from cleanarr.domain import (
    ActionStatus,
    FailureReason,
    ItemType,
    MediaDeletionEvent,
    MediaFingerprint,
    RadarrHistoryRecord,
    RadarrMovie,
)
from cleanarr.infrastructure.routers import MultiRadarrClient, RadarrTarget
from tests.fakes import FakeDownloaderClient, FakeRadarrClient, FakeSeerrClient


@pytest.mark.asyncio
@pytest.mark.parametrize("instances", [1, 2])
async def test_movie_cleanup_through_real_router_preserves_routed_identity(instances: int) -> None:
    target_hash = "A" * 40
    first = FakeRadarrClient(
        [RadarrMovie(1, "Movie", "/data/movie", 100, None)],
        {1: [RadarrHistoryRecord(1, 1, "grabbed", target_hash, None)]},
    )
    second = FakeRadarrClient(
        [RadarrMovie(1, "Other", "/data/other", 200, None)],
        {1: [RadarrHistoryRecord(1, 1, "grabbed", "B" * 40, None)]},
    )
    targets = [RadarrTarget("first", "First", first)]
    if instances == 2:
        targets.append(RadarrTarget("second", "Second", second))
    router = MultiRadarrClient(targets)
    movies = await router.list_movies()
    assert movies[0].id < 0
    if instances == 2:
        assert movies[0].id != movies[1].id
    downloader = FakeDownloaderClient({target_hash})
    strategy = MovieDeletionStrategy(
        radarr=router,
        dry_run=False,
        logger=logging.getLogger("test"),
        seerr=FakeSeerrClient([], [], []),
        downloader=downloader,
    )
    event = MediaDeletionEvent("ItemDeleted", ItemType.MOVIE, "source-id", "Movie", MediaFingerprint(tmdb_id=100))

    result = await strategy.handle(event)

    assert first.deleted_movie_ids == [1]
    assert second.deleted_movie_ids == []
    assert downloader.deleted_hashes == [target_hash]
    assert any(action.action == "delete_movie" and action.status is ActionStatus.DELETED for action in result.actions)
    assert not any(action.reason is FailureReason.OWNERSHIP_UNVERIFIABLE for action in result.actions)


@pytest.mark.asyncio
async def test_router_keeps_pack_block_when_raw_movie_ids_collide_across_instances() -> None:
    target_hash = "A" * 40
    first = FakeRadarrClient(
        [RadarrMovie(1, "Movie", "/data/movie", 100, None)],
        {1: [RadarrHistoryRecord(1, 1, "grabbed", target_hash, None)]},
    )
    second = FakeRadarrClient(
        [RadarrMovie(1, "Other", "/data/other", 200, None)],
        {1: [RadarrHistoryRecord(1, 1, "grabbed", target_hash, None)]},
    )
    router = MultiRadarrClient([RadarrTarget("first", "First", first), RadarrTarget("second", "Second", second)])
    downloader = FakeDownloaderClient({target_hash})
    strategy = MovieDeletionStrategy(
        radarr=router,
        dry_run=False,
        logger=logging.getLogger("test"),
        seerr=FakeSeerrClient([], [], []),
        downloader=downloader,
    )
    event = MediaDeletionEvent("ItemDeleted", ItemType.MOVIE, "source-id", "Movie", MediaFingerprint(tmdb_id=100))

    result = await strategy.handle(event)

    assert first.deleted_movie_ids == second.deleted_movie_ids == downloader.deleted_hashes == []
    assert any(action.reason is FailureReason.PACK_TORRENT for action in result.actions)


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid_id", [0, True, 1.0, "1"])
async def test_malformed_history_identity_cannot_authorize_cleanup(invalid_id) -> None:
    target_hash = "A" * 40
    radarr = FakeRadarrClient(
        [RadarrMovie(1, "Movie", "/data/movie", 100, None)],
        {1: [RadarrHistoryRecord(1, 1, "grabbed", target_hash, None)]},
    )

    async def invalid_history(download_id):
        return [RadarrHistoryRecord(1, invalid_id, "grabbed", target_hash, None)]

    radarr.list_download_history = invalid_history
    downloader = FakeDownloaderClient({target_hash})
    strategy = MovieDeletionStrategy(
        radarr=radarr,
        dry_run=False,
        logger=logging.getLogger("test"),
        seerr=FakeSeerrClient([], [], []),
        downloader=downloader,
    )
    event = MediaDeletionEvent("ItemDeleted", ItemType.MOVIE, "source-id", "Movie", MediaFingerprint(tmdb_id=100))

    result = await strategy.handle(event)

    assert radarr.deleted_movie_ids == downloader.deleted_hashes == []
    assert any(action.reason is FailureReason.OWNERSHIP_UNVERIFIABLE for action in result.actions)
