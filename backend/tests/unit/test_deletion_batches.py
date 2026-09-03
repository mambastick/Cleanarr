"""Focused safety scenarios for durable, hash-bound manual deletion batches."""

from __future__ import annotations

import asyncio
import sqlite3
from dataclasses import replace
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from cleanarr.application.deletion_batches import (
    BatchPlanChangedError,
    BatchQueueFullError,
    BatchValidationError,
    ManualDeletionBatchService,
)
from cleanarr.application.deletion_jobs import DeletionJobIdempotencyConflictError, DeletionJobIdempotencyRetiredError
from cleanarr.application.deletion_models import (
    ActionResultResponse,
    BatchChildPreviewStatus,
    BatchChildStatus,
    ManualDeleteBatchStatus,
    ManualDeleteBatchSubmitRequest,
    ManualDeleteRequest,
    ProcessingResultResponse,
)
from cleanarr.application.manual_deletion import LibraryItemChangedError
from cleanarr.domain import (
    ActionStatus,
    FailureReason,
    ItemType,
    LibraryMediaType,
    MediaDeletionEvent,
    MediaFingerprint,
    OverallStatus,
    encode_library_resource,
)
from cleanarr.infrastructure.deletion_repository import SQLiteDeletionRepository


def _event(payload: ManualDeleteRequest) -> MediaDeletionEvent:
    movie_id = payload.radarr_movie_id or 0
    return MediaDeletionEvent(
        notification_type="ItemDeleted",
        item_type=payload.item_type,
        item_id=f"manual:radarr:{movie_id}",
        name=f"Movie {movie_id}",
        fingerprint=MediaFingerprint(tmdb_id=movie_id, path=f"/media/{movie_id}"),
    )


async def _resolver(payload: ManualDeleteRequest) -> MediaDeletionEvent:
    return _event(payload)


async def _previewer(payload: ManualDeleteRequest, event: MediaDeletionEvent) -> ProcessingResultResponse:
    return ProcessingResultResponse(
        item_type=event.item_type,
        item_id=event.item_id,
        name=event.name,
        status=OverallStatus.SUCCESS,
        actions=[],
    )


def _batch_service(
    resolver: object,
    previewer: object,
    runner: object,
    *,
    db_path: Path,
    execution_lock: asyncio.Lock,
    **kwargs: object,
) -> ManualDeletionBatchService:
    return ManualDeletionBatchService(  # type: ignore[arg-type]
        resolver,
        previewer,
        runner,
        repository=SQLiteDeletionRepository(db_path),
        execution_lock=execution_lock,
        **kwargs,
    )


async def _wait_for_terminal(store: ManualDeletionBatchService, batch_id: UUID) -> None:
    for _ in range(200):
        if store.get(batch_id).status not in {ManualDeleteBatchStatus.QUEUED, ManualDeleteBatchStatus.RUNNING}:
            return
        await asyncio.sleep(0.01)
    raise AssertionError("batch did not finish")


def _request(movie_id: int, *, display_name: str | None = None) -> ManualDeleteRequest:
    return ManualDeleteRequest(item_type=ItemType.MOVIE, radarr_movie_id=movie_id, display_name=display_name)


