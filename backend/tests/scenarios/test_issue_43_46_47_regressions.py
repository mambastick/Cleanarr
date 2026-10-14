"""Regression contracts for collector persistence, strict identity, and movie exclusivity."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
import respx

from cleanarr.application.deletion_jobs import ManualDeletionJobService
from cleanarr.application.deletion_models import (
    ActionResultResponse,
    ManualDeleteJobStatus,
    ManualDeleteRequest,
    ProcessingResultResponse,
)
from cleanarr.application.manual_deletion import ManualDeletionService
from cleanarr.application.resolver import StrictMovieResolver, StrictSeerrResolver, StrictSeriesResolver
from cleanarr.application.strategies import DeletionStrategyFactory
from cleanarr.domain import (
    ActionResult,
    ActionStatus,
    ExternalServiceError,
    FailureReason,
    ItemType,
    MediaDeletionEvent,
    MediaFingerprint,
    OverallStatus,
    ProcessingResult,
    RadarrHistoryRecord,
    RadarrMovie,
    SeerrMedia,
    SonarrSeries,
)
from cleanarr.infrastructure.clients import RadarrClient
from cleanarr.infrastructure.deletion_repository import SQLiteDeletionRepository
from tests.fakes import FakeDownloaderClient, FakeRadarrClient, FakeSeerrClient, FakeSonarrClient


def _event() -> MediaDeletionEvent:
    return MediaDeletionEvent(
        notification_type="ItemDeleted",
        item_type=ItemType.MOVIE,
        item_id="manual:radarr:1",
        name="Movie",
        fingerprint=MediaFingerprint(tmdb_id=1, path="/media/movie"),
    )


def _result_response(
    event: MediaDeletionEvent, status: OverallStatus = OverallStatus.SUCCESS
) -> ProcessingResultResponse:
    return ProcessingResultResponse(
        item_type=event.item_type,
        item_id=event.item_id,
        name=event.name,
        status=status,
        fingerprint={"tmdb_id": event.fingerprint.tmdb_id, "path": event.fingerprint.path},
        actions=[],
    )


@pytest.mark.asyncio
async def test_manual_execute_records_the_complete_partial_mutation_result() -> None:
    event = _event()
    partial = ProcessingResult(
        event=event,
        status=OverallStatus.PARTIAL_FAILURE,
        actions=(
            ActionResult("radarr", "delete_movie", ActionStatus.DELETED, "Deleted movie."),
            ActionResult(
                "seerr",
                "delete_media",
                ActionStatus.FAILED,
                "Seerr unavailable.",
                reason=FailureReason.DOWNSTREAM_ERROR,
            ),
        ),
    )
    recorded: list[tuple[object, str | None]] = []

    class Strategy:
        async def handle(self, observed: MediaDeletionEvent):
            assert observed is event
            return partial

    class Factory:
        def for_item_type(self, item_type: ItemType, *, dry_run: bool = False):
            assert item_type is ItemType.MOVIE
            assert dry_run is False
            return Strategy()

    class Recorder:
        async def record(self, result: object, *, display_name: str | None = None) -> None:
            recorded.append((result, display_name))

    service = ManualDeletionService(
        radarr=lambda: SimpleNamespace(),
        sonarr=lambda: SimpleNamespace(),
        jellyfin=lambda: SimpleNamespace(),
        strategy_factory=lambda: Factory(),
        is_dry_run=lambda: False,
        activity_recorder=Recorder(),
    )
    request = ManualDeleteRequest(item_type=ItemType.MOVIE, radarr_movie_id=1, display_name="  Movie label  ")

    response = await service.execute(request, event)

    assert response.status is OverallStatus.PARTIAL_FAILURE
    assert len(recorded) == 1
    saved, display_name = recorded[0]
    assert saved is partial
    assert display_name == "Movie label"
    assert [action.status for action in partial.actions] == [ActionStatus.DELETED, ActionStatus.FAILED]


@pytest.mark.asyncio
async def test_job_persists_partial_mutation_result_and_never_replays_deleted_action(tmp_path: Path) -> None:
    event = _event()
    partial = _result_response(event, OverallStatus.PARTIAL_FAILURE).model_copy(
        update={
            "actions": [
                ActionResultResponse(
                    system="radarr",
                    action="delete_movie",
                    status=ActionStatus.DELETED,
                    message="Deleted movie.",
                    details={},
                ),
                ActionResultResponse(
                    system="seerr",
                    action="delete_media",
                    status=ActionStatus.FAILED,
                    message="Seerr unavailable.",
                    reason=FailureReason.DOWNSTREAM_ERROR,
                    details={"error": "Seerr unavailable."},
                ),
            ]
        }
    )
    calls = 0

    async def resolver(payload: ManualDeleteRequest) -> MediaDeletionEvent:
        return event

    async def previewer(payload: ManualDeleteRequest, observed: MediaDeletionEvent) -> ProcessingResultResponse:
        return _result_response(observed)

    async def runner(
        payload: ManualDeleteRequest, observed: MediaDeletionEvent, report: object
    ) -> ProcessingResultResponse:
        nonlocal calls
        calls += 1
        return partial

    service = ManualDeletionJobService(
        resolver,
        previewer,
        runner,
        repository=SQLiteDeletionRepository(tmp_path / "cleanarr.db"),
        retry_delays_seconds=(0.0,),
    )
    request = ManualDeleteRequest(item_type=ItemType.MOVIE, radarr_movie_id=1, idempotency_key=uuid4())
    preview = await service.preview(request)
    queued = await service.submit(request.model_copy(update={"confirmed_plan_hash": preview.plan_hash}))
    try:
        for _ in range(200):
            current = service.get(queued.id)
            if current.status is ManualDeleteJobStatus.FAILED:
                break
            await asyncio.sleep(0.01)
        failed = service.get(queued.id)
        assert failed.status is ManualDeleteJobStatus.FAILED
        assert failed.result is not None
        assert failed.result.status is OverallStatus.PARTIAL_FAILURE
        assert any(action.status is ActionStatus.DELETED for action in failed.result.actions)
        assert failed.error_code == "partial_result_not_retryable"
        assert failed.attempt_count == 1
        assert calls == 1
    finally:
        await service.stop()


@pytest.mark.asyncio
async def test_movie_hash_exclusivity_checks_radarr_movies_from_different_instances() -> None:
    movies = [
        RadarrMovie(1, "Movie", "/media/movie", 1, None, service_id="radarr-one"),
        RadarrMovie(2, "Mirror", "/media/mirror", 2, None, service_id="radarr-two"),
    ]
    radarr = FakeRadarrClient(
        movies,
        {
            1: [RadarrHistoryRecord(1, 1, "grabbed", "SHARED-HASH", None)],
            2: [RadarrHistoryRecord(2, 2, "grabbed", "shared-hash", None)],
        },
    )
    seerr = FakeSeerrClient([SeerrMedia(1, "movie", 1, None, None, None)], [], [])
    downloader = FakeDownloaderClient({"SHARED-HASH"})
    factory = DeletionStrategyFactory(
        dry_run=False,
        logger=logging.getLogger("tests"),
        radarr=radarr,
        sonarr=FakeSonarrClient([], {}, {}, {}),
        seerr=seerr,
        downloader=downloader,
    )

    result = await factory.for_item_type(ItemType.MOVIE).handle(_event())

    assert any(action.reason is FailureReason.PACK_TORRENT for action in result.actions)
    assert radarr.deleted_movie_ids == []
    assert downloader.deleted_hashes == []


@pytest.mark.parametrize("kind", ["movie", "series", "seerr_movie", "seerr_tv"])
def test_all_strict_resolvers_casefold_imdb(kind: str) -> None:
    fingerprint = MediaFingerprint(imdb_id="tt42")
    if kind == "movie":
        decision = StrictMovieResolver().resolve(
            fingerprint,
            [RadarrMovie(1, "Movie", "/other/path", None, "TT42")],
        )
    elif kind == "series":
        decision = StrictSeriesResolver().resolve(
            fingerprint,
            [SonarrSeries(1, "Series", "/other/path", None, None, "TT42")],
        )
    else:
        media_type = "movie" if kind == "seerr_movie" else "tv"
        resolver = StrictSeerrResolver()
        media = [SeerrMedia(1, media_type, None, None, "TT42", None)]
        decision = (
            resolver.resolve_movie(fingerprint, media)
            if media_type == "movie"
            else resolver.resolve_tv(fingerprint, media)
        )

    assert decision.candidate is not None
    assert decision.matched_by == "imdb_id"


@pytest.mark.parametrize("kind", ["movie", "series"])
def test_arr_resolvers_normalize_trailing_slashes_on_paths(kind: str) -> None:
    fingerprint = MediaFingerprint(path="/media/title/")
    if kind == "movie":
        decision = StrictMovieResolver().resolve(
            fingerprint,
            [RadarrMovie(1, "Movie", "/media/title", None, None)],
        )
    else:
        decision = StrictSeriesResolver().resolve(
            fingerprint,
            [SonarrSeries(1, "Series", "/media/title", None, None, None)],
        )

    assert decision.candidate is not None
    assert decision.matched_by == "path"


@pytest.mark.parametrize("kind", ["movie", "series", "seerr_movie", "seerr_tv"])
def test_all_strict_resolvers_fail_closed_when_provider_ids_are_absent(kind: str) -> None:
    fingerprint = MediaFingerprint()
    if kind == "movie":
        decision = StrictMovieResolver().resolve(fingerprint, [RadarrMovie(1, "Movie", "/media/title", None, None)])
    elif kind == "series":
        decision = StrictSeriesResolver().resolve(
            fingerprint, [SonarrSeries(1, "Series", "/media/title", None, None, None)]
        )
    else:
        media_type = "movie" if kind == "seerr_movie" else "tv"
        media = [SeerrMedia(1, media_type, None, None, None, None)]
        resolver = StrictSeerrResolver()
        decision = (
            resolver.resolve_movie(fingerprint, media)
            if media_type == "movie"
            else resolver.resolve_tv(fingerprint, media)
        )

    assert decision.candidate is None
    assert decision.reason is FailureReason.NO_MATCH


@pytest.mark.asyncio
@respx.mock
async def test_radarr_history_rejects_incomplete_payloads_instead_of_authorizing_cleanup() -> None:
    client = RadarrClient(base_url="http://radarr/api/v3", api_key="key", timeout_seconds=5)
    try:
        for payload in ({"page": 1}, {"records": {"id": 1}}, {"records": [{"id": 1, "movieId": 1}]}):
            respx.get("http://radarr/api/v3/history/movie").respond(status_code=200, json=payload)
            with pytest.raises(ExternalServiceError):
                await client.list_movie_history(1)
            respx.reset()
    finally:
        await client.close()


@pytest.mark.parametrize(
    "reason",
    [
        FailureReason.PACK_TORRENT,
        FailureReason.SHARED_FILE,
        FailureReason.SHARED_PATH,
        FailureReason.OWNERSHIP_UNVERIFIABLE,
    ],
)
async def test_blocked_scope_never_deletes_jellyfin_in_preview_or_live_execution(reason):
    from cleanarr.domain import ActionResult

    event = _event()
    result = ProcessingResult(
        event,
        OverallStatus.SUCCESS,
        (ActionResult("downloader", "delete_hash", ActionStatus.SKIPPED, "Retained", reason=reason),),
    )

    class Strategy:
        async def handle(self, ignored):
            return result

    class Factory:
        def for_item_type(self, kind, **kwargs):
            return Strategy()

    class Jellyfin:
        def __init__(self):
            self.deleted = []

        async def delete_item(self, item_id):
            self.deleted.append(item_id)

    class Recorder:
        async def record(self, value, **kwargs):
            pass

    jellyfin = Jellyfin()
    service = ManualDeletionService(
        radarr=lambda: FakeRadarrClient([], {}),
        sonarr=lambda: FakeSonarrClient([], {}, {}, {}),
        jellyfin=lambda: jellyfin,
        strategy_factory=lambda: Factory(),
        is_dry_run=lambda: False,
        activity_recorder=Recorder(),
    )
    request = ManualDeleteRequest(item_type=ItemType.MOVIE, radarr_movie_id=1, jellyfin_item_id="jf-item")
    preview = await service.preview(request, event)
    live = await service.execute(request, event)
    assert jellyfin.deleted == []
    assert preview.actions[-1].status is ActionStatus.SKIPPED
    assert live.actions[-1].status is ActionStatus.SKIPPED
