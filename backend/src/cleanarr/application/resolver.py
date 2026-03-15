"""Strict matching helpers."""

from __future__ import annotations

from dataclasses import dataclass

from cleanarr.domain import (
    FailureReason,
    JellyseerrMedia,
    MediaFingerprint,
    RadarrMovie,
    SonarrSeries,
)


@dataclass(frozen=True)
class MatchDecision[T]:
    """Outcome of a strict matching attempt."""

    candidate: T | None
    matched_by: str | None = None
    reason: FailureReason | None = None

    @property
    def is_match(self) -> bool:
        return self.candidate is not None


class StrictMovieResolver:
    """Resolve movies using strict identifiers only."""

    def resolve(
        self,
        fingerprint: MediaFingerprint,
        movies: list[RadarrMovie],
    ) -> MatchDecision[RadarrMovie]:
        if fingerprint.tmdb_id is not None:
            match = self._unique(
                [movie for movie in movies if movie.tmdb_id == fingerprint.tmdb_id],
                matched_by="tmdb_id",
            )
            if match is not None:
                return match

        if fingerprint.imdb_id:
            match = self._unique(
                [movie for movie in movies if movie.imdb_id == fingerprint.imdb_id],
                matched_by="imdb_id",
            )
            if match is not None:
                return match

        if fingerprint.normalized_path:
            path = fingerprint.normalized_path
            match = self._unique(
                [movie for movie in movies if movie.path.rstrip("/") == path],
                matched_by="path",
            )
            if match is not None:
                return match

        return MatchDecision(candidate=None, reason=FailureReason.NO_MATCH)

    @staticmethod
    def _unique(
        items: list[RadarrMovie],
        *,
        matched_by: str,
    ) -> MatchDecision[RadarrMovie] | None:
        if not items:
            return None
        if len(items) > 1:
            return MatchDecision(candidate=None, reason=FailureReason.AMBIGUOUS_MATCH)
        return MatchDecision(candidate=items[0], matched_by=matched_by)


class StrictSeriesResolver:
    """Resolve series using strict identifiers only."""

    def resolve(
        self,
        fingerprint: MediaFingerprint,
        series_list: list[SonarrSeries],
    ) -> MatchDecision[SonarrSeries]:
        if fingerprint.tvdb_id is not None:
            match = self._unique(
                [series for series in series_list if series.tvdb_id == fingerprint.tvdb_id],
                matched_by="tvdb_id",
            )
            if match is not None:
                return match

        if fingerprint.tmdb_id is not None:
            match = self._unique(
                [series for series in series_list if series.tmdb_id == fingerprint.tmdb_id],
                matched_by="tmdb_id",
            )
            if match is not None:
                return match

        if fingerprint.imdb_id:
            match = self._unique(
                [series for series in series_list if series.imdb_id == fingerprint.imdb_id],
                matched_by="imdb_id",
            )
            if match is not None:
                return match

        if fingerprint.normalized_path:
            path = fingerprint.normalized_path
            match = self._unique(
                [series for series in series_list if series.path.rstrip("/") == path],
                matched_by="path",
            )
            if match is not None:
                return match

        return MatchDecision(candidate=None, reason=FailureReason.NO_MATCH)

    @staticmethod
    def _unique(
        items: list[SonarrSeries],
        *,
        matched_by: str,
    ) -> MatchDecision[SonarrSeries] | None:
        if not items:
            return None
        if len(items) > 1:
            return MatchDecision(candidate=None, reason=FailureReason.AMBIGUOUS_MATCH)
        return MatchDecision(candidate=items[0], matched_by=matched_by)


class StrictJellyseerrResolver:
    """Resolve Jellyseerr media by strict external identifiers."""

    def resolve_movie(
        self,
        fingerprint: MediaFingerprint,
        media_items: list[JellyseerrMedia],
    ) -> MatchDecision[JellyseerrMedia]:
        movie_items = [item for item in media_items if item.media_type == "movie"]
        if fingerprint.tmdb_id is not None:
            match = self._unique([item for item in movie_items if item.tmdb_id == fingerprint.tmdb_id], "tmdb_id")
            if match is not None:
                return match
        if fingerprint.imdb_id:
            match = self._unique([item for item in movie_items if item.imdb_id == fingerprint.imdb_id], "imdb_id")
            if match is not None:
                return match
        return MatchDecision(candidate=None, reason=FailureReason.NO_MATCH)

    def resolve_tv(
        self,
        fingerprint: MediaFingerprint,
        media_items: list[JellyseerrMedia],
    ) -> MatchDecision[JellyseerrMedia]:
        tv_items = [item for item in media_items if item.media_type == "tv"]
        if fingerprint.tvdb_id is not None:
            match = self._unique([item for item in tv_items if item.tvdb_id == fingerprint.tvdb_id], "tvdb_id")
            if match is not None:
                return match
        if fingerprint.tmdb_id is not None:
            match = self._unique([item for item in tv_items if item.tmdb_id == fingerprint.tmdb_id], "tmdb_id")
            if match is not None:
                return match
        if fingerprint.imdb_id:
            match = self._unique([item for item in tv_items if item.imdb_id == fingerprint.imdb_id], "imdb_id")
            if match is not None:
                return match
        return MatchDecision(candidate=None, reason=FailureReason.NO_MATCH)

    @staticmethod
    def _unique(
        items: list[JellyseerrMedia],
        matched_by: str,
    ) -> MatchDecision[JellyseerrMedia] | None:
        if not items:
            return None
        if len(items) > 1:
            return MatchDecision(candidate=None, reason=FailureReason.AMBIGUOUS_MATCH)
        return MatchDecision(candidate=items[0], matched_by=matched_by)
