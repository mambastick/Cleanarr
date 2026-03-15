"""Scenario tests for end-to-end deletion logic."""

from __future__ import annotations

import logging

import pytest

from cleanarr.application.service import CascadeDeletionService
from cleanarr.application.strategies import DeletionStrategyFactory
from cleanarr.domain import (
    ActionStatus,
    ItemType,
    JellyseerrIssue,
    JellyseerrMedia,
    JellyseerrRequest,
    MediaDeletionEvent,
    MediaFingerprint,
    RadarrHistoryRecord,
    RadarrMovie,
    SonarrEpisode,
    SonarrHistoryRecord,
    SonarrSeries,
)
from tests.fakes import FakeDownloaderClient, FakeJellyseerrClient, FakeRadarrClient, FakeSonarrClient


def build_service(
    *,
    radarr: FakeRadarrClient | None = None,
    sonarr: FakeSonarrClient | None = None,
    jellyseerr: FakeJellyseerrClient | None = None,
    downloader: FakeDownloaderClient | None = None,
) -> CascadeDeletionService:
    factory = DeletionStrategyFactory(
        dry_run=False,
        logger=logging.getLogger("tests.scenarios"),
        radarr=radarr or FakeRadarrClient(movies=[], history_by_movie={}),
        sonarr=sonarr
        or FakeSonarrClient(series=[], history_by_series={}, episodes_by_series={}, episode_files_by_series={}),
        jellyseerr=jellyseerr or FakeJellyseerrClient(media=[], requests=[], issues=[]),
        downloader=downloader or FakeDownloaderClient(existing_hashes=set()),
    )
    return CascadeDeletionService(factory)


@pytest.mark.asyncio
async def test_movie_delete_cleans_radarr_jellyseerr_and_downloader() -> None:
    radarr = FakeRadarrClient(
        movies=[RadarrMovie(id=1, title="Movie", path="/data/movie", tmdb_id=100, imdb_id="tt100")],
        history_by_movie={
            1: [
                RadarrHistoryRecord(id=1, movie_id=1, event_type="grabbed", download_id="HASH100", imported_path=None),
            ]
        },
    )
    jellyseerr = FakeJellyseerrClient(
        media=[
            JellyseerrMedia(
                id=11, media_type="movie", tmdb_id=100, tvdb_id=None, imdb_id="tt100", jellyfin_media_id=None
            )
        ],
        requests=[
            JellyseerrRequest(
                id=21,
                media_id=11,
                media_type="movie",
                season_numbers=(),
                is_4k=False,
                server_id=0,
                profile_id=1,
                root_folder="/data/movie",
                language_profile_id=None,
                requested_by_id=1,
                tags=(),
            )
        ],
        issues=[JellyseerrIssue(id=31, media_id=11, problem_season=None, problem_episode=None)],
    )
    downloader = FakeDownloaderClient(existing_hashes={"HASH100"})
    service = build_service(radarr=radarr, jellyseerr=jellyseerr, downloader=downloader)

    result = await service.process(
        MediaDeletionEvent(
            notification_type="ItemDeleted",
            item_type=ItemType.MOVIE,
            item_id="movie-1",
            name="Movie",
            fingerprint=MediaFingerprint(tmdb_id=100, imdb_id="tt100"),
        )
    )

    assert result.status.value == "success"
    assert radarr.deleted_movie_ids == [1]
    assert downloader.deleted_hashes == ["HASH100"]
    assert jellyseerr.deleted_request_ids == [21]
    assert jellyseerr.deleted_issue_ids == [31]
    assert jellyseerr.deleted_media_ids == [11]


