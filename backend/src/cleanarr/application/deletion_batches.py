"""Application service for bounded, hash-bound durable deletion batches."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import logging
from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID, uuid4

from cleanarr.application.deletion_jobs import (
    DeletionExecutionFailure,
    DeletionJobIdempotencyConflictError,
    DeletionJobIdempotencyRetiredError,
    DeletionPreviewer,
    ManualDeleteResolver,
    ManualDeleteRunner,
    plan_hash,
)
from cleanarr.application.deletion_models import (
    BatchChildPreviewStatus,
    BatchChildStatus,
    ManualDeleteBatchChildPreviewResponse,
    ManualDeleteBatchChildResponse,
    ManualDeleteBatchListResponse,
    ManualDeleteBatchPreviewResponse,
    ManualDeleteBatchResponse,
    ManualDeleteBatchStatus,
    ManualDeleteBatchSubmitRequest,
    ManualDeleteRequest,
    ProcessingResultResponse,
)
from cleanarr.application.deletion_persistence import (
    DeletionBatchChildRecord,
    DeletionBatchRecord,
    DeletionRepositoryPort,
    DestructiveIdempotencyRecord,
)
from cleanarr.application.manual_deletion import ManualDeletionResolutionError
from cleanarr.domain import ActionStatus, FailureReason, ItemType, MediaDeletionEvent, OverallStatus
from cleanarr.redaction import redact_sensitive_text

_logger = logging.getLogger("cleanarr")
_SAFE_RETAINED_SKIP_REASONS = frozenset(
    {
        FailureReason.PACK_TORRENT,
        FailureReason.SHARED_FILE,
        FailureReason.SEEDING_POLICY,
        FailureReason.PARTIAL_REQUEST_RETAINED,
        FailureReason.NO_PARTIAL_REQUEST_CLEANUP,
    }
)


class BatchValidationError(ValueError):
    """A structurally invalid batch that must never reach preflight."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class BatchPlanChangedError(RuntimeError):
    """The submitted set no longer matches a fresh, mutation-free preview."""

    def __init__(self, message: str, *, code: str = "batch_plan_changed") -> None:
        super().__init__(message)
        self.code = code


class BatchQueueFullError(RuntimeError):
    """The durable bounded queue cannot accept another parent."""


class BatchNotFoundError(LookupError):
    """No visible batch exists for this identifier."""


