"""Deletion strategies."""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable, Mapping, Sequence
from datetime import UTC, datetime

from cleanarr.application.ports import (
    DownloaderClientPort,
    RadarrClientPort,
    RetentionRecorderPort,
    SeerrClientPort,
    SonarrClientPort,
)
from cleanarr.application.resolver import (
    StrictMovieResolver,
    StrictSeerrResolver,
    StrictSeriesResolver,
)
from cleanarr.application.results import ActionCollector
from cleanarr.application.safety import SonarrDeletionSafetyAnalyzer
from cleanarr.domain import (
    ActionStatus,
    AuthenticationError,
    FailureReason,
    ItemType,
    MediaDeletionEvent,
    ProcessingResult,
    RadarrHistoryRecord,
    RadarrMovie,
    ResourceNotFoundError,
    RetainedTorrent,
    SeerrIssue,
    SeerrMedia,
    SeerrRequest,
    SonarrEpisode,
)
from cleanarr.domain.config import TorrentRemovalPolicy

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
        seerr: SeerrClientPort,
        downloader: DownloaderClientPort,
        retention: RetentionRecorderPort | None = None,
        retention_thresholds: Mapping[str, tuple[float | None, int | None]] | None = None,
    ) -> None:
        self._dry_run = dry_run
        self._logger = logger
        self._seerr = seerr
        self._downloader = downloader
        self._retention = retention
        self._retention_thresholds = dict(retention_thresholds or {})
        self._seerr_resolver = StrictSeerrResolver()

    async def handle(self, event: MediaDeletionEvent) -> ProcessingResult:
        """Keep every observed action even when a later read unexpectedly fails."""
        collector = ActionCollector(event)
        try:
            return await self._handle(event, collector)
        except Exception as exc:
            collector.add(
                getattr(exc, "system", "cleanarr"),
                "process_event",
                ActionStatus.FAILED,
                "A downstream operation failed; earlier actions are retained.",
                reason=FailureReason.AUTHENTICATION_FAILED
                if isinstance(exc, AuthenticationError)
                else FailureReason.DOWNSTREAM_ERROR,
                error=str(exc),
            )
            return collector.build()

    @abstractmethod
    async def _handle(self, event: MediaDeletionEvent, collector: ActionCollector) -> ProcessingResult:
        """Process a single event using the caller-owned audit collector."""

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
                extra={
                    "system": system,
                    "action": action,
                    "correlation_id": collector.correlation_id,
                },
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

    async def _cleanup_hashes(
        self,
        collector: ActionCollector,
        hashes: set[str],
        *,
        allow_empty: bool = False,
        event: MediaDeletionEvent | None = None,
    ) -> bool:
        """Delete resolved hashes and report whether dependent mutations may continue."""

        if not hashes:
            collector.add(
                "downloader",
                "delete_hashes",
                ActionStatus.SKIPPED,
                "No safe downloader hashes were found for deletion.",
                reason=FailureReason.NO_MATCH,
            )
            return allow_empty

        try:
            removal_results = await self._downloader.delete_hashes(
                sorted(hashes),
                delete_files=True,
                dry_run=self._dry_run,
            )
        except Exception as exc:  # noqa: BLE001
            self._logger.exception(
                "Downloader removal failed",
                extra={"correlation_id": collector.correlation_id},
            )
            collector.add(
                "downloader",
                "delete_hashes",
                ActionStatus.FAILED,
                str(exc),
                reason=FailureReason.DOWNSTREAM_ERROR,
            )
            return False

        cleanup_succeeded = True
        for result in removal_results:
            if result.error:
                cleanup_succeeded = False
                collector.add(
                    result.client_kind or "downloader",
                    "delete_hash",
                    ActionStatus.FAILED,
                    result.error,
                    reason=FailureReason.DOWNSTREAM_ERROR,
                    hash=result.hash_value,
                    downloader_id=result.client_id,
                    downloader_name=result.client_name,
                    downloader_kind=result.client_kind,
                    torrent_name=result.torrent_name,
                    content_path=result.content_path,
                    download_directory=result.download_directory,
                    delete_files=result.delete_files,
                )
                continue
            if result.existed is None:
                cleanup_succeeded = False
                collector.add(
                    result.client_kind or "downloader",
                    "delete_hash",
                    ActionStatus.FAILED,
                    "Downloader existence could not be verified; dependent cleanup was blocked.",
                    reason=FailureReason.OWNERSHIP_UNVERIFIABLE,
                    hash=result.hash_value,
                    downloader_id=result.client_id,
                    downloader_name=result.client_name,
                    downloader_kind=result.client_kind,
                    skip_reason=result.skip_reason,
                )
                continue
            if result.skip_reason:
                skip_reason = {
                    "shared_path": FailureReason.SHARED_PATH,
                    "ownership_unverifiable": FailureReason.OWNERSHIP_UNVERIFIABLE,
                }.get(result.skip_reason, FailureReason.SEEDING_POLICY)
                if skip_reason is not FailureReason.SEEDING_POLICY:
                    cleanup_succeeded = False
                if skip_reason is FailureReason.SEEDING_POLICY and not self._dry_run:
                    if (
                        result.existed is not True
                        or event is None
                        or not result.client_id
                        or result.seeding_policy
                        not in {
                            TorrentRemovalPolicy.KEEP.value,
                            TorrentRemovalPolicy.DEFER.value,
                        }
                    ):
                        collector.add(
                            result.client_kind or "downloader",
                            "record_retention",
                            ActionStatus.FAILED,
                            "Retention evidence was incomplete; dependent cleanup was blocked.",
                            reason=FailureReason.DOWNSTREAM_ERROR,
                            hash=result.hash_value,
                            downloader_id=result.client_id,
                            seeding_policy=result.seeding_policy,
                        )
                        cleanup_succeeded = False
                        continue
                    min_ratio, min_time = self._retention_thresholds.get(result.client_id, (None, None))
                    record = RetainedTorrent(
                        client_id=result.client_id,
                        info_hash=result.hash_value.upper(),
                        policy=TorrentRemovalPolicy(result.seeding_policy),
                        correlation_id=collector.correlation_id,
                        provider_ids=self._provider_ids(event),
                        item_scope=self._item_scope(event),
                        retained_at=datetime.now(UTC),
                        min_seed_ratio=min_ratio,
                        min_seed_time_minutes=min_time,
                    )
                    retention_error: Exception | None = None
                    if self._retention is None:
                        retention_error = RuntimeError("retention recorder is not configured")
                    else:
                        try:
                            await self._retention.record_retention(record)
                        except Exception as exc:  # noqa: BLE001
                            retention_error = exc
                    if retention_error is not None:
                        collector.add(
                            result.client_kind or "downloader",
                            "record_retention",
                            ActionStatus.FAILED,
                            "Could not persist retention evidence; dependent cleanup was blocked.",
                            reason=FailureReason.DOWNSTREAM_ERROR,
                            error=str(retention_error),
                            hash=result.hash_value,
                            downloader_id=result.client_id,
                            seeding_policy=result.seeding_policy,
                        )
                        cleanup_succeeded = False
                        continue
                collector.add(
                    result.client_kind or "downloader",
                    "delete_hash",
                    ActionStatus.SKIPPED,
                    result.skip_reason,
                    reason=skip_reason,
                    hash=result.hash_value,
                    downloader_id=result.client_id,
                    downloader_name=result.client_name,
                    downloader_kind=result.client_kind,
                    seeding_policy=result.seeding_policy,
                    ratio=result.ratio,
                    seeding_time_seconds=result.seeding_time_seconds,
                    torrent_name=result.torrent_name,
                    content_path=result.content_path,
                    download_directory=result.download_directory,
                    delete_files=result.delete_files,
                )
                continue
            if self._dry_run and result.existed:
                status = ActionStatus.DRY_RUN
                message = f"DRY_RUN: would delete torrent hash {result.hash_value}."
            elif result.existed:
                status = ActionStatus.DELETED
                message = f"Deleted torrent hash {result.hash_value}."
            else:
                status = ActionStatus.ALREADY_ABSENT
                message = f"Torrent hash {result.hash_value} was already absent."
            collector.add(
                result.client_kind or "downloader",
                "delete_hash",
                status,
                message,
                hash=result.hash_value,
                downloader_id=result.client_id,
                downloader_name=result.client_name,
                downloader_kind=result.client_kind,
                seeding_policy=result.seeding_policy,
                ratio=result.ratio,
                seeding_time_seconds=result.seeding_time_seconds,
                torrent_name=result.torrent_name,
                content_path=result.content_path,
                download_directory=result.download_directory,
                delete_files=result.delete_files,
            )
        return cleanup_succeeded

    @staticmethod
    def _provider_ids(event: MediaDeletionEvent) -> dict[str, int | str]:
        """Keep only provider identifiers; paths and display metadata are excluded."""

        result: dict[str, int | str] = {}
        if event.fingerprint.tmdb_id is not None:
            result["tmdb_id"] = event.fingerprint.tmdb_id
        if event.fingerprint.tvdb_id is not None:
            result["tvdb_id"] = event.fingerprint.tvdb_id
        if event.fingerprint.imdb_id:
            result["imdb_id"] = event.fingerprint.imdb_id
        return result

    @staticmethod
    def _item_scope(event: MediaDeletionEvent) -> str:
        scope = event.item_type.value
        if event.season_number is not None:
            scope += f":season:{event.season_number}"
        if event.episode_numbers:
            scope += ":episodes:" + ",".join(str(number) for number in sorted(event.episode_numbers))
        return scope

    @staticmethod
    def _record_downloader_block(
        collector: ActionCollector,
        *,
        system: str,
        action: str,
        message: str,
        **details: object,
    ) -> None:
        collector.add(
            system,
            action,
            ActionStatus.SKIPPED,
            message,
            reason=FailureReason.DOWNSTREAM_ERROR,
            **details,
        )

    async def _read_seerr[T](
        self,
        collector: ActionCollector,
        action: str,
        read: Callable[[], Awaitable[Sequence[T]]],
    ) -> list[T] | None:
        try:
            return list(await read())
        except Exception as exc:
            collector.add(
                "seerr",
                action,
                ActionStatus.FAILED,
                "Could not read Seerr cleanup evidence.",
                reason=FailureReason.AUTHENTICATION_FAILED
                if isinstance(exc, AuthenticationError)
                else FailureReason.DOWNSTREAM_ERROR,
                error=str(exc),
            )
            return None

    async def _list_requests_for_media(self, media_id: int, collector: ActionCollector) -> list[SeerrRequest] | None:
        requests = await self._read_seerr(collector, "list_requests", self._seerr.list_requests)
        return None if requests is None else [request for request in requests if request.media_id == media_id]

    async def _list_issues_for_media(self, media_id: int, collector: ActionCollector) -> list[SeerrIssue] | None:
        issues = await self._read_seerr(collector, "list_issues", self._seerr.list_issues)
        return None if issues is None else [issue for issue in issues if issue.media_id == media_id]

    async def _resolve_seerr_media(
        self,
        event: MediaDeletionEvent,
        *,
        media_type: str,
        collector: ActionCollector,
    ) -> SeerrMedia | None:
        media_items = await self._read_seerr(collector, "resolve_media", self._seerr.list_media)
        if media_items is None:
            return None
        if media_type == "movie":
            decision = self._seerr_resolver.resolve_movie(event.fingerprint, media_items)
        else:
            decision = self._seerr_resolver.resolve_tv(event.fingerprint, media_items)

        if decision.candidate is not None:
            return decision.candidate

        collector.add(
            "seerr",
            "resolve_media",
            ActionStatus.SKIPPED,
            "No strict Seerr media match was found.",
            reason=decision.reason,
        )
        return None

    async def _cleanup_seerr_movie(
        self,
        event: MediaDeletionEvent,
        collector: ActionCollector,
    ) -> None:
        media = await self._resolve_seerr_media(event, media_type="movie", collector=collector)
        if media is None:
            return

        requests = await self._list_requests_for_media(media.id, collector)
        issues = await self._list_issues_for_media(media.id, collector)
        if requests is None or issues is None:
            return

        for request in requests:
            await self._run_mutation(
                collector,
                system="seerr",
                action="delete_request",
                message=f"Deleted Seerr request {request.id}.",
                mutation=bind_async(self._seerr.delete_request, request.id),
                request_id=request.id,
            )

        for issue in issues:
            await self._run_mutation(
                collector,
                system="seerr",
                action="delete_issue",
                message=f"Deleted Seerr issue {issue.id}.",
                mutation=bind_async(self._seerr.delete_issue, issue.id),
                issue_id=issue.id,
            )

        await self._run_mutation(
            collector,
            system="seerr",
            action="delete_media",
            message=f"Deleted Seerr media {media.id}.",
            mutation=bind_async(self._seerr.delete_media, media.id),
            media_id=media.id,
        )

    async def _cleanup_seerr_series(
        self,
        event: MediaDeletionEvent,
        collector: ActionCollector,
    ) -> None:
        media = await self._resolve_seerr_media(event, media_type="tv", collector=collector)
        if media is None:
            return

        requests = await self._list_requests_for_media(media.id, collector)
        issues = await self._list_issues_for_media(media.id, collector)
        if requests is None or issues is None:
            return

        for request in requests:
            await self._run_mutation(
                collector,
                system="seerr",
                action="delete_request",
                message=f"Deleted Seerr request {request.id}.",
                mutation=bind_async(self._seerr.delete_request, request.id),
                request_id=request.id,
            )

        for issue in issues:
            await self._run_mutation(
                collector,
                system="seerr",
                action="delete_issue",
                message=f"Deleted Seerr issue {issue.id}.",
                mutation=bind_async(self._seerr.delete_issue, issue.id),
                issue_id=issue.id,
            )

        await self._run_mutation(
            collector,
            system="seerr",
            action="delete_media",
            message=f"Deleted Seerr media {media.id}.",
            mutation=bind_async(self._seerr.delete_media, media.id),
            media_id=media.id,
        )

    async def _cleanup_seerr_season(
        self,
        event: MediaDeletionEvent,
        collector: ActionCollector,
    ) -> None:
        media = await self._resolve_seerr_media(event, media_type="tv", collector=collector)
        if media is None or event.season_number is None:
            return

        requests = await self._list_requests_for_media(media.id, collector)
        issues = await self._list_issues_for_media(media.id, collector)
        if requests is None or issues is None:
            return

        for request in requests:
            if event.season_number not in request.season_numbers:
                continue
            remaining_seasons = [number for number in request.season_numbers if number != event.season_number]
            if remaining_seasons:
                await self._run_mutation(
                    collector,
                    system="seerr",
                    action="update_request",
                    message=f"Removed season {event.season_number} from Seerr request {request.id}.",
                    mutation=bind_async(
                        self._seerr.update_request_seasons,
                        request,
                        season_numbers=remaining_seasons,
                    ),
                    request_id=request.id,
                    season_number=event.season_number,
                )
                continue
            await self._run_mutation(
                collector,
                system="seerr",
                action="delete_request",
                message=f"Deleted Seerr request {request.id}.",
                mutation=bind_async(self._seerr.delete_request, request.id),
                request_id=request.id,
                season_number=event.season_number,
            )

        matching_issues = [issue for issue in issues if issue.problem_season == event.season_number]
        for issue in matching_issues:
            await self._run_mutation(
                collector,
                system="seerr",
                action="delete_issue",
                message=f"Deleted Seerr issue {issue.id}.",
                mutation=bind_async(self._seerr.delete_issue, issue.id),
                issue_id=issue.id,
                season_number=event.season_number,
            )

    async def _cleanup_seerr_episode(
        self,
        event: MediaDeletionEvent,
        collector: ActionCollector,
        *,
        episodes: Sequence[SonarrEpisode],
    ) -> None:
        media = await self._resolve_seerr_media(event, media_type="tv", collector=collector)
        if media is None or event.season_number is None or not event.episode_numbers:
            return

        requests = await self._list_requests_for_media(media.id, collector)
        issues = await self._list_issues_for_media(media.id, collector)
        if requests is None or issues is None:
            return
        season_number = event.season_number
        episode_numbers = event.episode_numbers
        known_season_episodes = {
            episode.episode_number for episode in episodes if episode.season_number == season_number
        }
        covers_complete_season = bool(known_season_episodes) and known_season_episodes <= episode_numbers

        for request in requests:
            if season_number not in request.season_numbers:
                continue
            if not covers_complete_season:
                collector.add(
                    "seerr",
                    "retain_request",
                    ActionStatus.SKIPPED,
                    "Retained the Seerr request because Seerr requests are season-scoped and the event does not "
                    "safely cover the complete season.",
                    reason=FailureReason.PARTIAL_REQUEST_RETAINED,
                    request_id=request.id,
                    season_number=season_number,
                    episode_numbers=sorted(episode_numbers),
                    known_season_episode_numbers=sorted(known_season_episodes),
                )
                continue

            remaining_seasons = [number for number in request.season_numbers if number != season_number]
            if remaining_seasons:
                await self._run_mutation(
                    collector,
                    system="seerr",
                    action="update_request",
                    message=f"Removed fully deleted season {season_number} from Seerr request {request.id}.",
                    mutation=bind_async(
                        self._seerr.update_request_seasons,
                        request,
                        season_numbers=remaining_seasons,
                    ),
                    request_id=request.id,
                    season_number=season_number,
                    episode_numbers=sorted(episode_numbers),
                )
                continue
            await self._run_mutation(
                collector,
                system="seerr",
                action="delete_request",
                message=f"Deleted Seerr request {request.id} after the complete requested season was deleted.",
                mutation=bind_async(self._seerr.delete_request, request.id),
                request_id=request.id,
                season_number=season_number,
                episode_numbers=sorted(episode_numbers),
            )

        matching_issues = [
            issue
            for issue in issues
            if issue.problem_season == season_number and issue.problem_episode in episode_numbers
        ]
        for issue in matching_issues:
            await self._run_mutation(
                collector,
                system="seerr",
                action="delete_issue",
                message=f"Deleted Seerr issue {issue.id} for a deleted episode.",
                mutation=bind_async(self._seerr.delete_issue, issue.id),
                issue_id=issue.id,
                season_number=season_number,
                episode_number=issue.problem_episode,
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
        seerr: SeerrClientPort,
        downloader: DownloaderClientPort,
        retention: RetentionRecorderPort | None = None,
        retention_thresholds: Mapping[str, tuple[float | None, int | None]] | None = None,
    ) -> None:
        super().__init__(
            dry_run=dry_run,
            logger=logger,
            seerr=seerr,
            downloader=downloader,
            retention=retention,
            retention_thresholds=retention_thresholds,
        )
        self._radarr = radarr
        self._resolver = StrictMovieResolver()

    async def _movie_hashes_exclusive(
        self,
        collector: ActionCollector,
        movie_id: int,
        movies: Sequence[RadarrMovie],
        hashes: set[str],
    ) -> bool:
        """Retain the entire cascade unless all configured Radarr histories isolate the hash."""
        del movies
        if not hashes:
            return True  # The normal missing-hash guard below still blocks deletion.
        lookup = getattr(self._radarr, "list_download_history", None)
        if not callable(lookup):
            collector.add(
                "radarr",
                "verify_download_ownership",
                ActionStatus.FAILED,
                "Radarr does not provide hash-scoped ownership history.",
                reason=FailureReason.OWNERSHIP_UNVERIFIABLE,
            )
            return False
        semaphore = asyncio.Semaphore(4)
        normalized_hashes = sorted({value.upper() for value in hashes})

        async def history_for_hash(hash_value: str) -> tuple[str, Sequence[object]]:
            async with semaphore:
                records = await lookup(hash_value)
            return hash_value, records

        tasks = [asyncio.create_task(history_for_hash(hash_value)) for hash_value in normalized_hashes]
        try:
            histories = await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise
        except Exception as exc:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            collector.add(
                "radarr",
                "verify_download_ownership",
                ActionStatus.FAILED,
                "Could not verify exclusive movie download ownership.",
                reason=FailureReason.AUTHENTICATION_FAILED
                if isinstance(exc, AuthenticationError)
                else FailureReason.OWNERSHIP_UNVERIFIABLE,
                error=str(exc),
            )
            return False
        try:
            shared_hashes: set[str] = set()
            for hash_value, records in histories:
                if not isinstance(records, Sequence) or isinstance(records, (str, bytes)):
                    raise TypeError("Radarr returned malformed hash-scoped history.")
                for record in records:
                    if (
                        not isinstance(record, RadarrHistoryRecord)
                        or isinstance(record.movie_id, bool)
                        or record.movie_id <= 0
                    ):
                        raise TypeError("Radarr returned malformed hash-scoped history records.")
                    if not isinstance(record.download_id, str) or not record.download_id.strip():
                        raise TypeError("Radarr returned malformed hash-scoped download IDs.")
                    if record.download_id.strip().upper() != hash_value:
                        raise ValueError("Radarr returned history for a different download hash.")
                    if record.movie_id != movie_id:
                        shared_hashes.add(hash_value)
        except Exception as exc:  # noqa: BLE001 - malformed untrusted history fails closed
            collector.add(
                "radarr",
                "verify_download_ownership",
                ActionStatus.FAILED,
                "Could not verify exclusive movie download ownership.",
                reason=FailureReason.OWNERSHIP_UNVERIFIABLE,
                error=str(exc),
            )
            return False
        if shared_hashes:
            collector.add(
                "radarr",
                "verify_download_ownership",
                ActionStatus.SKIPPED,
                "A download hash is referenced by another movie; all dependent cleanup is blocked.",
                reason=FailureReason.PACK_TORRENT,
                hashes=sorted(shared_hashes),
            )
        return not shared_hashes

    async def _handle(self, event: MediaDeletionEvent, collector: ActionCollector) -> ProcessingResult:
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
            downloader_ready = await self._movie_hashes_exclusive(collector, movie.id, movies, hashes)
            if downloader_ready:
                downloader_ready = await self._cleanup_hashes(collector, hashes, event=event)
            if downloader_ready:
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
                    path=movie.path,
                    radarr_instance_id=movie.service_id,
                    radarr_instance_name=movie.service_name,
                )
            else:
                self._record_downloader_block(
                    collector,
                    system="radarr",
                    action="delete_movie",
                    message="Kept the Radarr movie so failed torrent cleanup can be retried safely.",
                    movie_id=movie.id,
                    path=movie.path,
                )

        if movie is None and decision.reason is not FailureReason.NO_MATCH:
            return collector.build()
        if movie is None or downloader_ready:
            await self._cleanup_seerr_movie(event, collector)
        else:
            self._record_downloader_block(
                collector,
                system="seerr",
                action="cleanup_movie",
                message="Kept Seerr records until torrent cleanup completes safely.",
            )
        return collector.build()


