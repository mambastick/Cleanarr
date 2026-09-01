"""Tests for persistent webhook idempotency and mutation serialization."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

import pytest

from cleanarr.application.deletion_events import DeletionExecutionCoordinator, WebhookInterruptedUnknownError
from cleanarr.domain import (
    ActionResult,
    ActionStatus,
    ItemType,
    MediaDeletionEvent,
    MediaFingerprint,
    OverallStatus,
    ProcessingResult,
)
from cleanarr.infrastructure.deletion_repository import SQLiteDeletionRepository


def _coordinator(db_path: Path) -> DeletionExecutionCoordinator:
    return DeletionExecutionCoordinator(SQLiteDeletionRepository(db_path))


def _event(
    item_id: str = "movie-1",
    *,
    occurred_at: datetime | None = None,
) -> MediaDeletionEvent:
    return MediaDeletionEvent(
        notification_type="ItemDeleted",
        item_type=ItemType.MOVIE,
        item_id=item_id,
        name="Movie",
        fingerprint=MediaFingerprint(tmdb_id=1, path="/media/shared-movie"),
        occurred_at=occurred_at,
    )


def _result(event: MediaDeletionEvent, status: OverallStatus = OverallStatus.SUCCESS) -> ProcessingResult:
    return ProcessingResult(
        event=event,
        status=status,
        actions=(
            ActionResult(
                system="radarr",
                action="delete_movie",
                status=ActionStatus.DELETED,
                message="Deleted movie.",
            ),
        ),
    )


@pytest.mark.asyncio
async def test_completed_event_is_suppressed_in_memory_and_after_restart(tmp_path: Path) -> None:
    db_path = tmp_path / "cleanarr.db"
    calls = 0

    async def processor(event: MediaDeletionEvent) -> ProcessingResult:
        nonlocal calls
        calls += 1
        return _result(event)

    coordinator = _coordinator(db_path)
    await coordinator.initialize()
    event = _event()

    first, first_duplicate = await coordinator.process_webhook(event, processor)
    second, second_duplicate = await coordinator.process_webhook(event, processor)

    assert first_duplicate is False
    assert second_duplicate is True
    assert second == first
    assert calls == 1

    restarted = _coordinator(db_path)
    await restarted.initialize()
    third, third_duplicate = await restarted.process_webhook(event, processor)
    assert third_duplicate is True
    assert third == first
    assert calls == 1


@pytest.mark.asyncio
async def test_partial_failure_remains_retryable_then_success_is_suppressed(tmp_path: Path) -> None:
    calls = 0

    async def processor(event: MediaDeletionEvent) -> ProcessingResult:
        nonlocal calls
        calls += 1
        status = OverallStatus.PARTIAL_FAILURE if calls == 1 else OverallStatus.SUCCESS
        return _result(event, status)

    coordinator = _coordinator(tmp_path / "cleanarr.db")
    await coordinator.initialize()
    event = _event()

    first, first_duplicate = await coordinator.process_webhook(event, processor)
    second, second_duplicate = await coordinator.process_webhook(event, processor)
    third, third_duplicate = await coordinator.process_webhook(event, processor)

    assert first.status is OverallStatus.PARTIAL_FAILURE
    assert first_duplicate is False
    assert second.status is OverallStatus.SUCCESS
    assert second_duplicate is False
    assert third_duplicate is True
    assert calls == 2


@pytest.mark.asyncio
async def test_ignored_event_remains_retryable_when_source_state_changes(tmp_path: Path) -> None:
    calls = 0

    async def processor(event: MediaDeletionEvent) -> ProcessingResult:
        nonlocal calls
        calls += 1
        status = OverallStatus.IGNORED if calls == 1 else OverallStatus.SUCCESS
        return _result(event, status)

    coordinator = _coordinator(tmp_path / "cleanarr.db")
    await coordinator.initialize()
    event = _event()

    first, first_duplicate = await coordinator.process_webhook(event, processor)
    second, second_duplicate = await coordinator.process_webhook(event, processor)

    assert first.status is OverallStatus.IGNORED
    assert first_duplicate is False
    assert second.status is OverallStatus.SUCCESS
    assert second_duplicate is False
    assert calls == 2


@pytest.mark.asyncio
async def test_processor_exception_leaves_an_interrupted_unknown_tombstone_after_restart(tmp_path: Path) -> None:
    calls = 0

    async def processor(event: MediaDeletionEvent) -> ProcessingResult:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("activity persistence failed")
        return _result(event)

    db_path = tmp_path / "cleanarr.db"
    coordinator = _coordinator(db_path)
    await coordinator.initialize()
    event = _event()

    with pytest.raises(RuntimeError, match="activity persistence failed"):
        await coordinator.process_webhook(event, processor)

    restarted = _coordinator(db_path)
    await restarted.initialize()
    with pytest.raises(WebhookInterruptedUnknownError) as raised:
        await restarted.process_webhook(event, processor)

    assert raised.value.code == "interrupted_unknown"
    assert calls == 1


@pytest.mark.asyncio
async def test_cancelled_processor_leaves_an_interrupted_unknown_tombstone_after_restart(tmp_path: Path) -> None:
    db_path = tmp_path / "cleanarr.db"
    entered = asyncio.Event()
    never_release = asyncio.Event()
    calls = 0

    async def processor(event: MediaDeletionEvent) -> ProcessingResult:
        nonlocal calls
        calls += 1
        entered.set()
        await never_release.wait()
        return _result(event)

    coordinator = _coordinator(db_path)
    await coordinator.initialize()
    task = asyncio.create_task(coordinator.process_webhook(_event(), processor))
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    restarted = _coordinator(db_path)
    await restarted.initialize()
    with pytest.raises(WebhookInterruptedUnknownError):
        await restarted.process_webhook(_event(), processor)
    assert calls == 1


@pytest.mark.asyncio
async def test_same_item_with_a_new_source_timestamp_is_not_suppressed(tmp_path: Path) -> None:
    calls = 0

    async def processor(event: MediaDeletionEvent) -> ProcessingResult:
        nonlocal calls
        calls += 1
        return _result(event)

    coordinator = _coordinator(tmp_path / "cleanarr.db")
    await coordinator.initialize()

    _, first_duplicate = await coordinator.process_webhook(
        _event(occurred_at=datetime(2026, 8, 12, 3, 0, tzinfo=UTC)),
        processor,
    )
    _, second_duplicate = await coordinator.process_webhook(
        _event(occurred_at=datetime(2026, 8, 13, 3, 0, tzinfo=UTC)),
        processor,
    )

    assert first_duplicate is False
    assert second_duplicate is False
    assert calls == 2


@pytest.mark.asyncio
async def test_process_wide_lock_serializes_events_sharing_a_path(tmp_path: Path) -> None:
    active = 0
    maximum_active = 0

    async def processor(event: MediaDeletionEvent) -> ProcessingResult:
        nonlocal active, maximum_active
        active += 1
        maximum_active = max(maximum_active, active)
        await asyncio.sleep(0.02)
        active -= 1
        return _result(event)

    coordinator = _coordinator(tmp_path / "cleanarr.db")
    await coordinator.initialize()

    await asyncio.gather(
        coordinator.process_webhook(_event("movie-1"), processor),
        coordinator.process_webhook(_event("movie-2"), processor),
    )

    assert maximum_active == 1
