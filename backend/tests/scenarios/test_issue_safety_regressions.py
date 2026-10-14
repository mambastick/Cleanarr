"""Regressions for loss of audit evidence and shared movie downloads."""

import logging

import pytest

from cleanarr.application.strategies import DeletionStrategyFactory
from cleanarr.domain import (
    ActionStatus,
    AuthenticationError,
    ContentScopeBlocker,
    DownloaderRemovalResult,
    ExternalServiceError,
    FailureReason,
    ItemType,
    MediaDeletionEvent,
    MediaFingerprint,
    RadarrHistoryRecord,
    RadarrMovie,
    SeerrMedia,
    SonarrEpisode,
    SonarrHistoryRecord,
    SonarrSeries,
)
from tests.fakes import FakeDownloaderClient, FakeRadarrClient, FakeSeerrClient, FakeSonarrClient


def fixture(kind):
    radarr = FakeRadarrClient(
        [RadarrMovie(1, "Movie", "/media/movie", 1, None)], {1: [RadarrHistoryRecord(1, 1, "grabbed", "ABC", None)]}
    )
    sonarr = FakeSonarrClient(
        [SonarrSeries(1, "Series", "/media/series", 2, 1, None)],
        {1: [SonarrHistoryRecord(1, 1, 10, "grabbed", "ABC", None, None)]},
        {1: [SonarrEpisode(10, 1, 1, 1, 20, True, True)]},
        {},
    )
    seerr = FakeSeerrClient([SeerrMedia(1, "movie" if kind is ItemType.MOVIE else "tv", 1, 2, None, None)], [], [])
    downloader = FakeDownloaderClient({"ABC"})
    factory = DeletionStrategyFactory(
        dry_run=False,
        logger=logging.getLogger("tests"),
        radarr=radarr,
        sonarr=sonarr,
        seerr=seerr,
        downloader=downloader,
    )
    event = MediaDeletionEvent(
        "ItemDeleted", kind, "id", "Title", MediaFingerprint(tmdb_id=1), season_number=1, episode_number=1
    )
    return factory, event, radarr, seerr, downloader


@pytest.mark.parametrize("kind", list(ItemType))
@pytest.mark.parametrize("read", ["list_media", "list_requests", "list_issues"])
@pytest.mark.parametrize(
    "error",
    [ExternalServiceError("seerr", "Unavailable"), AuthenticationError("seerr", "Denied"), RuntimeError("Unexpected")],
)
async def test_late_seerr_read_preserves_every_mutation(kind, read, error):
    factory, event, _, seerr, downloader = fixture(kind)

    async def fail():
        raise error

    setattr(seerr, read, fail)
    result = await factory.for_item_type(kind).handle(event)
    assert result.status.value == "partial_failure"
    assert downloader.deleted_hashes == ["ABC"]
    assert any(a.action == "delete_hash" and a.status is ActionStatus.DELETED for a in result.actions)
    assert any(a.system in {"radarr", "sonarr"} and a.status is ActionStatus.DELETED for a in result.actions)
    failure = next(a for a in result.actions if a.system == "seerr" and a.status is ActionStatus.FAILED)
    assert failure.action == ("resolve_media" if read == "list_media" else read)
    assert failure.reason is (
        FailureReason.AUTHENTICATION_FAILED
        if isinstance(error, AuthenticationError)
        else FailureReason.DOWNSTREAM_ERROR
    )


@pytest.mark.parametrize("failing_history", [False, True])
async def test_shared_movie_hash_or_unreadable_history_blocks_entire_cascade(failing_history):
    factory, event, radarr, seerr, downloader = fixture(ItemType.MOVIE)
    radarr.movies.append(RadarrMovie(2, "Other", "/media/other", 2, None))
    radarr.history_by_movie[2] = [RadarrHistoryRecord(2, 2, "downloadFolderImported", "abc", None)]
    original = radarr.list_download_history

    async def history(download_id):
        if failing_history:
            raise ExternalServiceError("radarr", "Unreadable history")
        return await original(download_id)

    radarr.list_download_history = history
    for dry_run in (True, False):
        result = await factory.for_item_type(ItemType.MOVIE, dry_run=dry_run).handle(event)
        assert any(
            a.reason is (FailureReason.OWNERSHIP_UNVERIFIABLE if failing_history else FailureReason.PACK_TORRENT)
            for a in result.actions
        )
    assert downloader.deleted_hashes == radarr.deleted_movie_ids == seerr.deleted_media_ids == []


@pytest.mark.parametrize("reason", [FailureReason.SIBLING_SCOPE_UNKNOWN, FailureReason.TORRENT_CLOSED])
async def test_structured_scope_blockers_prevent_dependent_media_cleanup(reason):
    factory, event, radarr, seerr, downloader = fixture(ItemType.MOVIE)

    async def blocked(hashes, *, delete_files, dry_run=False):
        return [
            DownloaderRemovalResult(
                hash_value="ABC",
                existed=True,
                client_id="target-client",
                client_kind="rtorrent",
                skip_reason=reason.value,
                blocking_torrents=(ContentScopeBlocker("sibling-client", "B" * 40, "Unverified sibling"),)
                if reason is FailureReason.SIBLING_SCOPE_UNKNOWN
                else (),
            )
        ]

    downloader.delete_hashes = blocked
    for dry_run in (True, False):
        result = await factory.for_item_type(ItemType.MOVIE, dry_run=dry_run).handle(event)
        action = next(action for action in result.actions if action.action == "delete_hash")
        assert action.status is ActionStatus.SKIPPED
        assert action.reason is reason
        if reason is FailureReason.SIBLING_SCOPE_UNKNOWN:
            assert action.details["blocking_torrents"] == [
                {"downloader_id": "sibling-client", "hash": "B" * 40, "torrent_name": "Unverified sibling"}
            ]
    assert downloader.deleted_hashes == radarr.deleted_movie_ids == seerr.deleted_media_ids == []