class ManualDeletionBatchService:
    """Persist and execute at most 50 canonical child plans per parent."""

    _ACTIVE = {ManualDeleteBatchStatus.QUEUED, ManualDeleteBatchStatus.RUNNING}
    _CHILD_TERMINAL = {
        BatchChildStatus.COMPLETED,
        BatchChildStatus.BLOCKED,
        BatchChildStatus.FAILED,
        BatchChildStatus.CANCELLED,
    }

    def __init__(
        self,
        resolver: ManualDeleteResolver,
        previewer: DeletionPreviewer,
        runner: ManualDeleteRunner,
        *,
        repository: DeletionRepositoryPort,
        execution_lock: asyncio.Lock,
        history_limit: int = 50,
        max_pending_parents: int = 20,
    ) -> None:
        self._resolver = resolver
        self._previewer = previewer
        self._runner = runner
        self._repository = repository
        self._execution_lock = execution_lock
        self._history_limit = max(1, min(history_limit, 50))
        self._max_pending_parents = max(1, max_pending_parents)
        self._batches: dict[UUID, DeletionBatchRecord] = {}
        self._queue: asyncio.Queue[UUID] = asyncio.Queue()
        self._scheduled: set[UUID] = set()
        self._worker_task: asyncio.Task[None] | None = None
        self._initialized = False
        self._start_lock = asyncio.Lock()

    async def start(self) -> None:
        async with self._start_lock:
            if not self._initialized:
                await asyncio.to_thread(self._repository.initialize)
                loaded = await asyncio.to_thread(self._repository.load_batches)
                self._batches = {batch.id: batch for batch in loaded}
                self._recover_interrupted()
                self._prune_history()
                self._initialized = True
            if self._worker_task is None or self._worker_task.done():
                self._worker_task = asyncio.create_task(self._worker_loop(), name="cleanarr-manual-batch-worker")
            for batch in self._batches.values():
                if batch.status in self._ACTIVE and any(
                    child.status is BatchChildStatus.QUEUED for child in batch.children
                ):
                    self._schedule(batch)

    async def stop(self) -> None:
        worker = self._worker_task
        self._worker_task = None
        if worker is not None:
            worker.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await worker
        self._scheduled.clear()
        self._queue = asyncio.Queue()

    async def preview(self, children: Sequence[ManualDeleteRequest]) -> ManualDeleteBatchPreviewResponse:
        await self.start()
        canonical_items = canonical_children(children)
        resolved = [
            (identity, request, *(await self._resolve_preview_child(request, identity)))
            for identity, request in canonical_items
        ]
        unsafe_scope_indexes = physical_overlap_indexes(resolved)
        previews: list[ManualDeleteBatchChildPreviewResponse] = []
        for index, (identity, _request, preview, event) in enumerate(resolved):
            if index not in unsafe_scope_indexes:
                previews.append(preview)
                continue
            invalid_scope = event is not None and _physical_mutation_scope(event) == ()
            previews.append(
                blocked_preview(
                    identity,
                    preview.display_name,
                    "invalid_mutation_scope" if invalid_scope else "overlapping_mutation_scope",
                    (
                        "The physical deletion scope is invalid and cannot be verified safely."
                        if invalid_scope
                        else "This item overlaps another physical deletion scope in the batch."
                    ),
                    plan=preview.plan,
                )
            )
        return preview_response(previews)

    async def submit(self, payload: ManualDeleteBatchSubmitRequest) -> ManualDeleteBatchResponse:
        await self.start()
        canonical_request = canonical_batch_request(payload.children, confirmed_batch_hash=payload.confirmed_batch_hash)
        existing = await self._lookup_idempotency(payload.idempotency_key, canonical_request)
        if existing is not None:
            return self._to_response(existing)

        preview = await self.preview(payload.children)
        if payload.confirmed_item_count != len(preview.children):
            raise BatchValidationError(
                "confirmed_item_count_mismatch", "confirmed_item_count does not match the unique batch items."
            )
        if preview.batch_hash != payload.confirmed_batch_hash:
            changed_code = (
                "library_item_changed"
                if any(child.blocked_code == "library_item_changed" for child in preview.children)
                else "batch_plan_changed"
            )
            raise BatchPlanChangedError(
                "The batch plan changed after it was reviewed. Preview and confirm it again.",
                code=changed_code,
            )
        if any(child.blocked_code == "library_item_changed" for child in preview.children):
            raise BatchPlanChangedError(
                "The library item changed; preview the current item before confirming the batch.",
                code="library_item_changed",
            )
        if sum(batch.status in self._ACTIVE for batch in self._batches.values()) >= self._max_pending_parents:
            raise BatchQueueFullError("The bounded deletion batch queue is full. Wait for an active batch to finish.")

        batch = batch_from_preview(preview, canonical_request, payload.confirmed_batch_hash, payload.children)
        claimed = await asyncio.to_thread(
            self._repository.create_batch_with_idempotency,
            batch,
            idempotency_key=payload.idempotency_key,
            original_request=payload.model_dump_json(),
            max_pending_parents=self._max_pending_parents,
        )
        if claimed.queue_full:
            raise BatchQueueFullError("The bounded deletion batch queue is full. Wait for an active batch to finish.")
        if claimed.existing is not None:
            existing = await self._resolve_existing_ledger(claimed.existing, canonical_request)
            return self._to_response(existing)

        self._batches[batch.id] = batch
        self._prune_history()
        if any(child.status is BatchChildStatus.QUEUED for child in batch.children):
            self._schedule(batch)
        else:
            self._finalize(batch)
        return self._to_response(batch)

    def get(self, batch_id: UUID) -> ManualDeleteBatchResponse:
        batch = self._batches.get(batch_id)
        if batch is None:
            raise BatchNotFoundError(str(batch_id))
        return self._to_response(batch)

    def list(self, *, limit: int, before: UUID | None = None) -> ManualDeleteBatchListResponse:
        if not 1 <= limit <= 50:
            raise BatchValidationError("invalid_limit", "limit must be between 1 and 50.")
        ordered = sorted(self._batches.values(), key=lambda batch: (batch.created_at, str(batch.id)), reverse=True)
        if before is not None:
            cursor = next((index for index, batch in enumerate(ordered) if batch.id == before), None)
            if cursor is None:
                raise BatchValidationError("invalid_cursor", "before must identify a visible batch.")
            ordered = ordered[cursor + 1 :]
        selected = ordered[:limit]
        next_before = str(selected[-1].id) if len(ordered) > limit and selected else None
        return ManualDeleteBatchListResponse(
            batches=[self._to_response(batch) for batch in selected], next_before=next_before
        )

    async def _lookup_idempotency(self, key: UUID, canonical_request: str) -> DeletionBatchRecord | None:
        ledger = await asyncio.to_thread(self._repository.lookup_destructive_idempotency, key)
        if ledger is None:
            return None
        return await self._resolve_existing_ledger(ledger, canonical_request)

    async def _resolve_existing_ledger(
        self, ledger: DestructiveIdempotencyRecord, canonical_request: str
    ) -> DeletionBatchRecord:
        if ledger.request_kind != "batch" or ledger.canonical_request_json != canonical_request:
            raise DeletionJobIdempotencyConflictError(
                "The idempotency_key was already used for a different confirmed deletion request."
            )
        batch = self._batches.get(ledger.resource_id)
        if batch is None:
            batch = await asyncio.to_thread(self._repository.load_batch, ledger.resource_id)
        if batch is None:
            raise DeletionJobIdempotencyRetiredError(
                "This idempotency_key belongs to deletion history that is no longer available."
            )
        self._batches[batch.id] = batch
        return batch

    async def _preview_child(
        self, request: ManualDeleteRequest, mutation_identity: str
    ) -> ManualDeleteBatchChildPreviewResponse:
        preview, _ = await self._resolve_preview_child(request, mutation_identity)
        return preview

    async def _resolve_preview_child(
        self, request: ManualDeleteRequest, mutation_identity: str
    ) -> tuple[ManualDeleteBatchChildPreviewResponse, MediaDeletionEvent | None]:
        """Resolve one child once and retain that exact event for a verified run."""

        child_display_name = request.display_name or request.item_type.value
        try:
            event = await self._resolver(request)
        except asyncio.CancelledError:
            raise
        except ManualDeletionResolutionError as exc:
            _logger.warning("Batch child preflight failed for a canonical item identity")
            return (
                blocked_preview(
                    mutation_identity,
                    child_display_name,
                    getattr(exc, "code", "resolution_failed"),
                    "The item could not be resolved safely.",
                ),
                None,
            )
        except Exception:  # noqa: BLE001 - downstream resolution must fail closed per child
            _logger.warning("Batch child resolution failed without recording downstream details")
            return (
                blocked_preview(
                    mutation_identity, child_display_name, "resolution_failed", "The item could not be resolved safely."
                ),
                None,
            )
        try:
            child_display_name = request.display_name or event.name or request.item_type.value
            plan = (await self._previewer(request, event)).model_copy(update={"display_name": child_display_name})
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - downstream input must fail closed
            _logger.warning("Batch child preflight failed for a canonical item identity")
            return (
                blocked_preview(
                    mutation_identity,
                    child_display_name,
                    "preflight_failed",
                    "The item could not be preflighted safely.",
                ),
                event,
            )
        blocked_code = plan_blocked_code(plan)
        if blocked_code is not None:
            return (
                blocked_preview(
                    mutation_identity,
                    child_display_name,
                    blocked_code,
                    "The item has a safety block and will not be mutated in this batch.",
                    plan=plan,
                ),
                event,
            )
        return (
            ManualDeleteBatchChildPreviewResponse(
                mutation_identity=mutation_identity,
                display_name=child_display_name,
                status=BatchChildPreviewStatus.READY,
                plan_hash=event_bound_plan_hash(plan, event),
                plan=plan,
            ),
            event,
        )

    async def _worker_loop(self) -> None:
        while True:
            batch_id = await self._queue.get()
            self._scheduled.discard(batch_id)
            batch: DeletionBatchRecord | None = None
            try:
                batch = self._batches.get(batch_id)
                if batch is not None and batch.status in self._ACTIVE:
                    await self._run_batch(batch)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - do not let one malformed parent kill the worker
                _logger.warning("Batch worker isolated an unexpected parent failure without logging downstream details")
                if batch is not None:
                    self._fail_unexpected_batch(batch)
            finally:
                self._queue.task_done()

    async def _run_batch(self, batch: DeletionBatchRecord) -> None:
        batch.status = ManualDeleteBatchStatus.RUNNING
        batch.started_at = batch.started_at or datetime.now(UTC)
        batch.message = "Executing safe child plans sequentially."
        self._repository.save_batch(batch)
        for child in batch.children:
            if child.status is not BatchChildStatus.QUEUED:
                continue
            child.status = BatchChildStatus.RUNNING
            child.started_at = datetime.now(UTC)
            child.message = "Refreshing the confirmed child plan before execution."
            self._repository.save_batch(batch)
            try:
                async with self._execution_lock:
                    fresh, verified_event = await self._resolve_preview_child(child.request, child.mutation_identity)
                    if (
                        fresh.status is not BatchChildPreviewStatus.READY
                        or fresh.plan_hash != child.plan_hash
                        or verified_event is None
                    ):
                        child.status = BatchChildStatus.BLOCKED
                        child.blocked_code = fresh.blocked_code or "plan_changed"
                        child.message = (
                            "The library item changed; no mutation was made."
                            if child.blocked_code == "library_item_changed"
                            else "The child plan changed or is no longer safe; no mutation was made."
                        )
                        child.completed_at = datetime.now(UTC)
                        self._repository.save_batch(batch)
                        continue
                    result = await self._runner(child.request, verified_event, ignore_progress)
            except asyncio.CancelledError:
                raise
            except DeletionExecutionFailure:
                child.status = BatchChildStatus.FAILED
                child.error_code = "execution_failed"
                child.error_message = "The downstream deletion command failed."
                child.message = "The child failed; later safe children will continue."
                child.completed_at = datetime.now(UTC)
            except Exception:  # noqa: BLE001 - do not persist downstream exception text
                _logger.warning("Batch child execution failed without recording downstream details")
                child.status = BatchChildStatus.FAILED
                child.error_code = "execution_failed"
                child.error_message = "The downstream deletion command failed."
                child.message = "The child failed; later safe children will continue."
                child.completed_at = datetime.now(UTC)
            else:
                child.result = with_display_name(result, child.display_name)
                child.completed_at = datetime.now(UTC)
                if result.status is OverallStatus.PARTIAL_FAILURE:
                    child.status = BatchChildStatus.FAILED
                    child.error_code = "partial_result"
                    child.error_message = "The child reported a partial downstream outcome."
                    child.message = "The child was only partially completed; later safe children will continue."
                elif plan_blocked_code(result) is not None:
                    child.status = BatchChildStatus.FAILED
                    child.error_code = "unsafe_result"
                    child.error_message = "The child reported a safety-attention outcome."
                    child.message = "The child was not treated as completed; later safe children will continue."
                else:
                    child.status = BatchChildStatus.COMPLETED
                    child.message = "Child deletion completed."
            self._repository.save_batch(batch)
        self._finalize(batch)

    def _fail_unexpected_batch(self, batch: DeletionBatchRecord) -> None:
        for child in batch.children:
            if child.status is BatchChildStatus.RUNNING:
                child.status = BatchChildStatus.FAILED
                child.error_code = "interrupted_unknown"
                child.error_message = "The child may have reached a downstream service; its outcome is unknown."
                child.message = "Child was not retried because its external outcome is unknown."
                child.completed_at = datetime.now(UTC)
            elif child.status is BatchChildStatus.QUEUED:
                child.status = BatchChildStatus.CANCELLED
                child.message = "The batch stopped before this child started."
                child.completed_at = datetime.now(UTC)
        batch.status = ManualDeleteBatchStatus.FAILED
        batch.message = "The batch stopped after an internal error; no queued child was retried."
        batch.error_code = "batch_worker_failed"
        batch.error_message = "The batch worker stopped unexpectedly."
        batch.completed_at = datetime.now(UTC)
        try:
            self._repository.save_batch(batch)
        except Exception:  # noqa: BLE001 - cannot safely recover a failed SQLite write in this process
            _logger.warning("Could not persist isolated batch-worker failure")

    def _finalize(self, batch: DeletionBatchRecord) -> None:
        completed = sum(child.status is BatchChildStatus.COMPLETED for child in batch.children)
        terminal = all(child.status in self._CHILD_TERMINAL for child in batch.children)
        if not terminal:
            return
        if completed == len(batch.children):
            batch.status = ManualDeleteBatchStatus.COMPLETED
            batch.message = "All child deletions completed."
        elif completed:
            batch.status = ManualDeleteBatchStatus.PARTIAL
            batch.message = "Some child deletions completed; blocked or failed children remain visible."
        else:
            batch.status = ManualDeleteBatchStatus.FAILED
            batch.message = "No child deletion completed safely."
        batch.completed_at = datetime.now(UTC)
        self._repository.save_batch(batch)
        self._prune_history()

    def _schedule(self, batch: DeletionBatchRecord) -> None:
        if batch.id not in self._scheduled:
            self._scheduled.add(batch.id)
            self._queue.put_nowait(batch.id)

    def _recover_interrupted(self) -> None:
        for batch in list(self._batches.values()):
            changed = False
            for child in batch.children:
                if child.status is BatchChildStatus.RUNNING:
                    child.status = BatchChildStatus.FAILED
                    child.error_code = "interrupted_unknown"
                    child.error_message = (
                        "The previous process stopped after this child began; its external outcome is unknown."
                    )
                    child.message = "Child was not retried because its external outcome is unknown."
                    child.completed_at = datetime.now(UTC)
                    changed = True
            if batch.status in self._ACTIVE and any(
                child.status is BatchChildStatus.QUEUED for child in batch.children
            ):
                batch.status = ManualDeleteBatchStatus.QUEUED
                batch.message = "Process restart detected; untouched queued children will resume."
                changed = True
            if changed:
                self._repository.save_batch(batch)
            if batch.status in self._ACTIVE:
                self._finalize(batch)

    def _prune_history(self, *, reserve: int = 0) -> None:
        terminal = sorted(
            (batch for batch in self._batches.values() if batch.status not in self._ACTIVE),
            key=lambda batch: (batch.created_at, str(batch.id)),
        )
        for batch in terminal[: max(0, len(terminal) - self._history_limit + reserve)]:
            self._repository.delete_batch(batch.id)
            self._batches.pop(batch.id, None)

    @staticmethod
    def _to_response(batch: DeletionBatchRecord) -> ManualDeleteBatchResponse:
        counts = {status: sum(child.status is status for child in batch.children) for status in BatchChildStatus}
        return ManualDeleteBatchResponse(
            id=batch.id,
            status=batch.status,
            message=redact_sensitive_text(batch.message),
            created_at=batch.created_at,
            started_at=batch.started_at,
            completed_at=batch.completed_at,
            error_code=batch.error_code,
            error_message=redact_sensitive_text(batch.error_message) if batch.error_message else None,
            total_count=len(batch.children),
            queued_count=counts[BatchChildStatus.QUEUED],
            running_count=counts[BatchChildStatus.RUNNING],
            completed_count=counts[BatchChildStatus.COMPLETED],
            blocked_count=counts[BatchChildStatus.BLOCKED],
            failed_count=counts[BatchChildStatus.FAILED],
            cancelled_count=counts[BatchChildStatus.CANCELLED],
            children=[
                ManualDeleteBatchChildResponse(
                    id=child.id,
                    mutation_identity=child.mutation_identity,
                    display_name=child.display_name,
                    status=child.status,
                    message=redact_sensitive_text(child.message),
                    blocked_code=child.blocked_code,
                    error_code=child.error_code,
                    error_message=redact_sensitive_text(child.error_message) if child.error_message else None,
                    preflight=child.preflight,
                    result=child.result,
                    started_at=child.started_at,
                    completed_at=child.completed_at,
                )
                for child in batch.children
            ],
        )


