"""Authenticated storage-health API projections."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal, cast

from pydantic import BaseModel

from cleanarr.application.storage import headline_status, rendered_volumes, storage_freshness, volume_freshness
from cleanarr.domain import StorageSnapshot


class StorageVolumeResponse(BaseModel):
    """One privacy-safe Arr volume observation; raw paths never leave the server."""

    volume_id: str
    service: Literal["radarr", "sonarr"]
    service_type: Literal["radarr", "sonarr"]
    service_id: str
    profile_id: str
    profile_name: str | None = None
    root_folder_id: int | None = None
    free_bytes: int | None = None
    total_bytes: int | None = None
    free_percent: float | None = None
    status: Literal["healthy", "warning", "critical", "unknown"]
    freshness: Literal["fresh", "stale", "unknown"]
    observed_at: datetime
    display_label: str
    error_code: str | None = None
    possible_duplicate: bool = False


class StorageThresholdsResponse(BaseModel):
    """Configured free-space boundaries used by the headline."""

    warning_free_percent: float
    critical_free_percent: float


class StorageResponse(BaseModel):
    """Storage dashboard response with a truthful collection headline."""

    generated_at: datetime
    headline: Literal["healthy", "warning", "critical", "unknown"]
    status: Literal["healthy", "warning", "critical", "unknown"]
    freshness: Literal["fresh", "stale", "unknown"]
    partial: bool
    volumes: list[StorageVolumeResponse]
    error_codes: list[str]
    warning_free_percent: float
    critical_free_percent: float
    thresholds: StorageThresholdsResponse

    @classmethod
    def from_snapshot(
        cls,
        snapshot: StorageSnapshot,
        *,
        warning_free_percent: float = 15.0,
        critical_free_percent: float = 5.0,
    ) -> StorageResponse:
        now = datetime.now(UTC)
        freshness = storage_freshness(snapshot, now=now)
        volumes = rendered_volumes(snapshot, now=now)
        headline = headline_status(snapshot, now=now)
        return cls(
            generated_at=snapshot.collected_at,
            headline=headline,
            status=headline,
            freshness=freshness,
            partial=snapshot.partial,
            volumes=[
                StorageVolumeResponse(
                    volume_id=volume.volume_id,
                    service=volume.service_kind,
                    service_type=volume.service_kind,
                    service_id=volume.profile_id,
                    profile_id=volume.profile_id,
                    profile_name=volume.profile_name,
                    root_folder_id=volume.root_folder_id,
                    free_bytes=volume.free_bytes,
                    total_bytes=volume.total_bytes,
                    free_percent=volume.free_percent,
                    status=cast(Literal["healthy", "warning", "critical", "unknown"], volume.status),
                    freshness=volume_freshness(volume, now=now),
                    observed_at=volume.collected_at,
                    display_label=volume.display_label,
                    error_code=volume.error_code,
                    possible_duplicate=volume.possible_duplicate,
                )
                for volume in volumes
            ],
            error_codes=list(snapshot.error_codes),
            warning_free_percent=warning_free_percent,
            critical_free_percent=critical_free_percent,
            thresholds=StorageThresholdsResponse(
                warning_free_percent=warning_free_percent,
                critical_free_percent=critical_free_percent,
            ),
        )
