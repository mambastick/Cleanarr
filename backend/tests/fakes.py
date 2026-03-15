"""Test fakes for application scenarios."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from cleanarr.domain import (
    DownloaderRemovalResult,
    JellyseerrIssue,
    JellyseerrMedia,
    JellyseerrRequest,
    RadarrHistoryRecord,
    RadarrMovie,
    SonarrEpisode,
    SonarrEpisodeFile,
    SonarrHistoryRecord,
    SonarrSeries,
)


@dataclass
class FakeRadarrClient:
    """In-memory Radarr fake."""

    movies: list[RadarrMovie]
    history_by_movie: dict[int, list[RadarrHistoryRecord]]
    deleted_movie_ids: list[int] = field(default_factory=list)

    async def list_movies(self) -> list[RadarrMovie]:
        return list(self.movies)

    async def list_movie_history(self, movie_id: int) -> list[RadarrHistoryRecord]:
        return list(self.history_by_movie.get(movie_id, []))

    async def delete_movie(
        self,
        movie_id: int,
        *,
        delete_files: bool,
        add_import_exclusion: bool,
    ) -> None:
        self.deleted_movie_ids.append(movie_id)
        self.movies = [movie for movie in self.movies if movie.id != movie_id]


@dataclass
class FakeSonarrClient:
    """In-memory Sonarr fake."""

    series: list[SonarrSeries]
    history_by_series: dict[int, list[SonarrHistoryRecord]]
    episodes_by_series: dict[int, list[SonarrEpisode]]
    episode_files_by_series: dict[int, list[SonarrEpisodeFile]]
    unmonitored_episode_ids: list[int] = field(default_factory=list)
    deleted_episode_file_ids: list[int] = field(default_factory=list)
    deleted_series_ids: list[int] = field(default_factory=list)

    async def list_series(self) -> list[SonarrSeries]:
        return list(self.series)

    async def list_series_history(self, series_id: int) -> list[SonarrHistoryRecord]:
        return list(self.history_by_series.get(series_id, []))

    async def list_episodes(self, series_id: int) -> list[SonarrEpisode]:
        return list(self.episodes_by_series.get(series_id, []))

    async def list_episode_files(self, series_id: int) -> list[SonarrEpisodeFile]:
        return list(self.episode_files_by_series.get(series_id, []))

    async def unmonitor_episodes(self, episode_ids: list[int]) -> None:
        self.unmonitored_episode_ids.extend(episode_ids)
        for series_id, episodes in self.episodes_by_series.items():
            self.episodes_by_series[series_id] = [
                SonarrEpisode(
                    id=episode.id,
                    series_id=episode.series_id,
                    season_number=episode.season_number,
                    episode_number=episode.episode_number,
                    episode_file_id=episode.episode_file_id,
                    has_file=episode.has_file,
                    monitored=False if episode.id in episode_ids else episode.monitored,
                )
                for episode in episodes
            ]

    async def delete_episode_file(self, episode_file_id: int) -> None:
        self.deleted_episode_file_ids.append(episode_file_id)

    async def delete_series(
        self,
        series_id: int,
        *,
        delete_files: bool,
        add_import_list_exclusion: bool,
    ) -> None:
        self.deleted_series_ids.append(series_id)
        self.series = [item for item in self.series if item.id != series_id]


@dataclass
class FakeJellyseerrClient:
    """In-memory Jellyseerr fake."""

    media: list[JellyseerrMedia]
    requests: list[JellyseerrRequest]
    issues: list[JellyseerrIssue]
    deleted_request_ids: list[int] = field(default_factory=list)
    updated_requests: dict[int, list[int]] = field(default_factory=dict)
    deleted_issue_ids: list[int] = field(default_factory=list)
    deleted_media_ids: list[int] = field(default_factory=list)

    async def list_media(self) -> list[JellyseerrMedia]:
        return list(self.media)

    async def list_requests(self) -> list[JellyseerrRequest]:
        return list(self.requests)

    async def list_issues(self) -> list[JellyseerrIssue]:
        return list(self.issues)

    async def delete_request(self, request_id: int) -> None:
        self.deleted_request_ids.append(request_id)
        self.requests = [request for request in self.requests if request.id != request_id]

    async def update_request_seasons(
        self,
        request: JellyseerrRequest,
        *,
        season_numbers: list[int],
    ) -> None:
        self.updated_requests[request.id] = season_numbers
        self.requests = [
            JellyseerrRequest(
                id=item.id,
                media_id=item.media_id,
                media_type=item.media_type,
                season_numbers=tuple(season_numbers) if item.id == request.id else item.season_numbers,
                is_4k=item.is_4k,
                server_id=item.server_id,
                profile_id=item.profile_id,
                root_folder=item.root_folder,
                language_profile_id=item.language_profile_id,
                requested_by_id=item.requested_by_id,
                tags=item.tags,
            )
            for item in self.requests
        ]

    async def delete_issue(self, issue_id: int) -> None:
        self.deleted_issue_ids.append(issue_id)
        self.issues = [issue for issue in self.issues if issue.id != issue_id]

    async def delete_media(self, media_id: int) -> None:
        self.deleted_media_ids.append(media_id)
        self.media = [item for item in self.media if item.id != media_id]


@dataclass
class FakeDownloaderClient:
    """In-memory downloader fake."""

    existing_hashes: set[str]
    deleted_hashes: list[str] = field(default_factory=list)

    async def delete_hashes(
        self,
        hashes: list[str],
        *,
        delete_files: bool,
    ) -> list[DownloaderRemovalResult]:
        results: list[DownloaderRemovalResult] = []
        for hash_value in hashes:
            normalized = hash_value.upper()
            existed = normalized in self.existing_hashes
            if existed:
                self.existing_hashes.remove(normalized)
                self.deleted_hashes.append(normalized)
            results.append(DownloaderRemovalResult(hash_value=normalized, existed=existed))
        return results


@dataclass
class FakeService:
    """Minimal service fake for API tests."""

    results: list[Any]
    seen_events: list[Any] = field(default_factory=list)

    async def process(self, event: Any) -> Any:
        self.seen_events.append(event)
        return self.results[len(self.seen_events) - 1]
