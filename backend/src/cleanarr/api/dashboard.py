"""Dashboard payloads and recent activity state."""

from __future__ import annotations

import asyncio
import sqlite3
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Lock
from urllib.parse import urlsplit, urlunsplit

from pydantic import BaseModel

from cleanarr.api.schemas import ProcessingResultResponse
from cleanarr.domain import ItemType, ProcessingResult
from cleanarr.domain.config import RuntimeConfig

JELLYFIN_GENERIC_TEMPLATE = """{
  "notification_type": "{{json_encode NotificationType}}",
  "item_type": "{{json_encode ItemType}}",
  "item_id": "{{json_encode ItemId}}",
  "name": "{{json_encode Name}}",
  "path": null,
  "tmdb_id": {{#if_exist Provider_tmdb}}{{Provider_tmdb}}{{else}}null{{/if_exist}},
  "tvdb_id": {{#if_exist Provider_tvdb}}{{Provider_tvdb}}{{else}}null{{/if_exist}},
  "imdb_id": {{#if_exist Provider_imdb}}"{{json_encode Provider_imdb}}"{{else}}null{{/if_exist}},
  "series_name": {{#if_exist SeriesName}}"{{json_encode SeriesName}}"{{else}}null{{/if_exist}},
  "series_id": {{#if_exist SeriesId}}"{{json_encode SeriesId}}"{{else}}null{{/if_exist}},
  "season_number": {{#if_exist SeasonNumber}}{{SeasonNumber}}{{else}}null{{/if_exist}},
  "episode_number": {{#if_exist EpisodeNumber}}{{EpisodeNumber}}{{else}}null{{/if_exist}},
  "episode_end_number": {{#if_exist EpisodeNumberEnd}}{{EpisodeNumberEnd}}{{else}}null{{/if_exist}},
  "occurred_at": "{{json_encode UtcTimestamp}}"
}"""

SAMPLE_WEBHOOK_PAYLOAD: dict[str, str | int | None] = {
    "notification_type": "ItemDeleted",
    "item_type": "Movie",
    "item_id": "example-item-id",
    "name": "Example Movie",
    "path": None,
    "tmdb_id": 10555,
    "tvdb_id": None,
    "imdb_id": "tt0307453",
    "series_name": None,
    "series_id": None,
    "season_number": None,
    "episode_number": None,
    "episode_end_number": None,
    "occurred_at": "2026-03-14T01:02:03Z",
}


@dataclass(frozen=True)
class ActivityRecord:
    """A processed webhook event recorded for UI inspection."""

    processed_at: datetime
    result: ProcessingResultResponse


