"""Privacy-safe operational metrics, support data, and configuration transfer."""

from __future__ import annotations

import re
from collections import Counter
from datetime import UTC, datetime
from math import isfinite
from typing import Literal
from urllib.parse import urlsplit, urlunsplit

from pydantic import BaseModel, Field, field_validator, model_validator

from cleanarr.api.dashboard import ActivityStore, HealthProbeStore, WebhookAttemptStore
from cleanarr.application.deletion_jobs import ManualDeletionJobService
from cleanarr.application.ports import DownloadsRepositoryPort
from cleanarr.domain.config import (
    CURRENT_CONFIG_SCHEMA_VERSION,
    BaseServiceConfig,
    DelugeServiceConfig,
    GeneralConfig,
    JellyfinServiceConfig,
    QbittorrentServiceConfig,
    RadarrServiceConfig,
    RTorrentServiceConfig,
    RuntimeConfig,
    SeerrServiceConfig,
    ServiceKind,
    SonarrServiceConfig,
    TorrentRemovalPolicy,
    TransmissionServiceConfig,
)
from cleanarr.infrastructure.database import LATEST_SCHEMA_VERSION

CONFIG_EXPORT_SCHEMA_VERSION: Literal[1] = 1
_SAFE_HEALTH_STATUSES = {"healthy", "unreachable", "unconfigured", "unknown"}
_SAFE_WEBHOOK_OUTCOMES = {
    "accepted",
    "completed",
    "duplicate",
    "ignored",
    "rejected_auth",
    "rejected_payload",
    "failed",
}
_DOWNSTREAM_SERVICES = {
    "Radarr": "radarr",
    "Sonarr": "sonarr",
    "Jellyfin": "jellyfin",
    "Seerr": "seerr",
    "Downloader": "downloader",
}
_SAFE_VERSION_RE = re.compile(r"^[0-9A-Za-z][0-9A-Za-z.+_-]{0,63}$")
_SAFE_CORRELATION_ID_RE = re.compile(r"^[0-9a-f]{32}$")


class RedactedGeneralConfig(BaseModel):
    """Non-secret global settings safe to transfer between installations."""

    log_level: str
    http_timeout_seconds: float
    activity_retention_days: int
    storage_warning_free_percent: float = Field(default=15.0, ge=0.0, le=100.0)
    storage_critical_free_percent: float = Field(default=5.0, ge=0.0, le=100.0)
    jellyfin_language: str
    ui_language: str

    @model_validator(mode="after")
    def validate_storage_thresholds(self) -> RedactedGeneralConfig:
        if not isfinite(self.storage_warning_free_percent) or not isfinite(self.storage_critical_free_percent):
            raise ValueError("Storage free-space thresholds must be finite numbers.")
        if not 0 <= self.storage_critical_free_percent < self.storage_warning_free_percent <= 100:
            raise ValueError("Storage thresholds must satisfy 0 <= critical < warning <= 100.")
        return self


class RedactedServiceConfig(BaseModel):
    """Service shape without credentials or URL-carried secrets."""

    id: str
    kind: ServiceKind
    name: str
    url: str
    enabled: bool
    is_default: bool
    seeding_policy: TorrentRemovalPolicy | None = None
    min_seed_ratio: float | None = Field(default=None, ge=0)
    min_seed_time_minutes: int | None = Field(default=None, ge=1)

    @field_validator("url", mode="before")
    @classmethod
    def remove_url_credentials(cls, value: object) -> str:
        return _sanitize_transfer_url(str(value))


class RedactedConfigExport(BaseModel):
    """Versioned, credential-free configuration transfer document."""

    export_schema_version: Literal[1] = CONFIG_EXPORT_SCHEMA_VERSION
    source_config_schema_version: int = CURRENT_CONFIG_SCHEMA_VERSION
    exported_at: datetime
    safety_notice: str
    general: RedactedGeneralConfig
    services: list[RedactedServiceConfig]

    @model_validator(mode="after")
    def reject_duplicate_profiles(self) -> RedactedConfigExport:
        identities = [(service.kind, service.id) for service in self.services]
        if len(identities) != len(set(identities)):
            raise ValueError("A configuration export cannot contain duplicate service kind/ID pairs.")
        return self


class ConfigImportResponse(BaseModel):
    """Safety outcome of a redacted configuration import."""

    imported_profiles: int
    updated_profiles: int
    added_profiles: int
    dry_run: bool
    all_imported_profiles_disabled: bool
    message: str