@pytest.mark.asyncio
async def test_batch_preview_is_canonical_and_rejects_duplicate_identities(tmp_path: Path) -> None:
    async def runner(payload, event, report):  # type: ignore[no-untyped-def]
        return await _previewer(payload, event)

    store = _batch_service(
        _resolver, _previewer, runner, db_path=tmp_path / "cleanarr.db", execution_lock=asyncio.Lock()
    )
    try:
        first = await store.preview([_request(2, display_name="Two"), _request(1, display_name="One")])
        second = await store.preview(
            [_request(1, display_name="Other title"), _request(2, display_name="Changed title")]
        )
        assert first.batch_hash == second.batch_hash
        assert [child.display_name for child in first.children] == ["One", "Two"]
        with pytest.raises(BatchValidationError, match="same destructive"):
            await store.preview([_request(1), _request(1, display_name="duplicate")])
        with pytest.raises(BatchValidationError, match="same destructive"):
            await store.preview(
                [
                    ManualDeleteRequest(item_type=ItemType.MOVIE, radarr_movie_id=1, jellyfin_item_id="jellyfin-a"),
                    ManualDeleteRequest(item_type=ItemType.MOVIE, radarr_movie_id=1, jellyfin_item_id="jellyfin-b"),
                ]
            )
        with pytest.raises(BatchValidationError, match="same destructive"):
            await store.preview(
                [
                    ManualDeleteRequest(
                        item_type=ItemType.MOVIE,
                        radarr_movie_id=1,
                        library_resource_id=encode_library_resource(LibraryMediaType.MOVIE, "radarr-a", 1),
                    ),
                    ManualDeleteRequest(
                        item_type=ItemType.MOVIE,
                        radarr_movie_id=1,
                        library_resource_id=encode_library_resource(LibraryMediaType.MOVIE, "radarr-b", 1),
                    ),
                ]
            )
        with pytest.raises(BatchValidationError, match="whole-series"):
            await store.preview(
                [
                    ManualDeleteRequest(item_type=ItemType.SERIES, sonarr_series_id=7),
                    ManualDeleteRequest(item_type=ItemType.SEASON, sonarr_series_id=7, season_number=1),
                ]
            )
        seasons = await store.preview(
            [
                ManualDeleteRequest(item_type=ItemType.SEASON, sonarr_series_id=7, season_number=1),
                ManualDeleteRequest(item_type=ItemType.SEASON, sonarr_series_id=7, season_number=2),
            ]
        )
        assert seasons.ready_count == 2
    finally:
        await store.stop()


@pytest.mark.asyncio
async def test_batch_preview_blocks_unexpected_resolution_failures_without_hiding_safe_siblings(tmp_path: Path) -> None:
    async def resolver(payload):  # type: ignore[no-untyped-def]
        if payload.radarr_movie_id == 2:
            raise RuntimeError("downstream connection details must not be exposed")
        return _event(payload)

    async def runner(payload, event, report):  # type: ignore[no-untyped-def]
        return await _previewer(payload, event)

    store = _batch_service(
        resolver, _previewer, runner, db_path=tmp_path / "cleanarr.db", execution_lock=asyncio.Lock()
    )
    try:
        preview = await store.preview([_request(1), _request(2), _request(3)])
        assert [child.status for child in preview.children] == [
            BatchChildPreviewStatus.READY,
            BatchChildPreviewStatus.BLOCKED,
            BatchChildPreviewStatus.READY,
        ]
        blocked = preview.children[1]
        assert blocked.blocked_code == "resolution_failed"
        assert blocked.blocked_message == "The item could not be resolved safely."
        assert "downstream" not in blocked.blocked_message
    finally:
        await store.stop()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("left_path", "right_path"),
    [
        ("/data/shared", "/data/shared"),
        ("/data/shared", "/data/shared/child"),
    ],
)
async def test_batch_preview_blocks_exact_and_nested_physical_scope_overlap(
    tmp_path: Path,
    left_path: str,
    right_path: str,
) -> None:
    async def resolver(payload: ManualDeleteRequest) -> MediaDeletionEvent:
        event = _event(payload)
        return replace(
            event,
            fingerprint=replace(
                event.fingerprint,
                path=left_path if payload.radarr_movie_id == 1 else right_path,
            ),
        )

    async def runner(payload, event, report):  # type: ignore[no-untyped-def]
        return await _previewer(payload, event)

    store = _batch_service(
        resolver,
        _previewer,
        runner,
        db_path=tmp_path / "cleanarr.db",
        execution_lock=asyncio.Lock(),
    )
    try:
        preview = await store.preview([_request(1), _request(2)])

        assert preview.ready_count == 0
        assert preview.blocked_count == 2
        assert {child.blocked_code for child in preview.children} == {"overlapping_mutation_scope"}
        assert all("/data" not in (child.blocked_message or "") for child in preview.children)
    finally:
        await store.stop()


