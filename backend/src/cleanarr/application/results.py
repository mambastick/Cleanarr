"""Helpers for assembling webhook results."""

from __future__ import annotations

from cleanarr.domain import (
    ActionResult,
    ActionStatus,
    FailureReason,
    MediaDeletionEvent,
    OverallStatus,
    ProcessingResult,
)


class ActionCollector:
    """Mutable builder for per-event action results."""

    def __init__(self, event: MediaDeletionEvent) -> None:
        self._event = event
        self._actions: list[ActionResult] = []

    def add(
        self,
        system: str,
        action: str,
        status: ActionStatus,
        message: str,
        *,
        reason: FailureReason | None = None,
        **details: object,
    ) -> None:
        self._actions.append(
            ActionResult(
                system=system,
                action=action,
                status=status,
                message=message,
                reason=reason,
                details=details,
            )
        )

    def build(self) -> ProcessingResult:
        statuses = {action.status for action in self._actions}
        if ActionStatus.FAILED in statuses:
            overall = OverallStatus.PARTIAL_FAILURE
        elif statuses and statuses <= {
            ActionStatus.SKIPPED,
            ActionStatus.IGNORED,
            ActionStatus.ALREADY_ABSENT,
        }:
            overall = OverallStatus.IGNORED
        else:
            overall = OverallStatus.SUCCESS
        return ProcessingResult(event=self._event, status=overall, actions=tuple(self._actions))