def canonical_children(children: Sequence[ManualDeleteRequest]) -> list[tuple[str, ManualDeleteRequest]]:
    if not 1 <= len(children) <= 50:
        raise BatchValidationError("invalid_batch_size", "A batch must contain between 1 and 50 items.")
    if any(child.confirmed_plan_hash is not None or child.idempotency_key is not None for child in children):
        raise BatchValidationError(
            "nested_confirmation_forbidden",
            "Batch children must not include confirmed_plan_hash or idempotency_key.",
        )
    pairs = [(mutation_identity(child), batch_child_request(child)) for child in children]
    overlap_identities = [destructive_overlap_identity(child) for _, child in pairs]
    if len(set(overlap_identities)) != len(overlap_identities):
        raise BatchValidationError(
            "duplicate_mutation_identity", "A batch cannot include the same destructive scope more than once."
        )
    series_scopes: dict[int, set[str]] = {}
    for _, child in pairs:
        if child.sonarr_series_id is not None and child.item_type in {ItemType.SERIES, ItemType.SEASON}:
            scope = "series" if child.item_type is ItemType.SERIES else f"season:{child.season_number}"
            series_scopes.setdefault(child.sonarr_series_id, set()).add(scope)
    if any("series" in scopes and len(scopes) > 1 for scopes in series_scopes.values()):
        raise BatchValidationError(
            "overlapping_mutation_scope",
            "A whole-series child cannot be combined with a season child from the same series.",
        )
    return sorted(pairs, key=lambda pair: pair[0])