@pytest.mark.asyncio
async def test_batch_preview_blocks_malformed_physical_scope_and_hash_binds_path(tmp_path: Path) -> None:
    current_path: str | None = "/data/one"

    async def resolver(payload: ManualDeleteRequest) -> MediaDeletionEvent:
        event = _event(payload)
        return replace(event, fingerprint=replace(event.fingerprint, path=current_path))

    async def runner(payload, event, report):  # type: ignore[no-untyped-def]
        return await _previewer(payload, event)

    store = _batch_service(
        resolver,
        _previewer,
        runner,
        db_path=tmp_path / "cleanarr.db",
        execution_lock=asyncio.Lock(),
    )
    try:
        preview = await store.preview([_request(1)])
        current_path = "/data/two"
        changed = await store.preview([_request(1)])
        assert changed.batch_hash != preview.batch_hash

        for invalid_path in ("/data/../private", None):
            current_path = invalid_path
            invalid = await store.preview([_request(1)])
            assert invalid.children[0].blocked_code == "invalid_mutation_scope"
    finally:
        await store.stop()


@pytest.mark.asyncio
async def test_batch_resource_mismatch_is_structured_and_cannot_be_submitted(tmp_path: Path) -> None:
    async def changed_resolver(payload):  # type: ignore[no-untyped-def]
        raise LibraryItemChangedError()

    async def runner(payload, event, report):  # type: ignore[no-untyped-def]
        return await _previewer(payload, event)

    store = _batch_service(
        changed_resolver,
        _previewer,
        runner,
        db_path=tmp_path / "cleanarr.db",
        execution_lock=asyncio.Lock(),
    )
    child = ManualDeleteRequest(
        item_type=ItemType.MOVIE,
        radarr_movie_id=1,
        library_resource_id=encode_library_resource(LibraryMediaType.MOVIE, "radarr-one", 1),
    )
    try:
        preview = await store.preview([child])
        assert preview.children[0].blocked_code == "library_item_changed"
        with pytest.raises(BatchPlanChangedError) as changed:
            await store.submit(
                ManualDeleteBatchSubmitRequest(
                    children=[child],
                    confirmed_batch_hash=preview.batch_hash,
                    confirmed_item_count=1,
                    idempotency_key=uuid4(),
                )
            )
        assert changed.value.code == "library_item_changed"
    finally:
        await store.stop()


@pytest.mark.asyncio
async def test_batch_preview_propagates_resolver_cancellation(tmp_path: Path) -> None:
    async def cancelled_resolver(payload):  # type: ignore[no-untyped-def]
        raise asyncio.CancelledError

    async def runner(payload, event, report):  # type: ignore[no-untyped-def]
        return await _previewer(payload, event)

    store = _batch_service(
        cancelled_resolver,
        _previewer,
        runner,
        db_path=tmp_path / "cleanarr.db",
        execution_lock=asyncio.Lock(),
    )
    try:
        with pytest.raises(asyncio.CancelledError):
            await store.preview([_request(1)])
    finally:
        await store.stop()


@pytest.mark.asyncio
async def test_batch_persists_preblocked_child_and_completes_safe_sibling(tmp_path: Path) -> None:
    calls: list[int] = []
    blocked_variant = "first"

    async def previewer(payload, event):  # type: ignore[no-untyped-def]
        if payload.radarr_movie_id == 2:
            result = ProcessingResultResponse(
                item_type=event.item_type,
                item_id=event.item_id,
                name=event.name,
                status=OverallStatus.SUCCESS,
                actions=[
                    ActionResultResponse(
                        system="downloader",
                        action="skip",
                        status=ActionStatus.SKIPPED,
                        reason=FailureReason.AMBIGUOUS_MATCH,
                        message="unsafe",
                        details={},
                    )
                ],
            )
            return result.model_copy(update={"name": blocked_variant})
        return await _previewer(payload, event)

    async def runner(payload, event, report):  # type: ignore[no-untyped-def]
        calls.append(payload.radarr_movie_id or 0)
        return await _previewer(payload, event)

    store = _batch_service(
        _resolver, previewer, runner, db_path=tmp_path / "cleanarr.db", execution_lock=asyncio.Lock()
    )
    children = [_request(1), _request(2)]
    try:
        preview = await store.preview(children)
        assert preview.children[1].plan_hash is not None
        blocked_variant = "changed"
        changed = await store.preview(children)
        assert changed.batch_hash != preview.batch_hash
        blocked_variant = "first"
        queued = await store.submit(
            ManualDeleteBatchSubmitRequest(
                children=children,
                idempotency_key=uuid4(),
                confirmed_batch_hash=preview.batch_hash,
                confirmed_item_count=2,
            )
        )
        await _wait_for_terminal(store, queued.id)
        result = store.get(queued.id)
        assert result.status is ManualDeleteBatchStatus.PARTIAL
        assert [child.status for child in result.children] == [BatchChildStatus.COMPLETED, BatchChildStatus.BLOCKED]
        assert calls == [1]
    finally:
        await store.stop()


