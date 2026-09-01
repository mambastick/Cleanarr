"""Pure application projections for deletion workflows.

These Pydantic models deliberately preserve the public API serialization
contract while keeping the deletion application services independent from the
FastAPI transport package.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from unicodedata import category
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator, model_validator

from cleanarr.domain import (
    ActionResult,
    ActionStatus,
    FailureReason,
    ItemType,
    MediaDeletionEvent,
    OverallStatus,
    ProcessingResult,
)
from cleanarr.redaction import redact_sensitive_mapping, redact_sensitive_text


class ActionResultResponse(BaseModel):
    """Serialized action result shared by application and API adapters."""

    system: str
    action: str
    status: ActionStatus
    message: str
    reason: FailureReason | None = None
    details: dict[str, object]

    @field_validator("message", mode="before")
    @classmethod
    def redact_message(cls, value: object) -> str:
        return redact_sensitive_text(str(value))

    @field_validator("details", mode="before")
    @classmethod
    def redact_details(cls, value: object) -> dict[str, object]:
        if not isinstance(value, dict):
            raise ValueError("Action details must be an object.")
        return redact_sensitive_mapping(value)

    @classmethod
    def from_domain(cls, action: ActionResult) -> ActionResultResponse:
        return cls(
            system=action.system,
            action=action.action,
            status=action.status,
            message=action.message,
            reason=action.reason,
            details=dict(action.details),
        )


class MediaFingerprintResponse(BaseModel):
    """Stable identifiers and path used to resolve a deletion target."""

    tmdb_id: int | None = None
    tvdb_id: int | None = None
    imdb_id: str | None = None
    path: str | None = None


class ProcessingResultResponse(BaseModel):
    """Serialized per-event result usable by durable deletion services."""

    item_type: ItemType
    correlation_id: str | None = None
    item_id: str
    name: str
    display_name: str | None = None
    status: OverallStatus
    fingerprint: MediaFingerprintResponse = Field(default_factory=MediaFingerprintResponse)
    season_number: int | None = None
    episode_number: int | None = None
    episode_end_number: int | None = None
    actions: list[ActionResultResponse]

    @model_validator(mode="after")
    def populate_display_name_fallback(self) -> ProcessingResultResponse:
        """Keep old persisted results usable after presentation data was introduced."""

        if not self.display_name:
            self.display_name = self.name.strip() or self.item_type.value
        return self

    @classmethod
    def from_domain(cls, result: ProcessingResult) -> ProcessingResultResponse:
        return cls(
            item_type=result.event.item_type,
            correlation_id=result.correlation_id,
            item_id=result.event.item_id,
            name=result.event.name,
            status=result.status,
            fingerprint=MediaFingerprintResponse(
                tmdb_id=result.event.fingerprint.tmdb_id,
                tvdb_id=result.event.fingerprint.tvdb_id,
                imdb_id=result.event.fingerprint.imdb_id,
                path=result.event.fingerprint.path,
            ),
            season_number=result.event.season_number,
            episode_number=result.event.episode_number,
            episode_end_number=result.event.episode_end_number,
            actions=[ActionResultResponse.from_domain(action) for action in result.actions],
        )

    def to_domain(self, event: MediaDeletionEvent) -> ProcessingResult:
        """Restore a cached result for its persisted source event."""

        return ProcessingResult(
            event=event,
            status=self.status,
            actions=tuple(
                ActionResult(
                    system=action.system,
                    action=action.action,
                    status=action.status,
                    message=action.message,
                    reason=action.reason,
                    details=action.details,
                )
                for action in self.actions
            ),
            correlation_id=self.correlation_id or uuid4().hex,
        )


class ManualDeleteRequest(BaseModel):
    """Application command for a manually selected deletion target."""

    item_type: ItemType
    sonarr_series_id: int | None = None
    radarr_movie_id: int | None = None
    season_number: int | None = None
    jellyfin_item_id: str | None = None
    confirmed_plan_hash: str | None = None
    idempotency_key: UUID | None = None
    display_name: str | None = Field(default=None, max_length=256)

    @field_validator("display_name", mode="before")
    @classmethod
    def validate_display_name(cls, value: object) -> str | None:
        """Accept presentation text without letting it become an ownership input."""

        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("display_name must be a string.")
        normalized = value.strip()
        if not normalized:
            return None
        if any(category(character) == "Cc" for character in normalized):
            raise ValueError("display_name must not contain control characters.")
        if len(normalized) > 256:
            raise ValueError("display_name must not exceed 256 characters.")
        return normalized


class ManualDeleteJobRequest(ManualDeleteRequest):
    """Confirmed request accepted by the durable deletion-jobs endpoint."""

    idempotency_key: UUID
    confirmed_plan_hash: str


class ManualDeleteJobStatus(StrEnum):
    """Lifecycle status of a queued manual deletion."""

    QUEUED = "queued"
    RUNNING = "running"
    RETRY_WAIT = "retry_wait"
    COMPLETED = "completed"
    FAILED = "failed"


class ManualDeleteJobPhase(StrEnum):
    """User-facing phase of a queued manual deletion."""

    QUEUED = "queued"
    PLANNING = "planning"
    LOCATING = "locating"
    CLEANING = "cleaning"
    RECORDING = "recording"
    JELLYFIN = "jellyfin"
    RETRYING = "retrying"
    COMPLETED = "completed"
    FAILED = "failed"


class ManualDeletePreviewResponse(BaseModel):
    """Dry-run plan generated before a manual deletion is confirmed."""

    generated_at: datetime
    plan_hash: str
    plan: ProcessingResultResponse


class ManualDeleteJobResponse(BaseModel):
    """Current state of one background manual deletion."""

    id: UUID
    item_type: ItemType
    item_name: str | None = None
    display_name: str
    status: ManualDeleteJobStatus
    phase: ManualDeleteJobPhase
    progress_percent: int
    message: str
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    next_retry_at: datetime | None = None
    attempt_count: int
    max_attempts: int
    preflight: ProcessingResultResponse
    result: ProcessingResultResponse | None = None
    error: str | None = None


class ManualDeleteJobListResponse(BaseModel):
    """Recent background manual deletions."""

    jobs: list[ManualDeleteJobResponse]


class BatchChildPreviewStatus(StrEnum):
    """Safety state returned for one previewed batch child."""

    READY = "ready"
    BLOCKED = "blocked"


class BatchChildStatus(StrEnum):
    """Durable lifecycle state for one batch child."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ManualDeleteBatchStatus(StrEnum):
    """Durable lifecycle state for one bounded batch."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ManualDeleteBatchPreviewRequest(BaseModel):
    """Mutation-free preview input, capped before downstream resolution."""

    children: list[ManualDeleteRequest] = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def children_are_unconfirmed(self) -> ManualDeleteBatchPreviewRequest:
        if any(child.confirmed_plan_hash is not None or child.idempotency_key is not None for child in self.children):
            raise ValueError("Batch children must not include confirmed_plan_hash or idempotency_key.")
        return self


class ManualDeleteBatchSubmitRequest(ManualDeleteBatchPreviewRequest):
    """A hash-bound, durably idempotent batch confirmation."""

    idempotency_key: UUID
    confirmed_batch_hash: str = Field(min_length=1, max_length=128)
    confirmed_item_count: int = Field(ge=1, le=50)

    @model_validator(mode="after")
    def count_matches_children(self) -> ManualDeleteBatchSubmitRequest:
        if self.confirmed_item_count != len(self.children):
            raise ValueError("confirmed_item_count must equal the number of submitted children.")
        return self


class ManualDeleteBatchChildPreviewResponse(BaseModel):
    """One canonical child plan or an explicit fail-closed block."""

    mutation_identity: str
    display_name: str
    status: BatchChildPreviewStatus
    plan_hash: str | None = None
    plan: ProcessingResultResponse | None = None
    blocked_code: str | None = None
    blocked_message: str | None = None


class ManualDeleteBatchPreviewResponse(BaseModel):
    """Canonical batch preflight. Blocked children remain visible."""

    generated_at: datetime
    batch_hash: str
    children: list[ManualDeleteBatchChildPreviewResponse] = Field(max_length=50)
    ready_count: int
    blocked_count: int


class ManualDeleteBatchChildResponse(BaseModel):
    """Persisted child state; idempotency keys never leave the server."""

    id: UUID
    mutation_identity: str
    display_name: str
    status: BatchChildStatus
    message: str
    blocked_code: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    preflight: ProcessingResultResponse | None = None
    result: ProcessingResultResponse | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None


class ManualDeleteBatchResponse(BaseModel):
    """Bounded parent detail and truthful child progress counts."""

    id: UUID
    status: ManualDeleteBatchStatus
    message: str
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_code: str | None = None
    error_message: str | None = None
    total_count: int = Field(ge=0, le=50)
    queued_count: int = Field(ge=0, le=50)
    running_count: int = Field(ge=0, le=50)
    completed_count: int = Field(ge=0, le=50)
    blocked_count: int = Field(ge=0, le=50)
    failed_count: int = Field(ge=0, le=50)
    cancelled_count: int = Field(ge=0, le=50)
    children: list[ManualDeleteBatchChildResponse] = Field(max_length=50)


class ManualDeleteBatchListResponse(BaseModel):
    """Stable, bounded reverse-chronological batch history page."""

    batches: list[ManualDeleteBatchResponse] = Field(max_length=50)
    next_before: str | None = None