class SupportActionCode(BaseModel):
    """Structured action fields that cannot contain media or credential data."""

    system: str
    action: str
    status: str
    reason: str | None


class SupportErrorRecord(BaseModel):
    """Redacted processing failure suitable for a support attachment."""

    processed_at: datetime
    correlation_id: str
    item_type: str
    status: str
    actions: list[SupportActionCode]


class SupportDownstreamRecord(BaseModel):
    """Non-identifying downstream state."""

    service: str
    configured_count: int
    enabled_count: int
    health_status: str
    version: str


class SupportBundle(BaseModel):
    """Credential- and media-name-free support snapshot."""

    generated_at: datetime
    cleanarr_version: str
    config_schema_version: int
    database_schema_version: int
    dry_run: bool
    storage_warning_free_percent: float = 15.0
    storage_critical_free_percent: float = 5.0
    downstream: list[SupportDownstreamRecord]
    recent_errors: list[SupportErrorRecord]
    webhook_outcomes: dict[str, int]
    manual_job_statuses: dict[str, int]
    download_action_statuses: dict[str, int] = Field(default_factory=dict)
    policy_decisions: dict[str, int] = Field(default_factory=dict)
    redaction_notice: str


def export_redacted_config(config: RuntimeConfig) -> RedactedConfigExport:
    """Create an explicitly versioned export with every credential omitted."""

    services = [
        RedactedServiceConfig(
            id=service.id,
            kind=service.kind,
            name=service.name,
            url=_sanitize_transfer_url(service.url),
            enabled=service.enabled,
            is_default=service.is_default,
            seeding_policy=getattr(service, "seeding_policy", None),
            min_seed_ratio=getattr(service, "min_seed_ratio", None),
            min_seed_time_minutes=getattr(service, "min_seed_time_minutes", None),
        )
        for service in [
            *config.radarr,
            *config.sonarr,
            *config.seerr,
            *config.downloaders,
            *config.jellyfin,
        ]
    ]
    return RedactedConfigExport(
        exported_at=datetime.now(UTC),
        safety_notice=(
            "Credentials and authentication settings are excluded. Imported profiles are disabled "
            "and dry-run is forced."
        ),
        general=RedactedGeneralConfig(
            log_level=config.general.log_level,
            http_timeout_seconds=config.general.http_timeout_seconds,
            activity_retention_days=config.general.activity_retention_days,
            storage_warning_free_percent=config.general.storage_warning_free_percent,
            storage_critical_free_percent=config.general.storage_critical_free_percent,
            jellyfin_language=config.general.jellyfin_language,
            ui_language=config.general.ui_language,
        ),
        services=services,
    )


def import_redacted_config(
    current: RuntimeConfig,
    document: RedactedConfigExport,
) -> tuple[RuntimeConfig, ConfigImportResponse]:
    """Merge a redacted export without deleting profiles or crossing auth boundaries."""

    general = _merge_safe_general(current.general, document.general)
    groups: dict[ServiceKind, list[BaseServiceConfig]] = {
        ServiceKind.RADARR: list(current.radarr),
        ServiceKind.SONARR: list(current.sonarr),
        ServiceKind.SEERR: list(current.seerr),
        ServiceKind.QBITTORRENT: [s for s in current.downloaders if s.kind is ServiceKind.QBITTORRENT],
        ServiceKind.TRANSMISSION: [s for s in current.downloaders if s.kind is ServiceKind.TRANSMISSION],
        ServiceKind.DELUGE: [s for s in current.downloaders if s.kind is ServiceKind.DELUGE],
        ServiceKind.RTORRENT: [s for s in current.downloaders if s.kind is ServiceKind.RTORRENT],
        ServiceKind.JELLYFIN: list(current.jellyfin),
    }
    updated = 0
    added = 0
    for imported in document.services:
        profiles = groups[imported.kind]
        existing_index = next(
            (index for index, profile in enumerate(profiles) if getattr(profile, "id", None) == imported.id),
            None,
        )
        if existing_index is None:
            profiles.append(_new_disabled_profile(imported))
            added += 1
        else:
            profiles[existing_index] = _update_disabled_profile(profiles[existing_index], imported)
            updated += 1

    downloaders = [
        *groups[ServiceKind.QBITTORRENT],
        *groups[ServiceKind.TRANSMISSION],
        *groups[ServiceKind.DELUGE],
        *groups[ServiceKind.RTORRENT],
    ]
    merged = RuntimeConfig.model_validate(
        {
            "config_schema_version": current.config_schema_version,
            "admin": current.admin.model_dump(),
            "general": general.model_dump(),
            "radarr": [profile.model_dump() for profile in groups[ServiceKind.RADARR]],
            "sonarr": [profile.model_dump() for profile in groups[ServiceKind.SONARR]],
            "seerr": [profile.model_dump() for profile in groups[ServiceKind.SEERR]],
            "downloaders": [profile.model_dump() for profile in downloaders],
            "jellyfin": [profile.model_dump() for profile in groups[ServiceKind.JELLYFIN]],
        }
    )
    return merged, ConfigImportResponse(
        imported_profiles=len(document.services),
        updated_profiles=updated,
        added_profiles=added,
        dry_run=True,
        all_imported_profiles_disabled=True,
        message=(
            "Import completed in dry-run mode. Re-enter credentials, test each profile, and enable it explicitly."
        ),
    )


