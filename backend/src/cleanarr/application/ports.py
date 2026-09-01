"""Application ports."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from cleanarr.domain import (
    DownloadActionClaim,
    DownloadActionStatus,
    DownloadControlAction,
    DownloaderControlResult,
    DownloaderListing,
    DownloaderRemovalResult,
    JellyfinCleanupItem,
    JellyfinItem,
    PlaybackObservation,
    RadarrHistoryRecord,
    RadarrMovie,
    SeerrIssue,
    SeerrMedia,
    SeerrRequest,
    SonarrEpisode,
    SonarrEpisodeFile,
    SonarrHistoryRecord,
    SonarrSeries,
    TorrentSnapshot,
)


class DownloadsRepositoryPort(Protocol):
    """Persistence boundary for normalized observations and action claims."""

    def save_listing(self, snapshots: tuple[TorrentSnapshot, ...], successful_clients: set[str]) -> None: ...
    def mark_all_stale(self, reason: str = "refresh_not_confirmed") -> None: ...
    def list_snapshots(self) -> list[TorrentSnapshot]: ...
    def get_snapshot(self, client_id: str, info_hash: str) -> TorrentSnapshot | None: ...
    def claim_action(
        self,
        *,
        idempotency_key: str,
        canonical_request: str,
        client_id: str,
        info_hash: str,
        action: DownloadControlAction,
        max_attempts: int,
        allow_retry: bool = False,
        source: str = "manual",
    ) -> DownloadActionClaim: ...
    def action_status(self, action_id: str) -> DownloadActionStatus | None: ...
    def action_record(self, action_id: str) -> DownloadActionClaim | None: ...
    def increment_attempt(self, action_id: str) -> int: ...
    def update_action(
        self, action_id: str, status: DownloadActionStatus, *, code: str | None = None, result: object = None
    ) -> None: ...
    def recover_running_actions(self) -> int: ...
    def record_policy_evaluation(
        self,
        *,
        revision: str,
        snapshot: TorrentSnapshot,
        facts: dict[str, object],
        reason_code: str,
        decision: str,
    ) -> None: ...
    def action_status_counts(self) -> dict[str, int]: ...
    def policy_decision_counts(self) -> dict[str, int]: ...
    def latest_policy_evaluations(self) -> dict[tuple[str, str], dict[str, object]]: ...
    def latest_action_projections(self, keys: set[tuple[str, str]]) -> dict[tuple[str, str], dict[str, object]]: ...


class DownloaderReadPort(Protocol):
    """Non-destructive downloader observations, separate from deletion."""

    async def list_torrents(self) -> DownloaderListing:
        """Return normalized snapshots and structured partial read failures."""


class DownloaderControlPort(Protocol):
    """Reversible single-torrent controls, separate from deletion."""

    async def control_torrent(self, info_hash: str, *, action: DownloadControlAction) -> DownloaderControlResult:
        """Reconcile and apply a pause or resume operation exactly once."""


class DownloaderFleetPort(Protocol):
    """Application boundary for a configured downloader fleet."""

    async def list_torrents(self) -> DownloaderListing: ...

    async def control_torrent(
        self, client_id: str, info_hash: str, *, action: DownloadControlAction
    ) -> DownloaderControlResult: ...

    def configured_client_ids(self) -> set[str]: ...


class JellyfinServerClientPort(Protocol):
    """Jellyfin operations used to confirm webhook deletions."""

    async def list_items(
        self,
        *,
        include_types: list[str],
        accept_language: str | None = None,
    ) -> Sequence[JellyfinItem]:
        """Return current Jellyfin items of the requested types."""


class JellyfinPlaybackReadPort(Protocol):
    """Read-only standard-Jellyfin playback boundary for future providers."""

    async def list_cleanup_items(
        self, *, accept_language: str | None = None, max_items: int = 200
    ) -> tuple[tuple[JellyfinCleanupItem, ...], bool]: ...

    async def list_playback_users(self, *, max_users: int = 20) -> tuple[tuple[str, ...], bool]: ...

    async def list_user_playback(
        self, *, user_id: str, item_ids: tuple[str, ...], accept_language: str | None = None
    ) -> tuple[PlaybackObservation, ...]: ...


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


class SeerrClientPort(Protocol):
    """Seerr operations used by the application layer."""

    async def list_media(self) -> Sequence[SeerrMedia]:
        """Return tracked media records."""

    async def list_requests(self) -> Sequence[SeerrRequest]:
        """Return all request records."""

    async def list_issues(self) -> Sequence[SeerrIssue]:
        """Return all issues."""

    async def delete_request(self, request_id: int) -> None:
        """Delete a request."""

    async def update_request_seasons(
        self,
        request: SeerrRequest,
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

    async def close(self) -> None:
        """Close resources owned by the adapter."""

    async def ping(self) -> None:
        """Validate connectivity and authentication."""

    async def get_version(self) -> str:
        """Return the downstream client version."""

    async def delete_hashes(
        self,
        hashes: Sequence[str],
        *,
        delete_files: bool,
        dry_run: bool = False,
    ) -> Sequence[DownloaderRemovalResult]:
        """Resolve hashes and delete them unless this is a dry-run preview."""
