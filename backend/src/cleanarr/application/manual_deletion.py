"""Manual deletion orchestration independent from HTTP transport and SQLite."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Sequence
from math import isqrt
from typing import Protocol

from cleanarr.application.deletion_jobs import DeletionProgressReporter
from cleanarr.application.deletion_models import ManualDeleteJobPhase, ManualDeleteRequest, ProcessingResultResponse
from cleanarr.application.library_identity import matching_jellyfin_items, matching_jellyfin_seasons
from cleanarr.application.ports import RadarrClientPort, SonarrClientPort
from cleanarr.application.resolver import StrictMovieResolver
from cleanarr.application.results import observe_actions
from cleanarr.application.strategies import DeletionStrategyFactory
from cleanarr.domain import (
    ActionResult,
    ActionStatus,
    FailureReason,
    ItemType,
    JellyfinItem,
    LibraryMediaType,
    LibraryResource,
    LibraryResourceError,
    MediaDeletionEvent,
    MediaFingerprint,
    OverallStatus,
    ProcessingResult,
    RadarrMovie,
    SonarrSeries,
    decode_library_resource,
)
from cleanarr.domain.config import RuntimeConfig

_logger = logging.getLogger("cleanarr")


class ManualDeletionResolutionError(RuntimeError):
    """A transport-neutral failure while resolving one manual selection."""


class ManualDeletionValidationError(ManualDeletionResolutionError, ValueError):
    """A malformed manual deletion command with stable transport-safe detail."""

    def __init__(self, message: str, *, code: str = "validation_error") -> None:
        super().__init__(message)
        self.code = code


class LibraryItemChangedError(ManualDeletionValidationError):
    """Stable library identity no longer matches the legacy routed selection."""

    def __init__(self, message: str = "The library item changed; preview it again.") -> None:
        super().__init__(message, code="library_item_changed")


class ManualDeletionNotFoundError(ManualDeletionResolutionError, LookupError):
    """The explicitly selected Arr item no longer exists."""


class JellyfinDeletionPort(Protocol):
    """Minimal downstream port needed after an otherwise safe manual cascade."""

    async def list_items(self, *, include_types: list[str]) -> Sequence[JellyfinItem]: ...

    async def delete_item(self, item_id: str) -> None: ...


class ActivityRecorderPort(Protocol):
    """Persist an application result without coupling orchestration to storage."""

    async def record(self, result: ProcessingResult, *, display_name: str | None = None) -> None: ...


class ManualDeletionService:
    """Resolve, preview, execute, and record one manually selected cascade."""

    def __init__(
        self,
        *,
        radarr: Callable[[], RadarrClientPort],
        sonarr: Callable[[], SonarrClientPort],
        jellyfin: Callable[[], JellyfinDeletionPort],
        strategy_factory: Callable[[], DeletionStrategyFactory],
        is_dry_run: Callable[[], bool],
        activity_recorder: ActivityRecorderPort,
        config: Callable[[], RuntimeConfig] | None = None,
    ) -> None:
        self._radarr = radarr
        self._sonarr = sonarr
        self._jellyfin = jellyfin
        self._strategy_factory = strategy_factory
        self._is_dry_run = is_dry_run
        self._activity_recorder = activity_recorder
        self._config = config

    async def resolve(self, payload: ManualDeleteRequest) -> MediaDeletionEvent:
        """Resolve an explicit library selection into one stable deletion event."""

        if payload.jellyfin_only:
            return await self._resolve_jellyfin_only_movie(payload)

        if payload.item_type is ItemType.MOVIE:
            if payload.radarr_movie_id is None:
                if payload.library_resource_id is not None:
                    raise LibraryItemChangedError()
                raise ManualDeletionValidationError("radarr_movie_id is required for movie deletion.")
            movies_list = list(await self._radarr().list_movies())
            movie = self._resolve_movie_resource(payload, movies_list)
            if movie is None:
                raise ManualDeletionNotFoundError(f"Radarr movie {payload.radarr_movie_id} not found.")
            await self._verify_jellyfin_binding(payload, LibraryMediaType.MOVIE, movie, movies_list)
            return MediaDeletionEvent(
                notification_type="ItemDeleted",
                item_type=ItemType.MOVIE,
                item_id=f"manual:radarr:{movie.id}",
                name=movie.title,
                fingerprint=MediaFingerprint(
                    tmdb_id=movie.tmdb_id,
                    imdb_id=movie.imdb_id,
                    path=movie.path,
                ),
            )

        if payload.item_type not in {ItemType.SERIES, ItemType.SEASON}:
            raise ManualDeletionValidationError("Manual deletion supports movies, series, and seasons.")
        if payload.sonarr_series_id is None:
            if payload.library_resource_id is not None:
                raise LibraryItemChangedError()
            raise ManualDeletionValidationError("sonarr_series_id is required for series/season deletion.")
        series_list = list(await self._sonarr().list_series())
        series = self._resolve_series_resource(payload, series_list)
        if series is None:
            raise ManualDeletionNotFoundError(f"Sonarr series {payload.sonarr_series_id} not found.")
        if payload.item_type is ItemType.SEASON and payload.season_number is None:
            raise ManualDeletionValidationError("season_number is required for season deletion.")
        await self._verify_jellyfin_binding(payload, LibraryMediaType.SERIES, series, series_list)
        scope = "series" if payload.item_type is ItemType.SERIES else f"season:{payload.season_number}"
        return MediaDeletionEvent(
            notification_type="ItemDeleted",
            item_type=payload.item_type,
            item_id=f"manual:sonarr:{series.id}:{scope}",
            name=series.title,
            fingerprint=MediaFingerprint(
                tvdb_id=series.tvdb_id,
                tmdb_id=series.tmdb_id,
                imdb_id=series.imdb_id,
                path=series.path,
            ),
            series_name=series.title,
            season_number=payload.season_number,
        )

    async def _resolve_jellyfin_only_movie(self, payload: ManualDeleteRequest) -> MediaDeletionEvent:
        """Bind a direct removal to one current Jellyfin movie and no Arr record."""

        assert payload.jellyfin_item_id is not None
        try:
            value = await self._jellyfin().list_items(include_types=["Movie"])
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - an incomplete catalogue cannot authorize deletion
            raise LibraryItemChangedError("The Jellyfin movie could not be verified; preview it again.") from exc
        if (
            not isinstance(value, Sequence)
            or isinstance(value, (str, bytes, bytearray))
            or any(not isinstance(item, JellyfinItem) for item in value)
        ):
            raise LibraryItemChangedError("The Jellyfin movie could not be verified; preview it again.")
        requested_id = payload.jellyfin_item_id.strip().casefold()
        matches = [item for item in value if item.id.strip().casefold() == requested_id and item.type == "Movie"]
        if len(matches) != 1:
            raise LibraryItemChangedError("The Jellyfin movie changed or no longer exists; preview it again.")
        item = matches[0]
        fingerprint = MediaFingerprint(tmdb_id=item.tmdb_id, imdb_id=item.imdb_id)
        configured_radarr = self._configured_profiles("radarr")
        arr_movies: list[RadarrMovie] = []
        if self._config is None or configured_radarr:
            if fingerprint.tmdb_id is None and not fingerprint.imdb_id:
                raise LibraryItemChangedError(
                    "The movie has no stable provider identifier for checking its Radarr relationship."
                )
            try:
                radarr_value = await self._radarr().list_movies()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - inability to disprove an Arr link must fail closed
                raise LibraryItemChangedError(
                    "The Radarr relationship could not be verified; preview it again."
                ) from exc
            if (
                not isinstance(radarr_value, Sequence)
                or isinstance(radarr_value, (str, bytes, bytearray))
                or any(not isinstance(movie, RadarrMovie) for movie in radarr_value)
            ):
                raise LibraryItemChangedError("The Radarr relationship could not be verified; preview it again.")
            arr_movies = list(radarr_value)
        decision = StrictMovieResolver().resolve(fingerprint, arr_movies)
        if decision.candidate is not None or decision.reason is FailureReason.AMBIGUOUS_MATCH:
            raise LibraryItemChangedError("This movie is now linked to Radarr; use the full cleanup plan instead.")
        return MediaDeletionEvent(
            notification_type="ItemDeleted",
            item_type=ItemType.MOVIE,
            item_id=f"manual:jellyfin:{item.id}",
            name=item.name.strip() or "Jellyfin movie",
            fingerprint=fingerprint,
        )

    def _resolve_movie_resource(
        self, payload: ManualDeleteRequest, movies: Sequence[RadarrMovie]
    ) -> RadarrMovie | None:
        if payload.library_resource_id is None:
            return next((movie for movie in movies if getattr(movie, "id", None) == payload.radarr_movie_id), None)
        resource = _decode_requested_resource(payload.library_resource_id, LibraryMediaType.MOVIE)
        profiles = self._configured_profiles("radarr")
        candidates = [
            movie for movie in movies if _resource_matches_item(movie, resource, profiles, profile_count=len(profiles))
        ]
        if len(candidates) != 1:
            raise LibraryItemChangedError()
        movie = candidates[0]
        if getattr(movie, "id", None) != payload.radarr_movie_id:
            raise LibraryItemChangedError()
        return movie

    def _resolve_series_resource(
        self, payload: ManualDeleteRequest, series: Sequence[SonarrSeries]
    ) -> SonarrSeries | None:
        if payload.library_resource_id is None:
            return next((item for item in series if getattr(item, "id", None) == payload.sonarr_series_id), None)
        resource = _decode_requested_resource(payload.library_resource_id, LibraryMediaType.SERIES)
        profiles = self._configured_profiles("sonarr")
        candidates = [
            item for item in series if _resource_matches_item(item, resource, profiles, profile_count=len(profiles))
        ]
        if len(candidates) != 1:
            raise LibraryItemChangedError()
        item = candidates[0]
        if getattr(item, "id", None) != payload.sonarr_series_id:
            raise LibraryItemChangedError()
        return item

    def _configured_profiles(self, kind: str) -> list[object]:
        if self._config is None:
            return []
        config = self._config()
        return [profile for profile in (config.radarr if kind == "radarr" else config.sonarr) if profile.enabled]

    async def _verify_jellyfin_binding(
        self,
        payload: ManualDeleteRequest,
        media_type: LibraryMediaType,
        raw_item: RadarrMovie | SonarrSeries,
        arr_items: Sequence[RadarrMovie | SonarrSeries],
    ) -> None:
        """Bind an additive stable resource to the exact Jellyfin target."""

        if payload.library_resource_id is None or payload.jellyfin_item_id is None:
            return
        try:
            include_types = ["Movie"] if media_type is LibraryMediaType.MOVIE else ["Series"]
            if payload.item_type is ItemType.SEASON:
                include_types.append("Season")
            value = await self._jellyfin().list_items(include_types=include_types)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - verification failure must fail closed
            raise LibraryItemChangedError("The library relationship could not be verified; preview it again.") from exc
        if (
            not isinstance(value, Sequence)
            or isinstance(value, (str, bytes, bytearray))
            or any(not isinstance(item, JellyfinItem) for item in value)
        ):
            raise LibraryItemChangedError("The library relationship could not be verified; preview it again.")
        matches = matching_jellyfin_items(
            raw_item,
            media_type,
            tuple(value),
        )
        if len(matches) != 1:
            raise LibraryItemChangedError()
        owners = [
            candidate for candidate in arr_items if len(matching_jellyfin_items(candidate, media_type, matches)) == 1
        ]
        if len(owners) != 1 or owners[0] is not raw_item:
            raise LibraryItemChangedError()
        targets: tuple[JellyfinItem, ...] = matches
        if payload.item_type is ItemType.SEASON:
            assert payload.season_number is not None
            targets = matching_jellyfin_seasons(matches[0].id, payload.season_number, tuple(value))
        if len(targets) != 1 or targets[0].id != payload.jellyfin_item_id:
            raise LibraryItemChangedError()

    async def preview(self, payload: ManualDeleteRequest, event: MediaDeletionEvent) -> ProcessingResultResponse:
        """Build a mutation-free plan containing every intended target."""

        if payload.jellyfin_only:
            return ProcessingResultResponse.from_domain(
                ProcessingResult(
                    event=event,
                    status=OverallStatus.SUCCESS,
                    actions=(
                        ActionResult(
                            system="jellyfin",
                            action="delete_item",
                            status=ActionStatus.DRY_RUN,
                            message=(
                                "Would remove only the selected movie from Jellyfin. "
                                "No Arr or torrent records will change."
                            ),
                            details={"jellyfin_item_id": payload.jellyfin_item_id, "scope": "jellyfin_only"},
                        ),
                    ),
                )
            )

        strategy = self._strategy_factory().for_item_type(event.item_type, dry_run=True)
        result = await strategy.handle(event)
        if payload.jellyfin_item_id:
            result = with_jellyfin_action(
                result,
                ActionResult(
                    system="jellyfin",
                    action="delete_item",
                    status=ActionStatus.DRY_RUN,
                    message="Would remove the selected item from Jellyfin after downstream cleanup succeeds.",
                    details={"jellyfin_item_id": payload.jellyfin_item_id},
                ),
            )
        return ProcessingResultResponse.from_domain(result)

    async def execute(
        self,
        payload: ManualDeleteRequest,
        event: MediaDeletionEvent,
        report_progress: DeletionProgressReporter | None = None,
    ) -> ProcessingResultResponse:
        """Execute a previously resolved manual deletion and record its outcome."""

        if payload.jellyfin_only:
            return await self._execute_jellyfin_only(payload, event, report_progress)

        report = report_progress or ignore_deletion_progress
        item_name = event.name
        report(
            ManualDeleteJobPhase.CLEANING,
            30,
            "Cleaning up Arr services, torrent clients, and Seerr.",
            item_name,
        )
        strategy = self._strategy_factory().for_item_type(event.item_type)
        completed_actions = 0

        def report_action(action: ActionResult) -> None:
            nonlocal completed_actions
            completed_actions += 1
            report(
                ManualDeleteJobPhase.CLEANING,
                min(78, 30 + completed_actions * 6),
                f"{action.system}: {action.message}",
                item_name,
            )

        with observe_actions(report_action):
            result = await strategy.handle(event)

        if payload.jellyfin_item_id and self._is_dry_run():
            result = with_jellyfin_action(
                result,
                ActionResult(
                    system="jellyfin",
                    action="delete_item",
                    status=ActionStatus.DRY_RUN,
                    message="Would remove the selected item from Jellyfin after downstream cleanup succeeds.",
                    details={"jellyfin_item_id": payload.jellyfin_item_id},
                ),
            )
        elif payload.jellyfin_item_id and result.status is OverallStatus.PARTIAL_FAILURE:
            result = with_jellyfin_action(
                result,
                ActionResult(
                    system="jellyfin",
                    action="delete_item",
                    status=ActionStatus.SKIPPED,
                    message="Kept the Jellyfin item because downstream cleanup did not finish safely.",
                    reason=FailureReason.DOWNSTREAM_ERROR,
                    details={"jellyfin_item_id": payload.jellyfin_item_id},
                ),
            )
        elif payload.jellyfin_item_id:
            report(ManualDeleteJobPhase.JELLYFIN, 92, "Removing the item from Jellyfin.", item_name)
            try:
                await self._jellyfin().delete_item(payload.jellyfin_item_id)
            except Exception as exc:  # noqa: BLE001
                _logger.warning("Failed to delete a Jellyfin item after cascade deletion: %s", type(exc).__name__)
                result = with_jellyfin_action(
                    result,
                    ActionResult(
                        system="jellyfin",
                        action="delete_item",
                        status=ActionStatus.FAILED,
                        message="Could not remove the selected item from Jellyfin.",
                        reason=FailureReason.DOWNSTREAM_ERROR,
                        details={"jellyfin_item_id": payload.jellyfin_item_id, "error": str(exc)},
                    ),
                )
            else:
                result = with_jellyfin_action(
                    result,
                    ActionResult(
                        system="jellyfin",
                        action="delete_item",
                        status=ActionStatus.DELETED,
                        message="Removed the selected item from Jellyfin.",
                        details={"jellyfin_item_id": payload.jellyfin_item_id},
                    ),
                )
        else:
            report(ManualDeleteJobPhase.RECORDING, 95, "Finalizing the background task.", item_name)

        report(ManualDeleteJobPhase.RECORDING, 97, "Saving the cleanup result to activity history.", item_name)
        value = payload.display_name or event.name or payload.item_type.value
        await self._activity_recorder.record(result, display_name=value)
        return ProcessingResultResponse.from_domain(result).model_copy(update={"display_name": value})

    async def _execute_jellyfin_only(
        self,
        payload: ManualDeleteRequest,
        event: MediaDeletionEvent,
        report_progress: DeletionProgressReporter | None,
    ) -> ProcessingResultResponse:
        report = report_progress or ignore_deletion_progress
        report(ManualDeleteJobPhase.JELLYFIN, 80, "Removing the selected movie from Jellyfin only.", event.name)
        if self._is_dry_run():
            action = ActionResult(
                system="jellyfin",
                action="delete_item",
                status=ActionStatus.DRY_RUN,
                message="Would remove only the selected movie from Jellyfin. No Arr or torrent records will change.",
                details={"jellyfin_item_id": payload.jellyfin_item_id, "scope": "jellyfin_only"},
            )
            status = OverallStatus.SUCCESS
        else:
            try:
                assert payload.jellyfin_item_id is not None
                await self._jellyfin().delete_item(payload.jellyfin_item_id)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - downstream failure is persisted for review
                _logger.warning("Failed to delete a verified Jellyfin-only movie: %s", type(exc).__name__)
                action = ActionResult(
                    system="jellyfin",
                    action="delete_item",
                    status=ActionStatus.FAILED,
                    message="Could not remove the selected movie from Jellyfin.",
                    reason=FailureReason.DOWNSTREAM_ERROR,
                    details={"jellyfin_item_id": payload.jellyfin_item_id, "scope": "jellyfin_only"},
                )
                status = OverallStatus.PARTIAL_FAILURE
            else:
                action = ActionResult(
                    system="jellyfin",
                    action="delete_item",
                    status=ActionStatus.DELETED,
                    message="Removed the selected movie from Jellyfin. No Arr or torrent records were changed.",
                    details={"jellyfin_item_id": payload.jellyfin_item_id, "scope": "jellyfin_only"},
                )
                status = OverallStatus.SUCCESS
        result = ProcessingResult(event=event, status=status, actions=(action,))
        value = payload.display_name or event.name or payload.item_type.value
        report(ManualDeleteJobPhase.RECORDING, 97, "Saving the Jellyfin-only result to activity history.", event.name)
        await self._activity_recorder.record(result, display_name=value)
        return ProcessingResultResponse.from_domain(result).model_copy(update={"display_name": value})


def with_jellyfin_action(result: ProcessingResult, action: ActionResult) -> ProcessingResult:
    actions = (*result.actions, action)
    overall = OverallStatus.PARTIAL_FAILURE if action.status is ActionStatus.FAILED else result.status
    return ProcessingResult(
        event=result.event,
        status=overall,
        actions=actions,
        correlation_id=result.correlation_id,
    )


def ignore_deletion_progress(
    phase: ManualDeleteJobPhase,
    progress_percent: int,
    message: str,
    item_name: str | None,
) -> None:
    """No-op reporter used by the backwards-compatible synchronous endpoint."""


def _decode_requested_resource(value: str, expected: LibraryMediaType) -> LibraryResource:
    try:
        resource = decode_library_resource(value)
    except LibraryResourceError as exc:
        raise LibraryItemChangedError() from exc
    if resource.media_type is not expected:
        raise LibraryItemChangedError()
    return resource


def _resource_matches_item(
    item: object,
    resource: LibraryResource,
    profiles: Sequence[object],
    *,
    profile_count: int,
) -> bool:
    service_id = getattr(item, "service_id", None)
    item_id = getattr(item, "id", None)
    if isinstance(item_id, bool) or not isinstance(item_id, int):
        return False
    routed = _routed_parts(item_id, profile_count)
    if routed is None:
        if item_id < 0:
            return False
        raw_id = item_id
        if not isinstance(service_id, str) or not service_id:
            if len(profiles) != 1:
                return False
            service_id = str(getattr(profiles[0], "id", ""))
    else:
        target_index, raw_id = routed
        if target_index >= len(profiles):
            return False
        target_service_id = str(getattr(profiles[target_index], "id", ""))
        if not isinstance(service_id, str) or not service_id:
            service_id = target_service_id
        elif service_id != target_service_id:
            return False
    return (
        service_id == resource.profile_id
        and raw_id == resource.raw_id
        and any(str(getattr(profile, "id", "")) == service_id for profile in profiles)
    )


def _routed_parts(value: int, profile_count: int) -> tuple[int, int] | None:
    if value >= 0:
        return None
    if profile_count <= 0:
        return None
    paired = -value - 1
    diagonal = (isqrt(8 * paired + 1) - 1) // 2
    diagonal_start = diagonal * (diagonal + 1) // 2
    raw_id = paired - diagonal_start
    target_index = diagonal - raw_id
    return (target_index, raw_id) if 0 <= target_index < profile_count else None
