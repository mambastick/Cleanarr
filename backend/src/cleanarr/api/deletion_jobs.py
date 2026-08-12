"""Durable queue for manual deletion jobs started from the web UI."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import logging
import sqlite3
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import HTTPException

from cleanarr.api.library_schemas import (
    ManualDeleteJobPhase,
    ManualDeleteJobResponse,
    ManualDeleteJobStatus,
    ManualDeletePreviewResponse,
    ManualDeleteRequest,
)
from cleanarr.api.schemas import JellyfinWebhookPayload, ProcessingResultResponse
from cleanarr.domain import MediaDeletionEvent, OverallStatus
from cleanarr.infrastructure.database import migrate_database
from cleanarr.redaction import redact_sensitive_text

DeletionProgressReporter = Callable[[ManualDeleteJobPhase, int, str, str | None], None]
ManualDeleteResolver = Callable[[ManualDeleteRequest], Awaitable[MediaDeletionEvent]]
DeletionPreviewer = Callable[[ManualDeleteRequest, MediaDeletionEvent], Awaitable[ProcessingResultResponse]]
ManualDeleteRunner = Callable[
    [ManualDeleteRequest, MediaDeletionEvent, DeletionProgressReporter],
    Awaitable[ProcessingResultResponse],
]

_logger = logging.getLogger("cleanarr")


class DeletionJobNotFoundError(LookupError):
    """Raised when a requested deletion job is not persisted."""


class DeletionJobActiveError(RuntimeError):
    """Raised when attempting to dismiss a queued, running, or retrying job."""


class DeletionPreflightError(RuntimeError):
    """Raised when a queued deletion was not confirmed against its exact plan."""


@dataclass
class _DeletionJob:
    id: UUID
    request: ManualDeleteRequest
    event: MediaDeletionEvent
    preflight: ProcessingResultResponse
    status: ManualDeleteJobStatus
    phase: ManualDeleteJobPhase
    progress_percent: int
    message: str
    created_at: datetime
    max_attempts: int
    item_name: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    next_retry_at: datetime | None = None
    attempt_count: int = 0
    result: ProcessingResultResponse | None = None
    error: str | None = None


class ManualDeletionJobStore:
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
        db_path: Path,
        history_limit: int = 50,
        max_attempts: int = 3,
        retry_delays_seconds: Sequence[float] = (5.0, 30.0),
        execution_lock: asyncio.Lock | None = None,
    ) -> None:
        self._resolver = resolver
        self._previewer = previewer
        self._runner = runner
        self._db_path = db_path
        self._history_limit = history_limit
        self._max_attempts = max(1, max_attempts)
        self._retry_delays_seconds = tuple(max(0.0, delay) for delay in retry_delays_seconds) or (0.0,)
        self._execution_lock = execution_lock or asyncio.Lock()
        self._jobs: dict[UUID, _DeletionJob] = {}
        self._queue: asyncio.Queue[UUID] = asyncio.Queue()
        self._scheduled: set[UUID] = set()
        self._delayed_tasks: dict[UUID, asyncio.Task[None]] = {}
        self._worker_task: asyncio.Task[None] | None = None
        self._initialized = False
        self._start_lock = asyncio.Lock()

    async def start(self) -> None:
        """Initialize persistence and start the queue worker."""

        async with self._start_lock:
            if not self._initialized:
                loaded_jobs = await asyncio.to_thread(self._initialize_and_load_sync)
                self._jobs = {job.id: job for job in loaded_jobs}
                self._recover_interrupted_jobs()
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
        for task in self._delayed_tasks.values():
            task.cancel()
        for task in self._delayed_tasks.values():
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
            plan_hash=_plan_hash(plan),
            plan=plan,
        )

    async def submit(self, payload: ManualDeleteRequest) -> ManualDeleteJobResponse:
        """Resolve, preflight, persist, and queue one deletion."""

        await self.start()
        event = await self._resolver(payload)
        preflight = await self._previewer(payload, event)
        validate_plan_confirmation(payload, preflight)
        self._prune_history()
        job = _DeletionJob(
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
        )
        self._jobs[job.id] = job
        self._save_job_sync(job)
        self._schedule_job(job)
        return self._to_response(job)

    def get(self, job_id: UUID) -> ManualDeleteJobResponse:
        """Return one job snapshot or raise when it no longer exists."""

        job = self._jobs.get(job_id)
        if job is None:
            raise DeletionJobNotFoundError(str(job_id))
        return self._to_response(job)

    def list_jobs(self) -> list[ManualDeleteJobResponse]:
        """Return newest jobs first."""

        jobs = sorted(self._jobs.values(), key=lambda job: job.created_at, reverse=True)
        return [self._to_response(job) for job in jobs]

    def dismiss(self, job_id: UUID) -> None:
        """Remove a terminal job from SQLite and visible history."""

        job = self._jobs.get(job_id)
        if job is None:
            raise DeletionJobNotFoundError(str(job_id))
        if job.status in self._ACTIVE_STATUSES:
            raise DeletionJobActiveError(str(job_id))
        del self._jobs[job_id]
        self._delete_job_sync(job_id)

    async def _worker_loop(self) -> None:
        while True:
            job_id = await self._queue.get()
            self._scheduled.discard(job_id)
            try:
                job = self._jobs.get(job_id)
                if job is not None and job.status in self._ACTIVE_STATUSES:
                    await self._run_job(job)
            finally:
                self._queue.task_done()

    async def _run_job(self, job: _DeletionJob) -> None:
        first_attempt = job.attempt_count == 0
        job.status = ManualDeleteJobStatus.RUNNING
        job.phase = ManualDeleteJobPhase.PLANNING
        job.progress_percent = 5
        job.message = "Refreshing the persisted preflight before execution."
        job.started_at = datetime.now(UTC)
        job.completed_at = None
        job.next_retry_at = None
        job.attempt_count += 1
        job.error = None
        self._save_job_sync(job)

        def report(
            phase: ManualDeleteJobPhase,
            progress_percent: int,
            message: str,
            item_name: str | None,
        ) -> None:
            job.phase = phase
            job.progress_percent = max(job.progress_percent, min(progress_percent, 99))
            job.message = message
            if item_name is not None:
                job.item_name = item_name
            self._save_job_sync(job)

        try:
            async with self._execution_lock:
                current_plan = await self._previewer(job.request, job.event)
                if first_attempt and _plan_hash(current_plan) != _plan_hash(job.preflight):
                    self._mark_failed(
                        job,
                        "The deletion plan changed while the job was queued. Preview it and confirm again.",
                    )
                    self._save_job_sync(job)
                    return
                job.progress_percent = max(job.progress_percent, 20)
                job.message = "Preflight verified; starting cleanup."
                self._save_job_sync(job)
                result = await self._runner(job.request, job.event, report)
        except asyncio.CancelledError:
            raise
        except HTTPException as exc:
            self._mark_failed(job, str(exc.detail))
            self._save_job_sync(job)
        except Exception as exc:  # noqa: BLE001
            _logger.exception("Manual deletion background job %s attempt %s failed", job.id, job.attempt_count)
            self._retry_or_fail(job, str(exc) or type(exc).__name__)
        else:
            job.result = result
            if result.status is OverallStatus.PARTIAL_FAILURE:
                self._retry_or_fail(job, "The deletion finished with retryable downstream errors.")
                return
            job.status = ManualDeleteJobStatus.COMPLETED
            job.phase = ManualDeleteJobPhase.COMPLETED
            job.progress_percent = 100
            job.item_name = result.name
            job.message = "Deletion completed."
            job.completed_at = datetime.now(UTC)
            job.error = None
            self._save_job_sync(job)

    def _retry_or_fail(self, job: _DeletionJob, message: str) -> None:
        message = redact_sensitive_text(message)
        job.error = message
        if job.attempt_count >= job.max_attempts:
            self._mark_failed(job, message)
            self._save_job_sync(job)
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
        self._save_job_sync(job)
        self._schedule_job(job)

    @staticmethod
    def _mark_failed(job: _DeletionJob, message: str) -> None:
        job.status = ManualDeleteJobStatus.FAILED
        job.phase = ManualDeleteJobPhase.FAILED
        job.progress_percent = 100
        job.message = "Deletion failed after all safe attempts."
        job.error = redact_sensitive_text(message)
        job.completed_at = datetime.now(UTC)
        job.next_retry_at = None

    def _schedule_job(self, job: _DeletionJob) -> None:
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

    def _recover_interrupted_jobs(self) -> None:
        now = datetime.now(UTC)
        for job in self._jobs.values():
            if job.status is ManualDeleteJobStatus.RUNNING:
                if job.phase is ManualDeleteJobPhase.PLANNING and job.attempt_count > 0:
                    # No mutation was started, so the original confirmed plan must
                    # still pass the first-attempt equality check after restart.
                    job.attempt_count -= 1
                job.status = ManualDeleteJobStatus.RETRY_WAIT
                job.phase = ManualDeleteJobPhase.RETRYING
                job.progress_percent = 0
                job.next_retry_at = now
                job.message = "Process restart detected; resuming from the persisted event and preflight."
                job.error = "Previous process stopped before the attempt completed."
                self._save_job_sync(job)

    def _prune_history(self) -> None:
        terminal_jobs = sorted(
            (job for job in self._jobs.values() if job.status not in self._ACTIVE_STATUSES),
            key=lambda job: job.created_at,
        )
        overflow = len(terminal_jobs) - self._history_limit + 1
        for job in terminal_jobs[: max(overflow, 0)]:
            self._jobs.pop(job.id, None)
            self._delete_job_sync(job.id)

    def _initialize_and_load_sync(self) -> list[_DeletionJob]:
        migrate_database(self._db_path)
        with sqlite3.connect(self._db_path) as connection:
            rows = connection.execute(
                "SELECT id, request_json, event_json, preflight_json, status, phase, progress_percent,"
                " message, item_name, created_at, started_at, completed_at, next_retry_at,"
                " attempt_count, max_attempts, result_json, error"
                " FROM manual_delete_jobs ORDER BY created_at DESC"
            ).fetchall()

        jobs: list[_DeletionJob] = []
        for row in rows:
            try:
                jobs.append(self._job_from_row(row))
            except Exception:  # noqa: BLE001
                _logger.exception("Ignoring an invalid persisted manual deletion job %s", row[0])
        return jobs

    def _save_job_sync(self, job: _DeletionJob) -> None:
        with sqlite3.connect(self._db_path) as connection:
            connection.execute(
                "INSERT INTO manual_delete_jobs ("
                " id, request_json, event_json, preflight_json, status, phase, progress_percent,"
                " message, item_name, created_at, started_at, completed_at, next_retry_at,"
                " attempt_count, max_attempts, result_json, error"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                " ON CONFLICT(id) DO UPDATE SET"
                " request_json=excluded.request_json, event_json=excluded.event_json,"
                " preflight_json=excluded.preflight_json, status=excluded.status, phase=excluded.phase,"
                " progress_percent=excluded.progress_percent, message=excluded.message,"
                " item_name=excluded.item_name, created_at=excluded.created_at,"
                " started_at=excluded.started_at, completed_at=excluded.completed_at,"
                " next_retry_at=excluded.next_retry_at, attempt_count=excluded.attempt_count,"
                " max_attempts=excluded.max_attempts, result_json=excluded.result_json, error=excluded.error",
                (
                    str(job.id),
                    job.request.model_dump_json(),
                    _event_to_json(job.event),
                    job.preflight.model_dump_json(),
                    job.status.value,
                    job.phase.value,
                    job.progress_percent,
                    job.message,
                    job.item_name,
                    job.created_at.isoformat(),
                    _datetime_to_text(job.started_at),
                    _datetime_to_text(job.completed_at),
                    _datetime_to_text(job.next_retry_at),
                    job.attempt_count,
                    job.max_attempts,
                    job.result.model_dump_json() if job.result is not None else None,
                    job.error,
                ),
            )
            connection.commit()

    def _delete_job_sync(self, job_id: UUID) -> None:
        with sqlite3.connect(self._db_path) as connection:
            connection.execute("DELETE FROM manual_delete_jobs WHERE id = ?", (str(job_id),))
            connection.commit()

    @staticmethod
    def _job_from_row(row: tuple[object, ...]) -> _DeletionJob:
        result_json = row[15]
        return _DeletionJob(
            id=UUID(str(row[0])),
            request=ManualDeleteRequest.model_validate_json(str(row[1])),
            event=JellyfinWebhookPayload.model_validate_json(str(row[2])).to_domain(),
            preflight=ProcessingResultResponse.model_validate_json(str(row[3])),
            status=ManualDeleteJobStatus(str(row[4])),
            phase=ManualDeleteJobPhase(str(row[5])),
            progress_percent=int(str(row[6])),
            message=redact_sensitive_text(str(row[7])),
            item_name=str(row[8]) if row[8] is not None else None,
            created_at=datetime.fromisoformat(str(row[9])),
            started_at=_datetime_from_value(row[10]),
            completed_at=_datetime_from_value(row[11]),
            next_retry_at=_datetime_from_value(row[12]),
            attempt_count=int(str(row[13])),
            max_attempts=int(str(row[14])),
            result=ProcessingResultResponse.model_validate_json(str(result_json)) if result_json is not None else None,
            error=redact_sensitive_text(str(row[16])) if row[16] is not None else None,
        )

    @staticmethod
    def _to_response(job: _DeletionJob) -> ManualDeleteJobResponse:
        return ManualDeleteJobResponse(
            id=job.id,
            item_type=job.request.item_type,
            item_name=job.item_name,
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
        )


def _event_to_json(event: MediaDeletionEvent) -> str:
    return JellyfinWebhookPayload.from_domain(event).model_dump_json()


def _datetime_to_text(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _datetime_from_value(value: object) -> datetime | None:
    return datetime.fromisoformat(str(value)) if value is not None else None


def _plan_hash(plan: ProcessingResultResponse) -> str:
    payload = json.dumps(
        plan.model_dump(mode="json", exclude={"correlation_id"}),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return hashlib.sha256(payload).hexdigest()


def validate_plan_confirmation(
    request: ManualDeleteRequest,
    plan: ProcessingResultResponse,
) -> None:
    """Fail closed unless a caller confirmed this exact canonical plan."""

    if plan.status is OverallStatus.PARTIAL_FAILURE:
        raise DeletionPreflightError("The deletion plan contains downstream failures and cannot be confirmed safely.")
    if request.confirmed_plan_hash is None:
        raise DeletionPreflightError("Preview the deletion plan before confirming it.")
    if request.confirmed_plan_hash != _plan_hash(plan):
        raise DeletionPreflightError(
            "The deletion plan changed after it was reviewed. Preview the current plan and confirm again."
        )
