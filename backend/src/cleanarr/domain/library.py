"""Domain primitives for the bounded library read model.

The library model intentionally contains no FastAPI, persistence, or UI types.
Stable resource identifiers are opaque transport values; callers must still
provide the legacy Arr routing identifier when requesting a destructive action.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import re
import secrets
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Literal


class LibraryMediaType(StrEnum):
    """The two Arr-backed media families exposed by the library browser."""

    MOVIE = "movie"
    SERIES = "series"


class LibraryReadState(StrEnum):
    """Completeness of a non-destructive library read."""

    COMPLETE = "complete"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"


class LibraryResourceError(ValueError):
    """A malformed or unsupported stable library resource identifier."""


@dataclass(frozen=True)
class LibraryResource:
    """Decoded stable identity used only to locate a current Arr item."""

    media_type: LibraryMediaType
    profile_id: str
    raw_id: int


@dataclass(frozen=True)
class LibraryItem:
    """Privacy-safe list projection for one movie or series."""

    resource_id: str
    media_type: LibraryMediaType
    profile_id: str
    profile_name: str | None
    raw_id: int
    legacy_id: int
    title: str
    added_at: datetime | None = None
    size_bytes: int | None = None
    has_file: bool | None = None
    jellyfin_item_id: str | None = None
    jellyfin_title: str | None = None
    year: int | None = None
    episode_count: int | None = None
    episode_file_count: int | None = None
    artwork_status: str = "unknown"
    playback_status: str = "unknown"
    play_count: int | None = None
    last_played_at: datetime | None = None
    playback_reason: str | None = "playback_not_loaded"
    seeding_state: str = "unknown"
    seeding_readiness: str = "unknown"
    seeding_ratio: float | None = None
    seeding_time_seconds: int | None = None
    seeding_reason: str | None = "seeding_not_loaded"
    fetched_at: datetime | None = None
    playback_freshness: str = "unknown"


@dataclass(frozen=True)
class LibraryEnrichment:
    """Bounded detail-only playback and downloader evidence."""

    playback_status: str = "unknown"
    playback_freshness: str = "unknown"
    play_count: int | None = None
    last_played_at: datetime | None = None
    playback_reason: str | None = "playback_not_loaded"
    seeding_state: str = "unknown"
    seeding_readiness: str = "unknown"
    seeding_ratio: float | None = None
    seeding_time_seconds: int | None = None
    seeding_reason: str | None = "seeding_not_loaded"
    failure_codes: tuple[str, ...] = ()


@dataclass(frozen=True)
class LibraryEpisode:
    """Bounded series-detail episode projection."""

    id: int
    season_number: int
    episode_number: int
    has_file: bool | None
    episode_file_id: int | None
    monitored: bool | None


@dataclass(frozen=True)
class LibraryFile:
    """Bounded series-detail episode-file projection."""

    id: int
    season_number: int | None
    size_bytes: int | None


@dataclass(frozen=True)
class ArtworkData:
    """Validated bytes returned by the authenticated Jellyfin image proxy."""

    content: bytes
    media_type: str


@dataclass(frozen=True)
class LibraryDetail:
    """One library item and optional bounded series details."""

    item: LibraryItem
    state: LibraryReadState
    revision: str = ""
    error_code: str | None = None
    episodes: tuple[LibraryEpisode, ...] = ()
    files: tuple[LibraryFile, ...] = ()


@dataclass(frozen=True)
class LibraryPage:
    """Ordered page over a revision-bound process cache."""

    items: tuple[LibraryItem, ...]
    state: LibraryReadState
    revision: str
    next_cursor: str | None
    error_code: str | None = None


@dataclass(frozen=True)
class StorageRootFolder:
    """Untrusted Arr root-folder metadata kept inside infrastructure only."""

    path: str
    folder_id: int | None = None
    accessible: bool | None = None
    service_id: str | None = None
    service_name: str | None = None


@dataclass(frozen=True)
class StorageDiskSpace:
    """Untrusted Arr disk-space metadata kept inside infrastructure only."""

    path: str
    free_bytes: int | None
    total_bytes: int | None


@dataclass(frozen=True)
class StorageProfileListing:
    """One profile's storage read, including a safe failure code."""

    service_kind: Literal["radarr", "sonarr"]
    service_id: str
    service_name: str | None
    roots: tuple[StorageRootFolder, ...]
    disk_spaces: tuple[StorageDiskSpace, ...]
    error_code: str | None = None


@dataclass(frozen=True)
class StorageVolume:
    """Storage projection with no path or credential fields."""

    volume_id: str
    service_kind: Literal["radarr", "sonarr"]
    profile_id: str
    profile_name: str | None
    root_folder_id: int | None
    free_bytes: int | None
    total_bytes: int | None
    free_percent: float | None
    status: str
    collected_at: datetime
    error_code: str | None = None
    display_label: str = "Storage volume"
    possible_duplicate: bool = False


@dataclass(frozen=True)
class StorageSnapshot:
    """Cached storage projection and collection-level completeness."""

    volumes: tuple[StorageVolume, ...]
    collected_at: datetime
    partial: bool
    error_codes: tuple[str, ...] = ()


