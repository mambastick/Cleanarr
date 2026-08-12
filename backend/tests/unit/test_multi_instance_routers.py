"""Tests for ownership-preserving multi-instance routers."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from cleanarr.domain import (
    DownloaderRemovalResult,
    ExternalServiceError,
    RadarrHistoryRecord,
    RadarrMovie,
    SonarrEpisode,
    SonarrEpisodeFile,
    SonarrHistoryRecord,
    SonarrSeries,
)
from cleanarr.infrastructure.downloaders import DownloaderTarget, MultiDownloaderClient
from cleanarr.infrastructure.routers import MultiRadarrClient, MultiSonarrClient, RadarrTarget, SonarrTarget
from tests.fakes import FakeDownloaderClient, FakeRadarrClient, FakeSonarrClient


class ManagedFakeRadarr(FakeRadarrClient):
    async def close(self) -> None:
        return None

    async def ping(self) -> None:
        return None

    async def get_version(self) -> str:
        return "test"


class ManagedFakeSonarr(FakeSonarrClient):
    async def close(self) -> None:
        return None

    async def ping(self) -> None:
        return None

    async def get_version(self) -> str:
        return "test"


class ManagedFakeDownloader(FakeDownloaderClient):
    async def close(self) -> None:
        return None

    async def ping(self) -> None:
        return None

    async def get_version(self) -> str:
        return "test"


@dataclass
class FailingDownloader:
    message: str
    seen_hashes: list[str] = field(default_factory=list)

    async def close(self) -> None:
        return None

    async def ping(self) -> None:
        return None

    async def get_version(self) -> str:
        return "test"

    async def delete_hashes(
        self,
        hashes: list[str],
        *,
        delete_files: bool,
        dry_run: bool = False,
    ) -> list[DownloaderRemovalResult]:
        self.seen_hashes.extend(hashes)
        raise ExternalServiceError("transmission", self.message)


@pytest.mark.asyncio
async def test_radarr_router_preserves_owner_when_raw_ids_collide() -> None:
    first = ManagedFakeRadarr(
        movies=[RadarrMovie(id=1, title="First", path="/first", tmdb_id=10, imdb_id=None)],
        history_by_movie={},
    )
    second = ManagedFakeRadarr(
        movies=[RadarrMovie(id=1, title="Second", path="/second", tmdb_id=20, imdb_id=None)],
        history_by_movie={
            1: [
                RadarrHistoryRecord(
                    id=4,
                    movie_id=1,
                    event_type="grabbed",
                    download_id="HASH",
                    imported_path="/second/file.mkv",
                )
            ]
        },
    )
    router = MultiRadarrClient(
        [
            RadarrTarget(id="radarr-a", name="Radarr A", client=first),
            RadarrTarget(id="radarr-b", name="Radarr B", client=second),
        ]
    )

    movies = list(await router.list_movies())
    assert movies[0].id != movies[1].id
    assert movies[1].service_id == "radarr-b"
    history = await router.list_movie_history(movies[1].id)
    await router.delete_movie(movies[1].id, delete_files=True, add_import_exclusion=False)

    assert history[0].movie_id == movies[1].id
    assert first.deleted_movie_ids == []
    assert second.deleted_movie_ids == [1]


@pytest.mark.asyncio
async def test_sonarr_router_routes_episode_and_file_mutations_to_owner() -> None:
    first = ManagedFakeSonarr(series=[], history_by_series={}, episodes_by_series={}, episode_files_by_series={})
    second = ManagedFakeSonarr(
        series=[SonarrSeries(id=1, title="Show", path="/shows/show", tvdb_id=20, tmdb_id=None, imdb_id=None)],
        history_by_series={
            1: [
                SonarrHistoryRecord(
                    id=3,
                    series_id=1,
                    episode_id=2,
                    event_type="grabbed",
                    download_id="HASH",
                    imported_path="/shows/show/S01E01.mkv",
                    release_type=None,
                )
            ]
        },
        episodes_by_series={
            1: [
                SonarrEpisode(
                    id=2,
                    series_id=1,
                    season_number=1,
                    episode_number=1,
                    episode_file_id=5,
                    has_file=True,
                    monitored=True,
                )
            ]
        },
        episode_files_by_series={
            1: [SonarrEpisodeFile(id=5, path="/shows/show/S01E01.mkv", relative_path=None, season_number=1)]
        },
    )
    router = MultiSonarrClient(
        [
            SonarrTarget(id="sonarr-a", name="Sonarr A", client=first),
            SonarrTarget(id="sonarr-b", name="Sonarr B", client=second),
        ]
    )

    series = (await router.list_series())[0]
    history = (await router.list_series_history(series.id))[0]
    episode = (await router.list_episodes(series.id))[0]
    episode_file = (await router.list_episode_files(series.id))[0]
    await router.unmonitor_episodes([episode.id])
    await router.delete_episode_file(episode_file.id)
    await router.unmonitor_season(series.id, 1)
    await router.delete_series(series.id, delete_files=True, add_import_list_exclusion=False)

    assert series.service_id == "sonarr-b"
    assert history.episode_id == episode.id
    assert second.unmonitored_episode_ids == [2]
    assert second.deleted_episode_file_ids == [5]
    assert second.unmonitored_seasons == [(1, 1)]
    assert second.deleted_series_ids == [1]


@pytest.mark.asyncio
async def test_downloader_router_checks_all_clients_and_keeps_partial_errors() -> None:
    qbittorrent = ManagedFakeDownloader(existing_hashes={"AA"})
    transmission = FailingDownloader(message="Transmission timed out")
    router = MultiDownloaderClient(
        [
            DownloaderTarget(id="qbt", name="qBittorrent", kind="qbittorrent", client=qbittorrent),
            DownloaderTarget(id="tr", name="Transmission", kind="transmission", client=transmission),
        ]
    )

    results = list(await router.delete_hashes(["aa"], delete_files=True))

    assert qbittorrent.deleted_hashes == ["AA"]
    assert transmission.seen_hashes == ["AA"]
    assert results[0].existed is True
    assert results[1].client_id == "tr"
    assert results[1].error == "Transmission timed out"
