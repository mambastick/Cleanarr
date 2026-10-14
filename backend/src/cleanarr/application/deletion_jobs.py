"""Application service for durable, hash-bound manual deletion jobs."""

from __future__ import annotations

import asyncio
import contextlib
import copy
import hashlib
import json
import logging
from collections import deque
from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from cleanarr.application.deletion_models import (
    ActionResultResponse,
    ManualDeleteJobPhase,
    ManualDeleteJobResponse,
    ManualDeleteJobStatus,
    ManualDeletePreviewResponse,
    ManualDeleteRequest,
    ProcessingResultResponse,
)
from cleanarr.application.deletion_persistence import (
    DeletionJobRecord,
    DeletionRepositoryPort,
    DestructiveIdempotencyRecord,
    display_name_fallback,
)
from cleanarr.domain import ActionStatus, FailureReason, MediaDeletionEvent, OverallStatus
from cleanarr.redaction import redact_sensitive_text

DeletionProgressReporter = Callable[[ManualDeleteJobPhase, int, str, str | None], None]
ManualDeleteResolver = Callable[[ManualDeleteRequest], Awaitable[MediaDeletionEvent]]
DeletionPreviewer = Callable[[ManualDeleteRequest, MediaDeletionEvent], Awaitable[ProcessingResultResponse]]
ManualDeleteRunner = Callable[
    [ManualDeleteRequest, MediaDeletionEvent, DeletionProgressReporter],
    Awaitable[ProcessingResultResponse],
]


class _OrderedJobWriter:
    """Serialize async progress snapshots through one worker-thread writer."""

    def __init__(self, repository: DeletionRepositoryPort) -> None:
        self._repository = repository
        self._pending: deque[DeletionJobRecord] = deque()
        self._task: asyncio.Task[None] | None = None
        self._failure: BaseException | None = None

    def submit(self, job: DeletionJobRecord) -> None:
        snapshot = copy.deepcopy(job)
        if self._pending and self._pending[-1].phase is snapshot.phase:
            self._pending[-1] = snapshot
        else:
            self._pending.append(snapshot)
        if self._task is not None and self._task.done() and self._failure is None:
            try:
                self._task.result()
            except BaseException as exc:  # noqa: BLE001 - preserve the first writer failure for flush()
                self._failure = exc
        if self._failure is None and (self._task is None or self._task.done()):
            self._task = asyncio.create_task(self._drain(), name="cleanarr-manual-deletion-progress-writer")

    async def _drain(self) -> None:
        while self._pending:
            snapshot = self._pending.popleft()
            await asyncio.to_thread(self._repository.save_job, snapshot)

    async def flush(self) -> None:
        if self._failure is not None:
            raise self._failure
        task = self._task
        if task is not None:
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                # Cancelling the caller must not cancel a worker-thread write.
                # The owning job drains the still-running writer in its finally block.
                if task.cancelled() and self._failure is None:
                    self._failure = asyncio.CancelledError()
                raise
            except BaseException as exc:  # noqa: BLE001 - expose persistence failure to the job worker
                if self._failure is None:
                    self._failure = exc
                raise
        if self._failure is not None:
            raise self._failure


class _JobProgressReporter:
    """Synchronous callback facade with an awaitable ordered flush."""

    def __init__(self, job: DeletionJobRecord, writer: _OrderedJobWriter) -> None:
        self._job = job
        self._writer = writer

    def __call__(self, phase: ManualDeleteJobPhase, progress_percent: int, message: str, item_name: str | None) -> None:
        self._job.status = ManualDeleteJobStatus.RUNNING
        self._job.phase = phase
        self._job.progress_percent = max(self._job.progress_percent, min(progress_percent, 99))
        self._job.message = message
        if item_name is not None:
            self._job.item_name = item_name
        self._writer.submit(self._job)

    async def flush(self) -> None:
        await self._writer.flush()


