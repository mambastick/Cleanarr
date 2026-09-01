"""Normalized, non-destructive downloader observations and controls.

This module deliberately contains no adapter, transport, persistence, or API
types.  In particular, these records never carry download paths, URLs, or
credentials: the info hash is the only stable torrent identifier exposed to
the application layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class TorrentState(StrEnum):
    """Conservative normalized torrent state."""

    DOWNLOADING = "downloading"
    SEEDING = "seeding"
    STOPPED = "stopped"
    QUEUED = "queued"
    CHECKING = "checking"
    ERROR = "error"
    UNKNOWN = "unknown"


class TorrentOwnership(StrEnum):
    """Ownership proven from an Arr grab history and downloader observation."""

    MANAGED = "managed"
    UNMANAGED = "unmanaged"
    CONFLICT = "conflict"
    UNKNOWN = "unknown"


class ListingFreshness(StrEnum):
    """Whether a read is directly observed during the current request."""

    FRESH = "fresh"
    STALE = "stale"
    UNKNOWN = "unknown"


class DownloadControlAction(StrEnum):
    PAUSE = "pause"
    RESUME = "resume"


class DownloadControlOutcome(StrEnum):
    APPLIED = "applied"
    ALREADY_IN_DESIRED_STATE = "already_in_desired_state"
    NOT_FOUND = "not_found"
    UNKNOWN = "unknown"
    FAILED = "failed"


class DownloadActionStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    ALREADY_IN_STATE = "already_in_state"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    UNCERTAIN = "uncertain"
    RECONCILE_REQUIRED = "reconcile_required"
    SIMULATED = "simulated"


@dataclass(frozen=True)
class DownloadActionClaim:
    action_id: str
    status: DownloadActionStatus
    conflict: bool = False
    code: str | None = None


@dataclass(frozen=True)
class TorrentSnapshot:
    """A safe normalized torrent observation from one configured client."""

    client_id: str
    client_name: str
    client_kind: str
    info_hash: str
    display_name: str | None
    state: TorrentState
    observed_at: datetime
    progress: float | None = None
    total_bytes: int | None = None
    downloaded_bytes: int | None = None
    uploaded_bytes: int | None = None
    ratio: float | None = None
    seeding_time_seconds: int | None = None
    download_speed_bytes_per_second: int | None = None
    upload_speed_bytes_per_second: int | None = None
    eta_seconds: int | None = None
    added_at: datetime | None = None
    completed_at: datetime | None = None
    activity_at: datetime | None = None
    category: str | None = None
    tags: tuple[str, ...] | None = None
    tracker_summary: str | None = None
    freshness: ListingFreshness = ListingFreshness.UNKNOWN
    ownership: TorrentOwnership = TorrentOwnership.UNKNOWN
    unavailable_reason: str | None = None

    @property
    def observation_key(self) -> str:
        return f"{self.client_id}:{self.info_hash}"


@dataclass(frozen=True)
class DownloaderReadFailure:
    """One client/entry failed while other client observations may be usable."""

    client_id: str
    client_name: str
    client_kind: str
    code: str


@dataclass(frozen=True)
class DownloaderListing:
    """Partial-safe result of reading one or more downloader clients."""

    torrents: tuple[TorrentSnapshot, ...] = ()
    failures: tuple[DownloaderReadFailure, ...] = ()
    completed_client_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class DownloaderControlResult:
    """The reconciled result of one reversible, single-client operation."""

    client_id: str
    client_name: str
    client_kind: str
    info_hash: str
    action: DownloadControlAction
    outcome: DownloadControlOutcome
    before: TorrentSnapshot | None = None
    after: TorrentSnapshot | None = None
    code: str | None = None
