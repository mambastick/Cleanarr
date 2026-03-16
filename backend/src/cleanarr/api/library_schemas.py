"""API schemas for library browsing and manual deletion actions."""

from __future__ import annotations

from pydantic import BaseModel

from cleanarr.domain import ItemType


class SeasonSummary(BaseModel):
    """Season-level summary for the library view."""

    season_number: int
    episode_count: int
    episode_file_count: int
    size_bytes: int
    jellyfin_season_id: str | None = None


class SeriesSummary(BaseModel):
    """Series-level summary for the library view."""

    sonarr_id: int
    title: str
    seasons: list[SeasonSummary]
    jellyfin_series_id: str | None = None


class LibrarySeriesResponse(BaseModel):
    """Response for GET /api/library/series."""

    series: list[SeriesSummary]


class MovieSummary(BaseModel):
    """Movie-level summary for the library view."""

    radarr_id: int
    title: str
    size_bytes: int
    has_file: bool
    jellyfin_movie_id: str | None = None


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
