"""API schemas for library browsing and manual deletion actions."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, cast

from pydantic import BaseModel, Field

from cleanarr.application.deletion_models import (
    BatchChildPreviewStatus,
    BatchChildStatus,
    ManualDeleteBatchChildPreviewResponse,
    ManualDeleteBatchChildResponse,
    ManualDeleteBatchListResponse,
    ManualDeleteBatchPreviewRequest,
    ManualDeleteBatchPreviewResponse,
    ManualDeleteBatchResponse,
    ManualDeleteBatchStatus,
    ManualDeleteBatchSubmitRequest,
    ManualDeleteJobListResponse,
    ManualDeleteJobPhase,
    ManualDeleteJobRequest,
    ManualDeleteJobResponse,
    ManualDeleteJobStatus,
    ManualDeletePreviewResponse,
    ManualDeleteRequest,
)
from cleanarr.domain import LibraryDetail, LibraryEpisode, LibraryFile, LibraryItem, LibraryMediaType

__all__ = (
    "BatchChildPreviewStatus",
    "BatchChildStatus",
    "LibraryMoviesResponse",
    "LibraryDetailResponse",
    "LibraryEpisodeResponse",
    "LibraryFileResponse",
    "LibraryFailureResponse",
    "LibraryArtworkResponse",
    "LibraryCountsResponse",
    "LibraryItemResponse",
    "LibraryItemsResponse",
    "LibraryPlaybackResponse",
    "LibrarySafetyResponse",
    "LibrarySeasonResponse",
    "LibrarySeedingResponse",
    "LibrarySeriesResponse",
    "ManualDeleteBatchChildPreviewResponse",
    "ManualDeleteBatchChildResponse",
    "ManualDeleteBatchListResponse",
    "ManualDeleteBatchPreviewRequest",
    "ManualDeleteBatchPreviewResponse",
    "ManualDeleteBatchResponse",
    "ManualDeleteBatchStatus",
    "ManualDeleteBatchSubmitRequest",
    "ManualDeleteJobListResponse",
    "ManualDeleteJobPhase",
    "ManualDeleteJobRequest",
    "ManualDeleteJobResponse",
    "ManualDeleteJobStatus",
    "ManualDeletePreviewResponse",
    "ManualDeleteRequest",
    "MovieSummary",
    "SeasonSummary",
    "SeriesSummary",
)


class SeasonSummary(BaseModel):
    """Season-level summary for the library view."""

    season_number: int
    episode_count: int
    episode_file_count: int
    size_bytes: int
    jellyfin_title: str | None = None
    jellyfin_season_id: str | None = None
    has_seerr_request: bool = False


class SeriesSummary(BaseModel):
    """Series-level summary for the library view."""

    sonarr_id: int
    title: str
    jellyfin_series_title: str | None = None
    seasons: list[SeasonSummary]
    jellyfin_series_id: str | None = None
    has_seerr_request: bool = False


class LibrarySeriesResponse(BaseModel):
    """Response for GET /api/library/series."""

    series: list[SeriesSummary]


class MovieSummary(BaseModel):
    """Movie-level summary for the library view."""

    radarr_id: int
    title: str
    jellyfin_movie_title: str | None = None
    size_bytes: int
    has_file: bool
    jellyfin_movie_id: str | None = None
    has_seerr_request: bool = False


class LibraryMoviesResponse(BaseModel):
    """Response for GET /api/library/movies."""

    movies: list[MovieSummary]


class LibraryFailureResponse(BaseModel):
    """Structured, non-sensitive source failure for list/detail reads."""

    source: str
    code: str
    message: str | None = None


class LibraryArtworkResponse(BaseModel):
    """Artwork availability and an authenticated proxy URL."""

    status: Literal["available", "missing", "unknown"]
    url: str | None = None


class LibraryCountsResponse(BaseModel):
    """Bounded Arr catalogue count summary; null means the source did not prove it."""

    seasons: int | None = None
    episodes: int | None = None
    files: int | None = None


class LibraryPlaybackResponse(BaseModel):
    """Detail-only playback facts with explicit freshness."""

    watched: Literal["watched", "never_watched", "unknown"] | None
    play_count: int | None
    last_played_at: datetime | None
    freshness: Literal["fresh", "stale", "unknown"] | None


class LibrarySeedingResponse(BaseModel):
    """Detail-only downloader facts; unknown is never treated as ready."""

    state: Literal["downloading", "seeding", "stopped", "unknown"] | None
    readiness: Literal["ready", "not_ready", "unknown"] | None
    ratio: float | None
    seeded_seconds: int | None
    reason: str | None


class LibrarySafetyResponse(BaseModel):
    """Safety posture for a selected item, separate from deletion authority."""

    status: Literal["safe", "blocked", "unknown"]
    reason: str | None


class LibrarySeasonResponse(BaseModel):
    """Bounded season summary for a selected series detail."""

    season_number: int
    title: str | None = None
    episode_count: int | None = None
    episode_file_count: int | None = None
    size: int | None = None


class LibraryItemResponse(BaseModel):
    """Stable, privacy-safe projection shared by movie and series cards.

    Raw Arr IDs, service URLs, root paths, credentials, and playback history
    are intentionally absent from this list projection.  The delete target is
    only a compatibility payload; the mutation endpoint still resolves and
    validates ownership before changing anything.
    """

    resource_id: str
    media_type: Literal["movie", "series"]
    display_name: str
    title: str
    year: int | None = None
    size: int | None = None
    has_file: bool | None = None
    counts: LibraryCountsResponse | None = None
    added_at: datetime | None = None
    artwork: LibraryArtworkResponse
    delete_target: dict[str, object] | None = None
    fetched_at: datetime | None = None
    catalog_revision: str

    @classmethod
    def from_domain(cls, item: LibraryItem, *, catalog_revision: str = "") -> LibraryItemResponse:
        artwork_status = (
            item.artwork_status if item.artwork_status in {"available", "missing", "unknown"} else "unknown"
        )
        if item.media_type is LibraryMediaType.MOVIE:
            counts = LibraryCountsResponse(files=(1 if item.has_file else 0) if item.has_file is not None else None)
        else:
            counts = LibraryCountsResponse(
                episodes=item.episode_count,
                files=item.episode_file_count,
            )
        return cls(
            resource_id=item.resource_id,
            media_type=item.media_type.value,
            display_name=item.jellyfin_title or item.title,
            title=item.title,
            year=item.year,
            size=item.size_bytes,
            has_file=item.has_file,
            counts=counts,
            added_at=item.added_at,
            artwork=LibraryArtworkResponse(
                status=cast(Literal["available", "missing", "unknown"], artwork_status),
                url=f"/api/library/artwork/{item.resource_id}" if artwork_status == "available" else None,
            ),
            delete_target={
                "item_type": "Movie" if item.media_type is LibraryMediaType.MOVIE else "Series",
                "resource_id": item.resource_id,
                "radarr_movie_id": item.legacy_id if item.media_type is LibraryMediaType.MOVIE else None,
                "sonarr_series_id": item.legacy_id if item.media_type is LibraryMediaType.SERIES else None,
                "jellyfin_item_id": item.jellyfin_item_id,
            },
            fetched_at=item.fetched_at,
            catalog_revision=catalog_revision,
        )


class LibraryItemsResponse(BaseModel):
    """Revision-bound cursor page for GET /api/library/items."""

    items: list[LibraryItemResponse]
    next_cursor: str | None = None
    source_status: Literal["complete", "partial", "unavailable"]
    source_failures: list[LibraryFailureResponse] = Field(default_factory=list)
    catalog_revision: str


class LibraryEpisodeResponse(BaseModel):
    """Bounded series-detail episode projection."""

    id: int
    season_number: int
    episode_number: int
    has_file: bool | None
    episode_file_id: int | None
    monitored: bool | None


class LibraryFileResponse(BaseModel):
    """Bounded series-detail episode-file projection without raw paths."""

    id: int
    season_number: int | None
    size_bytes: int | None


class LibraryDetailResponse(BaseModel):
    """Flat item detail with bounded playback, seeding, and series facts."""

    resource_id: str
    media_type: Literal["movie", "series"]
    display_name: str
    title: str
    year: int | None = None
    size: int | None = None
    has_file: bool | None = None
    counts: LibraryCountsResponse | None = None
    added_at: datetime | None = None
    artwork: LibraryArtworkResponse
    delete_target: dict[str, object] | None = None
    fetched_at: datetime | None = None
    catalog_revision: str
    playback: LibraryPlaybackResponse | None = None
    library_dates: dict[str, datetime | None] | None = None
    seeding: LibrarySeedingResponse | None = None
    seasons: list[LibrarySeasonResponse] | None = None
    safety: LibrarySafetyResponse | None = None
    # Flat aliases keep adapters that do not preserve nested objects usable;
    # nested objects above remain the canonical v2 representation.
    playback_status: Literal["watched", "never_watched", "unknown"] | None = None
    playback_freshness: Literal["fresh", "stale", "unknown"] | None = None
    play_count: int | None = None
    last_played_at: datetime | None = None
    seeding_state: Literal["downloading", "seeding", "stopped", "unknown"] | None = None
    seeding_readiness: Literal["ready", "not_ready", "unknown"] | None = None
    seeding_ratio: float | None = None
    seeding_time_seconds: int | None = None
    seeding_reason: str | None = None
    unknown_reasons: list[str] = Field(default_factory=list)

    @classmethod
    def from_domain(cls, detail: LibraryDetail) -> LibraryDetailResponse:
        item = LibraryItemResponse.from_domain(detail.item, catalog_revision=detail.revision)
        playback_status = _playback_status(detail.item.playback_status)
        playback_freshness = _playback_freshness(detail.item.playback_freshness)
        seeding_state = _seeding_state(detail.item.seeding_state)
        seeding_readiness = _seeding_readiness(detail.item.seeding_readiness)
        unknown_reasons = _detail_unknown_reasons(detail)
        return cls(
            **item.model_dump(),
            playback=LibraryPlaybackResponse(
                watched=playback_status,
                play_count=detail.item.play_count,
                last_played_at=detail.item.last_played_at,
                freshness=playback_freshness,
            ),
            library_dates={"added_at": detail.item.added_at, "updated_at": None},
            seeding=LibrarySeedingResponse(
                state=seeding_state,
                readiness=seeding_readiness,
                ratio=detail.item.seeding_ratio,
                seeded_seconds=detail.item.seeding_time_seconds,
                reason=detail.item.seeding_reason,
            ),
            seasons=(
                None
                if detail.item.media_type is not LibraryMediaType.SERIES
                or detail.error_code == "series_detail_unavailable"
                else _season_summaries(detail)
            ),
            safety=LibrarySafetyResponse(status="unknown", reason="safety_preflight_required"),
            playback_status=playback_status,
            playback_freshness=playback_freshness,
            play_count=detail.item.play_count,
            last_played_at=detail.item.last_played_at,
            seeding_state=seeding_state,
            seeding_readiness=seeding_readiness,
            seeding_ratio=detail.item.seeding_ratio,
            seeding_time_seconds=detail.item.seeding_time_seconds,
            seeding_reason=detail.item.seeding_reason,
            unknown_reasons=unknown_reasons,
        )


def _playback_status(value: str) -> Literal["watched", "never_watched", "unknown"]:
    return cast(
        Literal["watched", "never_watched", "unknown"],
        value if value in {"watched", "never_watched"} else "unknown",
    )


def _playback_freshness(value: str) -> Literal["fresh", "stale", "unknown"]:
    return cast(Literal["fresh", "stale", "unknown"], value if value in {"fresh", "stale"} else "unknown")


def _seeding_state(value: str) -> Literal["downloading", "seeding", "stopped", "unknown"]:
    return cast(
        Literal["downloading", "seeding", "stopped", "unknown"],
        value if value in {"downloading", "seeding", "stopped"} else "unknown",
    )


def _seeding_readiness(value: str) -> Literal["ready", "not_ready", "unknown"]:
    if value == "eligible":
        return "ready"
    if value in {"blocked", "excluded", "disabled"}:
        return "not_ready"
    return "unknown"


def _season_summaries(detail: LibraryDetail) -> list[LibrarySeasonResponse]:
    """Summarize the bounded episode/file pair without returning raw paths."""

    episodes_by_season: dict[int, list[LibraryEpisode]] = {}
    files_by_season: dict[int, list[LibraryFile]] = {}
    for episode in detail.episodes:
        episodes_by_season.setdefault(episode.season_number, []).append(episode)
    for file in detail.files:
        if file.season_number is not None:
            files_by_season.setdefault(file.season_number, []).append(file)
    season_numbers = sorted(set(episodes_by_season) | set(files_by_season))
    result: list[LibrarySeasonResponse] = []
    for season_number in season_numbers:
        episodes = episodes_by_season.get(season_number, [])
        files = files_by_season.get(season_number, [])
        sizes = [file.size_bytes for file in files]
        size = (
            sum(value for value in sizes if value is not None)
            if files and all(value is not None for value in sizes)
            else None
        )
        result.append(
            LibrarySeasonResponse(
                season_number=season_number,
                episode_count=len(episodes) if episodes else None,
                episode_file_count=len({file.id for file in files}) if files else None,
                size=size,
            )
        )
    return result


def _detail_unknown_reasons(detail: LibraryDetail) -> list[str]:
    values = [
        detail.item.playback_reason,
        detail.item.seeding_reason,
        detail.error_code,
        "safety_preflight_required",
    ]
    return list(dict.fromkeys(value for value in values if value))