async def _flush_writer_before_cancellation(writer: _OrderedJobWriter) -> None:
    """Drain an in-flight SQLite write before the owning job releases its lock."""

    flush_task = asyncio.create_task(writer.flush(), name="cleanarr-manual-deletion-progress-flush")
    try:
        await asyncio.shield(flush_task)
    except asyncio.CancelledError:
        # ``to_thread`` cannot cancel an SQLite call already running in the
        # executor.  Keep awaiting the writer so its close/commit boundary is
        # reached before the job's execution lock is released.
        await asyncio.shield(flush_task)
        raise


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
_SAFE_RETAINED_SKIP_REASON_VALUES = frozenset(reason.value for reason in _SAFE_RETAINED_SKIP_REASONS)
_VOLATILE_PLAN_ACTION_DETAILS = frozenset({"ratio", "seeding_time_seconds"})
_TRANSIENT_PREFLIGHT_REASONS = frozenset(
    {
        FailureReason.DOWNSTREAM_ERROR.value,
        FailureReason.AUTHENTICATION_FAILED.value,
    }
)
_READ_PREFLIGHT_ACTIONS = frozenset(
    {
        "process_event",
        "resolve_movie",
        "resolve_series",
        "resolve_media",
        "resolve_request",
        "verify_download_ownership",
        "verify_source",
        "verify_jellyfin_binding",
    }
)


class DeletionJobNotFoundError(LookupError):
    """Raised when a requested deletion job is not persisted."""


class DeletionJobActiveError(RuntimeError):
    """Raised when attempting to dismiss a queued, running, or retrying job."""