class SeriesDeletionStrategy(BaseDeletionStrategy):
    """Handle full series deletions."""

    def __init__(
        self,
        *,
        dry_run: bool,
        logger: logging.Logger,
        sonarr: SonarrClientPort,
        seerr: SeerrClientPort,
        downloader: DownloaderClientPort,
        retention: RetentionRecorderPort | None = None,
        retention_thresholds: Mapping[str, tuple[float | None, int | None]] | None = None,
    ) -> None:
        super().__init__(
            dry_run=dry_run,
            logger=logger,
            seerr=seerr,
            downloader=downloader,
            retention=retention,
            retention_thresholds=retention_thresholds,
        )
        self._sonarr = sonarr
        self._resolver = StrictSeriesResolver()
        self._safety = SonarrDeletionSafetyAnalyzer()

    async def _handle(self, event: MediaDeletionEvent, collector: ActionCollector) -> ProcessingResult:
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
            downloader_ready = await self._cleanup_hashes(collector, set(safety.hashes_to_delete), event=event)
            if downloader_ready:
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
                    path=series.path,
                    sonarr_instance_id=series.service_id,
                    sonarr_instance_name=series.service_name,
                )
            else:
                self._record_downloader_block(
                    collector,
                    system="sonarr",
                    action="delete_series",
                    message="Kept the Sonarr series so failed torrent cleanup can be retried safely.",
                    series_id=series.id,
                    path=series.path,
                )

        if series is None and decision.reason is not FailureReason.NO_MATCH:
            return collector.build()
        if series is None or downloader_ready:
            await self._cleanup_seerr_series(event, collector)
        else:
            self._record_downloader_block(
                collector,
                system="seerr",
                action="cleanup_series",
                message="Kept Seerr records until torrent cleanup completes safely.",
            )
        return collector.build()


