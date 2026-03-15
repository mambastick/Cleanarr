"""Deletion strategies."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable

from cleanarr.application.ports import (
    DownloaderClientPort,
    JellyseerrClientPort,
    RadarrClientPort,
    SonarrClientPort,
)
from cleanarr.application.resolver import (
    StrictJellyseerrResolver,
    StrictMovieResolver,
    StrictSeriesResolver,
)
from cleanarr.application.results import ActionCollector
from cleanarr.application.safety import SonarrDeletionSafetyAnalyzer
from cleanarr.domain import (
    ActionStatus,
    AuthenticationError,
    FailureReason,
    ItemType,
    JellyseerrIssue,
    JellyseerrMedia,
    JellyseerrRequest,
    MediaDeletionEvent,
    ProcessingResult,
    ResourceNotFoundError,
)

Mutation = Callable[[], Awaitable[object | None]]


def bind_async[**P, T](
    func: Callable[P, Awaitable[T]],
    /,
    *args: P.args,
    **kwargs: P.kwargs,
) -> Callable[[], Awaitable[T]]:
    """Bind arguments to an async callable and expose it as a zero-arg mutation."""

    async def mutation() -> T:
        return await func(*args, **kwargs)

    return mutation


class BaseDeletionStrategy(ABC):
    """Common strategy helpers."""

    def __init__(
        self,
        *,
        dry_run: bool,
        logger: logging.Logger,
        jellyseerr: JellyseerrClientPort,
        downloader: DownloaderClientPort,
    ) -> None:
        self._dry_run = dry_run
        self._logger = logger
        self._jellyseerr = jellyseerr
        self._downloader = downloader
        self._jellyseerr_resolver = StrictJellyseerrResolver()

    @abstractmethod
    async def handle(self, event: MediaDeletionEvent) -> ProcessingResult:
        """Process a single event."""

    async def _run_mutation(
        self,
        collector: ActionCollector,
        *,
        system: str,
        action: str,
        message: str,
        mutation: Mutation,
        reason: FailureReason | None = None,
        **details: object,
    ) -> None:
        if self._dry_run:
            collector.add(
                system,
                action,
                ActionStatus.DRY_RUN,
                f"DRY_RUN: {message}",
                reason=reason,
                **details,
            )
            return

        try:
            await mutation()
        except ResourceNotFoundError as exc:
            collector.add(
                system,
                action,
                ActionStatus.ALREADY_ABSENT,
                exc.message,
                reason=reason,
                **details,
            )
        except AuthenticationError as exc:
            collector.add(
                system,
                action,
                ActionStatus.FAILED,
                exc.message,
                reason=FailureReason.AUTHENTICATION_FAILED,
                **details,
            )
        except Exception as exc:  # noqa: BLE001
            self._logger.exception(
                "Downstream mutation failed",
                extra={"system": system, "action": action},
            )
            collector.add(
                system,
                action,
                ActionStatus.FAILED,
                str(exc),
                reason=FailureReason.DOWNSTREAM_ERROR,
                **details,
            )
        else:
            collector.add(system, action, ActionStatus.DELETED, message, reason=reason, **details)

    async def _cleanup_hashes(self, collector: ActionCollector, hashes: set[str]) -> None:
        if not hashes:
            collector.add(
                "downloader",
                "delete_hashes",
                ActionStatus.SKIPPED,
                "No safe downloader hashes were found for deletion.",
                reason=FailureReason.NO_MATCH,
            )
            return

        if self._dry_run:
            for hash_value in sorted(hashes):
                collector.add(
                    "downloader",
                    "delete_hash",
                    ActionStatus.DRY_RUN,
                    f"DRY_RUN: would delete torrent hash {hash_value}.",
                    hash=hash_value,
                )
            return

        try:
            removal_results = await self._downloader.delete_hashes(sorted(hashes), delete_files=True)
        except Exception as exc:  # noqa: BLE001
            self._logger.exception("Downloader removal failed")
            collector.add(
                "downloader",
                "delete_hashes",
                ActionStatus.FAILED,
                str(exc),
                reason=FailureReason.DOWNSTREAM_ERROR,
            )
            return

        for result in removal_results:
            status = ActionStatus.DELETED if result.existed else ActionStatus.ALREADY_ABSENT
            message = (
                f"Deleted torrent hash {result.hash_value}."
                if result.existed
                else f"Torrent hash {result.hash_value} was already absent."
            )
            collector.add("downloader", "delete_hash", status, message, hash=result.hash_value)

    async def _list_requests_for_media(self, media_id: int) -> list[JellyseerrRequest]:
        requests = await self._jellyseerr.list_requests()
        return [request for request in requests if request.media_id == media_id]

    async def _list_issues_for_media(self, media_id: int) -> list[JellyseerrIssue]:
        issues = await self._jellyseerr.list_issues()
        return [issue for issue in issues if issue.media_id == media_id]

    async def _resolve_jellyseerr_media(
        self,
        event: MediaDeletionEvent,
        *,
        media_type: str,
        collector: ActionCollector,
    ) -> JellyseerrMedia | None:
        media_items = list(await self._jellyseerr.list_media())
        if media_type == "movie":
            decision = self._jellyseerr_resolver.resolve_movie(event.fingerprint, media_items)
        else:
            decision = self._jellyseerr_resolver.resolve_tv(event.fingerprint, media_items)

        if decision.candidate is not None:
            return decision.candidate

        collector.add(
            "jellyseerr",
            "resolve_media",
            ActionStatus.SKIPPED,
            "No strict Jellyseerr media match was found.",
            reason=decision.reason,
        )
        return None

    async def _cleanup_jellyseerr_movie(
        self,
        event: MediaDeletionEvent,
        collector: ActionCollector,
    ) -> None:
        media = await self._resolve_jellyseerr_media(event, media_type="movie", collector=collector)
        if media is None:
            return

        requests = await self._list_requests_for_media(media.id)
        issues = await self._list_issues_for_media(media.id)

        for request in requests:
            await self._run_mutation(
                collector,
                system="jellyseerr",
                action="delete_request",
                message=f"Deleted Jellyseerr request {request.id}.",
                mutation=bind_async(self._jellyseerr.delete_request, request.id),
                request_id=request.id,
            )

        for issue in issues:
            await self._run_mutation(
                collector,
                system="jellyseerr",
                action="delete_issue",
                message=f"Deleted Jellyseerr issue {issue.id}.",
                mutation=bind_async(self._jellyseerr.delete_issue, issue.id),
                issue_id=issue.id,
            )

        await self._run_mutation(
            collector,
            system="jellyseerr",
            action="delete_media",
            message=f"Deleted Jellyseerr media {media.id}.",
            mutation=bind_async(self._jellyseerr.delete_media, media.id),
            media_id=media.id,
        )

    async def _cleanup_jellyseerr_series(
        self,
        event: MediaDeletionEvent,
        collector: ActionCollector,
    ) -> None:
        media = await self._resolve_jellyseerr_media(event, media_type="tv", collector=collector)
        if media is None:
            return

        requests = await self._list_requests_for_media(media.id)
        issues = await self._list_issues_for_media(media.id)

        for request in requests:
            await self._run_mutation(
                collector,
                system="jellyseerr",
                action="delete_request",
                message=f"Deleted Jellyseerr request {request.id}.",
                mutation=bind_async(self._jellyseerr.delete_request, request.id),
                request_id=request.id,
            )

        for issue in issues:
            await self._run_mutation(
                collector,
                system="jellyseerr",
                action="delete_issue",
                message=f"Deleted Jellyseerr issue {issue.id}.",
                mutation=bind_async(self._jellyseerr.delete_issue, issue.id),
                issue_id=issue.id,
            )

        await self._run_mutation(
            collector,
            system="jellyseerr",
            action="delete_media",
            message=f"Deleted Jellyseerr media {media.id}.",
            mutation=bind_async(self._jellyseerr.delete_media, media.id),
            media_id=media.id,
        )

    async def _cleanup_jellyseerr_season(
        self,
        event: MediaDeletionEvent,
        collector: ActionCollector,
    ) -> None:
        media = await self._resolve_jellyseerr_media(event, media_type="tv", collector=collector)
        if media is None or event.season_number is None:
            return

        requests = await self._list_requests_for_media(media.id)
        issues = await self._list_issues_for_media(media.id)

        for request in requests:
            if event.season_number not in request.season_numbers:
                continue
            remaining_seasons = [number for number in request.season_numbers if number != event.season_number]
            if remaining_seasons:
                await self._run_mutation(
                    collector,
                    system="jellyseerr",
                    action="update_request",
                    message=f"Removed season {event.season_number} from Jellyseerr request {request.id}.",
                    mutation=bind_async(
                        self._jellyseerr.update_request_seasons,
                        request,
                        season_numbers=remaining_seasons,
                    ),
                    request_id=request.id,
                    season_number=event.season_number,
                )
                continue
            await self._run_mutation(
                collector,
                system="jellyseerr",
                action="delete_request",
                message=f"Deleted Jellyseerr request {request.id}.",
                mutation=bind_async(self._jellyseerr.delete_request, request.id),
                request_id=request.id,
                season_number=event.season_number,
            )

        matching_issues = [issue for issue in issues if issue.problem_season == event.season_number]
        for issue in matching_issues:
            await self._run_mutation(
                collector,
                system="jellyseerr",
                action="delete_issue",
                message=f"Deleted Jellyseerr issue {issue.id}.",
                mutation=bind_async(self._jellyseerr.delete_issue, issue.id),
                issue_id=issue.id,
                season_number=event.season_number,
            )

    def _record_sonarr_match_failure(
        self,
        collector: ActionCollector,
        reason: FailureReason | None,
    ) -> None:
        collector.add(
            "sonarr",
            "resolve_series",
            ActionStatus.SKIPPED,
            "No strict Sonarr series match was found.",
            reason=reason,
        )


class MovieDeletionStrategy(BaseDeletionStrategy):
    """Handle movie deletions."""

    def __init__(
        self,
        *,
        dry_run: bool,
        logger: logging.Logger,
        radarr: RadarrClientPort,
        jellyseerr: JellyseerrClientPort,
        downloader: DownloaderClientPort,
    ) -> None:
        super().__init__(
            dry_run=dry_run,
            logger=logger,
            jellyseerr=jellyseerr,
            downloader=downloader,
        )
        self._radarr = radarr
        self._resolver = StrictMovieResolver()

    async def handle(self, event: MediaDeletionEvent) -> ProcessingResult:
        collector = ActionCollector(event)
        movies = list(await self._radarr.list_movies())
        decision = self._resolver.resolve(event.fingerprint, movies)
        movie = decision.candidate
        if movie is None:
            collector.add(
                "radarr",
                "resolve_movie",
                ActionStatus.SKIPPED,
                "No strict Radarr movie match was found.",
                reason=decision.reason,
            )
        else:
            history_records = list(await self._radarr.list_movie_history(movie.id))
            hashes = {
                record.download_id.upper()
                for record in history_records
                if record.event_type == "grabbed" and record.download_id
            }
            await self._cleanup_hashes(collector, hashes)
            await self._run_mutation(
                collector,
                system="radarr",
                action="delete_movie",
                message=f"Deleted Radarr movie {movie.id}.",
                mutation=bind_async(
                    self._radarr.delete_movie,
                    movie.id,
                    delete_files=True,
                    add_import_exclusion=False,
                ),
                movie_id=movie.id,
                title=movie.title,
            )

        await self._cleanup_jellyseerr_movie(event, collector)
        return collector.build()


class SeriesDeletionStrategy(BaseDeletionStrategy):
    """Handle full series deletions."""

    def __init__(
        self,
        *,
        dry_run: bool,
        logger: logging.Logger,
        sonarr: SonarrClientPort,
        jellyseerr: JellyseerrClientPort,
        downloader: DownloaderClientPort,
    ) -> None:
        super().__init__(
            dry_run=dry_run,
            logger=logger,
            jellyseerr=jellyseerr,
            downloader=downloader,
        )
        self._sonarr = sonarr
        self._resolver = StrictSeriesResolver()
        self._safety = SonarrDeletionSafetyAnalyzer()

    async def handle(self, event: MediaDeletionEvent) -> ProcessingResult:
        collector = ActionCollector(event)
        series_list = list(await self._sonarr.list_series())
        decision = self._resolver.resolve(event.fingerprint, series_list)
        series = decision.candidate
        if series is None:
            self._record_sonarr_match_failure(collector, decision.reason)
        else:
            history_records = list(await self._sonarr.list_series_history(series.id))
            episodes = list(await self._sonarr.list_episodes(series.id))
            safety = self._safety.analyze(event, episodes, history_records)
            for note in safety.notes:
                collector.add(
                    "sonarr",
                    "safety_note",
                    ActionStatus.SKIPPED,
                    note.message,
                    reason=note.reason,
                    **note.details,
                )
            await self._cleanup_hashes(collector, set(safety.hashes_to_delete))
            await self._run_mutation(
                collector,
                system="sonarr",
                action="delete_series",
                message=f"Deleted Sonarr series {series.id}.",
                mutation=bind_async(
                    self._sonarr.delete_series,
                    series.id,
                    delete_files=True,
                    add_import_list_exclusion=False,
                ),
                series_id=series.id,
                title=series.title,
            )

        await self._cleanup_jellyseerr_series(event, collector)
        return collector.build()


class SeasonDeletionStrategy(BaseDeletionStrategy):
    """Handle season deletions."""

    def __init__(
        self,
        *,
        dry_run: bool,
        logger: logging.Logger,
        sonarr: SonarrClientPort,
        jellyseerr: JellyseerrClientPort,
        downloader: DownloaderClientPort,
    ) -> None:
        super().__init__(
            dry_run=dry_run,
            logger=logger,
            jellyseerr=jellyseerr,
            downloader=downloader,
        )
        self._sonarr = sonarr
        self._resolver = StrictSeriesResolver()
        self._safety = SonarrDeletionSafetyAnalyzer()

    async def handle(self, event: MediaDeletionEvent) -> ProcessingResult:
        collector = ActionCollector(event)
        series_list = list(await self._sonarr.list_series())
        decision = self._resolver.resolve(event.fingerprint, series_list)
        series = decision.candidate
        if series is None:
            self._record_sonarr_match_failure(collector, decision.reason)
            await self._cleanup_jellyseerr_season(event, collector)
            return collector.build()

        history_records = list(await self._sonarr.list_series_history(series.id))
        episodes = list(await self._sonarr.list_episodes(series.id))
        safety = self._safety.analyze(event, episodes, history_records)
        for note in safety.notes:
            collector.add(
                "sonarr",
                "safety_note",
                ActionStatus.SKIPPED,
                note.message,
                reason=note.reason,
                **note.details,
            )

        if safety.episode_ids_to_unmonitor:
            episode_ids = sorted(safety.episode_ids_to_unmonitor)
            await self._run_mutation(
                collector,
                system="sonarr",
                action="unmonitor_episodes",
                message=f"Unmonitored {len(safety.episode_ids_to_unmonitor)} Sonarr episodes.",
                mutation=bind_async(self._sonarr.unmonitor_episodes, episode_ids),
                episode_ids=episode_ids,
            )
        else:
            collector.add(
                "sonarr",
                "unmonitor_episodes",
                ActionStatus.SKIPPED,
                "No episodes matched the requested season deletion scope.",
                reason=FailureReason.NO_MATCH,
            )

        await self._cleanup_hashes(collector, set(safety.hashes_to_delete))
        for episode_file_id in sorted(safety.episode_file_ids_to_delete):
            await self._run_mutation(
                collector,
                system="sonarr",
                action="delete_episode_file",
                message=f"Deleted Sonarr episode file {episode_file_id}.",
                mutation=bind_async(self._sonarr.delete_episode_file, episode_file_id),
                episode_file_id=episode_file_id,
            )

        await self._cleanup_jellyseerr_season(event, collector)
        return collector.build()


class EpisodeDeletionStrategy(BaseDeletionStrategy):
    """Handle episode deletions."""

    def __init__(
        self,
        *,
        dry_run: bool,
        logger: logging.Logger,
        sonarr: SonarrClientPort,
        jellyseerr: JellyseerrClientPort,
        downloader: DownloaderClientPort,
    ) -> None:
        super().__init__(
            dry_run=dry_run,
            logger=logger,
            jellyseerr=jellyseerr,
            downloader=downloader,
        )
        self._sonarr = sonarr
        self._resolver = StrictSeriesResolver()
        self._safety = SonarrDeletionSafetyAnalyzer()

    async def handle(self, event: MediaDeletionEvent) -> ProcessingResult:
        collector = ActionCollector(event)
        series_list = list(await self._sonarr.list_series())
        decision = self._resolver.resolve(event.fingerprint, series_list)
        series = decision.candidate
        if series is None:
            self._record_sonarr_match_failure(collector, decision.reason)
            collector.add(
                "jellyseerr",
                "partial_request_cleanup",
                ActionStatus.IGNORED,
                "Episode-level Jellyseerr cleanup is intentionally skipped in v1.",
                reason=FailureReason.NO_PARTIAL_REQUEST_CLEANUP,
            )
            return collector.build()

        history_records = list(await self._sonarr.list_series_history(series.id))
        episodes = list(await self._sonarr.list_episodes(series.id))
        safety = self._safety.analyze(event, episodes, history_records)
        for note in safety.notes:
            collector.add(
                "sonarr",
                "safety_note",
                ActionStatus.SKIPPED,
                note.message,
                reason=note.reason,
                **note.details,
            )

        if safety.episode_ids_to_unmonitor:
            episode_ids = sorted(safety.episode_ids_to_unmonitor)
            await self._run_mutation(
                collector,
                system="sonarr",
                action="unmonitor_episodes",
                message=f"Unmonitored {len(safety.episode_ids_to_unmonitor)} Sonarr episodes.",
                mutation=bind_async(self._sonarr.unmonitor_episodes, episode_ids),
                episode_ids=episode_ids,
            )
        else:
            collector.add(
                "sonarr",
                "unmonitor_episodes",
                ActionStatus.SKIPPED,
                "No episodes matched the requested episode deletion scope.",
                reason=FailureReason.NO_MATCH,
            )

        await self._cleanup_hashes(collector, set(safety.hashes_to_delete))
        for episode_file_id in sorted(safety.episode_file_ids_to_delete):
            await self._run_mutation(
                collector,
                system="sonarr",
                action="delete_episode_file",
                message=f"Deleted Sonarr episode file {episode_file_id}.",
                mutation=bind_async(self._sonarr.delete_episode_file, episode_file_id),
                episode_file_id=episode_file_id,
            )

        collector.add(
            "jellyseerr",
            "partial_request_cleanup",
            ActionStatus.IGNORED,
            "Episode-level Jellyseerr cleanup is intentionally skipped in v1.",
            reason=FailureReason.NO_PARTIAL_REQUEST_CLEANUP,
        )
        return collector.build()


class DeletionStrategyFactory:
    """Return the correct strategy for a webhook item type."""

    def __init__(
        self,
        *,
        dry_run: bool,
        logger: logging.Logger,
        radarr: RadarrClientPort,
        sonarr: SonarrClientPort,
        jellyseerr: JellyseerrClientPort,
        downloader: DownloaderClientPort,
    ) -> None:
        self._movie = MovieDeletionStrategy(
            dry_run=dry_run,
            logger=logger,
            radarr=radarr,
            jellyseerr=jellyseerr,
            downloader=downloader,
        )
        self._series = SeriesDeletionStrategy(
            dry_run=dry_run,
            logger=logger,
            sonarr=sonarr,
            jellyseerr=jellyseerr,
            downloader=downloader,
        )
        self._season = SeasonDeletionStrategy(
            dry_run=dry_run,
            logger=logger,
            sonarr=sonarr,
            jellyseerr=jellyseerr,
            downloader=downloader,
        )
        self._episode = EpisodeDeletionStrategy(
            dry_run=dry_run,
            logger=logger,
            sonarr=sonarr,
            jellyseerr=jellyseerr,
            downloader=downloader,
        )

    def for_item_type(self, item_type: ItemType) -> BaseDeletionStrategy:
        if item_type is ItemType.MOVIE:
            return self._movie
        if item_type is ItemType.SERIES:
            return self._series
        if item_type is ItemType.SEASON:
            return self._season
        return self._episode