def batch_child_request(request: ManualDeleteRequest) -> ManualDeleteRequest:
    return request.model_copy(update={"confirmed_plan_hash": None, "idempotency_key": None})


def mutation_identity(request: ManualDeleteRequest) -> str:
    return json.dumps(
        {
            "item_type": request.item_type.value,
            "radarr_movie_id": request.radarr_movie_id,
            "sonarr_series_id": request.sonarr_series_id,
            "season_number": request.season_number,
            "jellyfin_item_id": request.jellyfin_item_id,
            "jellyfin_only": request.jellyfin_only,
            "library_resource_id": request.library_resource_id,
        },
        separators=(",", ":"),
        sort_keys=True,
    )


def destructive_overlap_identity(request: ManualDeleteRequest) -> str:
    if request.radarr_movie_id is not None:
        return f"movie:{request.radarr_movie_id}"
    if request.sonarr_series_id is not None:
        if request.item_type is ItemType.SERIES:
            return f"series:{request.sonarr_series_id}"
        if request.item_type is ItemType.SEASON:
            return f"season:{request.sonarr_series_id}:{request.season_number}"
    if request.library_resource_id is not None:
        return f"resource:{request.library_resource_id}"
    if request.jellyfin_only and request.jellyfin_item_id is not None:
        return f"jellyfin-movie:{request.jellyfin_item_id.strip().casefold()}"
    return mutation_identity(request)


