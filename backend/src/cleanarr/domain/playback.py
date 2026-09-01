"""Transient, read-only playback evidence for cleanup recommendations.

The types in this module intentionally contain no Jellyfin transport objects and
are never persisted.  User ids are an internal correlation key only; callers
must not expose or log them.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class PlaybackStatus(StrEnum):
    WATCHED = "watched"
    NEVER_WATCHED = "never_watched"
    UNKNOWN = "unknown"


class CleanupMediaType(StrEnum):
    MOVIE = "movie"
    SERIES = "series"


@dataclass(frozen=True)
class JellyfinCleanupItem:
    """Safe subset of a standard Jellyfin Movie or Series response."""

    item_id: str
    display_name: str
    media_type: CleanupMediaType
    created_at: datetime | None
    added_at: datetime | None
    size_bytes: int | None
    tmdb_id: int | None = None
    tvdb_id: int | None = None
    imdb_id: str | None = None


@dataclass(frozen=True)
class PlaybackObservation:
    """One transient response for one expected user/item pair."""

    user_id: str
    item_id: str
    played: bool | None
    play_count: int | None
    last_played_at: datetime | None
    valid: bool = True


@dataclass(frozen=True)
class PlaybackAggregate:
    status: PlaybackStatus
    play_count: int | None
    watched_user_count: int | None
    last_played_at: datetime | None
    unavailable_reason: str | None = None


@dataclass(frozen=True)
class PlaybackReadResult:
    """A bounded provider result; failures are structured, never inferred."""

    users: tuple[str, ...] = ()
    observations: tuple[PlaybackObservation, ...] = ()
    truncated: bool = False
    failure_code: str | None = None


@dataclass(frozen=True)
class CleanupDeletionLink:
    """A convenience projection, never deletion authority."""

    item_type: str
    radarr_movie_id: int | None
    sonarr_series_id: int | None
    jellyfin_item_id: str
    display_name: str


@dataclass(frozen=True)
class SeedingSummary:
    """Only independently proven, fresh downloader facts are populated."""

    torrent_state: str
    readiness: str
    readiness_reason: str | None = None
    torrent_count: int | None = None
    ratio: float | None = None
    seeding_time_seconds: int | None = None
    unavailable_reason: str | None = None


@dataclass(frozen=True)
class CleanupCandidate:
    item: JellyfinCleanupItem
    playback: PlaybackAggregate
    seeding: SeedingSummary
    mapped_arr_id: int | None
    deletion_link: CleanupDeletionLink | None
    source: str
    fetched_at: datetime
    unavailable_reason: str | None = None


def unknown_playback(reason: str) -> PlaybackAggregate:
    return PlaybackAggregate(PlaybackStatus.UNKNOWN, None, None, None, reason)


def reduce_playback(
    *,
    expected_user_ids: tuple[str, ...],
    item_id: str,
    observations: tuple[PlaybackObservation, ...],
    scope_complete: bool,
) -> PlaybackAggregate:
    """Reduce one item's complete user scope without guessing missing evidence."""

    if not scope_complete or not expected_user_ids:
        return unknown_playback("playback_scope_incomplete")
    expected = set(expected_user_ids)
    if len(expected) != len(expected_user_ids):
        return unknown_playback("playback_scope_incomplete")
    matched = [item for item in observations if item.item_id == item_id]
    if len(matched) != len(expected):
        return unknown_playback("playback_observation_incomplete")
    by_user: dict[str, PlaybackObservation] = {}
    for observation in matched:
        if observation.user_id not in expected or observation.user_id in by_user:
            return unknown_playback("playback_observation_conflict")
        if not observation.valid or observation.played is None or observation.play_count is None:
            return unknown_playback("playback_observation_malformed")
        if observation.play_count < 0:
            return unknown_playback("playback_observation_malformed")
        if (observation.played and observation.play_count <= 0) or (
            not observation.played and observation.play_count != 0
        ):
            return unknown_playback("playback_observation_conflict")
        if not observation.played and observation.last_played_at is not None:
            return unknown_playback("playback_observation_conflict")
        by_user[observation.user_id] = observation
    if set(by_user) != expected:
        return unknown_playback("playback_observation_incomplete")
    values = tuple(by_user.values())
    watched = tuple(item for item in values if item.played)
    if not watched:
        return PlaybackAggregate(PlaybackStatus.NEVER_WATCHED, 0, 0, None)
    timestamps = tuple(item.last_played_at for item in watched if item.last_played_at is not None)
    return PlaybackAggregate(
        PlaybackStatus.WATCHED,
        sum(item.play_count or 0 for item in watched),
        len(watched),
        max(timestamps) if timestamps else None,
    )
