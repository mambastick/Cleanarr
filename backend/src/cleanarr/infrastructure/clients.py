"""HTTP adapters for downstream services."""

from __future__ import annotations

import asyncio
import base64
import math
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any
from urllib.parse import quote, urlparse

import httpx

from cleanarr.application.data_safety import (
    MAX_CONTENT_INVENTORY_SCOPES,
    ContentSafetyAssessment,
    assess_content_inventory,
    content_safety_blockers,
    content_safety_skip_reason,
    content_scope_matches,
    read_content_inventory,
    validate_scope_path,
)
from cleanarr.domain import (
    ArtworkData,
    AuthenticationError,
    CleanupMediaType,
    ContentScopeBlocker,
    DownloadControlAction,
    DownloadControlOutcome,
    DownloaderContentInventory,
    DownloaderContentInventoryFailure,
    DownloaderContentScope,
    DownloaderControlResult,
    DownloaderListing,
    DownloaderReadFailure,
    DownloaderRemovalResult,
    ExternalServiceError,
    JellyfinCleanupItem,
    JellyfinItem,
    ListingFreshness,
    PlaybackObservation,
    RadarrHistoryRecord,
    RadarrMovie,
    ResourceNotFoundError,
    SeerrIssue,
    SeerrMedia,
    SeerrRequest,
    SonarrEpisode,
    SonarrEpisodeFile,
    SonarrHistoryRecord,
    SonarrSeries,
    StorageDiskSpace,
    StorageRootFolder,
    TorrentOwnership,
    TorrentSnapshot,
    TorrentState,
)
from cleanarr.domain.config import TorrentRemovalPolicy
from cleanarr.domain.seeding import TorrentSeedingStatus, seeding_policy_skip_reason

_CONTROL_VERIFICATION_DELAYS = (0.0, 0.05, 0.1, 0.2, 0.4, 0.8)
_JELLYFIN_LIBRARY_PAGE_SIZE = 500
_JELLYFIN_LIBRARY_MAX_ITEMS = 20_000
_RADARR_HISTORY_PAGE_SIZE = 1_000
_RADARR_HISTORY_MAX_RECORDS = 10_000


def _optional_datetime(value: object) -> datetime | None:
    """Parse an Arr timestamp without allowing malformed metadata to escape."""

    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(UTC)


def _optional_nonnegative_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, float) and value.is_integer() and value >= 0:
        return int(value)
    return None


def _arr_size_on_disk(item: dict[str, Any]) -> int | None:
    """Prefer an explicit Arr size, retaining a valid zero value."""

    size = _optional_nonnegative_int(item.get("sizeOnDisk"))
    if size is not None:
        return size
    statistics = item.get("statistics")
    return _optional_nonnegative_int(statistics.get("sizeOnDisk")) if isinstance(statistics, dict) else None


def _arr_stat(item: dict[str, Any], key: str) -> object:
    statistics = item.get("statistics")
    return statistics.get(key) if isinstance(statistics, dict) else None


def _arr_has_files(item: dict[str, Any]) -> bool | None:
    count = _optional_nonnegative_int(_arr_stat(item, "episodeFileCount"))
    return count > 0 if count is not None else None


def _storage_root_folder(value: object) -> StorageRootFolder | None:
    if not isinstance(value, dict):
        return None
    path = value.get("path")
    if not isinstance(path, str) or not path.strip():
        return None
    folder_id = _optional_nonnegative_int(value.get("id"))
    accessible = value.get("accessible")
    return StorageRootFolder(
        path=path.strip(),
        folder_id=folder_id,
        accessible=accessible if isinstance(accessible, bool) else None,
    )


def _storage_disk_space(value: object) -> StorageDiskSpace | None:
    if not isinstance(value, dict):
        return None
    path = value.get("path")
    if not isinstance(path, str) or not path.strip():
        return None
    return StorageDiskSpace(
        path=path.strip(),
        free_bytes=_optional_nonnegative_int(value.get("freeSpace")),
        total_bytes=_optional_nonnegative_int(value.get("totalSpace")),
    )


def _optional_float(value: object) -> float | None:
    if not isinstance(value, (str, int, float)):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_int(value: object) -> int | None:
    if not isinstance(value, (str, int, float)):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_metadata_text(value: object, *, limit: int = 160) -> str | None:
    if not isinstance(value, str):
        return None
    text = " ".join("".join(character for character in value if character.isprintable()).split())[:limit]
    if not text or "://" in text:
        return None
    return text


def _safe_content_path(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    # A displayed path must identify the observed object exactly; never truncate
    # or remove characters to manufacture a different valid-looking path.
    if not value or len(value) > 4096 or not value.isprintable() or "://" in value:
        return None
    text = value
    paths = (PurePosixPath(text), PureWindowsPath(text))
    if not any(path.is_absolute() and ".." not in path.parts and len(path.parts) >= 2 for path in paths):
        return None
    return text


def _qbt_hash(value: object) -> str:
    normalized = value.strip().upper() if isinstance(value, str) else ""
    return (
        normalized
        if len(normalized) in {40, 64} and all(character in "0123456789ABCDEF" for character in normalized)
        else ""
    )


def _qbt_safe_text(value: object, *, limit: int = 160) -> str | None:
    if not isinstance(value, str):
        return None
    text = " ".join(value.split())[:limit]
    return None if not text or "://" in text or text.startswith(("/", "\\")) else text


def _qbt_nonnegative_int(value: object) -> int | None:
    parsed = _optional_int(value)
    return parsed if parsed is not None and parsed >= 0 else None


def _qbt_nonnegative_float(value: object) -> float | None:
    parsed = _optional_float(value)
    return parsed if parsed is not None and parsed >= 0 else None


def _qbt_zero_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value == 0


def _qbt_zero_progress(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
        and float(value) == 0
    )


def _qbt_timestamp(value: object) -> datetime | None:
    parsed = _qbt_nonnegative_int(value)
    if not parsed:
        return None
    try:
        return datetime.fromtimestamp(parsed, tz=UTC)
    except (OverflowError, OSError, ValueError):
        return None


def _qbt_eta(value: object) -> int | None:
    parsed = _qbt_nonnegative_int(value)
    return parsed if parsed is not None and parsed < 8_640_000 else None


def _qbt_failure(client: Any, code: str) -> DownloaderReadFailure:
    return DownloaderReadFailure(
        str(client._service_id or client._system),
        _qbt_safe_text(client._service_name) or client._system,
        client._system,
        code,
    )


def _qbt_snapshot(item: object, *, client: Any) -> TorrentSnapshot | None:
    if not isinstance(item, dict):
        return None
    info_hash = _qbt_hash(item.get("hash"))
    if not info_hash:
        return None
    raw_state = str(item.get("state") or "").casefold()
    state = (
        TorrentState.STOPPED
        if raw_state.startswith(("paused", "stopped"))
        else TorrentState.SEEDING
        if raw_state in {"uploading", "stalledup", "forcedup"}
        else TorrentState.DOWNLOADING
        if raw_state in {"downloading", "stalleddl", "forceddl", "metadl", "allocating", "moving"}
        else TorrentState.QUEUED
        if raw_state in {"queuedup", "queueddl"}
        else TorrentState.CHECKING
        if "check" in raw_state
        else TorrentState.ERROR
        if "error" in raw_state or "missingfiles" in raw_state
        else TorrentState.UNKNOWN
    )
    progress = _optional_float(item.get("progress"))
    if progress is not None and not 0 <= progress <= 1:
        progress = None
    tags = item.get("tags")
    safe_tags = (
        tuple(filter(None, (_qbt_safe_text(tag, limit=64) for tag in tags.split(","))))[:20]
        if isinstance(tags, str)
        else None
    )
    tracker_raw = item.get("tracker")
    tracker = urlparse(tracker_raw).hostname if isinstance(tracker_raw, str) and "://" in tracker_raw else None
    return TorrentSnapshot(
        str(client._service_id or client._system),
        _qbt_safe_text(client._service_name) or client._system,
        client._system,
        info_hash,
        _qbt_safe_text(item.get("name")),
        state,
        datetime.now(tz=UTC),
        progress=progress,
        total_bytes=_qbt_nonnegative_int(item.get("size")),
        downloaded_bytes=_qbt_nonnegative_int(item.get("downloaded")),
        uploaded_bytes=_qbt_nonnegative_int(item.get("uploaded")),
        ratio=_qbt_nonnegative_float(item.get("ratio")),
        seeding_time_seconds=_qbt_nonnegative_int(item.get("seeding_time")),
        download_speed_bytes_per_second=_qbt_nonnegative_int(item.get("dlspeed")),
        upload_speed_bytes_per_second=_qbt_nonnegative_int(item.get("upspeed")),
        eta_seconds=_qbt_eta(item.get("eta")),
        added_at=_qbt_timestamp(item.get("added_on")),
        completed_at=_qbt_timestamp(item.get("completion_on")),
        activity_at=_qbt_timestamp(item.get("last_activity")),
        category=_qbt_safe_text(item.get("category"), limit=64),
        tags=safe_tags,
        tracker_summary=_qbt_safe_text(tracker, limit=120),
        freshness=ListingFreshness.FRESH,
        ownership=TorrentOwnership.UNKNOWN,
    )


def _qbt_find(listing: DownloaderListing, info_hash: str) -> TorrentSnapshot | None:
    return next((torrent for torrent in listing.torrents if torrent.info_hash == info_hash), None)


def _qbt_has_desired_state(state: TorrentState, action: DownloadControlAction) -> bool:
    if action is DownloadControlAction.PAUSE:
        return state is TorrentState.STOPPED
    return state in {TorrentState.DOWNLOADING, TorrentState.SEEDING, TorrentState.QUEUED, TorrentState.CHECKING}


async def _qbt_verify_post_control_state(
    client: QbittorrentClient,
    info_hash: str,
    action: DownloadControlAction,
) -> tuple[TorrentSnapshot | None, str | None]:
    """Poll boundedly for qBittorrent's asynchronously visible state transition."""
    after: TorrentSnapshot | None = None
    failure_code = "post_state_unverified"
    for delay in _CONTROL_VERIFICATION_DELAYS:
        if delay:
            await asyncio.sleep(delay)
        try:
            listing = await client.list_torrents()
        except ExternalServiceError:
            failure_code = "mutation_or_post_read_failed"
            continue
        after = _qbt_find(listing, info_hash)
        if after is not None and _qbt_has_desired_state(after.state, action):
            return after, None
        failure_code = "post_read_incomplete" if after is None and listing.failures else "post_state_unverified"
    return after, failure_code


def _qbt_control_path(version: str, action: DownloadControlAction) -> str | None:
    numeric = version.lstrip("vV").split(".")
    try:
        major = int(numeric[0])
    except (IndexError, ValueError):
        return None
    if major >= 5:
        return "/api/v2/torrents/stop" if action is DownloadControlAction.PAUSE else "/api/v2/torrents/start"
    if major == 4:
        return "/api/v2/torrents/pause" if action is DownloadControlAction.PAUSE else "/api/v2/torrents/resume"
    return None


def _qbt_control(
    client: Any,
    info_hash: str,
    action: DownloadControlAction,
    outcome: DownloadControlOutcome,
    code: str,
    *,
    before: TorrentSnapshot | None = None,
    after: TorrentSnapshot | None = None,
) -> DownloaderControlResult:
    return DownloaderControlResult(
        str(client._service_id or client._system),
        _qbt_safe_text(client._service_name) or client._system,
        client._system,
        info_hash,
        action,
        outcome,
        before,
        after,
        code,
    )


class JsonServiceClient:
    """Small wrapper around httpx with domain-specific errors."""

    def __init__(
        self,
        *,
        system: str,
        base_url: str,
        timeout_seconds: float,
        headers: dict[str, str] | None = None,
    ) -> None:
        self._system = system
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=timeout_seconds,
            headers=headers,
            transport=httpx.AsyncHTTPTransport(retries=1),
        )

    async def close(self) -> None:
        """Close the underlying client."""

        await self._client.aclose()

    async def _request(
        self,
        method: str,
        path: str,
        *,
        expected_statuses: set[int] | None = None,
        treat_forbidden_as_authentication: bool = True,
        **kwargs: Any,
    ) -> Any:
        expected = expected_statuses or {200}
        try:
            response = await self._client.request(method, path, **kwargs)
        except httpx.TimeoutException as exc:
            raise ExternalServiceError(self._system, f"{self._system} request timed out") from exc
        except httpx.HTTPError as exc:
            raise ExternalServiceError(
                self._system,
                f"{self._system} request failed ({exc.__class__.__name__}).",
            ) from exc

        if response.status_code == 401 or (response.status_code == 403 and treat_forbidden_as_authentication):
            raise AuthenticationError(
                self._system,
                f"{self._system} rejected the configured credentials.",
            )
        if response.status_code == 404:
            raise ResourceNotFoundError(
                self._system,
                f"{self._system} resource was already absent.",
            )
        if response.status_code not in expected:
            raise ExternalServiceError(
                self._system,
                f"{self._system} returned unexpected status {response.status_code}.",
            )
        if response.status_code == 204 or not response.content:
            return None
        return response.json()