class DeletionPreflightError(RuntimeError):
    """Raised when a queued deletion was not confirmed against its exact plan."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class DeletionJobIdempotencyConflictError(RuntimeError):
    """Raised when a caller reuses a key for a different destructive request."""


class DeletionJobIdempotencyRequiredError(RuntimeError):
    """Raised when durable job submission omits its client-generated UUID."""


class DeletionJobIdempotencyRetiredError(RuntimeError):
    """Raised when a durable idempotency tombstone outlives visible history."""


class ManualDeletionJobService:
    """Persist manual jobs, resume interrupted work, and retry partial failures."""

    _ACTIVE_STATUSES = {
        ManualDeleteJobStatus.QUEUED,
        ManualDeleteJobStatus.RUNNING,
        ManualDeleteJobStatus.RETRY_WAIT,
    }

    def __init__(
        self,
        resolver: ManualDeleteResolver,
        previewer: DeletionPreviewer,
        runner: ManualDeleteRunner,
        *,
        repository: DeletionRepositoryPort,
        history_limit: int = 50,
        max_attempts: int = 3,
        retry_delays_seconds: Sequence[float] = (5.0, 30.0),
        execution_lock: asyncio.Lock | None = None,
    ) -> None:
        self._resolver = resolver
        self._previewer = previewer
        self._runner = runner
        self._repository = repository
        self._history_limit = history_limit
        self._max_attempts = max(1, max_attempts)
        self._retry_delays_seconds = tuple(max(0.0, delay) for delay in retry_delays_seconds) or (0.0,)
        self._execution_lock = execution_lock or asyncio.Lock()
        self._jobs: dict[UUID, DeletionJobRecord] = {}
        self._jobs_by_idempotency_key: dict[UUID, DeletionJobRecord] = {}
        self._queue: asyncio.Queue[UUID] = asyncio.Queue()
        self._scheduled: set[UUID] = set()
        self._delayed_tasks: dict[UUID, asyncio.Task[None]] = {}
        self._worker_task: asyncio.Task[None] | None = None
        self._initialized = False
        self._start_lock = asyncio.Lock()
        self._dismiss_lock = asyncio.Lock()
        self._settled: dict[UUID, asyncio.Event] = {}

    async def start(self) -> None:
        """Initialize persistence and start the queue worker."""

        async with self._start_lock:
            if not self._initialized:
                await asyncio.to_thread(self._repository.initialize)
                loaded_jobs = await asyncio.to_thread(self._repository.load_jobs)
                self._jobs = {job.id: job for job in loaded_jobs}
                self._jobs_by_idempotency_key = {
                    job.idempotency_key: job for job in loaded_jobs if job.idempotency_key is not None
                }
                await self._recover_interrupted_jobs()
                await self._prune_history()
                self._initialized = True
            if self._worker_task is None or self._worker_task.done():
                self._worker_task = asyncio.create_task(
                    self._worker_loop(),
                    name="cleanarr-manual-deletion-worker",
                )
            for job in self._jobs.values():
                if job.status in self._ACTIVE_STATUSES:
                    self._schedule_job(job)

    async def stop(self) -> None:
        """Stop workers while leaving recoverable state in SQLite."""

        worker = self._worker_task
        self._worker_task = None
        delayed_tasks = tuple(self._delayed_tasks.values())
        for task in delayed_tasks:
            task.cancel()
        for task in delayed_tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._delayed_tasks.clear()
        if worker is not None:
            worker.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await worker
        self._scheduled.clear()
        self._queue = asyncio.Queue()

    async def preview(self, payload: ManualDeleteRequest) -> ManualDeletePreviewResponse:
        """Resolve a media entity and return a mutation-free plan."""

        await self.start()
        event = await self._resolver(payload)
        plan = await self._previewer(payload, event)
        return ManualDeletePreviewResponse(
            generated_at=datetime.now(UTC),
            plan_hash=plan_hash(plan),
            plan=with_display_name(plan, display_name(payload, event)),
        )

    async def submit(self, payload: ManualDeleteRequest) -> ManualDeleteJobResponse:
        """Resolve, preflight, persist, and queue one deletion."""

        await self.start()
        if payload.idempotency_key is None:
            raise DeletionJobIdempotencyRequiredError("A client-generated UUID idempotency_key is required.")
        existing = self._jobs_by_idempotency_key.get(payload.idempotency_key)
        if existing is not None:
            return self._return_or_reject_idempotency_match(existing, payload)
        canonical = canonical_submission_request(payload)
        ledger = await asyncio.to_thread(self._repository.lookup_destructive_idempotency, payload.idempotency_key)
        if ledger is not None:
            return await self._resolve_existing_ledger(ledger, payload, canonical)

        event = await self._resolver(payload)
        preflight = with_display_name(await self._previewer(payload, event), display_name(payload, event))
        validate_plan_confirmation(payload, preflight)
        await self._prune_history(reserve=1)
        job = DeletionJobRecord(
            id=uuid4(),
            request=payload,
            event=event,
            preflight=preflight,
            status=ManualDeleteJobStatus.QUEUED,
            phase=ManualDeleteJobPhase.QUEUED,
            progress_percent=0,
            message="Preflight saved. Waiting for the current background task to finish.",
            created_at=datetime.now(UTC),
            max_attempts=self._max_attempts,
            item_name=event.name,
            idempotency_key=payload.idempotency_key,
            display_name=display_name(payload, event),
        )
        existing_ledger = await asyncio.to_thread(
            self._repository.create_job_with_idempotency,
            job,
            canonical_request=canonical,
            original_request=job.request.model_dump_json(),
        )
        if existing_ledger is not None:
            return await self._resolve_existing_ledger(existing_ledger, payload, canonical)

        self._jobs[job.id] = job
        self._jobs_by_idempotency_key[payload.idempotency_key] = job
        self._schedule_job(job)
        return self._to_response(job)

    async def _resolve_existing_ledger(
        self,
        ledger: DestructiveIdempotencyRecord,
        payload: ManualDeleteRequest,
        canonical: str,
    ) -> ManualDeleteJobResponse:
        if ledger.request_kind != "single" or not ledger_request_matches(ledger, canonical):
            raise DeletionJobIdempotencyConflictError(
                "The idempotency_key was already used for a different confirmed deletion request."
            )
        job = self._jobs.get(ledger.resource_id)
        if job is None:
            job = await asyncio.to_thread(self._repository.load_job, ledger.resource_id)
        if job is None:
            raise DeletionJobIdempotencyRetiredError(
                "This idempotency_key belongs to deletion history that is no longer available."
            )
        self._jobs[job.id] = job
        if job.idempotency_key is not None:
            self._jobs_by_idempotency_key[job.idempotency_key] = job
        return self._return_or_reject_idempotency_match(job, payload)

    @staticmethod
    def _return_or_reject_idempotency_match(
        job: DeletionJobRecord,
        payload: ManualDeleteRequest,
    ) -> ManualDeleteJobResponse:
        if canonical_submission_request(job.request) != canonical_submission_request(payload):
            raise DeletionJobIdempotencyConflictError(
                "The idempotency_key was already used for a different confirmed deletion request."
            )
        return ManualDeletionJobService._to_response(job)

    def get(self, job_id: UUID) -> ManualDeleteJobResponse:
        job = self._jobs.get(job_id)
        if job is None:
            raise DeletionJobNotFoundError(str(job_id))
        return self._to_response(job)

    def list_jobs(self) -> list[ManualDeleteJobResponse]:
        jobs = sorted(self._jobs.values(), key=lambda job: job.created_at, reverse=True)
        return [self._to_response(job) for job in jobs]

    async def dismiss(self, job_id: UUID) -> None:
        """Dismiss on the event loop only after the worker's final write settles."""
        async with self._dismiss_lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise DeletionJobNotFoundError(str(job_id))
            if job.status in self._ACTIVE_STATUSES:
                raise DeletionJobActiveError(str(job_id))
            settled = self._settled.get(job_id)
            if settled is not None:
                await settled.wait()
            await asyncio.to_thread(self._repository.delete_job, job_id)
            self._jobs.pop(job_id, None)
            self._settled.pop(job_id, None)
            if job.idempotency_key is not None:
                self._jobs_by_idempotency_key.pop(job.idempotency_key, None)

    async def _worker_loop(self) -> None:
        while True:
            job_id = await self._queue.get()
            self._scheduled.discard(job_id)
            settled = asyncio.Event()
            self._settled[job_id] = settled
            try:
                job = self._jobs.get(job_id)
                if job is not None and job.status in self._ACTIVE_STATUSES:
                    await self._run_job(job)
            finally:
                settled.set()
                self._queue.task_done()

    async def _run_job(self, job: DeletionJobRecord) -> None:
        job.status = ManualDeleteJobStatus.RUNNING
        job.phase = ManualDeleteJobPhase.PLANNING
        job.progress_percent = 5
        job.message = "Refreshing the persisted preflight before execution."
        job.started_at = datetime.now(UTC)
        job.completed_at = None
        job.next_retry_at = None
        job.attempt_count += 1
        job.error = None
        job.error_code = None
        # Freeze the planning snapshot before handing it to the worker thread.
        running_snapshot = copy.deepcopy(job)
        running_snapshot.status = ManualDeleteJobStatus.RUNNING
        await asyncio.to_thread(self._repository.save_job, running_snapshot)

        progress_writer = _OrderedJobWriter(self._repository)

        report = _JobProgressReporter(job, progress_writer)

        try:
            async with self._execution_lock:
                verified_event = job.event
                if job.request.library_resource_id is not None or job.request.jellyfin_only:
                    try:
                        verified_event = await self._resolver(job.request)
                    except asyncio.CancelledError:
                        raise
                    except Exception as exc:  # noqa: BLE001 - resource identity must fail closed
                        if getattr(exc, "code", None) == "library_item_changed":
                            self._mark_failed(
                                job,
                                "The library item changed; preview it again before retrying.",
                                error_code="library_item_changed",
                            )
                            await asyncio.to_thread(self._repository.save_job, job)
                            return
                        raise
                current_plan = await self._previewer(job.request, verified_event)
                preflight_code = _preflight_block_code(current_plan)
                if preflight_code == "unsafe_plan":
                    self._mark_failed(
                        job,
                        "The deletion preflight contains safety blockers and cannot be executed safely.",
                        error_code="unsafe_plan",
                    )
                    await asyncio.to_thread(self._repository.save_job, job)
                    return
                if preflight_code == "preflight_failed":
                    await self._retry_or_fail(
                        job,
                        "The deletion preflight could not be verified safely.",
                        error_code="preflight_failed",
                    )
                    return
                if plan_hash(current_plan) != plan_hash(job.preflight):
                    self._mark_failed(
                        job,
                        "The deletion plan changed while the job was queued. Preview it and confirm again.",
                        error_code="plan_changed",
                    )
                    await asyncio.to_thread(self._repository.save_job, job)
                    return
                job.progress_percent = max(job.progress_percent, 20)
                job.message = "Preflight verified; starting cleanup."
                await asyncio.to_thread(self._repository.save_job, job)
                try:
                    result = await self._runner(job.request, verified_event, report)
                finally:
                    await _flush_writer_before_cancellation(progress_writer)
        except asyncio.CancelledError:
            raise
        except DeletionExecutionFailure as exc:
            self._mark_failed(job, exc.message, error_code="execution_failed")
            await asyncio.to_thread(self._repository.save_job, job)
        except Exception as exc:  # noqa: BLE001
            _logger.exception("Manual deletion background job %s attempt %s failed", job.id, job.attempt_count)
            message = str(exc) or type(exc).__name__
            if job.phase not in {ManualDeleteJobPhase.PLANNING, ManualDeleteJobPhase.LOCATING}:
                self._mark_failed(job, message, error_code="interrupted_unknown")
                await asyncio.to_thread(self._repository.save_job, job)
            else:
                await self._retry_or_fail(job, message, error_code="preflight_failed")
        else:
            job.result = with_display_name(result, job.display_name or display_name(job.request, job.event))
            if result.status is OverallStatus.PARTIAL_FAILURE:
                failed_action = next(
                    (action for action in result.actions if action.status is ActionStatus.FAILED), None
                )
                original_error = (
                    str(failed_action.details.get("error") or failed_action.message)
                    if failed_action is not None
                    else "The deletion finished with downstream errors."
                )
                retention_failed = any(
                    action.status is ActionStatus.FAILED and action.action == "record_retention"
                    for action in result.actions
                )
                if any(action.status is ActionStatus.DELETED for action in result.actions):
                    self._mark_failed(job, original_error, error_code="partial_result_not_retryable")
                    job.message = "Partial cleanup completed; automatic replay is blocked."
                    await asyncio.to_thread(self._repository.save_job, job)
                elif retention_failed:
                    self._mark_failed(job, original_error, error_code="execution_failed")
                    job.message = "Durable retention recording failed; dependent cleanup was blocked."
                    await asyncio.to_thread(self._repository.save_job, job)
                elif _execution_result_block_code(result) == "unsafe_result":
                    self._mark_failed(job, original_error, error_code="unsafe_plan")
                    job.message = "Partial cleanup contained safety blockers; automatic replay is blocked."
                    await asyncio.to_thread(self._repository.save_job, job)
                else:
                    await self._retry_or_fail(job, original_error, error_code="execution_failed")
                return
            job.status = ManualDeleteJobStatus.COMPLETED
            job.phase = ManualDeleteJobPhase.COMPLETED
            job.progress_percent = 100
            job.message = "Deletion completed."
            job.completed_at = datetime.now(UTC)
            job.error = None
            job.error_code = None
            await asyncio.to_thread(self._repository.save_job, job)

    async def _retry_or_fail(self, job: DeletionJobRecord, message: str, *, error_code: str) -> None:
        message = redact_sensitive_text(message)
        job.error = message
        job.error_code = error_code
        if job.attempt_count >= job.max_attempts:
            self._mark_failed(job, message, error_code=error_code)
            await asyncio.to_thread(self._repository.save_job, job)
            return
        delay_index = min(job.attempt_count - 1, len(self._retry_delays_seconds) - 1)
        delay_seconds = self._retry_delays_seconds[delay_index]
        job.status = ManualDeleteJobStatus.RETRY_WAIT
        job.phase = ManualDeleteJobPhase.RETRYING
        job.progress_percent = 0
        job.next_retry_at = datetime.now(UTC) + timedelta(seconds=delay_seconds)
        job.message = (
            f"Attempt {job.attempt_count} of {job.max_attempts} failed; retry scheduled in {delay_seconds:g} seconds."
        )
        await asyncio.to_thread(self._repository.save_job, job)
        self._schedule_job(job)

    @staticmethod
    def _mark_failed(job: DeletionJobRecord, message: str, *, error_code: str) -> None:
        job.status = ManualDeleteJobStatus.FAILED
        job.phase = ManualDeleteJobPhase.FAILED
        job.progress_percent = 100
        job.message = "Deletion failed after all safe attempts."
        job.error = redact_sensitive_text(message)
        job.error_code = error_code
        job.completed_at = datetime.now(UTC)
        job.next_retry_at = None

    def _schedule_job(self, job: DeletionJobRecord) -> None:
        if job.id in self._scheduled:
            return
        self._scheduled.add(job.id)
        delay = 0.0
        if job.next_retry_at is not None:
            delay = max(0.0, (job.next_retry_at - datetime.now(UTC)).total_seconds())
        if delay <= 0:
            self._queue.put_nowait(job.id)
            return

        async def delayed_enqueue() -> None:
            try:
                await asyncio.sleep(delay)
                await self._queue.put(job.id)
            except asyncio.CancelledError:
                self._scheduled.discard(job.id)
                raise
            finally:
                self._delayed_tasks.pop(job.id, None)

        self._delayed_tasks[job.id] = asyncio.create_task(
            delayed_enqueue(),
            name=f"cleanarr-manual-deletion-retry-{job.id}",
        )

    async def _recover_interrupted_jobs(self) -> None:
        now = datetime.now(UTC)
        for job in self._jobs.values():
            if job.status is ManualDeleteJobStatus.RUNNING:
                if job.phase is ManualDeleteJobPhase.PLANNING:
                    if job.attempt_count > 0:
                        job.attempt_count -= 1
                    job.status = ManualDeleteJobStatus.RETRY_WAIT
                    job.phase = ManualDeleteJobPhase.RETRYING
                    job.progress_percent = 0
                    job.next_retry_at = now
                    job.message = "Process restart detected before mutation; rechecking the persisted preflight."
                    job.error = "Previous process stopped before the mutation phase began."
                    job.error_code = "interrupted_before_mutation"
                else:
                    job.status = ManualDeleteJobStatus.FAILED
                    job.phase = ManualDeleteJobPhase.FAILED
                    job.progress_percent = 100
                    job.next_retry_at = None
                    job.completed_at = now
                    job.message = "Deletion was not retried because its downstream outcome is unknown."
                    job.error = (
                        "interrupted_unknown: The previous process stopped after a potentially mutating phase began."
                    )
                    job.error_code = "interrupted_unknown"
                await asyncio.to_thread(self._repository.save_job, job)

    async def _prune_history(self, *, reserve: int = 0) -> None:
        terminal_jobs = sorted(
            (
                job
                for job in self._jobs.values()
                if job.status not in self._ACTIVE_STATUSES
                and (job.id not in self._settled or self._settled[job.id].is_set())
            ),
            key=lambda job: job.created_at,
        )
        overflow = len(terminal_jobs) - self._history_limit + reserve
        for job in terminal_jobs[: max(overflow, 0)]:
            self._jobs.pop(job.id, None)
            self._settled.pop(job.id, None)
            if job.idempotency_key is not None:
                self._jobs_by_idempotency_key.pop(job.idempotency_key, None)
            await asyncio.to_thread(self._repository.delete_job, job.id)

    @staticmethod
    def _to_response(job: DeletionJobRecord) -> ManualDeleteJobResponse:
        return ManualDeleteJobResponse(
            id=job.id,
            item_type=job.request.item_type,
            item_name=job.item_name,
            display_name=job.display_name
            or display_name_fallback(
                item_name=job.item_name,
                result_name=job.result.name if job.result is not None else job.event.name,
                item_type=job.request.item_type,
            ),
            status=job.status,
            phase=job.phase,
            progress_percent=job.progress_percent,
            message=job.message,
            created_at=job.created_at,
            started_at=job.started_at,
            completed_at=job.completed_at,
            next_retry_at=job.next_retry_at,
            attempt_count=job.attempt_count,
            max_attempts=job.max_attempts,
            preflight=job.preflight,
            result=job.result,
            error=job.error,
            error_code=job.error_code,
        )


