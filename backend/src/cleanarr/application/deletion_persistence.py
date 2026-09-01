"""State records and persistence ports for durable deletion workflows."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol
from uuid import UUID

from cleanarr.application.deletion_models import (
    BatchChildStatus,
    ManualDeleteBatchStatus,
    ManualDeleteJobPhase,
    ManualDeleteJobStatus,
    ManualDeleteRequest,
    ProcessingResultResponse,
)
from cleanarr.domain import MediaDeletionEvent


@dataclass
class DeletionJobRecord:
    """Application-owned durable state for one manual deletion job."""

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
    idempotency_key: UUID | None = None
    display_name: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    next_retry_at: datetime | None = None
    attempt_count: int = 0
    result: ProcessingResultResponse | None = None
    error: str | None = None


@dataclass
class DeletionBatchChildRecord:
    """Application-owned durable state for one independently safe batch child."""

    id: UUID
    position: int
    mutation_identity: str
    request: ManualDeleteRequest
    display_name: str
    status: BatchChildStatus
    message: str
    event: MediaDeletionEvent | None = None
    preflight: ProcessingResultResponse | None = None
    plan_hash: str | None = None
    blocked_code: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    result: ProcessingResultResponse | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None


@dataclass
class DeletionBatchRecord:
    """Application-owned durable parent state for a bounded deletion batch."""

    id: UUID
    canonical_request: str
    confirmed_batch_hash: str
    status: ManualDeleteBatchStatus
    message: str
    created_at: datetime
    children: list[DeletionBatchChildRecord] = field(default_factory=list)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_code: str | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class DestructiveIdempotencyRecord:
    """Raw durable ledger entry; application owns the comparison decision."""

    request_kind: str
    canonical_request_json: str
    original_request_json: str
    resource_id: UUID


@dataclass(frozen=True)
class BatchCreationResult:
    """Atomic repository result for a batch claim and bounded-queue check."""

    existing: DestructiveIdempotencyRecord | None = None
    queue_full: bool = False


class DeletionRepositoryPort(Protocol):
    """SQLite-independent persistence boundary for jobs, batches, and webhooks."""

    def initialize(self) -> None: ...

    def load_jobs(self) -> list[DeletionJobRecord]: ...

    def load_job(self, job_id: UUID) -> DeletionJobRecord | None: ...

    def save_job(self, job: DeletionJobRecord) -> None: ...

    def delete_job(self, job_id: UUID) -> None: ...

    def load_batches(self) -> list[DeletionBatchRecord]: ...

    def load_batch(self, batch_id: UUID) -> DeletionBatchRecord | None: ...

    def save_batch(self, batch: DeletionBatchRecord) -> None: ...

    def delete_batch(self, batch_id: UUID) -> None: ...

    def lookup_destructive_idempotency(self, key: UUID) -> DestructiveIdempotencyRecord | None: ...

    def create_job_with_idempotency(
        self,
        job: DeletionJobRecord,
        *,
        canonical_request: str,
        original_request: str,
    ) -> DestructiveIdempotencyRecord | None: ...

    def create_batch_with_idempotency(
        self,
        batch: DeletionBatchRecord,
        *,
        idempotency_key: UUID,
        original_request: str,
        max_pending_parents: int,
    ) -> BatchCreationResult: ...

    def load_completed_webhook(
        self, event_key: str, *, completed_after: datetime
    ) -> tuple[MediaDeletionEvent, ProcessingResultResponse] | None: ...

    def has_incomplete_webhook(self, event_key: str) -> bool: ...

    def mark_webhook_processing(self, event_key: str, event: MediaDeletionEvent, *, purge_before: datetime) -> None: ...

    def mark_webhook_completed(self, event_key: str, result: ProcessingResultResponse) -> None: ...

    def delete_webhook(self, event_key: str) -> None: ...

    def purge_webhooks(self, *, completed_before: datetime) -> None: ...


def display_name_fallback(*, item_name: str | None, result_name: str | None, item_type: object) -> str:
    """Use the historic safe title fallback without making it an identity input."""

    if item_name:
        return item_name
    if result_name:
        return result_name
    return str(getattr(item_type, "value", item_type))