def physical_overlap_indexes(
    resolved: Sequence[
        tuple[
            str,
            ManualDeleteRequest,
            ManualDeleteBatchChildPreviewResponse,
            MediaDeletionEvent | None,
        ]
    ],
) -> set[int]:
    """Find invalid or intersecting physical scopes without exposing raw paths."""

    blocked: set[int] = set()
    scopes: list[tuple[str, ...] | None] = []
    for index, (_identity, _request, preview, event) in enumerate(resolved):
        if preview.status is not BatchChildPreviewStatus.READY or event is None:
            scopes.append(None)
            continue
        scope = _physical_mutation_scope(event)
        scopes.append(scope)
        if scope == ():
            blocked.add(index)

    for left in range(len(resolved)):
        left_scope = scopes[left]
        if not left_scope:
            continue
        for right in range(left + 1, len(resolved)):
            right_scope = scopes[right]
            if not right_scope or _same_series_season_parent(resolved[left][1], resolved[right][1]):
                continue
            if _scope_is_ancestor(left_scope, right_scope) or _scope_is_ancestor(right_scope, left_scope):
                blocked.update((left, right))
    return blocked


def event_bound_plan_hash(plan: ProcessingResultResponse, event: MediaDeletionEvent) -> str:
    """Bind confirmation to a privacy-safe digest of the resolved physical scope."""

    scope = _physical_mutation_scope(event)
    scope_digest = hashlib.sha256("\x00".join(scope).encode()).hexdigest() if scope else None
    material = {"plan_hash": plan_hash(plan), "physical_scope": scope_digest}
    return hashlib.sha256(json.dumps(material, separators=(",", ":"), sort_keys=True).encode()).hexdigest()


