"""Domain models."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class ItemType(StrEnum):
    """Supported Jellyfin item types."""

    MOVIE = "Movie"
    SERIES = "Series"
    SEASON = "Season"
    EPISODE = "Episode"


class ActionStatus(StrEnum):
    """Mutation status for a single downstream action."""

    DELETED = "deleted"
    SKIPPED = "skipped"
    IGNORED = "ignored"
    FAILED = "failed"
    ALREADY_ABSENT = "already_absent"
    DRY_RUN = "dry_run"


class OverallStatus(StrEnum):
    """Top-level processing status."""

    SUCCESS = "success"
    PARTIAL_FAILURE = "partial_failure"
    IGNORED = "ignored"


class FailureReason(StrEnum):
    """Machine-readable reason codes."""

    AMBIGUOUS_MATCH = "ambiguous_match"
    NO_MATCH = "no_match"
    PACK_TORRENT = "pack_torrent"
    SHARED_FILE = "shared_file"
    NO_PARTIAL_REQUEST_CLEANUP = "no_partial_request_cleanup"
    DOWNSTREAM_ERROR = "downstream_error"
    AUTHENTICATION_FAILED = "authentication_failed"
    UNSUPPORTED_EVENT = "unsupported_event"


@dataclass(frozen=True)
class MediaFingerprint:
    """Identifiers used for strict downstream matching."""

    tmdb_id: int | None = None
    tvdb_id: int | None = None
    imdb_id: str | None = None
    path: str | None = None

    @property
    def normalized_path(self) -> str | None:
        if self.path is None:
            return None
        return self.path.rstrip("/")


@dataclass(frozen=True)
class MediaDeletionEvent:
    """Single deletion event derived from the webhook."""

    notification_type: str
    item_type: ItemType
    item_id: str
    name: str
    fingerprint: MediaFingerprint
    series_name: str | None = None
    series_id: str | None = None
    season_number: int | None = None
    episode_number: int | None = None
    episode_end_number: int | None = None
    occurred_at: datetime | None = None

    @property
    def is_item_deleted(self) -> bool:
        return self.notification_type == "ItemDeleted"

    @property
    def episode_numbers(self) -> frozenset[int]:
        if self.item_type is not ItemType.EPISODE or self.episode_number is None:
            return frozenset()
        end_number = self.episode_end_number or self.episode_number
        if end_number < self.episode_number:
            return frozenset({self.episode_number})
        return frozenset(range(self.episode_number, end_number + 1))


@dataclass(frozen=True)
class ActionResult:
    """Result of a single action against a downstream system."""

    system: str
    action: str
    status: ActionStatus
    message: str
    reason: FailureReason | None = None
    details: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ProcessingResult:
    """Aggregated result for one deletion event."""

    event: MediaDeletionEvent
    status: OverallStatus
    actions: tuple[ActionResult, ...]


@dataclass(frozen=True)
class SafetyNote:
    """Non-fatal note generated during conservative safety checks."""

    reason: FailureReason
    message: str
    details: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SafetyDecision:
    """Resolved cleanup scope for partial TV deletions."""

    target_episode_ids: frozenset[int]
    episode_ids_to_unmonitor: frozenset[int]
    episode_file_ids_to_delete: frozenset[int]
    hashes_to_delete: frozenset[str]
    notes: tuple[SafetyNote, ...] = ()


@dataclass(frozen=True)
class RadarrMovie:
    """Subset of Radarr movie metadata."""

    id: int
    title: str
    path: str
    tmdb_id: int | None
    imdb_id: str | None
    size_on_disk: int | None = None
    has_file: bool = False


@dataclass(frozen=True)
class JellyfinItem:
    """Subset of Jellyfin item metadata."""

    id: str
    name: str
    type: str
    tmdb_id: int | None = None
    tvdb_id: int | None = None
    imdb_id: str | None = None
    parent_id: str | None = None
    season_number: int | None = None


@dataclass(frozen=True)
class RadarrHistoryRecord:
    """Subset of Radarr history metadata."""

    id: int
    movie_id: int
    event_type: str
    download_id: str | None
    imported_path: str | None


@dataclass(frozen=True)
class SonarrSeries:
    """Subset of Sonarr series metadata."""

    id: int
    title: str
    path: str
    tvdb_id: int | None
    tmdb_id: int | None
    imdb_id: str | None


@dataclass(frozen=True)
class SonarrEpisode:
    """Subset of Sonarr episode metadata."""

    id: int
    series_id: int
    season_number: int
    episode_number: int
    episode_file_id: int | None
    has_file: bool
    monitored: bool


@dataclass(frozen=True)
class SonarrEpisodeFile:
    """Subset of Sonarr episode file metadata."""

    id: int
    path: str
    relative_path: str | None
    season_number: int | None
    size: int | None = None


@dataclass(frozen=True)
class SonarrHistoryRecord:
    """Subset of Sonarr history metadata."""

    id: int
    series_id: int
    episode_id: int | None
    event_type: str
    download_id: str | None
    imported_path: str | None
    release_type: str | None


@dataclass(frozen=True)
class JellyseerrMedia:
    """Subset of Jellyseerr media metadata."""

    id: int
    media_type: str
    tmdb_id: int | None
    tvdb_id: int | None
    imdb_id: str | None
    jellyfin_media_id: str | None


@dataclass(frozen=True)
class JellyseerrRequest:
    """Subset of Jellyseerr request metadata."""

    id: int
    media_id: int
    media_type: str
    season_numbers: tuple[int, ...]
    is_4k: bool
    server_id: int | None
    profile_id: int | None
    root_folder: str | None
    language_profile_id: int | None
    requested_by_id: int | None
    tags: tuple[int, ...]


@dataclass(frozen=True)
class JellyseerrIssue:
    """Subset of Jellyseerr issue metadata."""

    id: int
    media_id: int
    problem_season: int | None
    problem_episode: int | None


@dataclass(frozen=True)
class DownloaderRemovalResult:
    """qBittorrent removal outcome for a single hash."""

    hash_value: str
    existed: bool
