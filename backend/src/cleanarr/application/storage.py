"""Bounded, fail-closed storage health collection."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import math
import posixpath
import time
from collections.abc import Callable, Sequence
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import PurePosixPath
from typing import Literal, Protocol, cast

from cleanarr.domain import (
    StorageDiskSpace,
    StorageProfileListing,
    StorageRootFolder,
    StorageSnapshot,
    StorageVolume,
)
from cleanarr.domain.config import RuntimeConfig

_logger = logging.getLogger("cleanarr.storage")
_COLLECT_CACHE_SECONDS = 60.0
_FRESHNESS_SECONDS = 120.0
_MANUAL_REFRESH_SECONDS = 10.0
_StorageStatus = Literal["healthy", "warning", "critical", "unknown"]
_StorageFreshness = Literal["fresh", "stale", "unknown"]


class StorageReadClient(Protocol):
    """Minimal Arr client contract needed by the collector."""

    async def list_root_folders(self) -> Sequence[StorageRootFolder]: ...

    async def list_disk_space(self) -> Sequence[StorageDiskSpace]: ...


class RoutedStorageReadClient(StorageReadClient, Protocol):
    """Optional multi-profile storage boundary implemented by infrastructure."""

    async def list_storage(self) -> Sequence[StorageProfileListing]: ...


class StorageRefreshThrottledError(RuntimeError):
    """A manual refresh was requested inside the bounded throttle window."""

    code = "refresh_throttled"


class StorageCursorNotApplicableError(RuntimeError):
    """Reserved transport-neutral error for future storage cursors."""


class StorageService:
    """Collect Radarr/Sonarr volume state with coalescing and bounded freshness."""

    def __init__(
        self,
        *,
        config: Callable[[], RuntimeConfig],
        radarr: Callable[[], object],
        sonarr: Callable[[], object],
        now: Callable[[], float] | None = None,
    ) -> None:
        self._config = config
        self._radarr = radarr
        self._sonarr = sonarr
        self._now = now or time.monotonic
        self._snapshot: StorageSnapshot | None = None
        self._snapshot_monotonic: float | None = None
        self._snapshot_topology: str | None = None
        self._collection_task: asyncio.Task[StorageSnapshot] | None = None
        self._manual_collection_task: asyncio.Task[StorageSnapshot] | None = None
        self._last_manual_refresh: float | None = None
        self._lock = asyncio.Lock()

    async def get(self) -> StorageSnapshot:
        """Return a cached snapshot or coalesce one automatic collection."""

        snapshot = self._snapshot
        topology = _storage_topology(self._config())
        if (
            snapshot is not None
            and self._snapshot_monotonic is not None
            and self._snapshot_topology == topology
            and self._now() - self._snapshot_monotonic < _COLLECT_CACHE_SECONDS
        ):
            return snapshot
        return await self._collect_coalesced()

    async def refresh(self) -> StorageSnapshot:
        """Force one collection, coalescing concurrent callers and throttling manual calls."""

        async with self._lock:
            current = self._now()
            existing = self._collection_task
            if existing is not None and not existing.done():
                if self._manual_collection_task is not existing:
                    if (
                        self._last_manual_refresh is not None
                        and current - self._last_manual_refresh < _MANUAL_REFRESH_SECONDS
                    ):
                        raise StorageRefreshThrottledError(
                            "Storage refresh was requested too recently; wait before trying again."
                        )
                    self._last_manual_refresh = current
                    self._manual_collection_task = existing
                task = existing
            else:
                if (
                    self._last_manual_refresh is not None
                    and current - self._last_manual_refresh < _MANUAL_REFRESH_SECONDS
                ):
                    raise StorageRefreshThrottledError(
                        "Storage refresh was requested too recently; wait before trying again."
                    )
                self._last_manual_refresh = current
                task = asyncio.create_task(self._collect(), name="cleanarr-storage-refresh")
                self._collection_task = task
                self._manual_collection_task = task
        return await task

    async def _collect_coalesced(self) -> StorageSnapshot:
        async with self._lock:
            existing = self._collection_task
            if existing is None or existing.done():
                task = asyncio.create_task(self._collect(), name="cleanarr-storage-collection")
                self._collection_task = task
            else:
                task = existing
        return await task

    async def _collect(self) -> StorageSnapshot:
        collected_at = datetime.now(UTC)
        config = self._config()
        topology = _storage_topology(config)
        previous_snapshot = self._snapshot if self._snapshot_topology == topology else None
        sources = await asyncio.gather(
            self._read_source("radarr", self._radarr(), config.radarr),
            self._read_source("sonarr", self._sonarr(), config.sonarr),
        )
        listings = [listing for source in sources for listing in source]
        partial = False
        errors: list[str] = []
        volumes: list[StorageVolume] = []
        volume_paths: list[str] = []
        failed_profiles: dict[tuple[str, str], str] = {}
        for listing in listings:
            if listing.error_code is not None:
                partial = True
                errors.append(listing.error_code)
                if not listing.roots:
                    failed_profiles[(listing.service_kind, listing.service_id)] = listing.error_code
            for root in listing.roots:
                disk_space = None if root.accessible is False else _best_disk_space(root, listing.disk_spaces)
                free_bytes: int | None
                total_bytes: int | None
                free_percent: float | None
                if root.accessible is False:
                    partial = True
                    errors.append("root_folder_inaccessible")
                    free_bytes = None
                    total_bytes = None
                    free_percent = None
                    status = "unknown"
                    error_code = "root_folder_inaccessible"
                elif disk_space is None:
                    partial = True
                    errors.append("disk_space_missing")
                    free_bytes = None
                    total_bytes = None
                    free_percent = None
                    status = "unknown"
                    error_code = "disk_space_missing"
                else:
                    free_bytes = disk_space.free_bytes
                    total_bytes = disk_space.total_bytes
                    free_percent = _free_percent(free_bytes, total_bytes)
                    status = _threshold_status(
                        free_percent,
                        warning=config.general.storage_warning_free_percent,
                        critical=config.general.storage_critical_free_percent,
                    )
                    error_code = None
                    if status == "unknown":
                        partial = True
                        errors.append("disk_space_invalid")
                        error_code = "disk_space_invalid"
                volume_paths.append(_normalize_path(root.path))
                volumes.append(
                    StorageVolume(
                        volume_id=_volume_id(
                            service_kind=listing.service_kind,
                            profile_id=listing.service_id,
                            root=root,
                        ),
                        service_kind=listing.service_kind,
                        profile_id=listing.service_id,
                        profile_name=listing.service_name,
                        root_folder_id=root.folder_id,
                        free_bytes=free_bytes,
                        total_bytes=total_bytes,
                        free_percent=free_percent,
                        status=status,
                        collected_at=collected_at,
                        error_code=error_code,
                        display_label=_display_label(listing.service_kind, listing.service_name, root.folder_id),
                    )
                )
        if previous_snapshot is not None and failed_profiles:
            current_volume_ids = {volume.volume_id for volume in volumes}
            for previous in previous_snapshot.volumes:
                error_code = failed_profiles.get((previous.service_kind, previous.profile_id))
                if error_code is None or previous.volume_id in current_volume_ids:
                    continue
                # A failed refresh invalidates the status immediately, but the
                # last numeric observation remains useful when clearly marked
                # stale.  Never promote it back to a healthy deletion signal.
                volumes.append(replace(previous, status="unknown", error_code=error_code))
        duplicate_paths = {path for path in volume_paths if volume_paths.count(path) > 1}
        if duplicate_paths:
            volumes = [
                StorageVolume(
                    volume_id=volume.volume_id,
                    service_kind=volume.service_kind,
                    profile_id=volume.profile_id,
                    profile_name=volume.profile_name,
                    root_folder_id=volume.root_folder_id,
                    free_bytes=volume.free_bytes,
                    total_bytes=volume.total_bytes,
                    free_percent=volume.free_percent,
                    status=volume.status,
                    collected_at=volume.collected_at,
                    error_code=volume.error_code,
                    display_label=volume.display_label,
                    possible_duplicate=volume.possible_duplicate
                    or _volume_path_for_id(volume.volume_id, listings, duplicate_paths),
                )
                for volume in volumes
            ]
        if not listings or not volumes:
            configured = any(profile.enabled for profile in [*config.radarr, *config.sonarr])
            if configured:
                partial = True
                errors.append("storage_unavailable")
        snapshot = StorageSnapshot(
            volumes=tuple(volumes),
            collected_at=collected_at,
            partial=partial,
            error_codes=tuple(dict.fromkeys(errors)),
        )
        self._snapshot = snapshot
        self._snapshot_monotonic = self._now()
        self._snapshot_topology = topology
        return snapshot

    async def _read_source(
        self,
        service_kind: Literal["radarr", "sonarr"],
        client: object,
        profiles: Sequence[object],
    ) -> tuple[StorageProfileListing, ...]:
        """Read one Arr family; Multi clients preserve profile boundaries."""

        configured = [profile for profile in profiles if bool(getattr(profile, "enabled", False))]
        list_storage = getattr(client, "list_storage", None)
        if callable(list_storage):
            try:
                value = await list_storage()
                if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
                    raise ValueError("malformed routed storage metadata")
                if any(not isinstance(item, StorageProfileListing) for item in value):
                    raise ValueError("malformed routed storage metadata")
                normalized = tuple(value)
            except Exception:  # noqa: BLE001 - health reads fail closed
                _logger.warning("Storage read failed for %s", service_kind)
                return tuple(_unavailable_listing(service_kind, profile) for profile in configured) or (
                    _unavailable_listing(service_kind, None),
                )
            expected = {str(getattr(profile, "id", "")): profile for profile in configured}
            if not expected:
                return ()
            routed: list[StorageProfileListing] = []
            for profile_id, profile in expected.items():
                matches = [
                    listing
                    for listing in normalized
                    if listing.service_kind == service_kind and listing.service_id == profile_id
                ]
                routed.append(matches[0] if len(matches) == 1 else _unavailable_listing(service_kind, profile))
            return tuple(routed)

        try:
            storage_client = cast(StorageReadClient, client)
            roots_value, spaces_value = await asyncio.gather(
                storage_client.list_root_folders(),
                storage_client.list_disk_space(),
            )
            roots = tuple(_coerce_root(item) for item in roots_value)
            spaces = tuple(_coerce_space(item) for item in spaces_value)
            if any(item is None for item in (*roots, *spaces)):
                raise ValueError("malformed storage metadata")
            root_values = tuple(item for item in roots if item is not None)
            space_values = tuple(item for item in spaces if item is not None)
        except Exception:  # noqa: BLE001 - health reads fail closed
            _logger.warning("Storage read failed for %s", service_kind)
            return tuple(_unavailable_listing(service_kind, profile) for profile in configured) or (
                _unavailable_listing(service_kind, None),
            )
        if not configured:
            return ()
        if len(configured) == 1:
            profile = configured[0]
            return (
                StorageProfileListing(
                    service_kind=service_kind,
                    service_id=str(getattr(profile, "id", "unconfigured")),
                    service_name=_safe_profile_name(profile),
                    roots=tuple(_replace_root_identity(root, profile) for root in root_values),
                    disk_spaces=space_values,
                ),
            )
        # A non-routed fake/client cannot safely attribute paths to multiple
        # profiles.  Keep all profiles visible as unavailable rather than
        # guessing ownership or aggregating them.
        return tuple(_unavailable_listing(service_kind, profile) for profile in configured)


def volume_freshness(volume: StorageVolume, *, now: datetime | None = None) -> _StorageFreshness:
    """Classify one observation independently from other service profiles."""

    current = now or datetime.now(UTC)
    age = max(0.0, (current - volume.collected_at).total_seconds())
    has_numeric_sample = volume.free_bytes is not None and volume.total_bytes is not None
    if age > _FRESHNESS_SECONDS:
        return "stale" if has_numeric_sample else "unknown"
    if volume.error_code is not None:
        return "stale" if has_numeric_sample else "unknown"
    return "fresh"


def storage_freshness(snapshot: StorageSnapshot, *, now: datetime | None = None) -> _StorageFreshness:
    if not snapshot.volumes:
        return "unknown"
    current = now or datetime.now(UTC)
    states = tuple(volume_freshness(volume, now=current) for volume in snapshot.volumes)
    if not snapshot.partial and all(state == "fresh" for state in states):
        return "fresh"
    if any(state in {"fresh", "stale"} for state in states):
        return "stale"
    return "unknown"


def rendered_volumes(snapshot: StorageSnapshot, *, now: datetime | None = None) -> tuple[StorageVolume, ...]:
    """Re-render statuses so cached values become unknown after freshness expiry."""

    current = now or datetime.now(UTC)
    return tuple(
        volume
        if volume_freshness(volume, now=current) == "fresh"
        else replace(volume, status="unknown", error_code=volume.error_code or "stale_observation")
        for volume in snapshot.volumes
    )


def headline_status(snapshot: StorageSnapshot, *, now: datetime | None = None) -> _StorageStatus:
    """Apply the exact critical > unknown > worst-fresh precedence."""

    volumes = rendered_volumes(snapshot, now=now)
    if any(volume.status == "critical" for volume in volumes):
        return "critical"
    if snapshot.partial or any(volume.status == "unknown" for volume in volumes):
        return "unknown"
    if any(volume.status == "warning" for volume in volumes):
        return "warning"
    if any(volume.status == "healthy" for volume in volumes):
        return "healthy"
    return "unknown"


def _threshold_status(value: float | None, *, warning: float, critical: float) -> _StorageStatus:
    if value is None or not math.isfinite(value):
        return "unknown"
    if value >= warning:
        return "healthy"
    if value >= critical:
        return "warning"
    return "critical"


def _free_percent(free_bytes: int | None, total_bytes: int | None) -> float | None:
    if free_bytes is None or total_bytes is None or total_bytes <= 0 or free_bytes < 0 or free_bytes > total_bytes:
        return None
    value = free_bytes * 100.0 / total_bytes
    return value if math.isfinite(value) else None


def _normalize_path(value: str) -> str:
    candidate = value.replace("\\", "/").strip()
    if not candidate:
        return "/"
    # Collapse dot segments before doing lexical ancestor checks. PurePosixPath
    # deliberately retains ``..`` and therefore is insufficient for untrusted
    # Arr paths on its own.
    normalized = posixpath.normpath(str(PurePosixPath(candidate)))
    return normalized if normalized.startswith("/") else f"/{normalized}"


def _is_ancestor(parent: str, child: str) -> bool:
    normalized_parent = _normalize_path(parent).rstrip("/") or "/"
    normalized_child = _normalize_path(child).rstrip("/") or "/"
    return (
        normalized_parent == "/"
        or normalized_child == normalized_parent
        or normalized_child.startswith(f"{normalized_parent}/")
    )


def _best_disk_space(root: StorageRootFolder, spaces: Sequence[StorageDiskSpace]) -> StorageDiskSpace | None:
    candidates = [space for space in spaces if _is_ancestor(space.path, root.path)]
    if not candidates:
        return None
    return max(candidates, key=lambda space: len(_normalize_path(space.path)))


def _volume_id(*, service_kind: str, profile_id: str, root: StorageRootFolder) -> str:
    # The digest is deliberately opaque and profile-scoped: same underlying
    # mount used by Radarr and Sonarr remains two independent observations.
    material = f"{service_kind}\x00{profile_id}\x00{root.folder_id}\x00{_normalize_path(root.path)}".encode()
    return f"v1_{hashlib.sha256(material).hexdigest()[:32]}"


def _display_label(service_kind: str, profile_name: str | None, folder_id: int | None) -> str:
    service = service_kind.capitalize()
    profile = (
        " ".join(profile_name.split()).strip()[:160] if isinstance(profile_name, str) and profile_name.strip() else None
    )
    suffix = f" · root {folder_id}" if folder_id is not None else ""
    return f"{service}{f' · {profile}' if profile else ''}{suffix}"[:240]


def _volume_path_for_id(volume_id: str, listings: Sequence[StorageProfileListing], duplicate_paths: set[str]) -> bool:
    for listing in listings:
        for root in listing.roots:
            if _volume_id(service_kind=listing.service_kind, profile_id=listing.service_id, root=root) == volume_id:
                return _normalize_path(root.path) in duplicate_paths
    return False


def _storage_topology(config: RuntimeConfig) -> str:
    payload = {
        "radarr": [_storage_profile_fingerprint(profile) for profile in config.radarr],
        "sonarr": [_storage_profile_fingerprint(profile) for profile in config.sonarr],
        "warning": config.general.storage_warning_free_percent,
        "critical": config.general.storage_critical_free_percent,
    }
    return hashlib.sha256(repr(payload).encode()).hexdigest()


def _storage_profile_fingerprint(profile: object) -> tuple[object, ...]:
    """Hash connection-sensitive fields without retaining or exposing secrets."""

    api_key = getattr(profile, "api_key", "")
    secret_digest = hashlib.sha256(str(api_key).encode()).hexdigest()
    return (
        getattr(profile, "id", None),
        getattr(profile, "kind", None),
        getattr(profile, "enabled", None),
        getattr(profile, "url", None),
        secret_digest,
    )


def _coerce_root(value: object) -> StorageRootFolder | None:
    if isinstance(value, StorageRootFolder):
        return value
    if not isinstance(value, dict):
        return None
    path = value.get("path")
    if not isinstance(path, str) or not path.strip():
        return None
    folder_id = value.get("id")
    return StorageRootFolder(
        path=path.strip(),
        folder_id=folder_id
        if isinstance(folder_id, int) and not isinstance(folder_id, bool) and folder_id >= 0
        else None,
        accessible=value.get("accessible") if isinstance(value.get("accessible"), bool) else None,
    )


def _coerce_space(value: object) -> StorageDiskSpace | None:
    if isinstance(value, StorageDiskSpace):
        return value
    if not isinstance(value, dict):
        return None
    path = value.get("path")
    if not isinstance(path, str) or not path.strip():
        return None
    free, total = value.get("freeSpace"), value.get("totalSpace")
    return StorageDiskSpace(
        path=path.strip(),
        free_bytes=free if isinstance(free, int) and not isinstance(free, bool) and free >= 0 else None,
        total_bytes=total if isinstance(total, int) and not isinstance(total, bool) and total >= 0 else None,
    )


def _safe_profile_name(profile: object | None) -> str | None:
    value = getattr(profile, "name", None)
    return " ".join(value.split()).strip()[:160] if isinstance(value, str) and value.strip() else None


def _replace_root_identity(root: StorageRootFolder, profile: object) -> StorageRootFolder:
    return StorageRootFolder(
        path=root.path,
        folder_id=root.folder_id,
        accessible=root.accessible,
        service_id=str(getattr(profile, "id", "unconfigured")),
        service_name=_safe_profile_name(profile),
    )


def _unavailable_listing(service_kind: Literal["radarr", "sonarr"], profile: object | None) -> StorageProfileListing:
    return StorageProfileListing(
        service_kind=service_kind,
        service_id=str(getattr(profile, "id", "unavailable")),
        service_name=_safe_profile_name(profile),
        roots=(),
        disk_spaces=(),
        error_code="profile_unavailable",
    )