def _physical_mutation_scope(event: MediaDeletionEvent) -> tuple[str, ...]:
    path = event.fingerprint.path
    if path is None:
        return ()
    if not isinstance(path, str) or not path.strip() or any(ord(character) < 32 for character in path):
        return ()
    segments = path.replace("\\", "/").strip().split("/")
    if any(segment == ".." for segment in segments):
        return ()
    normalized = tuple(segment.casefold() for segment in segments if segment not in {"", "."})
    return normalized or ()


def _scope_is_ancestor(parent: tuple[str, ...], child: tuple[str, ...]) -> bool:
    return len(parent) <= len(child) and child[: len(parent)] == parent


def _same_series_season_parent(left: ManualDeleteRequest, right: ManualDeleteRequest) -> bool:
    if left.item_type is not ItemType.SEASON or right.item_type is not ItemType.SEASON:
        return False
    if left.library_resource_id is not None or right.library_resource_id is not None:
        return left.library_resource_id is not None and left.library_resource_id == right.library_resource_id
    return left.sonarr_series_id is not None and left.sonarr_series_id == right.sonarr_series_id


def canonical_batch_request(children: Sequence[ManualDeleteRequest], *, confirmed_batch_hash: str | None = None) -> str:
    payload: dict[str, object] = {
        "children": [
            {
                "mutation_identity": identity,
                "request": {
                    "item_type": request.item_type.value,
                    "radarr_movie_id": request.radarr_movie_id,
                    "sonarr_series_id": request.sonarr_series_id,
                    "season_number": request.season_number,
                    "jellyfin_item_id": request.jellyfin_item_id,
                    "jellyfin_only": request.jellyfin_only,
                    "library_resource_id": request.library_resource_id,
                },
            }
            for identity, request in canonical_children(children)
        ]
    }
    if confirmed_batch_hash is not None:
        payload["confirmed_batch_hash"] = confirmed_batch_hash
    return json.dumps(payload, separators=(",", ":"), sort_keys=True)


