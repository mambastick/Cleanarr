"""Pydantic API schemas."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from cleanarr.domain import (
    ActionResult,
    ActionStatus,
    FailureReason,
    ItemType,
    MediaDeletionEvent,
    MediaFingerprint,
    OverallStatus,
    ProcessingResult,
)


class JellyfinWebhookPayload(BaseModel):
    """Inbound webhook payload."""

    notification_type: str = Field(alias="notification_type")
    item_type: ItemType = Field(alias="item_type")
    item_id: str = Field(alias="item_id")
    name: str
    path: str | None = None
    tmdb_id: int | None = None
    tvdb_id: int | None = None
    imdb_id: str | None = None
    series_name: str | None = None
    series_id: str | None = None
    season_number: int | None = None
    episode_number: int | None = None
    episode_end_number: int | None = None
    occurred_at: datetime | None = None

    @field_validator("occurred_at", mode="before")
    @classmethod
    def normalize_occurred_at(cls, value: Any) -> Any:
        if value in {None, ""}:
            return None
        if isinstance(value, datetime):
            return value
        if not isinstance(value, str):
            return value

        normalized = value.strip()
        if not normalized:
            return None

        iso_candidate = normalized.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(iso_candidate)
        except ValueError:
            pass

        for fmt in (
            "%m/%d/%Y %H:%M:%S",
            "%m/%d/%Y %I:%M:%S %p",
            "%d.%m.%Y %H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
        ):
            try:
                return datetime.strptime(normalized, fmt).replace(tzinfo=UTC)
            except ValueError:
                continue

        return value

    @model_validator(mode="after")
    def validate_scope(self) -> JellyfinWebhookPayload:
        if self.item_type in {ItemType.SEASON, ItemType.EPISODE} and self.season_number is None:
            raise ValueError("season_number is required for season and episode deletions")
        if self.item_type is ItemType.EPISODE and self.episode_number is None:
            raise ValueError("episode_number is required for episode deletions")
        return self

    def to_domain(self) -> MediaDeletionEvent:
        fingerprint = MediaFingerprint(
            tmdb_id=self.tmdb_id,
            tvdb_id=self.tvdb_id,
            imdb_id=self.imdb_id,
            path=self.path,
        )
        return MediaDeletionEvent(
            notification_type=self.notification_type,
            item_type=self.item_type,
            item_id=self.item_id,
            name=self.name,
            fingerprint=fingerprint,
            series_name=self.series_name,
            series_id=self.series_id,
            season_number=self.season_number,
            episode_number=self.episode_number,
            episode_end_number=self.episode_end_number,
            occurred_at=self.occurred_at,
        )


class ActionResultResponse(BaseModel):
    """Serialized action result."""

    system: str
    action: str
    status: ActionStatus
    message: str
    reason: FailureReason | None = None
    details: dict[str, Any]

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


class ProcessingResultResponse(BaseModel):
    """Serialized per-event result."""

    item_type: ItemType
    item_id: str
    name: str
    status: OverallStatus
    actions: list[ActionResultResponse]

    @classmethod
    def from_domain(cls, result: ProcessingResult) -> ProcessingResultResponse:
        return cls(
            item_type=result.event.item_type,
            item_id=result.event.item_id,
            name=result.event.name,
            status=result.status,
            actions=[ActionResultResponse.from_domain(action) for action in result.actions],
        )


class WebhookBatchResponse(BaseModel):
    """Serialized webhook response."""

    status: OverallStatus
    results: list[ProcessingResultResponse]

    @classmethod
    def from_results(cls, results: list[ProcessingResult]) -> WebhookBatchResponse:
        statuses = {result.status for result in results}
        if OverallStatus.PARTIAL_FAILURE in statuses:
            overall = OverallStatus.PARTIAL_FAILURE
        elif statuses == {OverallStatus.IGNORED}:
            overall = OverallStatus.IGNORED
        else:
            overall = OverallStatus.SUCCESS
        return cls(
            status=overall,
            results=[ProcessingResultResponse.from_domain(result) for result in results],
        )
