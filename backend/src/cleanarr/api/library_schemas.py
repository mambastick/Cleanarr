"""API schemas for library browsing and manual deletion actions."""

from __future__ import annotations

from pydantic import BaseModel

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

__all__ = (
    "BatchChildPreviewStatus",
    "BatchChildStatus",
    "LibraryMoviesResponse",
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