def preview_response(children: list[ManualDeleteBatchChildPreviewResponse]) -> ManualDeleteBatchPreviewResponse:
    material = [
        {
            "mutation_identity": child.mutation_identity,
            "state": child.status.value,
            "plan_hash": child.plan_hash or blocked_artifact(child),
        }
        for child in children
    ]
    batch_hash = hashlib.sha256(json.dumps(material, separators=(",", ":"), sort_keys=True).encode()).hexdigest()
    return ManualDeleteBatchPreviewResponse(
        generated_at=datetime.now(UTC),
        batch_hash=batch_hash,
        children=children,
        ready_count=sum(child.status is BatchChildPreviewStatus.READY for child in children),
        blocked_count=sum(child.status is BatchChildPreviewStatus.BLOCKED for child in children),
    )


def blocked_preview(
    identity: str, value: str, code: str, message: str, *, plan: ProcessingResultResponse | None = None
) -> ManualDeleteBatchChildPreviewResponse:
    return ManualDeleteBatchChildPreviewResponse(
        mutation_identity=identity,
        display_name=value,
        status=BatchChildPreviewStatus.BLOCKED,
        plan_hash=plan_hash(plan) if plan is not None else None,
        plan=plan,
        blocked_code=code,
        blocked_message=message,
    )


