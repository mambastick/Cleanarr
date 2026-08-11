"""In-memory queue for manual deletion jobs started from the web UI."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import HTTPException

from cleanarr.api.library_schemas import (
    ManualDeleteJobPhase,
    ManualDeleteJobResponse,
    ManualDeleteJobStatus,
    ManualDeleteRequest,
)
from cleanarr.api.schemas import ProcessingResultResponse

DeletionProgressReporter = Callable[[ManualDeleteJobPhase, int, str, str | None], None]
ManualDeleteRunner = Callable[
    [ManualDeleteRequest, DeletionProgressReporter],
    Awaitable[ProcessingResultResponse],
]

_logger = logging.getLogger("cleanarr")


class DeletionJobNotFoundError(LookupError):
    """Raised when a requested deletion job is not present in memory."""


class DeletionJobActiveError(RuntimeError):
    """Raised when attempting to dismiss a queued or running job."""


@dataclass
class _DeletionJob:
    id: UUID
    request: ManualDeleteRequest
    status: ManualDeleteJobStatus
    phase: ManualDeleteJobPhase
    progress_percent: int
    message: str
    created_at: datetime
    item_name: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    result: ProcessingResultResponse | None = None
    error: str | None = None


class ManualDeletionJobStore:
    """Run manual deletions sequentially and expose progress snapshots."""

    def __init__(self, runner: ManualDeleteRunner, *, history_limit: int = 50) -> None:
        self._runner = runner
        self._history_limit = history_limit
        self._jobs: dict[UUID, _DeletionJob] = {}
        self._queue: asyncio.Queue[UUID] = asyncio.Queue()
        self._worker_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Start the queue worker if it is not already running."""

        if self._worker_task is None or self._worker_task.done():
            self._worker_task = asyncio.create_task(
                self._worker_loop(),
                name="cleanarr-manual-deletion-worker",
            )

    async def stop(self) -> None:
        """Stop the queue worker during application shutdown."""

        worker = self._worker_task
        self._worker_task = None
        if worker is None:
            return
        worker.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await worker

    async def submit(self, payload: ManualDeleteRequest) -> ManualDeleteJobResponse:
        """Queue a deletion and immediately return its first snapshot."""

        await self.start()
        self._prune_history()
        job = _DeletionJob(
            id=uuid4(),
            request=payload,
            status=ManualDeleteJobStatus.QUEUED,
            phase=ManualDeleteJobPhase.QUEUED,
            progress_percent=0,
            message="Waiting for the current background task to finish.",
            created_at=datetime.now(UTC),
        )
        self._jobs[job.id] = job
        await self._queue.put(job.id)
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
        """Remove a terminal job from the visible history."""

        job = self._jobs.get(job_id)
        if job is None:
            raise DeletionJobNotFoundError(str(job_id))
        if job.status in {ManualDeleteJobStatus.QUEUED, ManualDeleteJobStatus.RUNNING}:
            raise DeletionJobActiveError(str(job_id))
        del self._jobs[job_id]

    async def _worker_loop(self) -> None:
        while True:
            job_id = await self._queue.get()
            try:
                job = self._jobs.get(job_id)
                if job is not None:
                    await self._run_job(job)
            finally:
                self._queue.task_done()

    async def _run_job(self, job: _DeletionJob) -> None:
        job.status = ManualDeleteJobStatus.RUNNING
        job.started_at = datetime.now(UTC)

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

        try:
            result = await self._runner(job.request, report)
        except HTTPException as exc:
            self._mark_failed(job, str(exc.detail))
        except Exception as exc:  # noqa: BLE001
            _logger.exception("Manual deletion background job %s failed", job.id)
            self._mark_failed(job, str(exc) or type(exc).__name__)
        else:
            job.status = ManualDeleteJobStatus.COMPLETED
            job.phase = ManualDeleteJobPhase.COMPLETED
            job.progress_percent = 100
            job.result = result
            job.item_name = result.name
            job.message = (
                "Finished with some downstream errors." if result.status == "partial_failure" else "Deletion completed."
            )
            job.completed_at = datetime.now(UTC)

    @staticmethod
    def _mark_failed(job: _DeletionJob, message: str) -> None:
        job.status = ManualDeleteJobStatus.FAILED
        job.phase = ManualDeleteJobPhase.FAILED
        job.progress_percent = 100
        job.message = "Deletion failed."
        job.error = message
        job.completed_at = datetime.now(UTC)

    def _prune_history(self) -> None:
        terminal_jobs = sorted(
            (
                job
                for job in self._jobs.values()
                if job.status in {ManualDeleteJobStatus.COMPLETED, ManualDeleteJobStatus.FAILED}
            ),
            key=lambda job: job.created_at,
        )
        overflow = len(terminal_jobs) - self._history_limit + 1
        for job in terminal_jobs[: max(overflow, 0)]:
            self._jobs.pop(job.id, None)

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
            result=job.result,
            error=job.error,
        )
