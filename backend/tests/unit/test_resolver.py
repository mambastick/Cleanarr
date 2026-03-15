"""Tests for strict matching."""

from cleanarr.application.resolver import StrictMovieResolver, StrictSeriesResolver
from cleanarr.domain import FailureReason, MediaFingerprint, RadarrMovie, SonarrSeries


def test_movie_resolver_prefers_tmdb_before_imdb_and_path() -> None:
    resolver = StrictMovieResolver()
    movies = [
        RadarrMovie(id=1, title="Movie", path="/data/a", tmdb_id=100, imdb_id="tt100"),
        RadarrMovie(id=2, title="Movie 2", path="/data/b", tmdb_id=200, imdb_id="tt200"),
    ]

    match = resolver.resolve(
        MediaFingerprint(tmdb_id=200, imdb_id="tt100", path="/data/a"),
        movies,
    )

    assert match.candidate == movies[1]
    assert match.matched_by == "tmdb_id"


def test_movie_resolver_marks_ambiguous_matches() -> None:
    resolver = StrictMovieResolver()
    movies = [
        RadarrMovie(id=1, title="Movie", path="/data/a", tmdb_id=100, imdb_id="tt100"),
        RadarrMovie(id=2, title="Movie 2", path="/data/b", tmdb_id=100, imdb_id="tt200"),
    ]

    match = resolver.resolve(MediaFingerprint(tmdb_id=100), movies)

    assert match.candidate is None
    assert match.reason == FailureReason.AMBIGUOUS_MATCH


def test_series_resolver_falls_back_to_exact_path() -> None:
    resolver = StrictSeriesResolver()
    series = [
        SonarrSeries(id=1, title="Series", path="/data/series/one", tvdb_id=None, tmdb_id=None, imdb_id=None),
    ]

    match = resolver.resolve(MediaFingerprint(path="/data/series/one/"), series)

    assert match.candidate == series[0]
    assert match.matched_by == "path"
