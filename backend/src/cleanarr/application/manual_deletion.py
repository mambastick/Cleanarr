"""Manual deletion orchestration independent from HTTP transport and SQLite."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Protocol

from cleanarr.application.deletion_jobs import DeletionProgressReporter
from cleanarr.application.deletion_models import ManualDeleteJobPhase, ManualDeleteRequest, ProcessingResultResponse
from cleanarr.application.ports import RadarrClientPort, SonarrClientPort
from cleanarr.application.results import observe_actions
from cleanarr.application.strategies import DeletionStrategyFactory
from cleanarr.domain import (
    ActionResult,
    ActionStatus,
    FailureReason,
    ItemType,
    MediaDeletionEvent,
    MediaFingerprint,
    OverallStatus,
    ProcessingResult,
)

_logger = logging.getLogger("cleanarr")


class ManualDeletionResolutionError(RuntimeError):
    """A transport-neutral failure while resolving one manual selection."""


class ManualDeletionValidationError(ManualDeletionResolutionError, ValueError):
    """A malformed manual deletion command with stable transport-safe detail."""


class ManualDeletionNotFoundError(ManualDeletionResolutionError, LookupError):
    """The explicitly selected Arr item no longer exists."""


class JellyfinDeletionPort(Protocol):
    """Minimal downstream port needed after an otherwise safe manual cascade."""

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
    ) -> None:
        self._radarr = radarr
        self._sonarr = sonarr
        self._jellyfin = jellyfin
        self._strategy_factory = strategy_factory
        self._is_dry_run = is_dry_run
        self._activity_recorder = activity_recorder

    async def resolve(self, payload: ManualDeleteRequest) -> MediaDeletionEvent:
        """Resolve an explicit library selection into one stable deletion event."""

        if payload.item_type is ItemType.MOVIE:
            if payload.radarr_movie_id is None:
                raise ManualDeletionValidationError("radarr_movie_id is required for movie deletion.")
            movies_list = list(await self._radarr().list_movies())
            movie = next((movie for movie in movies_list if movie.id == payload.radarr_movie_id), None)
            if movie is None:
                raise ManualDeletionNotFoundError(f"Radarr movie {payload.radarr_movie_id} not found.")
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
            raise ManualDeletionValidationError("sonarr_series_id is required for series/season deletion.")
        series_list = list(await self._sonarr().list_series())
        series = next((series for series in series_list if series.id == payload.sonarr_series_id), None)
        if series is None:
            raise ManualDeletionNotFoundError(f"Sonarr series {payload.sonarr_series_id} not found.")
        if payload.item_type is ItemType.SEASON and payload.season_number is None:
            raise ManualDeletionValidationError("season_number is required for season deletion.")
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

    async def preview(self, payload: ManualDeleteRequest, event: MediaDeletionEvent) -> ProcessingResultResponse:
        """Build a mutation-free plan containing every intended target."""

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