class ActivityStore:
    """SQLite-backed activity log with configurable day-based retention."""

    def __init__(self, db_path: Path, *, retention_days: int = 30) -> None:
        self._db_path = db_path
        self._retention_days = retention_days

    def initialize_sync(self) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS activity ("
                "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
                "  processed_at TEXT NOT NULL,"
                "  result_json TEXT NOT NULL"
                ")"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_processed_at ON activity(processed_at)"
            )
            conn.commit()
        self._purge_sync()

    async def initialize(self) -> None:
        await asyncio.to_thread(self.initialize_sync)

    def _purge_sync(self) -> None:
        cutoff = (datetime.now(UTC) - timedelta(days=self._retention_days)).isoformat()
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("DELETE FROM activity WHERE processed_at < ?", (cutoff,))
            conn.commit()

    def _record_sync(self, result: ProcessingResult) -> None:
        now = datetime.now(UTC).isoformat()
        result_response = ProcessingResultResponse.from_domain(result)
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                "INSERT INTO activity (processed_at, result_json) VALUES (?, ?)",
                (now, result_response.model_dump_json()),
            )
            cutoff = (datetime.now(UTC) - timedelta(days=self._retention_days)).isoformat()
            conn.execute("DELETE FROM activity WHERE processed_at < ?", (cutoff,))
            conn.commit()

    async def record(self, result: ProcessingResult) -> None:
        await asyncio.to_thread(self._record_sync, result)

    def _snapshot_sync(self, limit: int) -> list[ActivityRecord]:
        with sqlite3.connect(self._db_path) as conn:
            rows = conn.execute(
                "SELECT processed_at, result_json FROM activity"
                " ORDER BY processed_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        records = []
        for processed_at, result_json in rows:
            try:
                records.append(
                    ActivityRecord(
                        processed_at=datetime.fromisoformat(processed_at),
                        result=ProcessingResultResponse.model_validate_json(result_json),
                    )
                )
            except Exception:  # noqa: BLE001
                pass
        return records

    async def snapshot(self, limit: int = 200) -> list[ActivityRecord]:
        return await asyncio.to_thread(self._snapshot_sync, limit)

    def set_retention_days(self, days: int) -> None:
        self._retention_days = days

    @property
    def retention_days(self) -> int:
        return self._retention_days


@dataclass(frozen=True)
class WebhookAttemptRecord:
    """Latest inbound webhook delivery attempt for setup diagnostics."""

    attempted_at: datetime
    outcome: str
    http_status: int
    message: str
    notification_type: str | None = None
    item_type: str | None = None
    item_name: str | None = None
    result_status: str | None = None


class WebhookAttemptStore:
    """Keep only the latest webhook attempt so the UI can guide setup."""

    def __init__(self) -> None:
        self._latest: WebhookAttemptRecord | None = None
        self._lock = Lock()

    def record(
        self,
        *,
        outcome: str,
        http_status: int,
        message: str,
        notification_type: str | None = None,
        item_type: str | None = None,
        item_name: str | None = None,
        result_status: str | None = None,
    ) -> None:
        with self._lock:
            self._latest = WebhookAttemptRecord(
                attempted_at=datetime.now(UTC),
                outcome=outcome,
                http_status=http_status,
                message=message,
                notification_type=notification_type,
                item_type=item_type,
                item_name=item_name,
                result_status=result_status,
            )

    def latest(self) -> WebhookAttemptRecord | None:
        with self._lock:
            return self._latest


class DashboardServiceResponse(BaseModel):
    """Top-level runtime summary."""

    name: str
    version: str
    dry_run: bool
    log_level: str
    downloader_kind: str
    webhook_token_configured: bool
    activity_retention_days: int


class DashboardEndpointResponse(BaseModel):
    """A public HTTP endpoint exposed by CleanArr."""

    method: str
    path: str
    description: str
    auth: str


class HealthProbeStore:
    """Stores latest connectivity probe results per downstream service."""

    _SERVICES = ("Radarr", "Sonarr", "Jellyfin", "Jellyseerr", "Downloader")

    def __init__(self) -> None:
        self._results: dict[str, str] = {name: "unconfigured" for name in self._SERVICES}
        self._lock = Lock()

    def update(self, service: str, status: str) -> None:
        with self._lock:
            self._results[service] = status

    def snapshot(self) -> dict[str, str]:
        with self._lock:
            return dict(self._results)


class DashboardDownstreamResponse(BaseModel):
    """Configured downstream dependency shown in the UI."""

    name: str
    role: str
    url: str
    configured: bool
    health_status: str


class DashboardRuleResponse(BaseModel):
    """Human-readable matching and cleanup policy for an item type."""

    item_type: ItemType
    matching_order: list[str]
    cleanup_steps: list[str]
    guardrails: list[str]


class DashboardActivityResponse(BaseModel):
    """A dashboard-friendly projection of a processing result."""

    processed_at: datetime
    action_summary: dict[str, int]
    result: ProcessingResultResponse


class DashboardWebhookStatusResponse(BaseModel):
    """Latest webhook delivery attempt shown in setup diagnostics."""

    attempted_at: datetime | None
    outcome: str
    http_status: int | None
    message: str
    notification_type: str | None = None
    item_type: str | None = None
    item_name: str | None = None
    result_status: str | None = None


class DashboardResponse(BaseModel):
    """Complete dashboard payload for the frontend."""

    service: DashboardServiceResponse
    endpoints: list[DashboardEndpointResponse]
    downstream: list[DashboardDownstreamResponse]
    rules: list[DashboardRuleResponse]
    jellyfin_template: str
    sample_payload: dict[str, str | int | None]
    recent_activity: list[DashboardActivityResponse]
    webhook_status: DashboardWebhookStatusResponse


async def build_dashboard_response(
    *,
    config: RuntimeConfig,
    downloader_kind: str,
    version: str,
    activity_store: ActivityStore,
    webhook_attempt_store: WebhookAttemptStore,
    health_probe_store: HealthProbeStore,
) -> DashboardResponse:
    """Build a single dashboard snapshot."""

    general = config.general
    active_radarr = _pick_active_url(config.radarr)
    active_sonarr = _pick_active_url(config.sonarr)
    active_jellyfin = _pick_active_url(config.jellyfin)
    active_jellyseerr = _pick_active_url(config.jellyseerr)
    active_downloader = _pick_active_url(config.downloaders)
    health = health_probe_store.snapshot()
    activity_records = await activity_store.snapshot()

    return DashboardResponse(
        service=DashboardServiceResponse(
            name="CleanArr",
            version=version,
            dry_run=general.dry_run,
            log_level=general.log_level,
            downloader_kind=downloader_kind,
            webhook_token_configured=bool(general.webhook_shared_token),
            activity_retention_days=activity_store.retention_days,
        ),
        endpoints=[
            DashboardEndpointResponse(
                method="POST",
                path="/webhook/jellyfin",
                description="Accepts Jellyfin ItemDeleted events and runs cascade cleanup.",
                auth="X-Webhook-Token or Authorization: Bearer <token>",
            ),
            DashboardEndpointResponse(
                method="GET",
                path="/api/dashboard",
                description="Returns the current dashboard snapshot used by the SPA.",
                auth="none",
            ),
            DashboardEndpointResponse(
                method="GET",
                path="/health/live",
                description="Container liveness probe.",
                auth="none",
            ),
            DashboardEndpointResponse(
                method="GET",
                path="/health/ready",
                description="Readiness probe for ingress and deployment checks.",
                auth="none",
            ),
        ],
        downstream=[
            DashboardDownstreamResponse(
                name="Radarr",
                role="Movie resolution and metadata cleanup",
                url=_sanitize_url(active_radarr),
                configured=bool(active_radarr),
                health_status=health.get("Radarr", "unconfigured"),
            ),
            DashboardDownstreamResponse(
                name="Sonarr",
                role="Series, season and episode cleanup",
                url=_sanitize_url(active_sonarr),
                configured=bool(active_sonarr),
                health_status=health.get("Sonarr", "unconfigured"),
            ),
            DashboardDownstreamResponse(
                name="Jellyfin",
                role="Media server and webhook source",
                url=_sanitize_url(active_jellyfin),
                configured=bool(active_jellyfin),
                health_status=health.get("Jellyfin", "unconfigured"),
            ),
            DashboardDownstreamResponse(
                name="Jellyseerr",
                role="Request and issue cleanup",
                url=_sanitize_url(active_jellyseerr),
                configured=bool(active_jellyseerr),
                health_status=health.get("Jellyseerr", "unconfigured"),
            ),
            DashboardDownstreamResponse(
                name="Downloader",
                role="Torrent hash deletion",
                url=_sanitize_url(active_downloader),
                configured=bool(active_downloader),
                health_status=health.get("Downloader", "unconfigured"),
            ),
        ],
        rules=_build_rules(),
        jellyfin_template=JELLYFIN_GENERIC_TEMPLATE,
        sample_payload=SAMPLE_WEBHOOK_PAYLOAD,
        recent_activity=[
            DashboardActivityResponse(
                processed_at=record.processed_at,
                action_summary=_summarize_actions(record.result),
                result=record.result,
            )
            for record in activity_records
        ],
        webhook_status=_build_webhook_status(webhook_attempt_store.latest()),
    )


def _build_webhook_status(
    record: WebhookAttemptRecord | None,
) -> DashboardWebhookStatusResponse:
    if record is None:
        return DashboardWebhookStatusResponse(
            attempted_at=None,
            outcome="waiting",
            http_status=None,
            message="No Jellyfin webhook has reached CleanArr yet.",
        )

    return DashboardWebhookStatusResponse(
        attempted_at=record.attempted_at,
        outcome=record.outcome,
        http_status=record.http_status,
        message=record.message,
        notification_type=record.notification_type,
        item_type=record.item_type,
        item_name=record.item_name,
        result_status=record.result_status,
    )


def _build_rules() -> list[DashboardRuleResponse]:
    tv_matching = ["tvdb_id", "tmdb_id", "imdb_id", "path"]
    return [
        DashboardRuleResponse(
            item_type=ItemType.MOVIE,
            matching_order=["tmdb_id", "imdb_id", "path"],
            cleanup_steps=[
                "Resolve movie in Radarr using strict identifiers only.",
                "Collect downloader hashes from grabbed Radarr history records.",
                "Delete safe hashes with deleteFiles=true.",
                "Delete the Radarr movie entry and matching Jellyseerr records.",
            ],
            guardrails=[
                "No fuzzy matching.",
                "No downstream mutation when resolution is ambiguous.",
            ],
        ),
        DashboardRuleResponse(
            item_type=ItemType.SERIES,
            matching_order=tv_matching,
            cleanup_steps=[
                "Resolve series in Sonarr and Jellyseerr.",
                "Delete downloader hashes belonging exclusively to the series.",
                "Delete the Sonarr series entry.",
                "Delete Jellyseerr requests, issues and media records for the series.",
            ],
            guardrails=[
                "Pack torrents shared with unrelated content are skipped.",
                "No direct DB writes to Arr or download clients.",
            ],
        ),
        DashboardRuleResponse(
            item_type=ItemType.SEASON,
            matching_order=tv_matching,
            cleanup_steps=[
                "Resolve the parent series in Sonarr and Jellyseerr.",
                "Unmonitor episodes in the target season.",
                "Delete only fully covered episode files and downloader hashes.",
                "Update or delete matching Jellyseerr season requests.",
            ],
            guardrails=[
                "Shared files across seasons are never removed.",
                "Torrent hashes spanning content outside the season are skipped.",
            ],
        ),
        DashboardRuleResponse(
            item_type=ItemType.EPISODE,
            matching_order=tv_matching,
            cleanup_steps=[
                "Resolve the parent series in Sonarr.",
                "Unmonitor only the target episode range.",
                "Delete episode files and hashes only when the scope is fully isolated.",
                "Leave Jellyseerr requests unchanged in v1.",
            ],
            guardrails=[
                "Multi-episode files are skipped if they exceed the requested scope.",
                "Pack torrents generate safety notes instead of destructive mutations.",
            ],
        ),
    ]


def _sanitize_url(raw_url: str) -> str:
    if not raw_url:
        return ""
    parsed = urlsplit(raw_url)
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


def _pick_active_url(services: Sequence[BaseModel]) -> str:
    enabled = [service for service in services if bool(getattr(service, "enabled", False))]
    active = next((service for service in enabled if bool(getattr(service, "is_default", False))), None)
    if active is None and enabled:
        active = enabled[0]
    return getattr(active, "url", "") if active is not None else ""


def _summarize_actions(result: ProcessingResultResponse) -> dict[str, int]:
    counts = Counter(action.status.value for action in result.actions)
    return dict(sorted(counts.items()))