class SeasonDeletionStrategy(BaseDeletionStrategy):
    """Handle season deletions."""

    def __init__(
        self,
        *,
        dry_run: bool,
        logger: logging.Logger,
        sonarr: SonarrClientPort,
        seerr: SeerrClientPort,
        downloader: DownloaderClientPort,
        retention: RetentionRecorderPort | None = None,
        retention_thresholds: Mapping[str, tuple[float | None, int | None]] | None = None,
    ) -> None:
        super().__init__(
            dry_run=dry_run,
            logger=logger,
            seerr=seerr,
            downloader=downloader,
            retention=retention,
            retention_thresholds=retention_thresholds,
        )
        self._sonarr = sonarr
        self._resolver = StrictSeriesResolver()
        self._safety = SonarrDeletionSafetyAnalyzer()

    async def _handle(self, event: MediaDeletionEvent, collector: ActionCollector) -> ProcessingResult:
        series_list = list(await self._sonarr.list_series())
        decision = self._resolver.resolve(event.fingerprint, series_list)
        series = decision.candidate
        if series is None:
            self._record_sonarr_match_failure(collector, decision.reason)
            if decision.reason is not FailureReason.NO_MATCH:
                return collector.build()
            await self._cleanup_seerr_season(event, collector)
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

        downloader_ready = await self._cleanup_hashes(
            collector,
            set(safety.hashes_to_delete),
            allow_empty=not safety.episode_file_ids_to_delete,
            event=event,
        )
        if not downloader_ready:
            self._record_downloader_block(
                collector,
                system="sonarr",
                action="delete_season_scope",
                message=(
                    "Kept Sonarr season files and monitoring state so failed torrent cleanup can be retried safely."
                ),
                series_id=series.id,
                season_number=event.season_number,
                path=series.path,
            )
            self._record_downloader_block(
                collector,
                system="seerr",
                action="cleanup_season",
                message="Kept Seerr records until torrent cleanup completes safely.",
            )
            return collector.build()

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

        for episode_file_id in sorted(safety.episode_file_ids_to_delete):
            await self._run_mutation(
                collector,
                system="sonarr",
                action="delete_episode_file",
                message=f"Deleted Sonarr episode file {episode_file_id}.",
                mutation=bind_async(self._sonarr.delete_episode_file, episode_file_id),
                episode_file_id=episode_file_id,
            )

        if event.season_number is not None:
            await self._run_mutation(
                collector,
                system="sonarr",
                action="unmonitor_season",
                message=f"Unmonitored Sonarr season {event.season_number} of series {series.id}.",
                mutation=bind_async(self._sonarr.unmonitor_season, series.id, event.season_number),
                series_id=series.id,
                season_number=event.season_number,
                path=series.path,
                sonarr_instance_id=series.service_id,
                sonarr_instance_name=series.service_name,
            )

        await self._cleanup_seerr_season(event, collector)
        return collector.build()