async def render_metrics(
    *,
    version: str,
    config: RuntimeConfig,
    activity_store: ActivityStore,
    webhook_attempt_store: WebhookAttemptStore,
    health_probe_store: HealthProbeStore,
    deletion_jobs: ManualDeletionJobService,
    downloads_repository: DownloadsRepositoryPort | None = None,
) -> str:
    """Render Prometheus text with only bounded, non-identifying labels."""

    activity_counts = await activity_store.metric_counts()
    health = health_probe_store.snapshot()
    service_counts = _service_counts(config)
    webhook_counts = Counter(_safe_webhook_outcome(record.outcome) for record in webhook_attempt_store.snapshot(80))
    job_counts = Counter(job.status.value for job in deletion_jobs.list_jobs())
    download_action_counts = downloads_repository.action_status_counts() if downloads_repository is not None else {}
    policy_counts = downloads_repository.policy_decision_counts() if downloads_repository is not None else {}

    lines = [
        "# HELP cleanarr_info CleanArr build information.",
        "# TYPE cleanarr_info gauge",
        f'cleanarr_info{{version="{_escape_label(version)}"}} 1',
        "# HELP cleanarr_dry_run Whether destructive operations are disabled globally.",
        "# TYPE cleanarr_dry_run gauge",
        f"cleanarr_dry_run {1 if config.general.dry_run else 0}",
        "# HELP cleanarr_configured_services Configured downstream profiles by integration kind.",
        "# TYPE cleanarr_configured_services gauge",
    ]
    for service, count in sorted(service_counts.items()):
        lines.append(f'cleanarr_configured_services{{service="{service}"}} {count}')
    lines.extend(
        [
            "# HELP cleanarr_downstream_health Latest downstream health by bounded service and status.",
            "# TYPE cleanarr_downstream_health gauge",
        ]
    )
    for display_name, service in _DOWNSTREAM_SERVICES.items():
        raw_status = health.get(display_name, "unknown")
        health_status = raw_status if raw_status in _SAFE_HEALTH_STATUSES else "unknown"
        lines.append(f'cleanarr_downstream_health{{service="{service}",status="{health_status}"}} 1')
    lines.extend(
        [
            "# HELP cleanarr_retained_operations Retained processing results by bounded item type and status.",
            "# TYPE cleanarr_retained_operations gauge",
        ]
    )
    for (item_type, result_status), count in sorted(activity_counts.items()):
        lines.append(
            "cleanarr_retained_operations"
            f'{{item_type="{_escape_label(item_type)}",status="{_escape_label(result_status)}"}} {count}'
        )
    lines.extend(
        [
            "# HELP cleanarr_retained_webhook_attempts Retained webhook delivery attempts by bounded outcome.",
            "# TYPE cleanarr_retained_webhook_attempts gauge",
        ]
    )
    for outcome, count in sorted(webhook_counts.items()):
        lines.append(f'cleanarr_retained_webhook_attempts{{outcome="{outcome}"}} {count}')
    lines.extend(
        [
            "# HELP cleanarr_manual_jobs Manual deletion jobs by status.",
            "# TYPE cleanarr_manual_jobs gauge",
        ]
    )
    for job_status, count in sorted(job_counts.items()):
        lines.append(f'cleanarr_manual_jobs{{status="{_escape_label(job_status)}"}} {count}')
    lines.extend(
        [
            "# HELP cleanarr_download_actions Reversible download actions by bounded status.",
            "# TYPE cleanarr_download_actions gauge",
        ]
    )
    for action_status, count in sorted(download_action_counts.items()):
        lines.append(f'cleanarr_download_actions{{status="{_escape_label(action_status)}"}} {count}')
    lines.extend(
        [
            "# HELP cleanarr_download_policy_decisions Policy evaluations by bounded decision.",
            "# TYPE cleanarr_download_policy_decisions gauge",
        ]
    )
    for decision, count in sorted(policy_counts.items()):
        lines.append(f'cleanarr_download_policy_decisions{{decision="{_escape_label(decision)}"}} {count}')
    return "\n".join(lines) + "\n"