@pytest.mark.asyncio
async def test_batch_submit_rechecks_plan_idempotency_and_restart_unknown_child(tmp_path: Path) -> None:
    db_path = tmp_path / "cleanarr.db"
    plan_version = "original"
    first_child_started = asyncio.Event()
    never_release = asyncio.Event()

    async def previewer(payload, event):  # type: ignore[no-untyped-def]
        result = await _previewer(payload, event)
        return result.model_copy(update={"name": f"{event.name}-{plan_version}"})

    async def interrupted_runner(payload, event, report):  # type: ignore[no-untyped-def]
        if payload.radarr_movie_id == 1:
            first_child_started.set()
            await never_release.wait()
        return await _previewer(payload, event)

    first_store = _batch_service(
        _resolver, previewer, interrupted_runner, db_path=db_path, execution_lock=asyncio.Lock()
    )
    children = [_request(1), _request(2)]
    preview = await first_store.preview(children)
    with pytest.raises(BatchPlanChangedError):
        plan_version = "changed"
        await first_store.submit(
            ManualDeleteBatchSubmitRequest(
                children=children,
                idempotency_key=uuid4(),
                confirmed_batch_hash=preview.batch_hash,
                confirmed_item_count=2,
            )
        )
    assert first_store.list(limit=50).batches == []
    with sqlite3.connect(db_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM manual_delete_batches").fetchone() == (0,)
        assert connection.execute("SELECT COUNT(*) FROM manual_delete_batch_children").fetchone() == (0,)
        assert connection.execute("SELECT COUNT(*) FROM destructive_idempotency_ledger").fetchone() == (0,)
    plan_version = "original"
    preview = await first_store.preview(children)
    key = uuid4()
    queued = await first_store.submit(
        ManualDeleteBatchSubmitRequest(
            children=children, idempotency_key=key, confirmed_batch_hash=preview.batch_hash, confirmed_item_count=2
        )
    )
    await first_child_started.wait()
    await first_store.stop()

    calls: list[int] = []

    async def resumed_runner(payload, event, report):  # type: ignore[no-untyped-def]
        calls.append(payload.radarr_movie_id or 0)
        return await _previewer(payload, event)

    resumed = _batch_service(_resolver, previewer, resumed_runner, db_path=db_path, execution_lock=asyncio.Lock())
    try:
        await resumed.start()
        await _wait_for_terminal(resumed, queued.id)
        result = resumed.get(queued.id)
        assert result.status is ManualDeleteBatchStatus.PARTIAL
        assert result.children[0].error_code == "interrupted_unknown"
        assert result.children[1].status is BatchChildStatus.COMPLETED
        assert calls == [2]
        duplicate = await resumed.submit(
            ManualDeleteBatchSubmitRequest(
                children=children, idempotency_key=key, confirmed_batch_hash=preview.batch_hash, confirmed_item_count=2
            )
        )
        assert duplicate.id == queued.id
    finally:
        await resumed.stop()


@pytest.mark.asyncio
async def test_batch_queue_cap_and_bounded_cursor_page(tmp_path: Path) -> None:
    runner_started = asyncio.Event()
    never_release = asyncio.Event()

    async def runner(payload, event, report):  # type: ignore[no-untyped-def]
        runner_started.set()
        await never_release.wait()
        return await _previewer(payload, event)

    store = _batch_service(
        _resolver,
        _previewer,
        runner,
        db_path=tmp_path / "cleanarr.db",
        execution_lock=asyncio.Lock(),
        max_pending_parents=1,
    )
    first_children = [_request(1)]
    second_children = [_request(2)]
    try:
        first_preview = await store.preview(first_children)
        first = await store.submit(
            ManualDeleteBatchSubmitRequest(
                children=first_children,
                idempotency_key=uuid4(),
                confirmed_batch_hash=first_preview.batch_hash,
                confirmed_item_count=1,
            )
        )
        await runner_started.wait()
        second_preview = await store.preview(second_children)
        with pytest.raises(BatchQueueFullError):
            await store.submit(
                ManualDeleteBatchSubmitRequest(
                    children=second_children,
                    idempotency_key=uuid4(),
                    confirmed_batch_hash=second_preview.batch_hash,
                    confirmed_item_count=1,
                )
            )
        page = store.list(limit=1)
        assert [batch.id for batch in page.batches] == [first.id]
        assert page.next_before is None
    finally:
        await store.stop()


@pytest.mark.asyncio
async def test_batch_execution_uses_the_exact_event_that_was_verified(tmp_path: Path) -> None:
    resolver_calls = 0
    runner_events: list[str] = []

    async def changing_resolver(payload):  # type: ignore[no-untyped-def]
        nonlocal resolver_calls
        resolver_calls += 1
        event = _event(payload)
        return replace(event, item_id=f"verified-event-{resolver_calls}")

    async def runner(payload, event, report):  # type: ignore[no-untyped-def]
        runner_events.append(event.item_id)
        return await _previewer(payload, event)

    async def stable_previewer(payload, event):  # type: ignore[no-untyped-def]
        return ProcessingResultResponse(
            item_type=payload.item_type,
            item_id="stable-owned-target",
            name="Stable plan",
            status=OverallStatus.SUCCESS,
            actions=[],
        )

    execution_lock = asyncio.Lock()
    await execution_lock.acquire()
    store = _batch_service(
        changing_resolver, stable_previewer, runner, db_path=tmp_path / "cleanarr.db", execution_lock=execution_lock
    )
    children = [_request(1)]
    try:
        preview = await store.preview(children)
        queued = await store.submit(
            ManualDeleteBatchSubmitRequest(
                children=children,
                idempotency_key=uuid4(),
                confirmed_batch_hash=preview.batch_hash,
                confirmed_item_count=1,
            )
        )
        execution_lock.release()
        await _wait_for_terminal(store, queued.id)
        # Preview, submit re-preview, and the immediate pre-mutation preview occur
        # once each; the runner must receive the third (not a fourth) event.
        assert resolver_calls == 3
        assert runner_events == ["verified-event-3"]
    finally:
        if execution_lock.locked():
            execution_lock.release()
        await store.stop()


@pytest.mark.asyncio
async def test_stale_partial_and_ignored_children_are_not_completed_and_later_siblings_continue(tmp_path: Path) -> None:
    execution_lock = asyncio.Lock()
    await execution_lock.acquire()
    stale = False
    stale_calls: list[int] = []

    async def stale_previewer(payload, event):  # type: ignore[no-untyped-def]
        result = await _previewer(payload, event)
        if stale and payload.radarr_movie_id == 1:
            return result.model_copy(update={"name": "changed-after-confirmation"})
        return result

    async def stale_runner(payload, event, report):  # type: ignore[no-untyped-def]
        stale_calls.append(payload.radarr_movie_id or 0)
        return await _previewer(payload, event)

    store = _batch_service(
        _resolver, stale_previewer, stale_runner, db_path=tmp_path / "stale.db", execution_lock=execution_lock
    )
    children = [_request(1), _request(2)]
    try:
        preview = await store.preview(children)
        queued = await store.submit(
            ManualDeleteBatchSubmitRequest(
                children=children,
                idempotency_key=uuid4(),
                confirmed_batch_hash=preview.batch_hash,
                confirmed_item_count=2,
            )
        )
        stale = True
        execution_lock.release()
        await _wait_for_terminal(store, queued.id)
        result = store.get(queued.id)
        assert result.status is ManualDeleteBatchStatus.PARTIAL
        assert result.children[0].status is BatchChildStatus.BLOCKED
        assert result.children[0].blocked_code == "plan_changed"
        assert result.children[1].status is BatchChildStatus.COMPLETED
        assert stale_calls == [2]
    finally:
        if execution_lock.locked():
            execution_lock.release()
        await store.stop()

    executed: list[int] = []

    async def mixed_runner(payload, event, report):  # type: ignore[no-untyped-def]
        executed.append(payload.radarr_movie_id or 0)
        result = await _previewer(payload, event)
        if payload.radarr_movie_id == 1:
            return result.model_copy(update={"status": OverallStatus.PARTIAL_FAILURE})
        if payload.radarr_movie_id == 2:
            return result.model_copy(update={"status": OverallStatus.IGNORED})
        return result

    mixed = _batch_service(
        _resolver, _previewer, mixed_runner, db_path=tmp_path / "mixed.db", execution_lock=asyncio.Lock()
    )
    mixed_children = [_request(1), _request(2), _request(3)]
    try:
        preview = await mixed.preview(mixed_children)
        queued = await mixed.submit(
            ManualDeleteBatchSubmitRequest(
                children=mixed_children,
                idempotency_key=uuid4(),
                confirmed_batch_hash=preview.batch_hash,
                confirmed_item_count=3,
            )
        )
        await _wait_for_terminal(mixed, queued.id)
        result = mixed.get(queued.id)
        assert result.status is ManualDeleteBatchStatus.PARTIAL
        assert [child.status for child in result.children] == [
            BatchChildStatus.FAILED,
            BatchChildStatus.FAILED,
            BatchChildStatus.COMPLETED,
        ]
        assert [child.error_code for child in result.children[:2]] == ["partial_result", "unsafe_result"]
        assert executed == [1, 2, 3]
    finally:
        await mixed.stop()


@pytest.mark.asyncio
async def test_batch_idempotency_tombstones_and_multi_page_history(tmp_path: Path) -> None:
    calls: list[int] = []

    async def runner(payload, event, report):  # type: ignore[no-untyped-def]
        calls.append(payload.radarr_movie_id or 0)
        return await _previewer(payload, event)

    db_path = tmp_path / "ledger.db"
    store = _batch_service(
        _resolver, _previewer, runner, db_path=db_path, execution_lock=asyncio.Lock(), history_limit=2
    )
    first_key = uuid4()
    try:
        created: list[UUID] = []
        for movie_id, key in ((1, first_key), (2, uuid4()), (3, uuid4())):
            children = [_request(movie_id)]
            preview = await store.preview(children)
            first, duplicate = await asyncio.gather(
                store.submit(
                    ManualDeleteBatchSubmitRequest(
                        children=children,
                        idempotency_key=key,
                        confirmed_batch_hash=preview.batch_hash,
                        confirmed_item_count=1,
                    )
                ),
                store.submit(
                    ManualDeleteBatchSubmitRequest(
                        children=children,
                        idempotency_key=key,
                        confirmed_batch_hash=preview.batch_hash,
                        confirmed_item_count=1,
                    )
                ),
            )
            assert first.id == duplicate.id
            created.append(first.id)
            await _wait_for_terminal(store, first.id)
        assert calls == [1, 2, 3]
        with pytest.raises(DeletionJobIdempotencyConflictError):
            changed_children = [_request(99)]
            changed_preview = await store.preview(changed_children)
            await store.submit(
                ManualDeleteBatchSubmitRequest(
                    children=changed_children,
                    idempotency_key=first_key,
                    confirmed_batch_hash=changed_preview.batch_hash,
                    confirmed_item_count=1,
                )
            )
        with pytest.raises(DeletionJobIdempotencyRetiredError):
            original_children = [_request(1)]
            original_preview = await store.preview(original_children)
            await store.submit(
                ManualDeleteBatchSubmitRequest(
                    children=original_children,
                    idempotency_key=first_key,
                    confirmed_batch_hash=original_preview.batch_hash,
                    confirmed_item_count=1,
                )
            )
        page_one = store.list(limit=1)
        page_two = store.list(limit=1, before=UUID(page_one.next_before or ""))
        assert page_one.next_before is not None
        assert len(page_one.batches) == len(page_two.batches) == 1
        assert page_one.batches[0].id != page_two.batches[0].id
        with sqlite3.connect(db_path) as connection:
            assert connection.execute("SELECT COUNT(*) FROM manual_delete_batches").fetchone() == (2,)
            assert connection.execute(
                "SELECT COUNT(*) FROM destructive_idempotency_ledger WHERE idempotency_key = ?", (str(first_key),)
            ).fetchone() == (1,)
    finally:
        await store.stop()


@pytest.mark.asyncio
async def test_batch_boundaries_all_blocked_and_nested_child_metadata(tmp_path: Path) -> None:
    resolver_calls = 0

    async def counting_resolver(payload):  # type: ignore[no-untyped-def]
        nonlocal resolver_calls
        resolver_calls += 1
        return _event(payload)

    async def blocked_previewer(payload, event):  # type: ignore[no-untyped-def]
        result = await _previewer(payload, event)
        return result.model_copy(update={"status": OverallStatus.IGNORED})

    async def runner(payload, event, report):  # type: ignore[no-untyped-def]
        raise AssertionError("blocked child must not run")

    store = _batch_service(
        counting_resolver, blocked_previewer, runner, db_path=tmp_path / "bounds.db", execution_lock=asyncio.Lock()
    )
    try:
        accepted = await store.preview([_request(index) for index in range(1, 51)])
        assert accepted.blocked_count == 50
        assert resolver_calls == 50
        with pytest.raises(BatchValidationError, match="between 1 and 50"):
            await store.preview([_request(index) for index in range(1, 52)])
        assert resolver_calls == 50
        children = [_request(1)]
        preview = await store.preview(children)
        all_blocked = await store.submit(
            ManualDeleteBatchSubmitRequest(
                children=children,
                idempotency_key=uuid4(),
                confirmed_batch_hash=preview.batch_hash,
                confirmed_item_count=1,
            )
        )
        assert all_blocked.status is ManualDeleteBatchStatus.FAILED
        assert all_blocked.children[0].status is BatchChildStatus.BLOCKED
        with pytest.raises(BatchValidationError, match="must not include"):
            await store.preview([_request(99).model_copy(update={"confirmed_plan_hash": "smuggled"})])
    finally:
        await store.stop()


@pytest.mark.asyncio
async def test_restart_prunes_terminal_history_without_resurrecting_deleted_rows(tmp_path: Path) -> None:
    db_path = tmp_path / "restart-prune.db"

    async def blocked_previewer(payload, event):  # type: ignore[no-untyped-def]
        return (await _previewer(payload, event)).model_copy(update={"status": OverallStatus.IGNORED})

    async def runner(payload, event, report):  # type: ignore[no-untyped-def]
        raise AssertionError("blocked child must not run")

    initial = _batch_service(
        _resolver,
        blocked_previewer,
        runner,
        db_path=db_path,
        execution_lock=asyncio.Lock(),
        history_limit=3,
    )
    try:
        for movie_id in range(1, 4):
            children = [_request(movie_id)]
            preview = await initial.preview(children)
            result = await initial.submit(
                ManualDeleteBatchSubmitRequest(
                    children=children,
                    idempotency_key=uuid4(),
                    confirmed_batch_hash=preview.batch_hash,
                    confirmed_item_count=1,
                )
            )
            assert result.status is ManualDeleteBatchStatus.FAILED
    finally:
        await initial.stop()

    resumed = _batch_service(
        _resolver,
        blocked_previewer,
        runner,
        db_path=db_path,
        execution_lock=asyncio.Lock(),
        history_limit=1,
    )
    try:
        await resumed.start()
        visible = resumed.list(limit=50)
        assert len(visible.batches) == 1
        assert visible.batches[0].cancelled_count == 0
        assert visible.batches[0].error_code is None
        with sqlite3.connect(db_path) as connection:
            assert connection.execute("SELECT COUNT(*) FROM manual_delete_batches").fetchone() == (1,)
            assert connection.execute("SELECT COUNT(*) FROM manual_delete_batch_children").fetchone() == (1,)
            assert connection.execute("SELECT COUNT(*) FROM destructive_idempotency_ledger").fetchone() == (3,)
    finally:
        await resumed.stop()