@pytest.mark.asyncio
async def test_series_delete_removes_full_series_and_related_requests() -> None:
    sonarr = FakeSonarrClient(
        series=[SonarrSeries(id=5, title="Series", path="/data/series", tvdb_id=200, tmdb_id=300, imdb_id="tt300")],
        history_by_series={
            5: [
                SonarrHistoryRecord(
                    id=1,
                    series_id=5,
                    episode_id=1001,
                    event_type="grabbed",
                    download_id="SERIESA",
                    imported_path=None,
                    release_type=None,
                ),
                SonarrHistoryRecord(
                    id=2,
                    series_id=5,
                    episode_id=1002,
                    event_type="grabbed",
                    download_id="SERIESB",
                    imported_path=None,
                    release_type=None,
                ),
            ]
        },
        episodes_by_series={
            5: [
                SonarrEpisode(
                    id=1001,
                    series_id=5,
                    season_number=1,
                    episode_number=1,
                    episode_file_id=501,
                    has_file=True,
                    monitored=True,
                ),
                SonarrEpisode(
                    id=1002,
                    series_id=5,
                    season_number=1,
                    episode_number=2,
                    episode_file_id=502,
                    has_file=True,
                    monitored=True,
                ),
            ]
        },
        episode_files_by_series={5: []},
    )
    jellyseerr = FakeJellyseerrClient(
        media=[
            JellyseerrMedia(id=50, media_type="tv", tmdb_id=300, tvdb_id=200, imdb_id="tt300", jellyfin_media_id=None)
        ],
        requests=[
            JellyseerrRequest(
                id=60,
                media_id=50,
                media_type="tv",
                season_numbers=(1,),
                is_4k=False,
                server_id=0,
                profile_id=1,
                root_folder="/data/series",
                language_profile_id=None,
                requested_by_id=1,
                tags=(),
            )
        ],
        issues=[JellyseerrIssue(id=61, media_id=50, problem_season=1, problem_episode=1)],
    )
    downloader = FakeDownloaderClient(existing_hashes={"SERIESA", "SERIESB"})
    service = build_service(sonarr=sonarr, jellyseerr=jellyseerr, downloader=downloader)

    result = await service.process(
        MediaDeletionEvent(
            notification_type="ItemDeleted",
            item_type=ItemType.SERIES,
            item_id="series-5",
            name="Series",
            fingerprint=MediaFingerprint(tvdb_id=200, tmdb_id=300, imdb_id="tt300"),
        )
    )

    assert result.status.value == "success"
    assert sonarr.deleted_series_ids == [5]
    assert set(downloader.deleted_hashes) == {"SERIESA", "SERIESB"}
    assert jellyseerr.deleted_request_ids == [60]
    assert jellyseerr.deleted_issue_ids == [61]
    assert jellyseerr.deleted_media_ids == [50]


@pytest.mark.asyncio
async def test_season_delete_updates_only_matching_season_request() -> None:
    sonarr = FakeSonarrClient(
        series=[SonarrSeries(id=8, title="Show", path="/data/show", tvdb_id=800, tmdb_id=801, imdb_id=None)],
        history_by_series={
            8: [
                SonarrHistoryRecord(
                    id=1,
                    series_id=8,
                    episode_id=201,
                    event_type="grabbed",
                    download_id="S2HASH1",
                    imported_path=None,
                    release_type=None,
                ),
                SonarrHistoryRecord(
                    id=2,
                    series_id=8,
                    episode_id=202,
                    event_type="grabbed",
                    download_id="S2HASH2",
                    imported_path=None,
                    release_type=None,
                ),
                SonarrHistoryRecord(
                    id=3,
                    series_id=8,
                    episode_id=101,
                    event_type="grabbed",
                    download_id="S1HASH",
                    imported_path=None,
                    release_type=None,
                ),
            ]
        },
        episodes_by_series={
            8: [
                SonarrEpisode(
                    id=101,
                    series_id=8,
                    season_number=1,
                    episode_number=1,
                    episode_file_id=401,
                    has_file=True,
                    monitored=True,
                ),
                SonarrEpisode(
                    id=201,
                    series_id=8,
                    season_number=2,
                    episode_number=1,
                    episode_file_id=402,
                    has_file=True,
                    monitored=True,
                ),
                SonarrEpisode(
                    id=202,
                    series_id=8,
                    season_number=2,
                    episode_number=2,
                    episode_file_id=403,
                    has_file=True,
                    monitored=True,
                ),
            ]
        },
        episode_files_by_series={8: []},
    )
    jellyseerr = FakeJellyseerrClient(
        media=[JellyseerrMedia(id=70, media_type="tv", tmdb_id=801, tvdb_id=800, imdb_id=None, jellyfin_media_id=None)],
        requests=[
            JellyseerrRequest(
                id=71,
                media_id=70,
                media_type="tv",
                season_numbers=(1, 2),
                is_4k=False,
                server_id=0,
                profile_id=1,
                root_folder="/data/show",
                language_profile_id=None,
                requested_by_id=1,
                tags=(),
            )
        ],
        issues=[JellyseerrIssue(id=72, media_id=70, problem_season=2, problem_episode=1)],
    )
    downloader = FakeDownloaderClient(existing_hashes={"S1HASH", "S2HASH1", "S2HASH2"})
    service = build_service(sonarr=sonarr, jellyseerr=jellyseerr, downloader=downloader)

    result = await service.process(
        MediaDeletionEvent(
            notification_type="ItemDeleted",
            item_type=ItemType.SEASON,
            item_id="season-2",
            name="Season 2",
            fingerprint=MediaFingerprint(tvdb_id=800, tmdb_id=801),
            season_number=2,
        )
    )

    assert result.status.value == "success"
    assert sonarr.unmonitored_episode_ids == [201, 202]
    assert sonarr.deleted_episode_file_ids == [402, 403]
    assert set(downloader.deleted_hashes) == {"S2HASH1", "S2HASH2"}
    assert jellyseerr.updated_requests == {71: [1]}
    assert jellyseerr.deleted_issue_ids == [72]


