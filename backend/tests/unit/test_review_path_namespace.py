"""Provider identity is independent from an untrusted source path namespace."""

from types import SimpleNamespace

import pytest

from cleanarr.api.schemas import JellyfinWebhookPayload
from cleanarr.application.deletion_models import ManualDeleteRequest
from cleanarr.application.manual_deletion import ManualDeletionService
from cleanarr.application.resolver import StrictMovieResolver, StrictSeriesResolver
from cleanarr.domain import FailureReason, ItemType, MediaFingerprint, RadarrMovie, SonarrSeries
from cleanarr.infrastructure.deletion_repository import decode_persisted_event, encode_persisted_event
from tests.fakes import FakeRadarrClient, FakeSonarrClient


@pytest.mark.parametrize("kind", ["movie", "series"])
def test_jellyfin_file_path_does_not_veto_provider_match(kind: str) -> None:
    fingerprint = MediaFingerprint(tmdb_id=100, imdb_id="tt100", path="/media/library/title/title.mkv")
    candidate = (
        RadarrMovie(id=1, title="Movie", path="/data/library/title", tmdb_id=100, imdb_id="tt100")
        if kind == "movie"
        else SonarrSeries(id=1, title="Series", path="/data/library/title", tvdb_id=None, tmdb_id=100, imdb_id="tt100")
    )
    resolver = StrictMovieResolver() if kind == "movie" else StrictSeriesResolver()
    assert resolver.resolve(fingerprint, [candidate]).candidate == candidate


@pytest.mark.parametrize("kind", ["movie", "series"])
def test_trusted_arr_path_conflict_remains_blocked(kind: str) -> None:
    fingerprint = MediaFingerprint(tmdb_id=100, path="/data/old", path_namespace="arr")
    candidate = (
        RadarrMovie(id=1, title="Movie", path="/data/new", tmdb_id=100, imdb_id=None)
        if kind == "movie"
        else SonarrSeries(id=1, title="Series", path="/data/new", tvdb_id=None, tmdb_id=100, imdb_id=None)
    )
    resolver = StrictMovieResolver() if kind == "movie" else StrictSeriesResolver()
    decision = resolver.resolve(fingerprint, [candidate])
    assert decision.candidate is None
    assert decision.reason == FailureReason.CONFLICTING_IDENTIFIERS


def test_path_namespace_never_overrides_conflicting_provider_ids() -> None:
    candidate = RadarrMovie(id=1, title="Movie", path="/data/title", tmdb_id=100, imdb_id="tt100")
    fingerprint = MediaFingerprint(tmdb_id=100, imdb_id="tt200", path="/media/title/title.mkv")
    decision = StrictMovieResolver().resolve(fingerprint, [candidate])
    assert decision.candidate is None
    assert decision.reason == FailureReason.CONFLICTING_IDENTIFIERS


def test_webhook_cannot_claim_an_authoritative_arr_namespace() -> None:
    payload = JellyfinWebhookPayload.model_validate(
        {
            "notification_type": "ItemDeleted",
            "item_type": "Movie",
            "item_id": "untrusted-id",
            "name": "Movie",
            "tmdb_id": 100,
            "path": "/data/title",
            "path_namespace": "arr",
        }
    )
    assert payload.to_domain().fingerprint.path_namespace is None


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", [ItemType.MOVIE, ItemType.SERIES])
async def test_trusted_manual_path_marker_survives_persistence(kind: ItemType) -> None:
    radarr = FakeRadarrClient([RadarrMovie(1, "Movie", "/data/movie", 100, None)], {})
    sonarr = FakeSonarrClient([SonarrSeries(1, "Series", "/data/series", 100, None, None)], {}, {}, {})
    service = ManualDeletionService(
        radarr=lambda: radarr,
        sonarr=lambda: sonarr,
        jellyfin=lambda: SimpleNamespace(),
        strategy_factory=lambda: SimpleNamespace(),
        is_dry_run=lambda: True,
        activity_recorder=SimpleNamespace(),
    )
    request = ManualDeleteRequest(
        item_type=kind,
        radarr_movie_id=1 if kind is ItemType.MOVIE else None,
        sonarr_series_id=1 if kind is ItemType.SERIES else None,
    )
    event = await service.resolve(request)
    assert event.fingerprint.path_namespace == "arr"
    restored = decode_persisted_event(encode_persisted_event(event))
    assert restored.fingerprint.path_namespace == "arr"