async def build_support_bundle(
    *,
    version: str,
    config: RuntimeConfig,
    activity_store: ActivityStore,
    webhook_attempt_store: WebhookAttemptStore,
    health_probe_store: HealthProbeStore,
    deletion_jobs: ManualDeletionJobService,
    downloads_repository: DownloadsRepositoryPort | None = None,
) -> SupportBundle:
    """Build a support snapshot without media names, IDs, URLs, or secrets."""

    activity = await activity_store.snapshot(limit=50)
    health = health_probe_store.snapshot()
    versions = health_probe_store.version_snapshot()
    counts = _service_counts(config)
    enabled_counts = _enabled_service_counts(config)
    recent_errors = []
    for record in activity:
        coded_actions = [
            SupportActionCode(
                system=action.system,
                action=action.action,
                status=action.status.value,
                reason=action.reason.value if action.reason is not None else None,
            )
            for action in record.result.actions
            if action.reason is not None or action.status.value == "failed"
        ]
        if record.result.status.value != "partial_failure" and not coded_actions:
            continue
        recent_errors.append(
            SupportErrorRecord(
                processed_at=record.processed_at,
                correlation_id=_safe_correlation_id(record.result.correlation_id),
                item_type=record.result.item_type.value,
                status=record.result.status.value,
                actions=coded_actions,
            )
        )

    webhook_counts = Counter(_safe_webhook_outcome(record.outcome) for record in webhook_attempt_store.snapshot(80))
    job_counts = Counter(job.status.value for job in deletion_jobs.list_jobs())
    download_action_counts = downloads_repository.action_status_counts() if downloads_repository is not None else {}
    policy_counts = downloads_repository.policy_decision_counts() if downloads_repository is not None else {}
    downstream = []
    for display_name, service_key in _DOWNSTREAM_SERVICES.items():
        configured_count = (
            sum(counts[kind] for kind in ("qbittorrent", "transmission", "deluge", "rtorrent"))
            if service_key == "downloader"
            else counts.get(service_key, 0)
        )
        enabled_count = (
            sum(enabled_counts[kind] for kind in ("qbittorrent", "transmission", "deluge", "rtorrent"))
            if service_key == "downloader"
            else enabled_counts.get(service_key, 0)
        )
        downstream.append(
            SupportDownstreamRecord(
                service=service_key,
                configured_count=configured_count,
                enabled_count=enabled_count,
                health_status=health.get(display_name, "unknown"),
                version=_safe_version(versions.get(display_name, "unknown"), service_key=service_key),
            )
        )
    return SupportBundle(
        generated_at=datetime.now(UTC),
        cleanarr_version=version,
        config_schema_version=config.config_schema_version,
        database_schema_version=LATEST_SCHEMA_VERSION,
        dry_run=config.general.dry_run,
        storage_warning_free_percent=config.general.storage_warning_free_percent,
        storage_critical_free_percent=config.general.storage_critical_free_percent,
        downstream=downstream,
        recent_errors=recent_errors,
        webhook_outcomes=dict(sorted(webhook_counts.items())),
        manual_job_statuses=dict(sorted(job_counts.items())),
        download_action_statuses=dict(sorted(download_action_counts.items())),
        policy_decisions=dict(sorted(policy_counts.items())),
        redaction_notice=(
            "Media names, media IDs, paths, service names, URLs, credentials, messages, "
            "and action details are excluded."
        ),
    )


def _merge_safe_general(current: GeneralConfig, imported: RedactedGeneralConfig) -> GeneralConfig:
    return current.model_copy(
        update={
            "dry_run": True,
            "log_level": imported.log_level,
            "http_timeout_seconds": imported.http_timeout_seconds,
            "activity_retention_days": imported.activity_retention_days,
            "storage_warning_free_percent": imported.storage_warning_free_percent,
            "storage_critical_free_percent": imported.storage_critical_free_percent,
            "jellyfin_language": imported.jellyfin_language,
            "ui_language": imported.ui_language,
        }
    )


