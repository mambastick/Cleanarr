"""API schemas for library browsing and manual deletion actions."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel

from cleanarr.api.schemas import ProcessingResultResponse
from cleanarr.domain import ItemType


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


class ManualDeleteRequest(BaseModel):
    """Request body for POST /api/actions/delete."""

    item_type: ItemType
    sonarr_series_id: int | None = None
    radarr_movie_id: int | None = None
    season_number: int | None = None
    jellyfin_item_id: str | None = None


class ManualDeleteJobStatus(StrEnum):
    """Lifecycle status of a queued manual deletion."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ManualDeleteJobPhase(StrEnum):
    """User-facing phase of a queued manual deletion."""

    QUEUED = "queued"
    LOCATING = "locating"
    CLEANING = "cleaning"
    RECORDING = "recording"
    JELLYFIN = "jellyfin"
    COMPLETED = "completed"
    FAILED = "failed"


class ManualDeleteJobResponse(BaseModel):
    """Current state of one background manual deletion."""

    id: UUID
    item_type: ItemType
    item_name: str | None = None
    status: ManualDeleteJobStatus
    phase: ManualDeleteJobPhase
    progress_percent: int
    message: str
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    result: ProcessingResultResponse | None = None
    error: str | None = None


class ManualDeleteJobListResponse(BaseModel):
    """Recent background manual deletions."""

    jobs: list[ManualDeleteJobResponse]