_RESOURCE_PREFIX = "r1_"
_RESOURCE_MAX_LENGTH = 256
_RESOURCE_PROFILE_RE = re.compile(r"^[^\x00-\x1f\x7f]{1,160}$")
_CURSOR_PREFIX = "c1_"
_CURSOR_MAX_LENGTH = 512
_CURSOR_SECRET = secrets.token_bytes(32)


def encode_library_resource(media_type: LibraryMediaType | str, profile_id: str, raw_id: int) -> str:
    """Encode a versioned opaque identity from profile ID and raw Arr ID."""

    try:
        kind = LibraryMediaType(media_type)
    except ValueError as exc:
        raise LibraryResourceError("Unsupported library media type.") from exc
    if not isinstance(profile_id, str) or not _RESOURCE_PROFILE_RE.fullmatch(profile_id) or not profile_id.strip():
        raise LibraryResourceError("Invalid library profile identity.")
    if isinstance(raw_id, bool) or not isinstance(raw_id, int) or raw_id < 0:
        raise LibraryResourceError("Invalid Arr resource identity.")
    payload = json.dumps(
        {"m": kind.value, "p": profile_id, "i": raw_id},
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    encoded = base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")
    return f"{_RESOURCE_PREFIX}{encoded}"


def decode_library_resource(value: str) -> LibraryResource:
    """Decode and strictly validate an opaque stable library identity."""

    if not isinstance(value, str) or len(value) > _RESOURCE_MAX_LENGTH or not value.startswith(_RESOURCE_PREFIX):
        raise LibraryResourceError("Invalid library resource identifier.")
    encoded = value[len(_RESOURCE_PREFIX) :]
    if not encoded or any(
        character not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_" for character in encoded
    ):
        raise LibraryResourceError("Invalid library resource identifier.")
    try:
        payload = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
    except (ValueError, TypeError, UnicodeDecodeError, json.JSONDecodeError, binascii.Error) as exc:
        raise LibraryResourceError("Invalid library resource identifier.") from exc
    if not isinstance(payload, dict) or set(payload) != {"i", "m", "p"}:
        raise LibraryResourceError("Invalid library resource identifier.")
    profile_id = payload.get("p")
    raw_id = payload.get("i")
    media_value = payload.get("m")
    if not isinstance(media_value, str):
        raise LibraryResourceError("Invalid library resource identifier.")
    try:
        media_type = LibraryMediaType(media_value)
    except ValueError as exc:
        raise LibraryResourceError("Invalid library resource identifier.") from exc
    if not isinstance(profile_id, str) or not _RESOURCE_PROFILE_RE.fullmatch(profile_id) or not profile_id.strip():
        raise LibraryResourceError("Invalid library resource identifier.")
    if isinstance(raw_id, bool) or not isinstance(raw_id, int) or raw_id < 0:
        raise LibraryResourceError("Invalid library resource identifier.")
    canonical = encode_library_resource(media_type, profile_id, raw_id)
    if not hmac.compare_digest(canonical, value):
        raise LibraryResourceError("Invalid library resource identifier.")
    return LibraryResource(media_type=media_type, profile_id=profile_id, raw_id=raw_id)


def _cursor_signature(revision: str, key: str, offset: int) -> str:
    message = f"{revision}:{key}:{offset}".encode()
    return hmac.new(_CURSOR_SECRET, message, hashlib.sha256).hexdigest()[:32]


def encode_library_cursor(*, revision: str, key: str, offset: int) -> str:
    """Encode a revision-bound cursor without embedding query text."""

    if not revision or not key or isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
        raise LibraryResourceError("Invalid library cursor.")
    payload = {"k": key, "o": offset, "r": revision, "s": _cursor_signature(revision, key, offset)}
    encoded = (
        base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
        .decode("ascii")
        .rstrip("=")
    )
    return f"{_CURSOR_PREFIX}{encoded}"


def decode_library_cursor(value: str) -> tuple[str, str, int]:
    """Decode a cursor and reject tampering before application lookup."""

    if not isinstance(value, str) or len(value) > _CURSOR_MAX_LENGTH or not value.startswith(_CURSOR_PREFIX):
        raise LibraryResourceError("Invalid library cursor.")
    encoded = value[len(_CURSOR_PREFIX) :]
    if not encoded or any(
        character not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_" for character in encoded
    ):
        raise LibraryResourceError("Invalid library cursor.")
    try:
        payload = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
    except (ValueError, TypeError, UnicodeDecodeError, json.JSONDecodeError, binascii.Error) as exc:
        raise LibraryResourceError("Invalid library cursor.") from exc
    if not isinstance(payload, dict) or set(payload) != {"k", "o", "r", "s"}:
        raise LibraryResourceError("Invalid library cursor.")
    revision, key, offset, signature = payload.get("r"), payload.get("k"), payload.get("o"), payload.get("s")
    if (
        not isinstance(revision, str)
        or not revision
        or not isinstance(key, str)
        or not key
        or isinstance(offset, bool)
        or not isinstance(offset, int)
        or offset < 0
        or not isinstance(signature, str)
        or not hmac.compare_digest(signature, _cursor_signature(revision, key, offset))
    ):
        raise LibraryResourceError("Invalid library cursor.")
    return revision, key, offset