class RadarrClient(JsonServiceClient):
    """Radarr HTTP client."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        timeout_seconds: float,
        service_id: str | None = None,
        service_name: str | None = None,
    ) -> None:
        super().__init__(
            system="radarr",
            base_url=base_url,
            timeout_seconds=timeout_seconds,
            headers={"X-Api-Key": api_key},
        )
        self._service_id = service_id
        self._service_name = service_name

    async def ping(self) -> None:
        """Verify Radarr connectivity."""
        await self._request("GET", "/system/status")

    async def get_version(self) -> str:
        payload = await self._request("GET", "/system/status")
        return str(payload.get("version") or "unknown") if isinstance(payload, dict) else "unknown"

    async def list_movies(self) -> Sequence[RadarrMovie]:
        payload = await self._request("GET", "/movie")
        return [
            RadarrMovie(
                id=item["id"],
                title=item["title"],
                path=item["path"],
                tmdb_id=item.get("tmdbId"),
                imdb_id=item.get("imdbId"),
                size_on_disk=_arr_size_on_disk(item),
                has_file=item.get("hasFile") if isinstance(item.get("hasFile"), bool) else None,
                added_at=_optional_datetime(item.get("added") or item.get("dateAdded")),
                service_id=self._service_id,
                service_name=self._service_name,
                year=_optional_nonnegative_int(item.get("year")),
            )
            for item in payload
        ]

    async def list_root_folders(self) -> Sequence[StorageRootFolder]:
        """Return Radarr root folders for the storage read model."""

        payload = await self._request("GET", "/rootfolder")
        if not isinstance(payload, list):
            raise ExternalServiceError("radarr", "Radarr returned an invalid root-folder response.")
        roots = [_storage_root_folder(item) for item in payload]
        if any(root is None for root in roots):
            raise ExternalServiceError("radarr", "Radarr returned malformed root-folder metadata.")
        return tuple(root for root in roots if root is not None)

    async def list_disk_space(self) -> Sequence[StorageDiskSpace]:
        """Return Radarr disk-space records for the storage read model."""

        payload = await self._request("GET", "/diskspace")
        if not isinstance(payload, list):
            raise ExternalServiceError("radarr", "Radarr returned an invalid disk-space response.")
        spaces = [_storage_disk_space(item) for item in payload]
        if any(space is None for space in spaces):
            raise ExternalServiceError("radarr", "Radarr returned malformed disk-space metadata.")
        return tuple(space for space in spaces if space is not None)

    async def list_movie_history(self, movie_id: int) -> Sequence[RadarrHistoryRecord]:
        payload = await self._request(
            "GET",
            "/history/movie",
            params={"movieId": movie_id, "page": 1, "pageSize": 1000, "sortKey": "date", "sortDirection": "descending"},
        )
        if isinstance(payload, list):
            records = payload
        elif isinstance(payload, dict) and isinstance(payload.get("records"), list):
            records = payload["records"]
            total = payload.get("totalRecords")
            if isinstance(total, bool) or not isinstance(total, int) or total != len(records):
                raise ExternalServiceError("radarr", "Radarr returned incomplete movie history.")
        else:
            raise ExternalServiceError("radarr", "Radarr returned invalid movie history.")
        if len(records) > 10000 or any(
            not isinstance(item, dict)
            or not isinstance(item.get("id"), int)
            or not isinstance(item.get("movieId"), int)
            or not isinstance(item.get("eventType"), str)
            or not isinstance(item.get("data", {}), dict)
            for item in records
        ):
            raise ExternalServiceError("radarr", "Radarr returned invalid or excessive movie history.")
        return [
            RadarrHistoryRecord(
                id=item["id"],
                movie_id=item["movieId"],
                event_type=item["eventType"],
                download_id=item.get("downloadId") or item.get("data", {}).get("torrentInfoHash"),
                imported_path=item.get("data", {}).get("importedPath"),
            )
            for item in records
        ]

    async def list_download_history(self, download_id: str) -> Sequence[RadarrHistoryRecord]:
        """Return complete, bounded history selected by Radarr's downloadId filter."""
        if not download_id.strip():
            raise ExternalServiceError("radarr", "Radarr download history requires a download identifier.")
        result: list[RadarrHistoryRecord] = []
        seen_ids: set[int] = set()
        expected_total: int | None = None
        page = 1
        while True:
            payload = await self._request(
                "GET",
                "/history",
                params={
                    "downloadId": download_id,
                    "page": page,
                    "pageSize": _RADARR_HISTORY_PAGE_SIZE,
                    "sortKey": "date",
                    "sortDirection": "descending",
                },
            )
            if not isinstance(payload, dict) or not isinstance(payload.get("records"), list):
                raise ExternalServiceError("radarr", "Radarr returned invalid download history.")
            total = payload.get("totalRecords")
            if isinstance(total, bool) or not isinstance(total, int) or total < 0:
                raise ExternalServiceError("radarr", "Radarr returned invalid download history metadata.")
            if expected_total is None:
                expected_total = total
                if total > _RADARR_HISTORY_MAX_RECORDS:
                    raise ExternalServiceError("radarr", "Radarr download history exceeds the safe bounded limit.")
            elif total != expected_total:
                raise ExternalServiceError("radarr", "Radarr returned inconsistent download history metadata.")
            records = payload["records"]
            if len(records) > _RADARR_HISTORY_PAGE_SIZE:
                raise ExternalServiceError("radarr", "Radarr returned an oversized download history page.")
            if len(result) + len(records) > expected_total:
                raise ExternalServiceError("radarr", "Radarr returned records beyond the reported download history.")
            for item in records:
                data = item.get("data", {}) if isinstance(item, dict) else None
                if (
                    not isinstance(item, dict)
                    or isinstance(item.get("id"), bool)
                    or not isinstance(item.get("id"), int)
                    or item["id"] <= 0
                    or isinstance(item.get("movieId"), bool)
                    or not isinstance(item.get("movieId"), int)
                    or item["movieId"] <= 0
                    or not isinstance(item.get("eventType"), str)
                    or not isinstance(data, dict)
                ):
                    raise ExternalServiceError("radarr", "Radarr returned invalid download history records.")
                record_download_id = item.get("downloadId") or data.get("torrentInfoHash")
                if not isinstance(record_download_id, str) or record_download_id.casefold() != download_id.casefold():
                    raise ExternalServiceError("radarr", "Radarr returned out-of-scope download history records.")
                if item["id"] in seen_ids:
                    raise ExternalServiceError("radarr", "Radarr returned duplicate download history records.")
                seen_ids.add(item["id"])
                result.append(
                    RadarrHistoryRecord(
                        id=item["id"],
                        movie_id=item["movieId"],
                        event_type=item["eventType"],
                        download_id=record_download_id,
                        imported_path=data.get("importedPath"),
                    )
                )
            if len(result) > _RADARR_HISTORY_MAX_RECORDS:
                raise ExternalServiceError("radarr", "Radarr download history exceeds the safe bounded limit.")
            if len(result) == expected_total:
                return result
            if not records:
                raise ExternalServiceError("radarr", "Radarr returned incomplete download history.")
            page += 1

    async def delete_movie(
        self,
        movie_id: int,
        *,
        delete_files: bool,
        add_import_exclusion: bool,
    ) -> None:
        await self._request(
            "DELETE",
            f"/movie/{movie_id}",
            expected_statuses={200},
            params={
                "deleteFiles": str(delete_files).lower(),
                "addImportExclusion": str(add_import_exclusion).lower(),
            },
        )