class DeletionExecutionFailure(RuntimeError):
    """An execution adapter failure that must not be retried by a manual job."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def plan_hash(plan: ProcessingResultResponse) -> str:
    """Hash canonical safety content, excluding presentation and correlation values."""

    material = plan.model_dump(mode="json", exclude={"correlation_id", "display_name"})
    for action in material["actions"]:
        action.pop("message", None)
        for key in _VOLATILE_PLAN_ACTION_DETAILS:
            action["details"].pop(key, None)
    payload = json.dumps(
        material,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return hashlib.sha256(payload).hexdigest()


def validate_plan_confirmation(request: ManualDeleteRequest, plan: ProcessingResultResponse) -> None:
    """Fail closed unless a caller confirmed this exact canonical plan."""

    if (
        _preflight_block_code(plan) is not None
        or plan.status in {OverallStatus.PARTIAL_FAILURE, OverallStatus.IGNORED}
        or any(
            action.status in {ActionStatus.IGNORED, ActionStatus.FAILED}
            or (action.status is ActionStatus.SKIPPED and action.reason not in _SAFE_RETAINED_SKIP_REASONS)
            for action in plan.actions
        )
    ):
        raise DeletionPreflightError(
            "unsafe_plan",
            "The deletion plan contains failures or safety attention items and cannot be confirmed safely.",
        )
    if request.confirmed_plan_hash is None:
        raise DeletionPreflightError("confirmation_required", "Preview the deletion plan before confirming it.")
    if request.confirmed_plan_hash != plan_hash(plan):
        raise DeletionPreflightError(
            "plan_changed",
            "The deletion plan changed after it was reviewed. Preview the current plan and confirm again.",
        )


def _preflight_failure_code(plan: ProcessingResultResponse) -> str | None:
    """Classify failed preflight evidence before treating it as plan drift."""

    if any(
        action.status is ActionStatus.SKIPPED and _action_reason(action) not in _SAFE_RETAINED_SKIP_REASON_VALUES
        for action in plan.actions
    ):
        return "unsafe_plan"
    failed = [action for action in plan.actions if action.status is ActionStatus.FAILED]
    if not failed:
        return None
    if all(
        _action_reason(action) in _TRANSIENT_PREFLIGHT_REASONS and _is_read_preflight_action(action.action)
        for action in failed
    ):
        return "preflight_failed"
    return "unsafe_plan"


def _preflight_block_code(plan: ProcessingResultResponse) -> str | None:
    """Classify a refreshed preflight, including the impossible mutated-plan case."""

    if any(action.status is ActionStatus.DELETED for action in plan.actions):
        return "unsafe_plan"
    return _preflight_failure_code(plan)


def _execution_result_block_code(plan: ProcessingResultResponse) -> str | None:
    """Classify execution evidence separately from mutation-free preflight."""

    if plan.status is OverallStatus.IGNORED or any(
        action.status is ActionStatus.IGNORED
        or (action.status is ActionStatus.SKIPPED and _action_reason(action) not in _SAFE_RETAINED_SKIP_REASON_VALUES)
        or (
            action.status is ActionStatus.FAILED
            and (
                _action_reason(action) not in _TRANSIENT_PREFLIGHT_REASONS
                or not _is_read_preflight_action(action.action)
                or action.action == "process_event"
            )
        )
        for action in plan.actions
    ):
        return "unsafe_result"
    if any(action.status is ActionStatus.FAILED for action in plan.actions):
        return "execution_failed"
    return None


def _action_reason(action: ActionResultResponse) -> str | None:
    reason = action.reason
    return getattr(reason, "value", reason) if reason is not None else None


def _is_read_preflight_action(action: str) -> bool:
    return action in _READ_PREFLIGHT_ACTIONS or action.startswith(("resolve_", "verify_", "read_", "list_"))


def canonical_submission_request(payload: ManualDeleteRequest) -> str:
    """Serialize only mutation-relevant confirmation inputs for idempotency."""

    return json.dumps(
        {
            "item_type": payload.item_type.value,
            "sonarr_series_id": payload.sonarr_series_id,
            "radarr_movie_id": payload.radarr_movie_id,
            "season_number": payload.season_number,
            "jellyfin_item_id": payload.jellyfin_item_id,
            "jellyfin_only": payload.jellyfin_only,
            "library_resource_id": payload.library_resource_id,
            "confirmed_plan_hash": payload.confirmed_plan_hash,
        },
        separators=(",", ":"),
        sort_keys=True,
    )


def ledger_request_matches(ledger: DestructiveIdempotencyRecord, expected: str) -> bool:
    """Compare modern and migrated ledger rows without trusting stored JSON shape."""

    if ledger.canonical_request_json == expected:
        return True
    for value in (ledger.canonical_request_json, ledger.original_request_json):
        try:
            request = ManualDeleteRequest.model_validate_json(value)
        except Exception:  # noqa: BLE001 - corrupt historical rows fail closed
            continue
        if canonical_submission_request(request) == expected:
            return True
    return False


def display_name(payload: ManualDeleteRequest, event: MediaDeletionEvent) -> str:
    return display_name_fallback(item_name=payload.display_name, result_name=event.name, item_type=payload.item_type)


def with_display_name(plan: ProcessingResultResponse, value: str) -> ProcessingResultResponse:
    return plan.model_copy(update={"display_name": value})