class EpisodeDeletionStrategy(BaseDeletionStrategy):
    """Handle episode deletions."""

    def __init__(
        self,
        *,
        dry_run: bool,
        logger: logging.Logger,
        sonarr: SonarrClientPort,
        seerr: SeerrClientPort,
        downloader: DownloaderClientPort,
        retention: RetentionRecorderPort | None = None,
        retention_thresholds: Mapping[str, tuple[float | None, int | None]] | None = None,
    ) -> None:
        super().__init__(
            dry_run=dry_run,
            logger=logger,
            seerr=seerr,
            downloader=downloader,
            retention=retention,
            retention_thresholds=retention_thresholds,
        )
        self._sonarr = sonarr
        self._resolver = StrictSeriesResolver()
        self._safety = SonarrDeletionSafetyAnalyzer()

    async def _handle(self, event: MediaDeletionEvent, collector: ActionCollector) -> ProcessingResult:
        series_list = list(await self._sonarr.list_series())
        decision = self._resolver.resolve(event.fingerprint, series_list)
        series = decision.candidate
        if series is None:
            self._record_sonarr_match_failure(collector, decision.reason)
            if decision.reason is not FailureReason.NO_MATCH:
                return collector.build()
            await self._cleanup_seerr_episode(event, collector, episodes=())
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

        downloader_ready = await self._cleanup_hashes(
            collector,
            set(safety.hashes_to_delete),
            allow_empty=not safety.episode_file_ids_to_delete,
            event=event,
        )
        if not downloader_ready:
            self._record_downloader_block(
                collector,
                system="sonarr",
                action="delete_episode_scope",
                message=(
                    "Kept Sonarr episode files and monitoring state so failed torrent cleanup can be retried safely."
                ),
                series_id=series.id,
                season_number=event.season_number,
                episode_numbers=sorted(event.episode_numbers),
                path=series.path,
            )
            self._record_downloader_block(
                collector,
                system="seerr",
                action="cleanup_episode",
                message="Kept Seerr records until torrent cleanup completes safely.",
            )
            return collector.build()

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

        for episode_file_id in sorted(safety.episode_file_ids_to_delete):
            await self._run_mutation(
                collector,
                system="sonarr",
                action="delete_episode_file",
                message=f"Deleted Sonarr episode file {episode_file_id}.",
                mutation=bind_async(self._sonarr.delete_episode_file, episode_file_id),
                episode_file_id=episode_file_id,
            )

        await self._cleanup_seerr_episode(event, collector, episodes=episodes)
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
        seerr: SeerrClientPort,
        downloader: DownloaderClientPort,
        retention: RetentionRecorderPort | None = None,
        retention_thresholds: Mapping[str, tuple[float | None, int | None]] | None = None,
    ) -> None:
        self._dry_run = dry_run
        self._logger = logger
        self._radarr = radarr
        self._sonarr = sonarr
        self._seerr = seerr
        self._downloader = downloader
        self._retention = retention
        self._retention_thresholds = dict(retention_thresholds or {})

    def for_item_type(
        self,
        item_type: ItemType,
        *,
        dry_run: bool | None = None,
    ) -> BaseDeletionStrategy:
        """Build a live strategy or an explicit dry-run preflight strategy."""

        effective_dry_run = self._dry_run if dry_run is None else dry_run
        if item_type is ItemType.MOVIE:
            return MovieDeletionStrategy(
                dry_run=effective_dry_run,
                logger=self._logger,
                radarr=self._radarr,
                seerr=self._seerr,
                downloader=self._downloader,
                retention=self._retention,
                retention_thresholds=self._retention_thresholds,
            )
        if item_type is ItemType.SERIES:
            return SeriesDeletionStrategy(
                dry_run=effective_dry_run,
                logger=self._logger,
                sonarr=self._sonarr,
                seerr=self._seerr,
                downloader=self._downloader,
                retention=self._retention,
                retention_thresholds=self._retention_thresholds,
            )
        if item_type is ItemType.SEASON:
            return SeasonDeletionStrategy(
                dry_run=effective_dry_run,
                logger=self._logger,
                sonarr=self._sonarr,
                seerr=self._seerr,
                downloader=self._downloader,
                retention=self._retention,
                retention_thresholds=self._retention_thresholds,
            )
        return EpisodeDeletionStrategy(
            dry_run=effective_dry_run,
            logger=self._logger,
            sonarr=self._sonarr,
            seerr=self._seerr,
            downloader=self._downloader,
            retention=self._retention,
            retention_thresholds=self._retention_thresholds,
        )