class NullRadarrClient:
    """No-op fallback when no active Radarr service is configured."""

    async def close(self) -> None:
        return None

    async def ping(self) -> None:
        return None

    async def get_version(self) -> str:
        return "not configured"

    async def list_movies(self) -> Sequence[RadarrMovie]:
        return []

    async def list_movie_history(self, movie_id: int) -> Sequence[RadarrHistoryRecord]:
        return []

    async def list_download_history(self, download_id: str) -> Sequence[RadarrHistoryRecord]:
        return []

    async def list_root_folders(self) -> Sequence[StorageRootFolder]:
        return []

    async def list_disk_space(self) -> Sequence[StorageDiskSpace]:
        return []

    async def list_storage(self) -> Sequence[object]:
        return []

    async def delete_movie(
        self,
        movie_id: int,
        *,
        delete_files: bool,
        add_import_exclusion: bool,
    ) -> None:
        return None


class SonarrClient(JsonServiceClient):
    """Sonarr HTTP client."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        timeout_seconds: float,
        service_id: str | None = None,
        service_name: str | None = None,
    ) -> None:
        super().__init__(
            system="sonarr",
            base_url=base_url,
            timeout_seconds=timeout_seconds,
            headers={"X-Api-Key": api_key},
        )
        self._service_id = service_id
        self._service_name = service_name

    async def ping(self) -> None:
        """Verify Sonarr connectivity."""
        await self._request("GET", "/system/status")

    async def get_version(self) -> str:
        payload = await self._request("GET", "/system/status")
        return str(payload.get("version") or "unknown") if isinstance(payload, dict) else "unknown"

    async def list_series(self) -> Sequence[SonarrSeries]:
        payload = await self._request("GET", "/series")
        return [
            SonarrSeries(
                id=item["id"],
                title=item["title"],
                path=item["path"],
                tvdb_id=item.get("tvdbId"),
                tmdb_id=item.get("tmdbId"),
                imdb_id=item.get("imdbId"),
                added_at=_optional_datetime(item.get("added") or item.get("dateAdded")),
                size_on_disk=_optional_nonnegative_int(_arr_stat(item, "sizeOnDisk")),
                has_file=_arr_has_files(item),
                service_id=self._service_id,
                service_name=self._service_name,
                year=_optional_nonnegative_int(item.get("year")),
                episode_count=(_optional_nonnegative_int(_arr_stat(item, "episodeCount"))),
                episode_file_count=(_optional_nonnegative_int(_arr_stat(item, "episodeFileCount"))),
            )
            for item in payload
        ]

    async def list_root_folders(self) -> Sequence[StorageRootFolder]:
        """Return Sonarr root folders for the storage read model."""

        payload = await self._request("GET", "/rootfolder")
        if not isinstance(payload, list):
            raise ExternalServiceError("sonarr", "Sonarr returned an invalid root-folder response.")
        roots = [_storage_root_folder(item) for item in payload]
        if any(root is None for root in roots):
            raise ExternalServiceError("sonarr", "Sonarr returned malformed root-folder metadata.")
        return tuple(root for root in roots if root is not None)

    async def list_disk_space(self) -> Sequence[StorageDiskSpace]:
        """Return Sonarr disk-space records for the storage read model."""

        payload = await self._request("GET", "/diskspace")
        if not isinstance(payload, list):
            raise ExternalServiceError("sonarr", "Sonarr returned an invalid disk-space response.")
        spaces = [_storage_disk_space(item) for item in payload]
        if any(space is None for space in spaces):
            raise ExternalServiceError("sonarr", "Sonarr returned malformed disk-space metadata.")
        return tuple(space for space in spaces if space is not None)

    async def list_series_history(self, series_id: int) -> Sequence[SonarrHistoryRecord]:
        payload = await self._request(
            "GET",
            "/history/series",
            params={
                "seriesId": series_id,
                "page": 1,
                "pageSize": 1000,
                "sortKey": "date",
                "sortDirection": "descending",
            },
        )
        records = payload if isinstance(payload, list) else payload.get("records", [])
        return [
            SonarrHistoryRecord(
                id=item["id"],
                series_id=item["seriesId"],
                episode_id=item.get("episodeId"),
                event_type=item["eventType"],
                download_id=item.get("downloadId") or item.get("data", {}).get("torrentInfoHash"),
                imported_path=item.get("data", {}).get("importedPath"),
                release_type=item.get("data", {}).get("releaseType"),
            )
            for item in records
        ]

    async def list_episodes(self, series_id: int) -> Sequence[SonarrEpisode]:
        payload = await self._request("GET", "/episode", params={"seriesId": series_id})
        return [
            SonarrEpisode(
                id=item["id"],
                series_id=item["seriesId"],
                season_number=item["seasonNumber"],
                episode_number=item["episodeNumber"],
                episode_file_id=item.get("episodeFileId") or None,
                has_file=item["hasFile"],
                monitored=item["monitored"],
            )
            for item in payload
        ]

    async def list_episode_files(self, series_id: int) -> Sequence[SonarrEpisodeFile]:
        payload = await self._request("GET", "/episodeFile", params={"seriesId": series_id})
        return [
            SonarrEpisodeFile(
                id=item["id"],
                path=item["path"],
                relative_path=item.get("relativePath"),
                season_number=item.get("seasonNumber"),
                size=item.get("size"),
            )
            for item in payload
        ]

    async def unmonitor_episodes(self, episode_ids: Sequence[int]) -> None:
        await self._request(
            "PUT",
            "/episode/monitor",
            expected_statuses={200, 202},
            json={"episodeIds": list(episode_ids), "monitored": False},
        )

    async def unmonitor_season(self, series_id: int, season_number: int) -> None:
        series_data = await self._request("GET", f"/series/{series_id}")
        seasons = series_data.get("seasons", [])
        for season in seasons:
            if season.get("seasonNumber") == season_number:
                season["monitored"] = False
                break
        await self._request("PUT", f"/series/{series_id}", expected_statuses={200, 202}, json=series_data)

    async def delete_episode_file(self, episode_file_id: int) -> None:
        await self._request("DELETE", f"/episodeFile/{episode_file_id}", expected_statuses={200})

    async def delete_series(
        self,
        series_id: int,
        *,
        delete_files: bool,
        add_import_list_exclusion: bool,
    ) -> None:
        await self._request(
            "DELETE",
            f"/series/{series_id}",
            expected_statuses={200},
            params={
                "deleteFiles": str(delete_files).lower(),
                "addImportListExclusion": str(add_import_list_exclusion).lower(),
            },
        )


class NullSonarrClient:
    """No-op fallback when no active Sonarr service is configured."""

    async def close(self) -> None:
        return None

    async def ping(self) -> None:
        return None

    async def get_version(self) -> str:
        return "not configured"

    async def list_series(self) -> Sequence[SonarrSeries]:
        return []

    async def list_series_history(self, series_id: int) -> Sequence[SonarrHistoryRecord]:
        return []

    async def list_root_folders(self) -> Sequence[StorageRootFolder]:
        return []

    async def list_disk_space(self) -> Sequence[StorageDiskSpace]:
        return []

    async def list_storage(self) -> Sequence[object]:
        return []

    async def list_episodes(self, series_id: int) -> Sequence[SonarrEpisode]:
        return []

    async def list_episode_files(self, series_id: int) -> Sequence[SonarrEpisodeFile]:
        return []

    async def unmonitor_episodes(self, episode_ids: Sequence[int]) -> None:
        return None

    async def unmonitor_season(self, series_id: int, season_number: int) -> None:
        return None

    async def delete_episode_file(self, episode_file_id: int) -> None:
        return None

    async def delete_series(
        self,
        series_id: int,
        *,
        delete_files: bool,
        add_import_list_exclusion: bool,
    ) -> None:
        return None


class SeerrClient(JsonServiceClient):
    """Seerr HTTP client."""

    def __init__(self, *, base_url: str, api_key: str, timeout_seconds: float) -> None:
        super().__init__(
            system="seerr",
            base_url=base_url,
            timeout_seconds=timeout_seconds,
            headers={"X-Api-Key": api_key},
        )

    async def ping(self) -> None:
        """Verify Seerr connectivity."""

        await self._request("GET", "/auth/me")
        self._build_xsrf_headers()

    async def get_version(self) -> str:
        payload = await self._request("GET", "/status")
        return str(payload.get("version") or "unknown") if isinstance(payload, dict) else "unknown"

    def _build_xsrf_headers(self, response_cookies: httpx.Cookies | None = None) -> dict[str, str]:
        """Build the complete cookie/header pair required by Seerr's CSRF middleware."""

        def get_cookie(name: str) -> str | None:
            value = response_cookies.get(name) if response_cookies is not None else None
            return value or self._client.cookies.get(name)

        xsrf_token = get_cookie("XSRF-TOKEN")
        csrf_secret = get_cookie("_csrf")
        if not xsrf_token and not csrf_secret:
            return {}

        missing = [name for name, value in (("XSRF-TOKEN", xsrf_token), ("_csrf", csrf_secret)) if not value]
        if missing:
            raise ExternalServiceError(
                self._system,
                f"{self._system} did not return the CSRF cookies required for mutation requests "
                f"({', '.join(missing)} missing).",
            )
        assert xsrf_token is not None
        assert csrf_secret is not None

        return {
            "X-XSRF-TOKEN": xsrf_token,
            "Cookie": f"_csrf={csrf_secret}; XSRF-TOKEN={xsrf_token}",
        }

    @staticmethod
    def _merge_xsrf_cookie_header(existing_cookie: str, xsrf_cookie: str) -> str:
        """Preserve unrelated caller cookies while replacing stale CSRF values."""

        preserved: list[str] = []
        for fragment in existing_cookie.split(";"):
            normalized = fragment.strip()
            name, separator, _ = normalized.partition("=")
            if normalized and (not separator or name not in {"_csrf", "XSRF-TOKEN"}):
                preserved.append(normalized)
        return "; ".join([*preserved, xsrf_cookie])

    async def _prepare_xsrf_headers(self, path: str) -> dict[str, str]:
        """Fetch a fresh XSRF token for Seerr mutation endpoints."""

        try:
            response = await self._client.request("HEAD", path)
        except httpx.TimeoutException as exc:
            raise ExternalServiceError(self._system, f"{self._system} request timed out") from exc
        except httpx.HTTPError as exc:
            raise ExternalServiceError(
                self._system,
                f"{self._system} request failed ({exc.__class__.__name__}).",
            ) from exc

        if response.status_code in {401, 403}:
            raise AuthenticationError(
                self._system,
                f"{self._system} rejected the configured credentials.",
            )
        if response.status_code not in {200, 204, 405}:
            raise ExternalServiceError(
                self._system,
                f"{self._system} returned unexpected status {response.status_code} while preparing XSRF headers.",
            )

        return self._build_xsrf_headers(response.cookies)

    async def _request_with_xsrf(
        self,
        method: str,
        path: str,
        *,
        expected_statuses: set[int] | None = None,
        **kwargs: Any,
    ) -> Any:
        headers = httpx.Headers(kwargs.pop("headers", {}))
        xsrf_headers = await self._prepare_xsrf_headers(path)
        existing_cookie = headers.get("cookie")
        xsrf_cookie = xsrf_headers.get("Cookie")
        if existing_cookie and xsrf_cookie:
            xsrf_headers["Cookie"] = self._merge_xsrf_cookie_header(existing_cookie, xsrf_cookie)
        headers.update(xsrf_headers)
        return await self._request(
            method,
            path,
            expected_statuses=expected_statuses,
            treat_forbidden_as_authentication=False,
            headers=headers,
            **kwargs,
        )

    async def list_media(self) -> Sequence[SeerrMedia]:
        skip = 0
        take = 100
        results: list[SeerrMedia] = []
        total_results = 0
        while True:
            payload = await self._request(
                "GET",
                "/media",
                params={"take": take, "skip": skip, "filter": "all", "sort": "added"},
            )
            page_info = payload.get("pageInfo", {})
            total_results = page_info.get("results", 0)
            for item in payload.get("results", []):
                results.append(
                    SeerrMedia(
                        id=item["id"],
                        media_type=item["mediaType"],
                        tmdb_id=item.get("tmdbId"),
                        tvdb_id=item.get("tvdbId"),
                        imdb_id=item.get("imdbId"),
                        jellyfin_media_id=item.get("jellyfinMediaId"),
                    )
                )
            skip += take
            if skip >= total_results:
                break
        return results

    async def list_requests(self) -> Sequence[SeerrRequest]:
        skip = 0
        results: list[SeerrRequest] = []
        total_results = 0
        while True:
            payload = await self._request(
                "GET",
                "/request",
                params={"take": 100, "skip": skip, "filter": "all", "sort": "added", "sortDirection": "desc"},
            )
            page_info = payload.get("pageInfo", {})
            total_results = page_info.get("results", 0)
            for item in payload.get("results", []):
                seasons = tuple(season["seasonNumber"] for season in (item.get("seasons") or []))
                requested_by = item.get("requestedBy") or {}
                results.append(
                    SeerrRequest(
                        id=item["id"],
                        media_id=item["media"]["id"],
                        media_type=item["type"],
                        season_numbers=seasons,
                        is_4k=item["is4k"],
                        server_id=item.get("serverId"),
                        profile_id=item.get("profileId"),
                        root_folder=item.get("rootFolder"),
                        language_profile_id=item.get("languageProfileId"),
                        requested_by_id=requested_by.get("id"),
                        tags=tuple(item.get("tags") or []),
                    )
                )
            skip += 100
            if skip >= total_results:
                break
        return results

    async def list_issues(self) -> Sequence[SeerrIssue]:
        skip = 0
        results: list[SeerrIssue] = []
        total_results = 0
        while True:
            payload = await self._request(
                "GET",
                "/issue",
                params={"take": 100, "skip": skip, "filter": "all", "sort": "added"},
            )
            page_info = payload.get("pageInfo", {})
            total_results = page_info.get("results", 0)
            for item in payload.get("results", []):
                media = item.get("media") or {}
                results.append(
                    SeerrIssue(
                        id=item["id"],
                        media_id=media["id"],
                        problem_season=item.get("problemSeason"),
                        problem_episode=item.get("problemEpisode"),
                    )
                )
            skip += 100
            if skip >= total_results:
                break
        return results

    async def delete_request(self, request_id: int) -> None:
        await self._request_with_xsrf("DELETE", f"/request/{request_id}", expected_statuses={204})

    async def update_request_seasons(
        self,
        request: SeerrRequest,
        *,
        season_numbers: Sequence[int],
    ) -> None:
        payload: dict[str, Any] = {
            "mediaType": request.media_type,
            "seasons": list(season_numbers),
            "is4k": request.is_4k,
        }
        if request.server_id is not None:
            payload["serverId"] = request.server_id
        if request.profile_id is not None:
            payload["profileId"] = request.profile_id
        if request.root_folder is not None:
            payload["rootFolder"] = request.root_folder
        if request.language_profile_id is not None:
            payload["languageProfileId"] = request.language_profile_id
        if request.requested_by_id is not None:
            payload["userId"] = request.requested_by_id
        await self._request_with_xsrf("PUT", f"/request/{request.id}", json=payload)

    async def delete_issue(self, issue_id: int) -> None:
        await self._request_with_xsrf("DELETE", f"/issue/{issue_id}", expected_statuses={204})

    async def delete_media(self, media_id: int) -> None:
        await self._request_with_xsrf("DELETE", f"/media/{media_id}", expected_statuses={204})


