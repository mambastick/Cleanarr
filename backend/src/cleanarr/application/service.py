"""Application service entrypoint."""

from __future__ import annotations

from cleanarr.application.ports import JellyfinServerClientPort
from cleanarr.application.results import ActionCollector
from cleanarr.application.strategies import DeletionStrategyFactory
from cleanarr.domain import (
    ActionStatus,
    AuthenticationError,
    ExternalServiceError,
    FailureReason,
    JellyfinItem,
    MediaDeletionEvent,
    OverallStatus,
    ProcessingResult,
)


class CascadeDeletionService:
    """Coordinate webhook processing and deletion strategies."""

    def __init__(
        self,
        strategy_factory: DeletionStrategyFactory,
        jellyfin: JellyfinServerClientPort | None = None,
    ) -> None:
        self._strategy_factory = strategy_factory
        self._jellyfin = jellyfin

    async def process(self, event: MediaDeletionEvent) -> ProcessingResult:
        if not event.is_item_deleted:
            collector = ActionCollector(event)
            collector.add(
                "webhook",
                "filter_notification",
                ActionStatus.IGNORED,
                f"NotificationType {event.notification_type} is not handled.",
                reason=FailureReason.UNSUPPORTED_EVENT,
            )
            result = collector.build()
            return ProcessingResult(
                event=result.event,
                status=OverallStatus.IGNORED,
                actions=result.actions,
                correlation_id=result.correlation_id,
            )

        source_guard_result = await self._confirm_source_absent(event)
        if source_guard_result is not None:
            return source_guard_result

        strategy = self._strategy_factory.for_item_type(event.item_type)
        try:
            return await strategy.handle(event)
        except ExternalServiceError as exc:
            collector = ActionCollector(event)
            collector.add(
                exc.system,
                "process_event",
                ActionStatus.FAILED,
                exc.message,
                reason=(
                    FailureReason.AUTHENTICATION_FAILED
                    if isinstance(exc, AuthenticationError)
                    else FailureReason.DOWNSTREAM_ERROR
                ),
            )
            result = collector.build()
            return ProcessingResult(
                event=result.event,
                status=OverallStatus.PARTIAL_FAILURE,
                actions=result.actions,
                correlation_id=result.correlation_id,
            )

    async def _confirm_source_absent(self, event: MediaDeletionEvent) -> ProcessingResult | None:
        """Fail closed when Jellyfin still exposes the supposedly deleted item."""

        if self._jellyfin is None:
            return None

        try:
            items = await self._jellyfin.list_items(include_types=[event.item_type.value])
        except Exception as exc:  # noqa: BLE001
            collector = ActionCollector(event)
            collector.add(
                "jellyfin",
                "confirm_deletion",
                ActionStatus.FAILED,
                "Could not confirm that the item is absent from Jellyfin; cascade deletion was blocked.",
                reason=FailureReason.DOWNSTREAM_ERROR,
                error=str(exc),
            )
            result = collector.build()
            return ProcessingResult(
                event=result.event,
                status=OverallStatus.PARTIAL_FAILURE,
                actions=result.actions,
                correlation_id=result.correlation_id,
            )

        current_item = next((item for item in items if self._matches_event(event, item)), None)
        if current_item is None:
            return None

        collector = ActionCollector(event)
        collector.add(
            "jellyfin",
            "confirm_deletion",
            ActionStatus.IGNORED,
            "A matching item is still present in Jellyfin; cascade deletion was blocked as a possible move or rescan.",
            reason=FailureReason.SOURCE_STILL_PRESENT,
            jellyfin_item_id=current_item.id,
            jellyfin_item_name=current_item.name,
        )
        result = collector.build()
        return ProcessingResult(
            event=result.event,
            status=OverallStatus.IGNORED,
            actions=result.actions,
            correlation_id=result.correlation_id,
        )

    @staticmethod
    def _matches_event(event: MediaDeletionEvent, item: JellyfinItem) -> bool:
        if item.id == event.item_id:
            return True

        fingerprint = event.fingerprint
        if fingerprint.tvdb_id is not None and item.tvdb_id == fingerprint.tvdb_id:
            return True
        if fingerprint.tmdb_id is not None and item.tmdb_id == fingerprint.tmdb_id:
            return True
        if fingerprint.imdb_id and item.imdb_id:
            return fingerprint.imdb_id.casefold() == item.imdb_id.casefold()
        return False