def _new_disabled_profile(imported: RedactedServiceConfig) -> BaseServiceConfig:
    common = {
        "id": imported.id,
        "name": imported.name,
        "url": imported.url,
        "enabled": False,
        "is_default": False,
    }
    downloader = {
        **common,
        "seeding_policy": imported.seeding_policy or TorrentRemovalPolicy.IMMEDIATE,
        "min_seed_ratio": imported.min_seed_ratio,
        "min_seed_time_minutes": imported.min_seed_time_minutes,
    }
    if imported.kind is ServiceKind.RADARR:
        return RadarrServiceConfig.model_validate({**common, "api_key": ""})
    if imported.kind is ServiceKind.SONARR:
        return SonarrServiceConfig.model_validate({**common, "api_key": ""})
    if imported.kind is ServiceKind.SEERR:
        return SeerrServiceConfig.model_validate({**common, "api_key": ""})
    if imported.kind is ServiceKind.JELLYFIN:
        return JellyfinServiceConfig.model_validate({**common, "api_key": ""})
    if imported.kind is ServiceKind.QBITTORRENT:
        return QbittorrentServiceConfig.model_validate({**downloader, "username": "", "password": "", "api_key": None})
    if imported.kind is ServiceKind.TRANSMISSION:
        return TransmissionServiceConfig.model_validate({**downloader, "username": "", "password": ""})
    if imported.kind is ServiceKind.DELUGE:
        return DelugeServiceConfig.model_validate({**downloader, "password": ""})
    return RTorrentServiceConfig.model_validate({**downloader, "username": "", "password": ""})


def _update_disabled_profile(
    existing: BaseServiceConfig,
    imported: RedactedServiceConfig,
) -> BaseServiceConfig:
    updates: dict[str, object] = {
        "name": imported.name,
        "url": imported.url,
        "enabled": False,
        "is_default": False,
    }
    if imported.kind in {
        ServiceKind.QBITTORRENT,
        ServiceKind.TRANSMISSION,
        ServiceKind.DELUGE,
        ServiceKind.RTORRENT,
    }:
        updates.update(
            {
                "seeding_policy": imported.seeding_policy or TorrentRemovalPolicy.IMMEDIATE,
                "min_seed_ratio": imported.min_seed_ratio,
                "min_seed_time_minutes": imported.min_seed_time_minutes,
            }
        )
    return existing.model_copy(update=updates)


def _service_counts(config: RuntimeConfig) -> Counter[str]:
    return Counter(
        service.kind.value
        for service in [*config.radarr, *config.sonarr, *config.seerr, *config.downloaders, *config.jellyfin]
    )


def _enabled_service_counts(config: RuntimeConfig) -> Counter[str]:
    return Counter(
        service.kind.value
        for service in [*config.radarr, *config.sonarr, *config.seerr, *config.downloaders, *config.jellyfin]
        if service.enabled
    )


def _sanitize_transfer_url(raw_url: str) -> str:
    parsed = urlsplit(raw_url)
    hostname = parsed.hostname or ""
    if ":" in hostname and not hostname.startswith("["):
        hostname = f"[{hostname}]"
    try:
        port = f":{parsed.port}" if parsed.port is not None else ""
    except ValueError:
        port = ""
    return urlunsplit((parsed.scheme, f"{hostname}{port}", parsed.path, "", ""))


def _safe_webhook_outcome(value: str) -> str:
    return value if value in _SAFE_WEBHOOK_OUTCOMES else "other"


def _safe_correlation_id(value: str | None) -> str:
    return value if value is not None and _SAFE_CORRELATION_ID_RE.fullmatch(value) else "legacy-no-correlation-id"


def _safe_version(value: str, *, service_key: str) -> str:
    if service_key != "downloader":
        return value if _SAFE_VERSION_RE.fullmatch(value) else "unknown"

    parts = value.split(", ")
    allowed_kinds = {"qbittorrent", "transmission", "deluge", "rtorrent"}
    for part in parts:
        kind, separator, version = part.partition("=")
        if not separator or kind not in allowed_kinds or not _SAFE_VERSION_RE.fullmatch(version):
            return "unknown"
    return value


def _escape_label(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')
