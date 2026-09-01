"""Transport schemas for bounded Downloads endpoints."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from cleanarr.domain.downloads import DownloadActionStatus, DownloadControlAction, TorrentSnapshot


class DownloadActionProjection(BaseModel):
    """Bounded audit projection; excludes idempotency/canonical request data."""

    action_id: str
    source: str
    status: DownloadActionStatus
    code: str | None
    attempt_count: int
    max_attempts: int
    created_at: datetime
    updated_at: datetime
    result: dict[str, str | None] | None = None


class DownloadItemResponse(BaseModel):
    client_id: str
    client_name: str
    client_kind: str
    info_hash: str
    observed_at: datetime
    display_name: str | None
    state: str
    freshness: str
    ownership: str
    progress: float | None
    total_bytes: int | None
    downloaded_bytes: int | None
    uploaded_bytes: int | None
    ratio: float | None
    seeding_time_seconds: int | None
    download_speed_bytes_per_second: int | None
    upload_speed_bytes_per_second: int | None
    eta_seconds: int | None
    added_at: datetime | None
    completed_at: datetime | None
    activity_at: datetime | None
    category: str | None
    tags: list[str] | None
    tracker_summary: str | None
    unavailable_reason: str | None
    policy_decision: str | None = None
    policy_reason_code: str | None = None
    policy_facts: dict[str, object] | None = None
    latest_action: DownloadActionProjection | None = None

    @classmethod
    def from_domain(
        cls,
        item: TorrentSnapshot,
        policy: dict[str, object] | None = None,
        action: dict[str, object] | None = None,
    ) -> DownloadItemResponse:
        payload = {**item.__dict__, "tags": list(item.tags) if item.tags is not None else None}
        if policy:
            payload.update(
                policy_decision=policy.get("decision"),
                policy_reason_code=policy.get("reason_code"),
                policy_facts=policy.get("facts"),
            )
        if action:
            payload["latest_action"] = DownloadActionProjection.model_validate(action)
        return cls(**payload)


class DownloadsResponse(BaseModel):
    items: list[DownloadItemResponse]
    next_cursor: str | None
    source_status: str
    failures: list[str]
    failure_details: list[dict[str, str]] = Field(default_factory=list)
    active_count: int


class DownloadRefreshResponse(DownloadsResponse):
    refreshed: bool


class DownloadActionRequest(BaseModel):
    client_id: str = Field(min_length=1, max_length=128)
    info_hash: str = Field(pattern=r"^[0-9a-fA-F]{40}([0-9a-fA-F]{24})?$")
    action: DownloadControlAction
    idempotency_key: str = Field(min_length=36, max_length=36)


class DownloadActionResponse(BaseModel):
    action_id: str
    status: DownloadActionStatus
    code: str | None = None
