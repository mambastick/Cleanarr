"""Helpers for assembling webhook results."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from cleanarr.domain import (
    ActionResult,
    ActionStatus,
    FailureReason,
    MediaDeletionEvent,
    OverallStatus,
    ProcessingResult,
)

ActionObserver = Callable[[ActionResult], None]
_action_observer: ContextVar[ActionObserver | None] = ContextVar(
    "cleanarr_action_observer",
    default=None,
)


@contextmanager
def observe_actions(observer: ActionObserver) -> Iterator[None]:
    """Report actions produced in the current async task without affecting other jobs."""

    token = _action_observer.set(observer)
    try:
        yield
    finally:
        _action_observer.reset(token)


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
        result = ActionResult(
            system=system,
            action=action,
            status=status,
            message=message,
            reason=reason,
            details=details,
        )
        self._actions.append(result)
        observer = _action_observer.get()
        if observer is not None:
            observer(result)

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