@pytest.mark.asyncio
async def test_episode_delete_removes_single_safe_file_and_hash() -> None:
    sonarr = FakeSonarrClient(
        series=[SonarrSeries(id=9, title="Show", path="/data/show", tvdb_id=900, tmdb_id=901, imdb_id=None)],
        history_by_series={
            9: [
                SonarrHistoryRecord(
                    id=1,
                    series_id=9,
                    episode_id=301,
                    event_type="grabbed",
                    download_id="EPHASH",
                    imported_path=None,
                    release_type=None,
                ),
            ]
        },
        episodes_by_series={
            9: [
                SonarrEpisode(
                    id=301,
                    series_id=9,
                    season_number=3,
                    episode_number=4,
                    episode_file_id=501,
                    has_file=True,
                    monitored=True,
                ),
            ]
        },
        episode_files_by_series={9: []},
    )
    service = build_service(
        sonarr=sonarr,
        jellyseerr=FakeJellyseerrClient(media=[], requests=[], issues=[]),
        downloader=FakeDownloaderClient(existing_hashes={"EPHASH"}),
    )

    result = await service.process(
        MediaDeletionEvent(
            notification_type="ItemDeleted",
            item_type=ItemType.EPISODE,
            item_id="ep-301",
            name="Episode 4",
            fingerprint=MediaFingerprint(tvdb_id=900, tmdb_id=901),
            season_number=3,
            episode_number=4,
        )
    )

    assert result.status.value == "success"
    assert sonarr.unmonitored_episode_ids == [301]
    assert sonarr.deleted_episode_file_ids == [501]
    assert any(action.status == ActionStatus.IGNORED for action in result.actions if action.system == "jellyseerr")


@pytest.mark.asyncio
async def test_episode_delete_logs_pack_and_does_not_remove_hash_or_file() -> None:
    sonarr = FakeSonarrClient(
        series=[
            SonarrSeries(id=10, title="Packed Show", path="/data/packed", tvdb_id=1000, tmdb_id=1001, imdb_id=None)
        ],
        history_by_series={
            10: [
                SonarrHistoryRecord(
                    id=1,
                    series_id=10,
                    episode_id=401,
                    event_type="grabbed",
                    download_id="PACKHASH",
                    imported_path=None,
                    release_type="MultiEpisode",
                ),
                SonarrHistoryRecord(
                    id=2,
                    series_id=10,
                    episode_id=402,
                    event_type="grabbed",
                    download_id="PACKHASH",
                    imported_path=None,
                    release_type="MultiEpisode",
                ),
            ]
        },
        episodes_by_series={
            10: [
                SonarrEpisode(
                    id=401,
                    series_id=10,
                    season_number=1,
                    episode_number=1,
                    episode_file_id=601,
                    has_file=True,
                    monitored=True,
                ),
                SonarrEpisode(
                    id=402,
                    series_id=10,
                    season_number=1,
                    episode_number=2,
                    episode_file_id=602,
                    has_file=True,
                    monitored=True,
                ),
            ]
        },
        episode_files_by_series={10: []},
    )
    downloader = FakeDownloaderClient(existing_hashes={"PACKHASH"})
    service = build_service(
        sonarr=sonarr, jellyseerr=FakeJellyseerrClient(media=[], requests=[], issues=[]), downloader=downloader
    )

    result = await service.process(
        MediaDeletionEvent(
            notification_type="ItemDeleted",
            item_type=ItemType.EPISODE,
            item_id="ep-401",
            name="Episode 1",
            fingerprint=MediaFingerprint(tvdb_id=1000, tmdb_id=1001),
            season_number=1,
            episode_number=1,
        )
    )

    assert result.status.value == "success"
    assert sonarr.deleted_episode_file_ids == []
    assert downloader.deleted_hashes == []
    assert any(action.reason and action.reason.value == "pack_torrent" for action in result.actions)


@pytest.mark.asyncio
async def test_duplicate_movie_delete_becomes_idempotent_no_match_on_second_run() -> None:
    radarr = FakeRadarrClient(
        movies=[RadarrMovie(id=99, title="Movie", path="/data/movie", tmdb_id=999, imdb_id=None)],
        history_by_movie={
            99: [RadarrHistoryRecord(id=1, movie_id=99, event_type="grabbed", download_id="H999", imported_path=None)]
        },
    )
    service = build_service(
        radarr=radarr,
        jellyseerr=FakeJellyseerrClient(media=[], requests=[], issues=[]),
        downloader=FakeDownloaderClient(existing_hashes={"H999"}),
    )
    event = MediaDeletionEvent(
        notification_type="ItemDeleted",
        item_type=ItemType.MOVIE,
        item_id="movie-99",
        name="Movie",
        fingerprint=MediaFingerprint(tmdb_id=999),
    )

    first_result = await service.process(event)
    second_result = await service.process(event)

    assert first_result.status.value == "success"
    assert second_result.status.value == "ignored"
    assert any(action.reason and action.reason.value == "no_match" for action in second_result.actions)