def blocked_artifact(child: ManualDeleteBatchChildPreviewResponse) -> str:
    return hashlib.sha256(
        json.dumps(
            {"mutation_identity": child.mutation_identity, "blocked_code": child.blocked_code},
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
    ).hexdigest()


def plan_blocked_code(plan: ProcessingResultResponse) -> str | None:
    if plan.status in {OverallStatus.PARTIAL_FAILURE, OverallStatus.IGNORED}:
        return "unsafe_plan"
    if any(
        action.status in {ActionStatus.IGNORED, ActionStatus.FAILED}
        or (action.status is ActionStatus.SKIPPED and action.reason not in _SAFE_RETAINED_SKIP_REASONS)
        for action in plan.actions
    ):
        return "unsafe_plan"
    return None


def batch_from_preview(
    preview: ManualDeleteBatchPreviewResponse,
    canonical_request: str,
    confirmed_hash: str,
    source_children: Sequence[ManualDeleteRequest],
) -> DeletionBatchRecord:
    requests_by_identity = dict(canonical_children(source_children))
    children: list[DeletionBatchChildRecord] = []
    for position, preview_child in enumerate(preview.children):
        request = requests_by_identity[preview_child.mutation_identity]
        children.append(
            DeletionBatchChildRecord(
                id=uuid4(),
                position=position,
                mutation_identity=preview_child.mutation_identity,
                request=request,
                display_name=preview_child.display_name,
                status=BatchChildStatus.QUEUED
                if preview_child.status is BatchChildPreviewStatus.READY
                else BatchChildStatus.BLOCKED,
                message="Preflight saved. Waiting for earlier batch children."
                if preview_child.status is BatchChildPreviewStatus.READY
                else (preview_child.blocked_message or "The child was blocked during preflight."),
                preflight=preview_child.plan,
                plan_hash=preview_child.plan_hash,
                blocked_code=preview_child.blocked_code,
            )
        )
    return DeletionBatchRecord(
        id=uuid4(),
        canonical_request=canonical_request,
        confirmed_batch_hash=confirmed_hash,
        status=ManualDeleteBatchStatus.QUEUED,
        message="Batch preflight saved. Waiting for safe child execution.",
        created_at=datetime.now(UTC),
        children=children,
    )


def with_display_name(plan: ProcessingResultResponse, value: str) -> ProcessingResultResponse:
    return plan.model_copy(update={"display_name": value})


def ignore_progress(*_: object) -> None:
    return None
