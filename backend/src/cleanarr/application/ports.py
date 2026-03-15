"""Application ports."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

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


class RadarrClientPort(Protocol):
    """Radarr operations used by the application layer."""

    async def list_movies(self) -> Sequence[RadarrMovie]:
        """Return all known movies."""

    async def list_movie_history(self, movie_id: int) -> Sequence[RadarrHistoryRecord]:
        """Return history for a single movie."""

    async def delete_movie(
        self,
        movie_id: int,
        *,
        delete_files: bool,
        add_import_exclusion: bool,
    ) -> None:
        """Delete a movie from Radarr."""


class SonarrClientPort(Protocol):
    """Sonarr operations used by the application layer."""

    async def list_series(self) -> Sequence[SonarrSeries]:
        """Return all known series."""

    async def list_series_history(self, series_id: int) -> Sequence[SonarrHistoryRecord]:
        """Return history for a single series."""

    async def list_episodes(self, series_id: int) -> Sequence[SonarrEpisode]:
        """Return episodes for a series."""

    async def list_episode_files(self, series_id: int) -> Sequence[SonarrEpisodeFile]:
        """Return episode files for a series."""

    async def unmonitor_episodes(self, episode_ids: Sequence[int]) -> None:
        """Disable monitoring for specific episodes."""

    async def unmonitor_season(self, series_id: int, season_number: int) -> None:
        """Disable monitoring for a specific season."""

    async def delete_episode_file(self, episode_file_id: int) -> None:
        """Delete a single episode file."""

    async def delete_series(
        self,
        series_id: int,
        *,
        delete_files: bool,
        add_import_list_exclusion: bool,
    ) -> None:
        """Delete a series from Sonarr."""


class JellyseerrClientPort(Protocol):
    """Jellyseerr operations used by the application layer."""

    async def list_media(self) -> Sequence[JellyseerrMedia]:
        """Return tracked media records."""

    async def list_requests(self) -> Sequence[JellyseerrRequest]:
        """Return all request records."""

    async def list_issues(self) -> Sequence[JellyseerrIssue]:
        """Return all issues."""

    async def delete_request(self, request_id: int) -> None:
        """Delete a request."""

    async def update_request_seasons(
        self,
        request: JellyseerrRequest,
        *,
        season_numbers: Sequence[int],
    ) -> None:
        """Update the requested seasons for a TV request."""

    async def delete_issue(self, issue_id: int) -> None:
        """Delete an issue."""

    async def delete_media(self, media_id: int) -> None:
        """Delete a media record."""


class DownloaderClientPort(Protocol):
    """Download client abstraction."""

    async def delete_hashes(
        self,
        hashes: Sequence[str],
        *,
        delete_files: bool,
    ) -> Sequence[DownloaderRemovalResult]:
        """Delete hashes from the underlying download client."""