class NullSeerrClient:
    """No-op fallback when no active Seerr service is configured."""

    async def close(self) -> None:
        return None

    async def ping(self) -> None:
        return None

    async def get_version(self) -> str:
        return "not configured"

    async def list_media(self) -> Sequence[SeerrMedia]:
        return []

    async def list_requests(self) -> Sequence[SeerrRequest]:
        return []

    async def list_issues(self) -> Sequence[SeerrIssue]:
        return []

    async def delete_request(self, request_id: int) -> None:
        return None

    async def update_request_seasons(
        self,
        request: SeerrRequest,
        *,
        season_numbers: Sequence[int],
    ) -> None:
        return None

    async def delete_issue(self, issue_id: int) -> None:
        return None

    async def delete_media(self, media_id: int) -> None:
        return None


class QbittorrentClient:
    """qBittorrent WebUI API client."""

    def __init__(
        self,
        *,
        base_url: str,
        username: str = "",
        password: str = "",
        api_key: str | None = None,
        timeout_seconds: float,
        service_id: str | None = None,
        service_name: str | None = None,
        seeding_policy: TorrentRemovalPolicy = TorrentRemovalPolicy.IMMEDIATE,
        min_seed_ratio: float | None = None,
        min_seed_time_minutes: int | None = None,
    ) -> None:
        self._system = "qbittorrent"
        self._username = username
        self._password = password
        self._api_key = api_key
        self._service_id = service_id
        self._service_name = service_name
        self._seeding_policy = seeding_policy
        self._min_seed_ratio = min_seed_ratio
        self._min_seed_time_minutes = min_seed_time_minutes
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else None
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=timeout_seconds,
            headers=headers,
            transport=httpx.AsyncHTTPTransport(retries=1),
        )

    async def close(self) -> None:
        """Close the underlying client."""

        await self._client.aclose()

    async def _login(self) -> None:
        if self._api_key:
            return
        try:
            response = await self._client.post(
                "/api/v2/auth/login",
                data={"username": self._username, "password": self._password},
            )
        except httpx.HTTPError as exc:
            raise ExternalServiceError(
                self._system,
                f"qBittorrent login failed ({exc.__class__.__name__}).",
            ) from exc

        if response.status_code == 204:
            return
        if response.status_code in {401, 403} or response.text.strip() != "Ok.":
            raise AuthenticationError(self._system, "qBittorrent rejected the configured credentials.")

    async def ping(self) -> None:
        """Validate qBittorrent credentials and session setup."""

        await self.get_version()

    async def get_version(self) -> str:
        """Return the qBittorrent application version."""

        await self._login()
        try:
            response = await self._client.get("/api/v2/app/version")
        except httpx.HTTPError as exc:
            raise ExternalServiceError(
                self._system,
                f"qBittorrent ping failed ({exc.__class__.__name__}).",
            ) from exc

        if response.status_code in {401, 403}:
            raise AuthenticationError(self._system, "qBittorrent rejected the configured credentials.")
        if response.status_code >= 400:
            raise ExternalServiceError(
                self._system,
                f"qBittorrent returned unexpected status {response.status_code}.",
            )
        return response.text.strip() or "unknown"

    async def delete_hashes(
        self,
        hashes: Sequence[str],
        *,
        delete_files: bool,
        dry_run: bool = False,
    ) -> Sequence[DownloaderRemovalResult]:
        return await self._delete_hashes_with_assessment(hashes, delete_files=delete_files, dry_run=dry_run)

    async def _delete_hashes_with_assessment(
        self,
        hashes: Sequence[str],
        *,
        delete_files: bool,
        dry_run: bool = False,
        assessment: ContentSafetyAssessment | None = None,
        assessment_client_id: str | None = None,
    ) -> Sequence[DownloaderRemovalResult]:
        normalized = list(dict.fromkeys(hash_value.strip().upper() for hash_value in hashes if hash_value.strip()))
        if not normalized:
            return []

        await self._login()
        matches = await self._matching_torrents(normalized)
        safety_client_id = assessment_client_id or self._system
        if delete_files and assessment is None:
            inventory = await read_content_inventory(self)
            assessment = assess_content_inventory(
                ((self._system, inventory),),
                normalized,
                known_existing={self._system: tuple(matches)},
            )
        deletion_hashes: set[str] = set()
        results: list[DownloaderRemovalResult] = []
        for hash_value in normalized:
            match = matches.get(hash_value)
            if match is None:
                results.append(self._result(hash_value, existed=False))
                continue
            canonical_hash, status, torrent_name, content_path = match
            safety_reason = (
                content_safety_skip_reason(assessment, safety_client_id, hash_value) if assessment is not None else None
            )
            if (
                delete_files
                and assessment is not None
                and safety_reason is None
                and (
                    content_path is None
                    or not content_scope_matches(assessment, safety_client_id, hash_value, content_path, exact=True)
                )
            ):
                safety_reason = "ownership_unverifiable"
            skip_reason = safety_reason or seeding_policy_skip_reason(
                self._seeding_policy,
                min_seed_ratio=self._min_seed_ratio,
                min_seed_time_minutes=self._min_seed_time_minutes,
                status=status,
            )
            if delete_files and safety_reason is None and skip_reason is None and content_path is None:
                skip_reason = "ownership_unverifiable"
            if skip_reason is None:
                deletion_hashes.add(canonical_hash)
            results.append(
                self._result(
                    hash_value,
                    existed=True,
                    skip_reason=skip_reason,
                    blocking_torrents=(
                        content_safety_blockers(assessment, safety_client_id, hash_value)
                        if assessment is not None
                        else ()
                    ),
                    status=status,
                    torrent_name=torrent_name,
                    content_path=content_path,
                    delete_files=delete_files if skip_reason is None else False,
                )
            )
        if deletion_hashes and not dry_run:
            await self._delete_existing_hashes(deletion_hashes, delete_files=delete_files)
        return results

    async def list_content_inventory(self) -> DownloaderContentInventory:
        """Read qBittorrent content roots for every torrent without exposing them publicly."""

        await self._login()
        try:
            response = await self._client.get(
                "/api/v2/torrents/info",
                params={
                    "fields": (
                        "hash,infohash_v1,infohash_v2,content_path,state,total_size,completed,downloaded,save_path,progress,name"
                    )
                },
            )
        except httpx.HTTPError as exc:
            raise ExternalServiceError(self._system, "qBittorrent content inventory failed.") from exc
        if response.status_code in {401, 403}:
            raise AuthenticationError(self._system, "qBittorrent rejected the configured credentials.")
        if response.status_code >= 400:
            raise ExternalServiceError(self._system, "qBittorrent content inventory failed.")
        try:
            payload = response.json()
        except ValueError as exc:
            raise ExternalServiceError(self._system, "qBittorrent returned an invalid content inventory.") from exc
        if not isinstance(payload, list):
            return DownloaderContentInventory(
                failures=(DownloaderContentInventoryFailure("invalid_content_inventory"),)
            )
        if len(payload) > MAX_CONTENT_INVENTORY_SCOPES:
            return DownloaderContentInventory(failures=(DownloaderContentInventoryFailure("inventory_limit_exceeded"),))
        scopes: list[DownloaderContentScope] = []
        failures: list[DownloaderContentInventoryFailure] = []
        for item in payload:
            if not isinstance(item, dict):
                failures.append(DownloaderContentInventoryFailure("malformed_content_scope"))
                continue
            raw_aliases = [item.get(key) for key in ("hash", "infohash_v1", "infohash_v2")]
            if any(raw_value not in (None, "") and not _qbt_hash(raw_value) for raw_value in raw_aliases):
                failures.append(DownloaderContentInventoryFailure("invalid_content_scope"))
                continue
            aliases = tuple(
                dict.fromkeys(_qbt_hash(raw_value) for raw_value in raw_aliases if raw_value not in (None, ""))
            )
            info_hash = aliases[0] if aliases else ""
            torrent_name = _safe_metadata_text(item.get("name"))
            raw_path = item.get("content_path")
            path = validate_scope_path(raw_path, minimum_parts=2)
            if info_hash and raw_path in (None, ""):
                total_size = item.get("total_size")
                if (
                    item.get("state") == "metaDL"
                    and isinstance(total_size, int)
                    and not isinstance(total_size, bool)
                    and total_size in {-1, 0}
                    and _qbt_zero_int(item.get("completed"))
                    and _qbt_zero_int(item.get("downloaded"))
                    and _qbt_zero_progress(item.get("progress"))
                ):
                    scopes.append(
                        DownloaderContentScope(
                            info_hash=info_hash,
                            hash_aliases=aliases[1:],
                            paths=(),
                            empty_verified=True,
                            torrent_name=torrent_name,
                        )
                    )
                    continue
                root = validate_scope_path(item.get("save_path"), minimum_parts=2)
                if root is not None:
                    scopes.append(
                        DownloaderContentScope(
                            info_hash=info_hash,
                            hash_aliases=aliases[1:],
                            paths=(root,),
                            uncertain=True,
                            torrent_name=torrent_name,
                        )
                    )
                    continue
            if not info_hash or path is None:
                failures.append(DownloaderContentInventoryFailure("invalid_content_scope"))
                continue
            scopes.append(
                DownloaderContentScope(
                    info_hash=info_hash, hash_aliases=aliases[1:], paths=(path,), torrent_name=torrent_name
                )
            )
        return DownloaderContentInventory(scopes=tuple(scopes), failures=tuple(failures))

    async def list_torrents(self) -> DownloaderListing:
        """Return safe normalized torrent snapshots without exposing data paths."""
        await self._login()
        try:
            response = await self._client.get("/api/v2/torrents/info")
        except httpx.HTTPError as exc:
            raise ExternalServiceError(self._system, "qBittorrent torrent listing failed.") from exc
        if response.status_code in {401, 403}:
            raise AuthenticationError(self._system, "qBittorrent rejected the configured credentials.")
        if response.status_code >= 400:
            raise ExternalServiceError(self._system, "qBittorrent torrent listing failed.")
        try:
            payload = response.json()
        except ValueError as exc:
            raise ExternalServiceError(self._system, "qBittorrent returned an invalid JSON response.") from exc
        if not isinstance(payload, list):
            return DownloaderListing(failures=(_qbt_failure(self, "invalid_torrent_list"),))
        snapshots: list[TorrentSnapshot] = []
        failures: list[DownloaderReadFailure] = []
        for item in payload:
            snapshot = _qbt_snapshot(item, client=self)
            if snapshot is None:
                failures.append(_qbt_failure(self, "malformed_torrent"))
            else:
                snapshots.append(snapshot)
        return DownloaderListing(torrents=tuple(snapshots), failures=tuple(failures))

    async def control_torrent(self, info_hash: str, *, action: DownloadControlAction) -> DownloaderControlResult:
        normalized = _qbt_hash(info_hash)
        if not normalized:
            return _qbt_control(self, normalized, action, DownloadControlOutcome.UNKNOWN, "invalid_identifier")
        try:
            pre_listing = await self.list_torrents()
        except ExternalServiceError:
            return _qbt_control(self, normalized, action, DownloadControlOutcome.UNKNOWN, "pre_read_failed")
        before = _qbt_find(pre_listing, normalized)
        if before is None and pre_listing.failures:
            return _qbt_control(self, normalized, action, DownloadControlOutcome.UNKNOWN, "pre_read_incomplete")
        if before is None:
            return _qbt_control(self, normalized, action, DownloadControlOutcome.NOT_FOUND, "not_found")
        if before.state is TorrentState.UNKNOWN:
            return _qbt_control(
                self, normalized, action, DownloadControlOutcome.UNKNOWN, "pre_state_unknown", before=before
            )
        if _qbt_has_desired_state(before.state, action):
            return _qbt_control(
                self,
                normalized,
                action,
                DownloadControlOutcome.ALREADY_IN_DESIRED_STATE,
                "already_in_desired_state",
                before=before,
            )
        try:
            control_path = _qbt_control_path(await self.get_version(), action)
            if control_path is None:
                return _qbt_control(
                    self,
                    normalized,
                    action,
                    DownloadControlOutcome.UNKNOWN,
                    "unsupported_client_version",
                    before=before,
                )
            response = await self._client.post(control_path, data={"hashes": normalized})
            if response.status_code in {401, 403}:
                raise AuthenticationError(self._system, "qBittorrent rejected the configured credentials.")
            if response.status_code >= 400:
                raise ExternalServiceError(self._system, "qBittorrent control request failed.")
        except ExternalServiceError:
            return _qbt_control(
                self, normalized, action, DownloadControlOutcome.UNKNOWN, "mutation_or_post_read_failed", before=before
            )
        after, failure_code = await _qbt_verify_post_control_state(self, normalized, action)
        if failure_code is not None:
            return _qbt_control(
                self,
                normalized,
                action,
                DownloadControlOutcome.UNKNOWN,
                failure_code,
                before=before,
                after=after,
            )
        assert after is not None
        return _qbt_control(
            self, normalized, action, DownloadControlOutcome.APPLIED, "applied", before=before, after=after
        )

    async def _matching_torrents(
        self,
        hashes: Sequence[str],
    ) -> dict[str, tuple[str, TorrentSeedingStatus, str | None, str | None]]:
        try:
            response = await self._client.get(
                "/api/v2/torrents/info",
                params={"hashes": "|".join(hashes)},
            )
        except httpx.HTTPError as exc:
            raise ExternalServiceError(
                self._system,
                f"qBittorrent torrent lookup failed ({exc.__class__.__name__}).",
            ) from exc

        if response.status_code in {401, 403}:
            raise AuthenticationError(self._system, "qBittorrent rejected the configured credentials.")
        if response.status_code >= 400:
            raise ExternalServiceError(
                self._system,
                f"qBittorrent returned unexpected status {response.status_code}.",
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise ExternalServiceError(self._system, "qBittorrent returned an invalid JSON response.") from exc
        if not isinstance(payload, list):
            raise ExternalServiceError(self._system, "qBittorrent returned an unexpected torrent list.")

        requested = set(hashes)
        matches: dict[str, tuple[str, TorrentSeedingStatus, str | None, str | None]] = {}
        for item in payload:
            if not isinstance(item, dict):
                raise ExternalServiceError(self._system, "qBittorrent returned malformed target metadata.")
            identifiers = {str(item[key]).upper() for key in ("hash", "infohash_v1", "infohash_v2") if item.get(key)}
            if not identifiers:
                raise ExternalServiceError(self._system, "qBittorrent returned missing target identifiers.")
            matched = identifiers.intersection(requested)
            if not matched:
                continue
            canonical_hash = str(item.get("hash") or sorted(identifiers)[0]).upper()
            status = TorrentSeedingStatus(
                ratio=_optional_float(item.get("ratio")),
                seeding_time_seconds=_optional_int(item.get("seeding_time")),
            )
            torrent_name = _safe_metadata_text(item.get("name"))
            content_path = _safe_content_path(item.get("content_path"))
            for hash_value in matched:
                if hash_value in matches:
                    raise ExternalServiceError(self._system, "qBittorrent returned duplicate target metadata.")
                matches[hash_value] = (canonical_hash, status, torrent_name, content_path)
        return matches

    async def _delete_existing_hashes(self, hashes: set[str], *, delete_files: bool) -> None:
        try:
            response = await self._client.post(
                "/api/v2/torrents/delete",
                data={"hashes": "|".join(sorted(hashes)), "deleteFiles": str(delete_files).lower()},
            )
        except httpx.HTTPError as exc:
            raise ExternalServiceError(
                self._system,
                f"qBittorrent delete failed ({exc.__class__.__name__}).",
            ) from exc

        if response.status_code in {401, 403}:
            raise AuthenticationError(self._system, "qBittorrent rejected the configured credentials.")
        if response.status_code >= 400:
            raise ExternalServiceError(
                self._system,
                f"qBittorrent returned unexpected status {response.status_code}.",
            )

    def _result(
        self,
        hash_value: str,
        *,
        existed: bool,
        skip_reason: str | None = None,
        status: TorrentSeedingStatus | None = None,
        torrent_name: str | None = None,
        content_path: str | None = None,
        delete_files: bool | None = None,
        blocking_torrents: tuple[ContentScopeBlocker, ...] = (),
    ) -> DownloaderRemovalResult:
        return DownloaderRemovalResult(
            hash_value=hash_value,
            existed=existed,
            client_id=self._service_id,
            client_name=self._service_name,
            client_kind=self._system,
            skip_reason=skip_reason,
            seeding_policy=self._seeding_policy.value,
            ratio=status.ratio if status is not None else None,
            seeding_time_seconds=status.seeding_time_seconds if status is not None else None,
            torrent_name=torrent_name,
            content_path=content_path,
            delete_files=delete_files,
            blocking_torrents=blocking_torrents,
        )


class JellyfinServerClient(JsonServiceClient):
    """Jellyfin media server HTTP client."""

    def __init__(self, *, base_url: str, api_key: str, timeout_seconds: float) -> None:
        super().__init__(
            system="jellyfin",
            base_url=base_url,
            timeout_seconds=timeout_seconds,
            headers={"Authorization": f'MediaBrowser Token="{api_key}"'},
        )

    async def ping(self) -> None:
        """Verify Jellyfin connectivity and the configured credential."""
        await self._request("GET", "/System/Info")

    async def get_version(self) -> str:
        payload = await self._request("GET", "/System/Info")
        return str(payload.get("Version") or "unknown") if isinstance(payload, dict) else "unknown"

    async def find_items(
        self,
        *,
        ids: Sequence[str] = (),
        provider_ids: Sequence[str] = (),
        include_types: Sequence[str] = (),
        accept_language: str | None = None,
    ) -> Sequence[JellyfinItem]:
        """Look up exact IDs or verify a complete bounded catalogue before filtering providers."""
        if not ids and not provider_ids:
            raise ExternalServiceError("jellyfin", "Jellyfin lookup requires an item or provider identifier.")
        request_kwargs: dict[str, Any] = {}
        if accept_language:
            request_kwargs["headers"] = {"Accept-Language": accept_language}
        params: dict[str, Any] = {
            "Recursive": "true",
            "Fields": "ProviderIds,ParentId,IndexNumber",
            "EnableTotalRecordCount": "true",
        }
        if ids:
            params["Ids"] = ",".join(ids)
        if ids:
            if include_types:
                params["IncludeItemTypes"] = ",".join(include_types)
            payload = await self._request("GET", "/Items", params=params, **request_kwargs)
            if not isinstance(payload, dict) or not isinstance(payload.get("Items"), list):
                raise ExternalServiceError("jellyfin", "Jellyfin returned invalid targeted lookup data.")
            total = payload.get("TotalRecordCount")
            if total is None or isinstance(total, bool) or not isinstance(total, int) or total < 0:
                raise ExternalServiceError("jellyfin", "Jellyfin returned invalid targeted lookup metadata.")
            raw_items = payload["Items"]
            if len(raw_items) != total:
                raise ExternalServiceError("jellyfin", "Jellyfin returned an incomplete targeted lookup.")
            result: list[JellyfinItem] = []
            for item in raw_items:
                parsed = self._library_item(item)
                if parsed is None:
                    raise ExternalServiceError("jellyfin", "Jellyfin returned invalid targeted lookup data.")
                result.append(parsed)
            requested_ids = set(ids)
            returned_ids = [item.id for item in result]
            if any(item_id not in requested_ids for item_id in returned_ids) or len(returned_ids) != len(
                set(returned_ids)
            ):
                raise ExternalServiceError("jellyfin", "Jellyfin returned inconsistent targeted lookup items.")
            return result
        result = await self._list_complete_items(include_types=include_types, request_kwargs=request_kwargs)
        provider_tokens = {provider_id.casefold() for provider_id in provider_ids}
        return [item for item in result if self._matches_provider_ids(item, provider_tokens)]

    async def _list_complete_items(
        self, *, include_types: Sequence[str], request_kwargs: dict[str, Any]
    ) -> list[JellyfinItem]:
        """Read a complete, bounded Jellyfin catalogue with one allowed churn restart."""
        for attempt in range(2):
            result, changed = await self._list_complete_items_pass(
                include_types=include_types,
                request_kwargs=request_kwargs,
            )
            if not changed:
                return result
            if attempt == 1:
                raise ExternalServiceError("jellyfin", "Jellyfin provider catalogue changed repeatedly.")
        raise AssertionError("unreachable")

    async def _list_complete_items_pass(
        self, *, include_types: Sequence[str], request_kwargs: dict[str, Any]
    ) -> tuple[list[JellyfinItem], bool]:
        """Read one catalogue pass, discarding it when its authoritative total changes."""
        result: list[JellyfinItem] = []
        seen_ids: set[str] = set()
        expected_total: int | None = None
        start_index = 0
        while True:
            payload = await self._request(
                "GET",
                "/Items",
                params={
                    "Recursive": "true",
                    "IncludeItemTypes": ",".join(include_types),
                    "Fields": "ProviderIds,ParentId,IndexNumber",
                    "StartIndex": start_index,
                    "Limit": _JELLYFIN_LIBRARY_PAGE_SIZE,
                    "EnableTotalRecordCount": "true",
                },
                **request_kwargs,
            )
            if not isinstance(payload, dict) or not isinstance(payload.get("Items"), list):
                raise ExternalServiceError("jellyfin", "Jellyfin returned invalid provider catalogue data.")
            total = payload.get("TotalRecordCount")
            if total is None or isinstance(total, bool) or not isinstance(total, int) or total < 0:
                raise ExternalServiceError("jellyfin", "Jellyfin returned unverifiable provider catalogue metadata.")
            if expected_total is None:
                expected_total = total
                if total > _JELLYFIN_LIBRARY_MAX_ITEMS:
                    raise ExternalServiceError(
                        "jellyfin", "Jellyfin provider catalogue exceeds the safe bounded limit."
                    )
            raw_items = payload["Items"]
            if len(raw_items) > _JELLYFIN_LIBRARY_PAGE_SIZE:
                raise ExternalServiceError("jellyfin", "Jellyfin returned an oversized provider catalogue page.")
            changed = expected_total is not None and total != expected_total
            if changed and start_index > total:
                if raw_items:
                    raise ExternalServiceError(
                        "jellyfin", "Jellyfin returned inconsistent provider catalogue metadata."
                    )
                return [], True
            for item in raw_items:
                parsed = self._library_item(item)
                if parsed is None or (include_types and parsed.type not in include_types):
                    raise ExternalServiceError("jellyfin", "Jellyfin returned invalid or out-of-scope provider data.")
                if parsed.id in seen_ids:
                    raise ExternalServiceError("jellyfin", "Jellyfin returned duplicate provider catalogue items.")
                seen_ids.add(parsed.id)
                result.append(parsed)
            start_index += len(raw_items)
            if changed:
                return [], True
            if start_index > total:
                raise ExternalServiceError("jellyfin", "Jellyfin returned inconsistent provider catalogue metadata.")
            if start_index == total:
                return result, False
            if not raw_items:
                raise ExternalServiceError("jellyfin", "Jellyfin returned incomplete provider catalogue data.")

    @staticmethod
    def _matches_provider_ids(item: JellyfinItem, provider_tokens: set[str]) -> bool:
        item_tokens: set[str] = set()
        if item.tmdb_id is not None:
            item_tokens.add(f"tmdb.{item.tmdb_id}")
        if item.tvdb_id is not None:
            item_tokens.add(f"tvdb.{item.tvdb_id}")
        if item.imdb_id:
            item_tokens.add(f"imdb.{item.imdb_id}")
        return bool({token.casefold() for token in item_tokens} & provider_tokens)

    async def list_items(
        self,
        *,
        include_types: list[str],
        accept_language: str | None = None,
    ) -> Sequence[JellyfinItem]:
        request_kwargs: dict[str, Any] = {}
        if accept_language:
            request_kwargs["headers"] = {"Accept-Language": accept_language}
        result: list[JellyfinItem] = []
        start_index = 0
        expected_total: int | None = None
        total_was_reported: bool | None = None
        while True:
            payload = await self._request(
                "GET",
                "/Items",
                params={
                    "Recursive": "true",
                    "IncludeItemTypes": ",".join(include_types),
                    "Fields": "ProviderIds,ParentId,IndexNumber",
                    "StartIndex": start_index,
                    "Limit": _JELLYFIN_LIBRARY_PAGE_SIZE,
                },
                **request_kwargs,
            )
            if not isinstance(payload, dict) or not isinstance(payload.get("Items"), list):
                raise ExternalServiceError("jellyfin", "Jellyfin returned invalid library data.")
            raw_items = payload["Items"]
            total = payload.get("TotalRecordCount")
            if total is not None and (isinstance(total, bool) or not isinstance(total, int) or total < 0):
                raise ExternalServiceError("jellyfin", "Jellyfin returned invalid library metadata.")
            reported = isinstance(total, int)
            if total_was_reported is None:
                total_was_reported = reported
                expected_total = total if reported else None
            elif reported != total_was_reported or (reported and total != expected_total):
                raise ExternalServiceError("jellyfin", "Jellyfin returned inconsistent library metadata.")
            for item in raw_items:
                parsed = self._library_item(item)
                if parsed is None:
                    raise ExternalServiceError("jellyfin", "Jellyfin returned invalid library data.")
                result.append(parsed)
            start_index += len(raw_items)
            if isinstance(total, int) and start_index > total:
                raise ExternalServiceError("jellyfin", "Jellyfin returned inconsistent library metadata.")
            if len(result) > _JELLYFIN_LIBRARY_MAX_ITEMS or (
                isinstance(total, int) and total > _JELLYFIN_LIBRARY_MAX_ITEMS
            ):
                raise ExternalServiceError("jellyfin", "Jellyfin library exceeds the safe catalogue limit.")
            if not raw_items:
                if isinstance(total, int) and start_index < total:
                    raise ExternalServiceError("jellyfin", "Jellyfin returned an incomplete library catalogue.")
                break
            if isinstance(total, int) and start_index >= total:
                break
            if total is None and len(raw_items) < _JELLYFIN_LIBRARY_PAGE_SIZE:
                break
        return result

    @staticmethod
    def _library_item(item: object) -> JellyfinItem | None:
        if not isinstance(item, dict):
            return None
        item_id = item.get("Id")
        item_type = item.get("Type")
        if not isinstance(item_id, str) or not item_id.strip() or len(item_id) > 256 or not isinstance(item_type, str):
            return None
        provider_ids = item.get("ProviderIds") or {}
        if not isinstance(provider_ids, dict):
            return None
        tmdb_raw = provider_ids.get("Tmdb")
        tvdb_raw = provider_ids.get("Tvdb")
        return JellyfinItem(
            id=item_id,
            name=item.get("Name", "") if isinstance(item.get("Name", ""), str) else "",
            type=item_type,
            tmdb_id=int(tmdb_raw) if tmdb_raw and str(tmdb_raw).isdigit() else None,
            tvdb_id=int(tvdb_raw) if tvdb_raw and str(tvdb_raw).isdigit() else None,
            imdb_id=provider_ids.get("Imdb") if isinstance(provider_ids.get("Imdb"), str) else None,
            parent_id=(
                item.get("ParentId") or item.get("SeriesId")
                if isinstance(item.get("ParentId") or item.get("SeriesId"), str)
                else None
            ),
            season_number=(
                item.get("IndexNumber")
                if isinstance(item.get("IndexNumber"), int) and not isinstance(item.get("IndexNumber"), bool)
                else None
            ),
        )

    async def get_primary_artwork(self, item_id: str) -> ArtworkData | None:
        """Read one Jellyfin Primary image with a strict bounded proxy contract."""

        if not isinstance(item_id, str) or not item_id.strip() or len(item_id) > 256:
            raise ResourceNotFoundError("jellyfin", "Jellyfin artwork item was not found.")
        try:
            async with self._client.stream("GET", f"/Items/{quote(item_id, safe='')}/Images/Primary") as response:
                if response.status_code in {401, 403}:
                    raise AuthenticationError("jellyfin", "Jellyfin rejected the configured credentials.")
                if response.status_code == 404:
                    return None
                if response.status_code >= 400:
                    raise ExternalServiceError("jellyfin", "Jellyfin artwork request failed.")
                content_length = response.headers.get("content-length")
                if content_length is not None:
                    try:
                        if int(content_length) > 5 * 1024 * 1024:
                            raise ExternalServiceError("jellyfin", "Jellyfin artwork exceeds the maximum size.")
                    except ValueError as exc:
                        raise ExternalServiceError("jellyfin", "Jellyfin returned invalid artwork metadata.") from exc
                media_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                if media_type not in {"image/jpeg", "image/png", "image/webp", "image/avif"}:
                    raise ExternalServiceError("jellyfin", "Jellyfin returned an unsupported artwork type.")
                content = bytearray()
                async for chunk in response.aiter_bytes():
                    if len(content) + len(chunk) > 5 * 1024 * 1024:
                        raise ExternalServiceError("jellyfin", "Jellyfin artwork exceeds the maximum size.")
                    content.extend(chunk)
                return ArtworkData(content=bytes(content), media_type=media_type)
        except httpx.TimeoutException as exc:
            raise ExternalServiceError("jellyfin", "Jellyfin artwork request timed out.") from exc
        except httpx.HTTPError as exc:
            raise ExternalServiceError("jellyfin", "Jellyfin artwork request failed.") from exc

    @staticmethod
    def _cleanup_datetime(value: object) -> tuple[datetime | None, bool]:
        if value is None:
            return None, True
        if not isinstance(value, str) or not value:
            return None, False
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None, False
        if parsed.tzinfo is None:
            return None, False
        return parsed.astimezone(UTC), True

    @staticmethod
    def _cleanup_int(value: object) -> int | None:
        return value if isinstance(value, int) and not isinstance(value, bool) else None

    @classmethod
    def _cleanup_item(cls, raw: object) -> JellyfinCleanupItem | None:
        if not isinstance(raw, dict):
            return None
        item_id = raw.get("Id")
        item_type = raw.get("Type")
        name = raw.get("Name")
        if not isinstance(item_id, str) or not item_id or not isinstance(name, str) or not isinstance(item_type, str):
            return None
        media_type = {"Movie": CleanupMediaType.MOVIE, "Series": CleanupMediaType.SERIES}.get(item_type)
        if media_type is None:
            return None
        provider_ids = raw.get("ProviderIds")
        provider_ids = provider_ids if isinstance(provider_ids, dict) else {}
        tmdb = provider_ids.get("Tmdb")
        tvdb = provider_ids.get("Tvdb")
        imdb = provider_ids.get("Imdb")
        created_at, created_valid = cls._cleanup_datetime(raw.get("DateCreated"))
        added_at, added_valid = cls._cleanup_datetime(raw.get("DateLastMediaAdded"))
        # A media source may represent an alternative rendition.  Reporting a
        # size for several sources would create a misleading aggregate, so it
        # is deliberately unavailable unless Jellyfin supplies one valid size.
        sources = raw.get("MediaSources")
        size: int | None = None
        if isinstance(sources, list):
            values = [source.get("Size") for source in sources if isinstance(source, dict)]
            if len(values) == 1 and isinstance(values[0], int) and not isinstance(values[0], bool) and values[0] >= 0:
                size = values[0]
        return JellyfinCleanupItem(
            item_id=item_id,
            display_name=_qbt_safe_text(name, limit=240) or "Untitled",
            media_type=media_type,
            created_at=created_at if created_valid else None,
            added_at=added_at if added_valid else None,
            size_bytes=size,
            tmdb_id=int(tmdb) if isinstance(tmdb, str) and tmdb.isdigit() else None,
            tvdb_id=int(tvdb) if isinstance(tvdb, str) and tvdb.isdigit() else None,
            imdb_id=imdb.strip() if isinstance(imdb, str) and imdb.strip() else None,
        )

    async def list_cleanup_items(
        self, *, accept_language: str | None = None, max_items: int = 200
    ) -> tuple[tuple[JellyfinCleanupItem, ...], bool]:
        """Read a bounded, paginated Movie/Series catalogue without user data."""

        limit = min(50, max(1, max_items))
        start = 0
        items: list[JellyfinCleanupItem] = []
        truncated = False
        headers = {"Accept-Language": accept_language} if accept_language else None
        while True:
            payload = await self._request(
                "GET",
                "/Items",
                params={
                    "Recursive": "true",
                    "IncludeItemTypes": "Movie,Series",
                    "Fields": "DateCreated,DateLastMediaAdded,MediaSources,ParentId,ProviderIds",
                    "EnableUserData": "false",
                    "StartIndex": start,
                    "Limit": limit,
                },
                headers=headers,
            )
            if not isinstance(payload, dict) or not isinstance(payload.get("Items"), list):
                raise ExternalServiceError("jellyfin", "Jellyfin returned an invalid cleanup catalogue.")
            raw_items = payload["Items"]
            for raw in raw_items:
                parsed = self._cleanup_item(raw)
                if parsed is None:
                    raise ExternalServiceError("jellyfin", "Jellyfin returned malformed cleanup metadata.")
                items.append(parsed)
            total = payload.get("TotalRecordCount")
            if not isinstance(total, int) or total < 0:
                raise ExternalServiceError("jellyfin", "Jellyfin returned an invalid cleanup catalogue count.")
            start += len(raw_items)
            if start >= total:
                break
            if len(items) >= max_items or not raw_items:
                truncated = True
                break
        return tuple(items[:max_items]), truncated

    async def list_playback_users(self, *, max_users: int = 20) -> tuple[tuple[str, ...], bool]:
        payload = await self._request("GET", "/Users")
        if not isinstance(payload, list):
            raise ExternalServiceError("jellyfin", "Jellyfin returned an invalid user scope.")
        user_ids: list[str] = []
        for raw in payload:
            user_id = raw.get("Id") if isinstance(raw, dict) else None
            if not isinstance(user_id, str) or not user_id or user_id in user_ids:
                raise ExternalServiceError("jellyfin", "Jellyfin returned an invalid user scope.")
            user_ids.append(user_id)
        return tuple(user_ids[:max_users]), len(user_ids) > max_users

    async def list_user_playback(
        self, *, user_id: str, item_ids: tuple[str, ...], accept_language: str | None = None
    ) -> tuple[PlaybackObservation, ...]:
        if not item_ids or len(item_ids) > 50:
            raise ValueError("Jellyfin playback item chunks must contain 1-50 IDs.")
        headers = {"Accept-Language": accept_language} if accept_language else None
        payload = await self._request(
            "GET",
            "/Items",
            params={"UserId": user_id, "Ids": ",".join(item_ids), "EnableUserData": "true"},
            headers=headers,
        )
        if not isinstance(payload, dict) or not isinstance(payload.get("Items"), list):
            raise ExternalServiceError("jellyfin", "Jellyfin returned invalid playback data.")
        observations: list[PlaybackObservation] = []
        for raw in payload["Items"]:
            item_id = raw.get("Id") if isinstance(raw, dict) else None
            user_data = raw.get("UserData") if isinstance(raw, dict) else None
            if not isinstance(item_id, str) or not isinstance(user_data, dict):
                continue
            played = user_data.get("Played")
            play_count = user_data.get("PlayCount")
            last_played, timestamp_valid = self._cleanup_datetime(user_data.get("LastPlayedDate"))
            valid = isinstance(played, bool) and isinstance(play_count, int) and not isinstance(play_count, bool)
            observations.append(
                PlaybackObservation(
                    user_id=user_id,
                    item_id=item_id,
                    played=played if isinstance(played, bool) else None,
                    play_count=play_count if isinstance(play_count, int) and not isinstance(play_count, bool) else None,
                    last_played_at=last_played,
                    valid=valid and timestamp_valid,
                )
            )
        return tuple(observations)

    async def delete_item(self, item_id: str) -> None:
        if not isinstance(item_id, str) or not item_id.strip() or len(item_id) > 256:
            raise ResourceNotFoundError("jellyfin", "Jellyfin item was not found.")
        await self._request("DELETE", f"/Items/{quote(item_id, safe='')}", expected_statuses={200, 204, 404})

    async def list_plugins(self) -> list[dict[str, Any]]:
        """Return the list of installed Jellyfin plugins."""
        data = await self._request("GET", "/Plugins")
        return data if isinstance(data, list) else []

    async def get_plugin_config_raw(self, plugin_id: str) -> Any:
        """Fetch a plugin's configuration object."""
        return await self._request("GET", f"/Plugins/{plugin_id}/Configuration")

    async def set_plugin_config_raw(self, plugin_id: str, config: Any) -> None:
        """Write back a plugin's configuration object."""
        await self._request(
            "POST",
            f"/Plugins/{plugin_id}/Configuration",
            json=config,
            expected_statuses={200, 204},
        )

    async def setup_webhook(
        self,
        *,
        webhook_url: str,
        webhook_token: str | None,
        template: str,
    ) -> dict[str, Any]:
        """Auto-configure the Jellyfin Webhook plugin for CleanArr.

        Returns a dict with keys: ``found``, ``configured``, ``message``.
        """
        plugins = await self.list_plugins()
        webhook_plugin = next(
            (p for p in plugins if "webhook" in p.get("Name", "").lower()),
            None,
        )
        if webhook_plugin is None:
            return {
                "found": False,
                "configured": False,
                "message": (
                    "Webhook plugin not found. Install it via Jellyfin → Dashboard → Plugins → Catalog → Webhook."
                ),
            }

        plugin_id = webhook_plugin["Id"]
        config = await self.get_plugin_config_raw(plugin_id)
        if not isinstance(config, dict):
            config = {}

        generics: list[dict[str, Any]] = list(config.get("GenericOptions", []))

        # Remove all previous CleanArr entries and leftover entries with no name
        # and no URI (artifacts of earlier incorrect configuration attempts).
        generics = [
            g for g in generics if g.get("WebhookName") != "CleanArr" and (g.get("WebhookName") or g.get("WebhookUri"))
        ]

        headers: list[dict[str, str]] = [{"Key": "X-Webhook-Token", "Value": webhook_token}] if webhook_token else []
        template_b64 = base64.b64encode(template.encode()).decode()
        our_entry: dict[str, Any] = {
            "WebhookName": "CleanArr",
            "WebhookUri": webhook_url,
            "NotificationTypes": ["ItemDeleted"],
            "EnableMovies": True,
            "EnableEpisodes": True,
            "EnableSeries": True,
            "EnableSeasons": True,
            "EnableAlbums": True,
            "EnableSongs": True,
            "EnableVideos": True,
            "EnableWebhook": True,
            "SendAllProperties": False,
            "TrimWhitespace": False,
            "SkipEmptyMessageBody": False,
            "Template": template_b64,
            "Headers": headers,
            "Fields": [],
            "UserFilter": [],
        }
        generics.append(our_entry)
        config["GenericOptions"] = generics

        await self.set_plugin_config_raw(plugin_id, config)
        return {
            "found": True,
            "configured": True,
            "message": "Webhook configured in Jellyfin successfully.",
        }


class NullJellyfinServerClient:
    """No-op fallback when no active Jellyfin server is configured."""

    async def close(self) -> None:
        return None

    async def ping(self) -> None:
        return None

    async def get_version(self) -> str:
        return "not configured"

    async def find_items(
        self,
        *,
        ids: Sequence[str] = (),
        provider_ids: Sequence[str] = (),
        include_types: Sequence[str] = (),
        accept_language: str | None = None,
    ) -> Sequence[JellyfinItem]:
        raise ExternalServiceError("jellyfin", "Jellyfin is not configured; source absence cannot be verified.")

    async def list_items(
        self,
        *,
        include_types: list[str],
        accept_language: str | None = None,
    ) -> Sequence[JellyfinItem]:
        return []

    async def get_primary_artwork(self, item_id: str) -> ArtworkData | None:
        return None

    async def list_cleanup_items(
        self, *, accept_language: str | None = None, max_items: int = 200
    ) -> tuple[tuple[JellyfinCleanupItem, ...], bool]:
        return (), False

    async def list_playback_users(self, *, max_users: int = 20) -> tuple[tuple[str, ...], bool]:
        return (), False

    async def list_user_playback(
        self, *, user_id: str, item_ids: tuple[str, ...], accept_language: str | None = None
    ) -> tuple[PlaybackObservation, ...]:
        return ()

    async def delete_item(self, item_id: str) -> None:
        return None

    async def list_plugins(self) -> list[dict[str, Any]]:
        return []

    async def get_plugin_config_raw(self, plugin_id: str) -> Any:
        return {}

    async def set_plugin_config_raw(self, plugin_id: str, config: Any) -> None:
        return None

    async def setup_webhook(
        self,
        *,
        webhook_url: str,
        webhook_token: str | None,
        template: str,
    ) -> dict[str, Any]:
        return {"found": False, "configured": False, "message": "Jellyfin not configured."}


class NullDownloaderClient:
    """No-op fallback when no active download client is configured."""

    async def close(self) -> None:
        return None

    async def ping(self) -> None:
        return None

    async def get_version(self) -> str:
        return "not configured"

    def configured_client_ids(self) -> set[str]:
        return set()

    async def list_torrents(self) -> DownloaderListing:
        return DownloaderListing()

    async def list_content_inventory(self) -> DownloaderContentInventory:
        return DownloaderContentInventory()

    async def control_torrent(
        self, client_id: str, info_hash: str | None = None, *, action: DownloadControlAction
    ) -> DownloaderControlResult:
        if info_hash is None:
            info_hash = client_id
            client_id = "not_configured"
        return DownloaderControlResult(
            client_id=client_id,
            client_name="not configured",
            client_kind="none",
            info_hash=_qbt_hash(info_hash),
            action=action,
            outcome=DownloadControlOutcome.UNKNOWN,
            code="not_configured",
        )

    async def delete_hashes(
        self,
        hashes: Sequence[str],
        *,
        delete_files: bool,
        dry_run: bool = False,
    ) -> Sequence[DownloaderRemovalResult]:
        return [DownloaderRemovalResult(hash_value=hash_value.upper(), existed=False) for hash_value in hashes]
