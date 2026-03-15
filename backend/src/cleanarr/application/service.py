"""Application service entrypoint."""

from __future__ import annotations

from cleanarr.application.results import ActionCollector
from cleanarr.application.strategies import DeletionStrategyFactory
from cleanarr.domain import (
    ActionStatus,
    AuthenticationError,
    ExternalServiceError,
    FailureReason,
    MediaDeletionEvent,
    OverallStatus,
    ProcessingResult,
)


class CascadeDeletionService:
    """Coordinate webhook processing and deletion strategies."""

    def __init__(self, strategy_factory: DeletionStrategyFactory) -> None:
        self._strategy_factory = strategy_factory

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
            )

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
            )
