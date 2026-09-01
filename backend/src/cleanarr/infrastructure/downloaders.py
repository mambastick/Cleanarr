"""Torrent download-client adapters."""

from __future__ import annotations

import asyncio
import posixpath
import time
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import PurePosixPath
from typing import Any, cast
from urllib.parse import urlparse
from xmlrpc.client import Fault, dumps, loads

import httpx

from cleanarr.application.ports import DownloaderClientPort, DownloaderControlPort, DownloaderReadPort
from cleanarr.domain import (
    AuthenticationError,
    DownloadControlAction,
    DownloadControlOutcome,
    DownloaderControlResult,
    DownloaderListing,
    DownloaderReadFailure,
    DownloaderRemovalResult,
    ExternalServiceError,
    ListingFreshness,
    TorrentOwnership,
    TorrentSnapshot,
    TorrentState,
)
from cleanarr.domain.config import TorrentRemovalPolicy
from cleanarr.domain.seeding import TorrentSeedingStatus, seeding_policy_skip_reason

_CONTROL_VERIFICATION_DELAYS = (0.0, 0.05, 0.1, 0.2, 0.4, 0.8)


@dataclass(frozen=True)
class DownloaderTarget:
    """A configured downloader client plus its stable runtime identity."""

    id: str
    name: str
    kind: str
    client: DownloaderClientPort


class MultiDownloaderClient:
    """Fan out hash ownership checks and removals to every enabled downloader."""

    def __init__(self, targets: Sequence[DownloaderTarget], *, max_read_concurrency: int = 4) -> None:
        self._targets = tuple(targets)
        self._max_read_concurrency = max(1, min(max_read_concurrency, 16))

    def configured_client_ids(self) -> set[str]:
        return {target.id for target in self._targets}

    async def close(self) -> None:
        await asyncio.gather(*(target.client.close() for target in self._targets))

    async def ping(self) -> None:
        await asyncio.gather(*(target.client.ping() for target in self._targets))

    async def get_version(self) -> str:
        versions = await asyncio.gather(*(target.client.get_version() for target in self._targets))
        return ", ".join(
            f"{kind}={version}"
            for kind, version in sorted(
                {(target.kind, version) for target, version in zip(self._targets, versions, strict=True)}
            )
        )

    async def delete_hashes(
        self,
        hashes: Sequence[str],
        *,
        delete_files: bool,
        dry_run: bool = False,
    ) -> Sequence[DownloaderRemovalResult]:
        normalized = _normalize_hashes(hashes)
        if not normalized:
            return []

        outcomes = await asyncio.gather(
            *(
                target.client.delete_hashes(normalized, delete_files=delete_files, dry_run=dry_run)
                for target in self._targets
            ),
            return_exceptions=True,
        )
        results: list[DownloaderRemovalResult] = []
        for target, outcome in zip(self._targets, outcomes, strict=True):
            if isinstance(outcome, Exception):
                message = outcome.message if isinstance(outcome, ExternalServiceError) else str(outcome)
                results.extend(
                    DownloaderRemovalResult(
                        hash_value=hash_value,
                        existed=False,
                        client_id=target.id,
                        client_name=target.name,
                        client_kind=target.kind,
                        error=message,
                    )
                    for hash_value in normalized
                )
                continue
            if isinstance(outcome, BaseException):
                raise outcome
            results.extend(outcome)
        return results

    async def list_torrents(self) -> DownloaderListing:
        """Read every configured client without allowing one failed target to hide others."""
        semaphore = asyncio.Semaphore(self._max_read_concurrency)

        async def read_target(target: DownloaderTarget) -> tuple[DownloaderTarget, DownloaderListing | Exception]:
            async with semaphore:
                try:
                    return target, await cast(DownloaderReadPort, target.client).list_torrents()
                except Exception as exc:  # adapters are isolated by target; cancellation propagates
                    return target, exc

        outcomes = await asyncio.gather(*(read_target(target) for target in self._targets))
        torrents: list[TorrentSnapshot] = []
        failures: list[DownloaderReadFailure] = []
        completed_client_ids: list[str] = []
        for target, outcome in outcomes:
            if isinstance(outcome, Exception):
                failures.append(_read_failure(target, "client_read_failed"))
                continue
            torrents.extend(
                replace(snapshot, client_id=target.id, client_name=target.name, client_kind=target.kind)
                for snapshot in outcome.torrents
            )
            failures.extend(
                replace(failure, client_id=target.id, client_name=target.name, client_kind=target.kind)
                for failure in outcome.failures
            )
            if not outcome.failures:
                completed_client_ids.append(target.id)
        return DownloaderListing(
            torrents=tuple(torrents),
            failures=tuple(failures),
            completed_client_ids=tuple(completed_client_ids),
        )

    async def control_torrent(
        self, client_id: str, info_hash: str, *, action: DownloadControlAction
    ) -> DownloaderControlResult:
        """Route one reversible operation to its owner; never broadcast mutations."""
        target = next((candidate for candidate in self._targets if candidate.id == client_id), None)
        if target is None:
            return DownloaderControlResult(
                client_id=client_id,
                client_name="unknown client",
                client_kind="unknown",
                info_hash=_normalize_single_hash(info_hash),
                action=action,
                outcome=DownloadControlOutcome.UNKNOWN,
                code="unknown_client",
            )
        try:
            result = await cast(DownloaderControlPort, target.client).control_torrent(info_hash, action=action)
        except Exception:
            return DownloaderControlResult(
                client_id=target.id,
                client_name=target.name,
                client_kind=target.kind,
                info_hash=_normalize_single_hash(info_hash),
                action=action,
                outcome=DownloadControlOutcome.FAILED,
                code="client_control_failed",
            )
        return replace(
            result,
            client_id=target.id,
            client_name=target.name,
            client_kind=target.kind,
        )


class _UnsupportedTransmissionRpc(Exception):
    """Signal that the server only supports the legacy Transmission RPC generation."""


class TransmissionClient:
    """Transmission adapter supporting legacy RPC and JSON-RPC 2.0."""

    def __init__(
        self,
        *,
        base_url: str,
        username: str,
        password: str,
        timeout_seconds: float,
        service_id: str | None = None,
        service_name: str | None = None,
        seeding_policy: TorrentRemovalPolicy = TorrentRemovalPolicy.IMMEDIATE,
        min_seed_ratio: float | None = None,
        min_seed_time_minutes: int | None = None,
    ) -> None:
        self._system = "transmission"
        self._url = base_url.rstrip("/")
        self._service_id = service_id
        self._service_name = service_name
        self._seeding_policy = seeding_policy
        self._min_seed_ratio = min_seed_ratio
        self._min_seed_time_minutes = min_seed_time_minutes
        self._session_id: str | None = None
        self._modern: bool | None = None
        self._version: str | None = None
        auth = httpx.BasicAuth(username, password) if username or password else None
        self._client = httpx.AsyncClient(
            timeout=timeout_seconds,
            auth=auth,
            transport=httpx.AsyncHTTPTransport(retries=1),
        )
        self._request_id = 0

    async def close(self) -> None:
        await self._client.aclose()

    async def ping(self) -> None:
        await self.get_version()

    async def get_version(self) -> str:
        if self._version is not None:
            return self._version

        if self._modern is None:
            try:
                result = await self._call_generation(
                    method="session_get",
                    params={"fields": ["version", "rpc_version_semver"]},
                    modern=True,
                )
            except _UnsupportedTransmissionRpc:
                result = await self._call_generation(method="session-get", params={}, modern=False)
                self._modern = False
            else:
                self._modern = True
        else:
            result = await self._call_generation(
                method="session_get" if self._modern else "session-get",
                params={"fields": ["version", "rpc_version_semver"]} if self._modern else {},
                modern=self._modern,
            )

        version = result.get("version") or result.get("rpc_version_semver") or result.get("rpc-version-semver")
        self._version = str(version or "unknown")
        return self._version

    async def delete_hashes(
        self,
        hashes: Sequence[str],
        *,
        delete_files: bool,
        dry_run: bool = False,
    ) -> Sequence[DownloaderRemovalResult]:
        normalized = _normalize_hashes(hashes)
        if not normalized:
            return []

        await self.get_version()
        modern = self._modern is True
        hash_key = "hash_string" if modern else "hashString"
        ratio_key = "upload_ratio" if modern else "uploadRatio"
        seeding_time_key = "seconds_seeding" if modern else "secondsSeeding"
        result = await self._call_generation(
            method="torrent_get" if modern else "torrent-get",
            params={"fields": ["id", hash_key, ratio_key, seeding_time_key]},
            modern=modern,
        )
        torrents = result.get("torrents", [])
        torrent_ids: list[int] = []
        matches: dict[str, tuple[TorrentSeedingStatus, str | None]] = {}
        for torrent in torrents if isinstance(torrents, list) else []:
            if not isinstance(torrent, dict):
                continue
            hash_value = str(torrent.get(hash_key, "")).upper()
            if hash_value in normalized and isinstance(torrent.get("id"), int):
                status = TorrentSeedingStatus(
                    ratio=_optional_float(torrent.get(ratio_key)),
                    seeding_time_seconds=_optional_int(torrent.get(seeding_time_key)),
                )
                skip_reason = self._skip_reason(status)
                matches[hash_value] = (status, skip_reason)
                if skip_reason is None:
                    torrent_ids.append(torrent["id"])

        if torrent_ids and not dry_run:
            await self._call_generation(
                method="torrent_remove" if modern else "torrent-remove",
                params={
                    "ids": torrent_ids,
                    "delete_local_data" if modern else "delete-local-data": delete_files,
                },
                modern=modern,
            )
        return [
            self._result(
                hash_value,
                existed=hash_value in matches,
                status=matches[hash_value][0] if hash_value in matches else None,
                skip_reason=matches[hash_value][1] if hash_value in matches else None,
            )
            for hash_value in normalized
        ]

    async def list_torrents(self) -> DownloaderListing:
        await self.get_version()
        modern = self._modern is True
        fields = (
            [
                "hash_string",
                "name",
                "status",
                "percent_done",
                "total_size",
                "have_valid",
                "uploaded_ever",
                "upload_ratio",
                "seconds_seeding",
                "rate_download",
                "rate_upload",
                "eta",
                "added_date",
                "done_date",
                "activity_date",
                "labels",
                "tracker_stats",
            ]
            if modern
            else [
                "hashString",
                "name",
                "status",
                "percentDone",
                "totalSize",
                "haveValid",
                "uploadedEver",
                "uploadRatio",
                "secondsSeeding",
                "rateDownload",
                "rateUpload",
                "eta",
                "addedDate",
                "doneDate",
                "activityDate",
                "labels",
                "trackerStats",
            ]
        )
        result = await self._call_generation(
            method="torrent_get" if modern else "torrent-get", params={"fields": fields}, modern=modern
        )
        raw_torrents = result.get("torrents")
        if not isinstance(raw_torrents, list):
            return DownloaderListing(failures=(_local_failure(self, "invalid_torrent_list"),))
        snapshots: list[TorrentSnapshot] = []
        failures: list[DownloaderReadFailure] = []
        for item in raw_torrents:
            snapshot = _transmission_snapshot(item, modern=modern, client=self)
            if snapshot is None:
                failures.append(_local_failure(self, "malformed_torrent"))
            else:
                snapshots.append(snapshot)
        return DownloaderListing(torrents=tuple(snapshots), failures=tuple(failures))

    async def control_torrent(self, info_hash: str, *, action: DownloadControlAction) -> DownloaderControlResult:
        normalized = _normalize_single_hash(info_hash)
        if not normalized:
            return _control_invalid(self, normalized, action)
        try:
            pre_listing = await self.list_torrents()
        except ExternalServiceError:
            return _control_unknown(self, normalized, action, "pre_read_failed")
        before = _find_snapshot(pre_listing, normalized)
        if before is None and pre_listing.failures:
            return _control_unknown(self, normalized, action, "pre_read_incomplete")
        if before is None:
            return _control_not_found(self, normalized, action)
        if before.state is TorrentState.UNKNOWN:
            return _control_unknown(self, normalized, action, "pre_state_unknown", before=before)
        if _has_desired_state(before.state, action):
            return _control_already(self, normalized, action, before)
        modern = self._modern is True
        try:
            await self._call_generation(
                method=("torrent_stop" if action is DownloadControlAction.PAUSE else "torrent_start")
                if modern
                else ("torrent-stop" if action is DownloadControlAction.PAUSE else "torrent-start"),
                params={"ids": [normalized]},
                modern=modern,
            )
        except ExternalServiceError:
            return _control_unknown(self, normalized, action, "mutation_or_post_read_failed", before=before)
        after, failure_code = await _verify_post_control_state(self, normalized, action)
        if failure_code is not None:
            return _control_unknown(self, normalized, action, failure_code, before=before, after=after)
        assert after is not None
        return _control_applied(self, normalized, action, before, after)

    async def _call_generation(self, *, method: str, params: dict[str, Any], modern: bool) -> dict[str, Any]:
        self._request_id += 1
        if modern:
            payload: dict[str, Any] = {
                "jsonrpc": "2.0",
                "method": method,
                "params": params,
                "id": self._request_id,
            }
        else:
            payload = {"method": method, "arguments": params, "tag": self._request_id}

        response = await self._post(payload)
        try:
            body = response.json()
        except ValueError as exc:
            raise ExternalServiceError(self._system, "Transmission returned an invalid JSON response.") from exc
        if not isinstance(body, dict):
            raise ExternalServiceError(self._system, "Transmission returned an unexpected RPC response.")

        if modern:
            error = body.get("error")
            if isinstance(error, dict):
                message = str(error.get("message") or "unknown JSON-RPC error")
                if error.get("code") == -32601 or "method" in message.casefold():
                    raise _UnsupportedTransmissionRpc("unsupported RPC generation")
                raise ExternalServiceError(self._system, "Transmission RPC failed.")
            result = body.get("result")
            if not isinstance(result, dict):
                raise _UnsupportedTransmissionRpc("Transmission did not accept JSON-RPC 2.0.")
            return cast(dict[str, Any], result)

        rpc_result = body.get("result")
        if rpc_result != "success":
            raise ExternalServiceError(self._system, "Transmission RPC failed.")
        arguments = body.get("arguments", {})
        if not isinstance(arguments, dict):
            raise ExternalServiceError(self._system, "Transmission returned invalid legacy RPC arguments.")
        return cast(dict[str, Any], arguments)

    async def _post(self, payload: dict[str, Any]) -> httpx.Response:
        headers = {"X-Transmission-Session-Id": self._session_id} if self._session_id else {}
        try:
            response = await self._client.post(self._url, json=payload, headers=headers)
            if response.status_code == 409:
                session_id = response.headers.get("X-Transmission-Session-Id")
                if not session_id:
                    raise ExternalServiceError(self._system, "Transmission omitted its required session ID.")
                self._session_id = session_id
                response = await self._client.post(
                    self._url,
                    json=payload,
                    headers={"X-Transmission-Session-Id": session_id},
                )
        except httpx.HTTPError as exc:
            raise ExternalServiceError(
                self._system,
                f"Transmission request failed ({exc.__class__.__name__}).",
            ) from exc

        if response.status_code in {401, 403}:
            raise AuthenticationError(self._system, "Transmission rejected the configured credentials.")
        if response.status_code >= 400:
            raise ExternalServiceError(
                self._system,
                f"Transmission returned unexpected status {response.status_code}.",
            )
        return response

    def _skip_reason(self, status: TorrentSeedingStatus) -> str | None:
        return seeding_policy_skip_reason(
            self._seeding_policy,
            min_seed_ratio=self._min_seed_ratio,
            min_seed_time_minutes=self._min_seed_time_minutes,
            status=status,
        )

    def _result(
        self,
        hash_value: str,
        *,
        existed: bool,
        status: TorrentSeedingStatus | None = None,
        skip_reason: str | None = None,
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
        )


class DelugeClient:
    """Deluge Web JSON-RPC adapter."""

    def __init__(
        self,
        *,
        base_url: str,
        password: str,
        timeout_seconds: float,
        service_id: str | None = None,
        service_name: str | None = None,
        seeding_policy: TorrentRemovalPolicy = TorrentRemovalPolicy.IMMEDIATE,
        min_seed_ratio: float | None = None,
        min_seed_time_minutes: int | None = None,
    ) -> None:
        self._system = "deluge"
        self._url = base_url.rstrip("/")
        self._password = password
        self._service_id = service_id
        self._service_name = service_name
        self._seeding_policy = seeding_policy
        self._min_seed_ratio = min_seed_ratio
        self._min_seed_time_minutes = min_seed_time_minutes
        self._authenticated = False
        self._request_id = 0
        self._client = httpx.AsyncClient(
            timeout=timeout_seconds,
            transport=httpx.AsyncHTTPTransport(retries=1),
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def ping(self) -> None:
        await self.get_version()

    async def get_version(self) -> str:
        await self._login()
        connected = await self._rpc("web.connected", [])
        if connected is not True:
            raise ExternalServiceError(self._system, "Deluge Web is not connected to a daemon.")
        version = await self._rpc("daemon.get_version", [])
        return str(version or "unknown")

    async def delete_hashes(
        self,
        hashes: Sequence[str],
        *,
        delete_files: bool,
        dry_run: bool = False,
    ) -> Sequence[DownloaderRemovalResult]:
        normalized = _normalize_hashes(hashes)
        if not normalized:
            return []

        await self._login()
        torrent_ids = await self._rpc("core.get_session_state", [])
        torrent_ids = torrent_ids if isinstance(torrent_ids, list) else []
        actual_ids = {
            str(torrent_id).upper(): str(torrent_id)
            for torrent_id in torrent_ids
            if str(torrent_id).upper() in normalized
        }
        existing = set(actual_ids)
        statuses: dict[str, TorrentSeedingStatus] = {}
        if existing and self._seeding_policy is TorrentRemovalPolicy.DEFER:
            raw_statuses = await self._rpc(
                "core.get_torrents_status",
                [{}, ["ratio", "seeding_time"]],
            )
            if isinstance(raw_statuses, dict):
                for torrent_id, raw_status in raw_statuses.items():
                    normalized_id = str(torrent_id).upper()
                    if normalized_id not in existing or not isinstance(raw_status, dict):
                        continue
                    statuses[normalized_id] = TorrentSeedingStatus(
                        ratio=_optional_float(raw_status.get("ratio")),
                        seeding_time_seconds=_optional_int(raw_status.get("seeding_time")),
                    )

        decisions = {
            hash_value: self._skip_reason(statuses.get(hash_value, TorrentSeedingStatus())) for hash_value in existing
        }
        removable = {hash_value for hash_value in existing if decisions[hash_value] is None}
        if removable and not dry_run:
            errors = await self._rpc(
                "core.remove_torrents",
                [[actual_ids[hash_value] for hash_value in sorted(removable)], delete_files],
            )
            if errors:
                raise ExternalServiceError(self._system, "Deluge failed to remove one or more torrents.")
        return [
            self._result(
                hash_value,
                existed=hash_value in existing,
                status=statuses.get(hash_value),
                skip_reason=decisions.get(hash_value),
            )
            for hash_value in normalized
        ]

    async def list_torrents(self) -> DownloaderListing:
        await self._login()
        fields = [
            "name",
            "state",
            "progress",
            "total_size",
            "total_done",
            "total_uploaded",
            "ratio",
            "seeding_time",
            "download_payload_rate",
            "upload_payload_rate",
            "eta",
            "time_added",
            "completed_time",
            "label",
            "tracker",
        ]
        raw_torrents = await self._rpc("core.get_torrents_status", [{}, fields])
        if not isinstance(raw_torrents, dict):
            return DownloaderListing(failures=(_local_failure(self, "invalid_torrent_list"),))
        snapshots: list[TorrentSnapshot] = []
        failures: list[DownloaderReadFailure] = []
        for torrent_id, item in raw_torrents.items():
            snapshot = _deluge_snapshot(torrent_id, item, client=self)
            if snapshot is None:
                failures.append(_local_failure(self, "malformed_torrent"))
            else:
                snapshots.append(snapshot)
        return DownloaderListing(torrents=tuple(snapshots), failures=tuple(failures))

    async def control_torrent(self, info_hash: str, *, action: DownloadControlAction) -> DownloaderControlResult:
        normalized = _normalize_single_hash(info_hash)
        if not normalized:
            return _control_invalid(self, normalized, action)
        try:
            pre_listing = await self.list_torrents()
        except ExternalServiceError:
            return _control_unknown(self, normalized, action, "pre_read_failed")
        before = _find_snapshot(pre_listing, normalized)
        if before is None and pre_listing.failures:
            return _control_unknown(self, normalized, action, "pre_read_incomplete")
        if before is None:
            return _control_not_found(self, normalized, action)
        if before.state is TorrentState.UNKNOWN:
            return _control_unknown(self, normalized, action, "pre_state_unknown", before=before)
        if _has_desired_state(before.state, action):
            return _control_already(self, normalized, action, before)
        try:
            torrent_ids = await self._rpc("core.get_session_state", [])
            actual_id = (
                next(
                    (
                        str(torrent_id)
                        for torrent_id in torrent_ids
                        if _normalize_single_hash(str(torrent_id)) == normalized
                    ),
                    None,
                )
                if isinstance(torrent_ids, list)
                else None
            )
            if actual_id is None:
                return _control_unknown(self, normalized, action, "pre_read_incomplete", before=before)
            await self._rpc(
                "core.pause_torrent" if action is DownloadControlAction.PAUSE else "core.resume_torrent",
                [[actual_id]],
            )
        except ExternalServiceError:
            return _control_unknown(self, normalized, action, "mutation_or_post_read_failed", before=before)
        after, failure_code = await _verify_post_control_state(self, normalized, action)
        if failure_code is not None:
            return _control_unknown(self, normalized, action, failure_code, before=before, after=after)
        assert after is not None
        return _control_applied(self, normalized, action, before, after)

    async def _login(self) -> None:
        if self._authenticated:
            return
        result = await self._rpc("auth.login", [self._password], allow_unauthenticated=True)
        if not result:
            raise AuthenticationError(self._system, "Deluge rejected the configured password.")
        self._authenticated = True

    async def _rpc(self, method: str, params: list[Any], *, allow_unauthenticated: bool = False) -> Any:
        self._request_id += 1
        try:
            response = await self._client.post(
                self._url,
                json={"method": method, "params": params, "id": self._request_id},
            )
        except httpx.HTTPError as exc:
            raise ExternalServiceError(
                self._system,
                f"Deluge request failed ({exc.__class__.__name__}).",
            ) from exc

        if response.status_code in {401, 403}:
            raise AuthenticationError(self._system, "Deluge rejected the configured credentials.")
        if response.status_code >= 400:
            raise ExternalServiceError(
                self._system,
                f"Deluge returned unexpected status {response.status_code}.",
            )
        try:
            body = response.json()
        except ValueError as exc:
            raise ExternalServiceError(self._system, "Deluge returned an invalid JSON response.") from exc
        if not isinstance(body, dict):
            raise ExternalServiceError(self._system, "Deluge returned an unexpected RPC response.")
        error = body.get("error")
        if error:
            if not allow_unauthenticated and "Not authenticated" in str(error):
                self._authenticated = False
                raise AuthenticationError(self._system, "Deluge Web session is not authenticated.")
            raise ExternalServiceError(self._system, "Deluge RPC failed.")
        return body.get("result")

    def _skip_reason(self, status: TorrentSeedingStatus) -> str | None:
        return seeding_policy_skip_reason(
            self._seeding_policy,
            min_seed_ratio=self._min_seed_ratio,
            min_seed_time_minutes=self._min_seed_time_minutes,
            status=status,
        )

    def _result(
        self,
        hash_value: str,
        *,
        existed: bool,
        status: TorrentSeedingStatus | None = None,
        skip_reason: str | None = None,
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
        )


class RTorrentClient:
    """rTorrent HTTP XML-RPC adapter."""

    def __init__(
        self,
        *,
        base_url: str,
        username: str,
        password: str,
        timeout_seconds: float,
        service_id: str | None = None,
        service_name: str | None = None,
        seeding_policy: TorrentRemovalPolicy = TorrentRemovalPolicy.IMMEDIATE,
        min_seed_ratio: float | None = None,
        min_seed_time_minutes: int | None = None,
    ) -> None:
        self._system = "rtorrent"
        self._url = base_url.rstrip("/")
        self._service_id = service_id
        self._service_name = service_name
        self._seeding_policy = seeding_policy
        self._min_seed_ratio = min_seed_ratio
        self._min_seed_time_minutes = min_seed_time_minutes
        auth = httpx.BasicAuth(username, password) if username or password else None
        self._client = httpx.AsyncClient(
            timeout=timeout_seconds,
            auth=auth,
            transport=httpx.AsyncHTTPTransport(retries=1),
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def ping(self) -> None:
        await self.get_version()

    async def get_version(self) -> str:
        version = await self._rpc("system.client_version")
        return str(version or "unknown")

    async def delete_hashes(
        self,
        hashes: Sequence[str],
        *,
        delete_files: bool,
        dry_run: bool = False,
    ) -> Sequence[DownloaderRemovalResult]:
        normalized = _normalize_hashes(hashes)
        if not normalized:
            return []

        torrent_ids = await self._rpc("download_list")
        torrent_ids = torrent_ids if isinstance(torrent_ids, (list, tuple)) else []
        existing = {str(torrent_id).upper() for torrent_id in torrent_ids if str(torrent_id).upper() in normalized}
        statuses: dict[str, TorrentSeedingStatus] = {}
        decisions: dict[str, str | None] = {}
        for hash_value in sorted(existing):
            status = await self._seeding_status(hash_value)
            statuses[hash_value] = status
            decisions[hash_value] = self._skip_reason(status)
            if decisions[hash_value] is not None or dry_run:
                continue
            if delete_files:
                data_path = await self._data_path(hash_value)
                await self._rpc("d.stop", hash_value)
                await self._rpc("d.close", hash_value)
                await self._rpc("execute.throw", "", "/bin/rm", "-rf", "--", data_path)
            await self._rpc("d.erase", hash_value)
        return [
            self._result(
                hash_value,
                existed=hash_value in existing,
                status=statuses.get(hash_value),
                skip_reason=decisions.get(hash_value),
            )
            for hash_value in normalized
        ]

    async def list_torrents(self) -> DownloaderListing:
        raw_ids = await self._rpc("download_list")
        torrent_ids = raw_ids if isinstance(raw_ids, (list, tuple)) else None
        if torrent_ids is None:
            return DownloaderListing(failures=(_local_failure(self, "invalid_torrent_list"),))
        semaphore = asyncio.Semaphore(4)

        async def read_one(torrent_id: object) -> TorrentSnapshot | None:
            info_hash = _normalize_single_hash(str(torrent_id))
            if not info_hash:
                return None
            async with semaphore:
                try:
                    return await self._read_snapshot(info_hash)
                except AuthenticationError:
                    raise
                except ExternalServiceError:
                    return None

        entries = await asyncio.gather(*(read_one(torrent_id) for torrent_id in torrent_ids))
        snapshots = [snapshot for snapshot in entries if snapshot is not None]
        failures = tuple(
            _local_failure(self, "malformed_or_unreadable_torrent") for snapshot in entries if snapshot is None
        )
        return DownloaderListing(torrents=tuple(snapshots), failures=failures)

    async def _read_snapshot(self, info_hash: str) -> TorrentSnapshot:
        raw_state, raw_active = await asyncio.gather(
            self._rpc("d.state", info_hash),
            self._rpc("d.is_active", info_hash),
        )
        optional_values = await asyncio.gather(
            self._rpc("d.name", info_hash),
            self._rpc("d.completed_bytes", info_hash),
            self._rpc("d.size_bytes", info_hash),
            self._rpc("d.up.total", info_hash),
            self._rpc("d.ratio", info_hash),
            self._rpc("d.timestamp.finished", info_hash),
            self._rpc("d.down.rate", info_hash),
            self._rpc("d.up.rate", info_hash),
            self._rpc("d.timestamp.started", info_hash),
            self._rpc("d.timestamp.last_active", info_hash),
            self._rpc("d.custom1", info_hash),
            self._rpc("d.tracker", info_hash),
            return_exceptions=True,
        )
        for outcome in optional_values:
            if isinstance(outcome, AuthenticationError):
                raise outcome
            if isinstance(outcome, BaseException) and not isinstance(outcome, Exception):
                raise outcome
        values = [None if isinstance(outcome, Exception) else outcome for outcome in optional_values]
        snapshot = _rtorrent_snapshot(info_hash, [values[0], raw_state, raw_active, *values[1:]], client=self)
        if any(isinstance(outcome, Exception) for outcome in optional_values):
            return replace(snapshot, unavailable_reason="optional_metrics_unavailable")
        return snapshot

    async def control_torrent(self, info_hash: str, *, action: DownloadControlAction) -> DownloaderControlResult:
        normalized = _normalize_single_hash(info_hash)
        if not normalized:
            return _control_invalid(self, normalized, action)
        try:
            pre_listing = await self.list_torrents()
        except ExternalServiceError:
            return _control_unknown(self, normalized, action, "pre_read_failed")
        before = _find_snapshot(pre_listing, normalized)
        if before is None and pre_listing.failures:
            return _control_unknown(self, normalized, action, "pre_read_incomplete")
        if before is None:
            return _control_not_found(self, normalized, action)
        if before.state is TorrentState.UNKNOWN:
            return _control_unknown(self, normalized, action, "pre_state_unknown", before=before)
        if _has_desired_state(before.state, action):
            return _control_already(self, normalized, action, before)
        try:
            # d.pause/d.resume are deliberately distinct from destructive d.stop/close/erase.
            await self._rpc("d.pause" if action is DownloadControlAction.PAUSE else "d.resume", normalized)
        except ExternalServiceError:
            return _control_unknown(self, normalized, action, "mutation_or_post_read_failed", before=before)
        after, failure_code = await _verify_post_control_state(self, normalized, action)
        if failure_code is not None:
            return _control_unknown(self, normalized, action, failure_code, before=before, after=after)
        assert after is not None
        return _control_applied(self, normalized, action, before, after)

    async def _seeding_status(self, hash_value: str) -> TorrentSeedingStatus:
        if self._seeding_policy is not TorrentRemovalPolicy.DEFER:
            return TorrentSeedingStatus()
        raw_ratio = _optional_float(await self._rpc("d.ratio", hash_value))
        finished_at = _optional_int(await self._rpc("d.timestamp.finished", hash_value))
        seeding_time = max(0, int(time.time()) - finished_at) if finished_at else None
        return TorrentSeedingStatus(
            ratio=raw_ratio / 1000 if raw_ratio is not None else None,
            seeding_time_seconds=seeding_time,
        )

    def _skip_reason(self, status: TorrentSeedingStatus) -> str | None:
        return seeding_policy_skip_reason(
            self._seeding_policy,
            min_seed_ratio=self._min_seed_ratio,
            min_seed_time_minutes=self._min_seed_time_minutes,
            status=status,
        )

    async def _data_path(self, hash_value: str) -> str:
        base_path = str(await self._rpc("d.base_path", hash_value) or "")
        if not base_path:
            directory = str(await self._rpc("d.directory", hash_value) or "")
            name = str(await self._rpc("d.name", hash_value) or "")
            is_multi_file = bool(await self._rpc("d.is_multi_file", hash_value))
            base_path = directory if is_multi_file else posixpath.join(directory, name)

        path = PurePosixPath(base_path)
        if not path.is_absolute() or ".." in path.parts or len(path.parts) < 3:
            raise ExternalServiceError(
                self._system,
                f"rTorrent returned an unsafe data path; refusing local-data removal: {base_path!r}",
            )
        return str(path)

    async def _rpc(self, method: str, *params: Any) -> Any:
        request_body = dumps(params, methodname=method, allow_none=True)
        try:
            response = await self._client.post(
                self._url,
                content=request_body,
                headers={"Content-Type": "text/xml"},
            )
        except httpx.HTTPError as exc:
            raise ExternalServiceError(
                self._system,
                f"rTorrent request failed ({exc.__class__.__name__}).",
            ) from exc

        if response.status_code in {401, 403}:
            raise AuthenticationError(self._system, "rTorrent rejected the configured credentials.")
        if response.status_code >= 400:
            raise ExternalServiceError(
                self._system,
                f"rTorrent returned unexpected status {response.status_code}.",
            )
        try:
            values, _ = loads(response.content)
        except Fault as exc:
            raise ExternalServiceError(self._system, "rTorrent RPC failed.") from exc
        except Exception as exc:
            raise ExternalServiceError(self._system, "rTorrent returned an invalid XML-RPC response.") from exc
        return values[0] if values else None

    def _result(
        self,
        hash_value: str,
        *,
        existed: bool,
        status: TorrentSeedingStatus | None = None,
        skip_reason: str | None = None,
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
        )


def _normalize_single_hash(value: str) -> str:
    normalized = value.strip().upper()
    return (
        normalized
        if len(normalized) in {40, 64} and all(character in "0123456789ABCDEF" for character in normalized)
        else ""
    )


def _read_failure(target: DownloaderTarget, code: str) -> DownloaderReadFailure:
    return DownloaderReadFailure(target.id, target.name, target.kind, code)


def _local_failure(client: Any, code: str) -> DownloaderReadFailure:
    return DownloaderReadFailure(
        str(client._service_id or client._system),
        _safe_text(client._service_name) or str(client._system),
        str(client._system),
        code,
    )


def _client_fields(client: Any) -> tuple[str, str, str]:
    kind = str(client._system)
    return str(client._service_id or kind), _safe_text(client._service_name) or kind, kind


def _find_snapshot(listing: DownloaderListing, info_hash: str) -> TorrentSnapshot | None:
    return next((torrent for torrent in listing.torrents if torrent.info_hash == info_hash), None)


def _has_desired_state(state: TorrentState, action: DownloadControlAction) -> bool:
    if action is DownloadControlAction.PAUSE:
        return state is TorrentState.STOPPED
    return state in {TorrentState.DOWNLOADING, TorrentState.SEEDING, TorrentState.QUEUED, TorrentState.CHECKING}


async def _verify_post_control_state(
    client: Any,
    info_hash: str,
    action: DownloadControlAction,
) -> tuple[TorrentSnapshot | None, str | None]:
    """Poll boundedly for an asynchronously applied reversible control command."""
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
        after = _find_snapshot(listing, info_hash)
        if after is not None and _has_desired_state(after.state, action):
            return after, None
        failure_code = "post_read_incomplete" if after is None and listing.failures else "post_state_unverified"
    return after, failure_code


def _control_result(
    client: Any,
    info_hash: str,
    action: DownloadControlAction,
    outcome: DownloadControlOutcome,
    code: str,
    *,
    before: TorrentSnapshot | None = None,
    after: TorrentSnapshot | None = None,
) -> DownloaderControlResult:
    client_id, client_name, client_kind = _client_fields(client)
    return DownloaderControlResult(client_id, client_name, client_kind, info_hash, action, outcome, before, after, code)


def _control_unknown(
    client: Any,
    info_hash: str,
    action: DownloadControlAction,
    code: str,
    *,
    before: TorrentSnapshot | None = None,
    after: TorrentSnapshot | None = None,
) -> DownloaderControlResult:
    return _control_result(client, info_hash, action, DownloadControlOutcome.UNKNOWN, code, before=before, after=after)


def _control_not_found(client: Any, info_hash: str, action: DownloadControlAction) -> DownloaderControlResult:
    return _control_result(client, info_hash, action, DownloadControlOutcome.NOT_FOUND, "not_found")


def _control_invalid(client: Any, info_hash: str, action: DownloadControlAction) -> DownloaderControlResult:
    return _control_result(client, info_hash, action, DownloadControlOutcome.UNKNOWN, "invalid_identifier")


def _control_already(
    client: Any, info_hash: str, action: DownloadControlAction, before: TorrentSnapshot
) -> DownloaderControlResult:
    return _control_result(
        client,
        info_hash,
        action,
        DownloadControlOutcome.ALREADY_IN_DESIRED_STATE,
        "already_in_desired_state",
        before=before,
        after=before,
    )


def _control_applied(
    client: Any, info_hash: str, action: DownloadControlAction, before: TorrentSnapshot, after: TorrentSnapshot
) -> DownloaderControlResult:
    return _control_result(
        client, info_hash, action, DownloadControlOutcome.APPLIED, "applied", before=before, after=after
    )


def _safe_text(value: object, *, limit: int = 160) -> str | None:
    if not isinstance(value, str):
        return None
    text = " ".join(value.split())[:limit]
    if not text or "://" in text or text.startswith(("/", "\\")):
        return None
    return text


def _safe_tracker(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    parsed = urlparse(value if "://" in value else f"//{value}")
    return _safe_text(parsed.hostname, limit=120)


def _safe_tags(value: object) -> tuple[str, ...] | None:
    if value is None:
        return None
    if isinstance(value, str):
        values: Sequence[object] = value.split(",")
    elif isinstance(value, (list, tuple, set)):
        values = tuple(value)
    else:
        return None
    return tuple(filter(None, (_safe_text(tag, limit=64) for tag in values)))[:20]


def _nonnegative_int(value: object) -> int | None:
    parsed = _optional_int(value)
    return parsed if parsed is not None and parsed >= 0 else None


def _nonnegative_float(value: object) -> float | None:
    parsed = _optional_float(value)
    return parsed if parsed is not None and parsed >= 0 else None


def _progress(value: object) -> float | None:
    parsed = _optional_float(value)
    if parsed is None:
        return None
    if parsed > 1 and parsed <= 100:
        parsed /= 100
    return parsed if 0 <= parsed <= 1 else None


def _fraction(value: object) -> float | None:
    parsed = _optional_float(value)
    return parsed if parsed is not None and 0 <= parsed <= 1 else None


def _eta(value: object) -> int | None:
    parsed = _nonnegative_int(value)
    return parsed if parsed is not None and parsed < 8_640_000 else None


def _timestamp(value: object) -> datetime | None:
    parsed = _nonnegative_int(value)
    if not parsed:
        return None
    try:
        return datetime.fromtimestamp(parsed, tz=UTC)
    except (OverflowError, OSError, ValueError):
        return None


def _snapshot(
    client: Any,
    info_hash: str,
    *,
    name: object,
    state: TorrentState,
    progress: object = None,
    total: object = None,
    downloaded: object = None,
    uploaded: object = None,
    ratio: object = None,
    seed_time: object = None,
    down_speed: object = None,
    up_speed: object = None,
    eta: object = None,
    added: object = None,
    completed: object = None,
    activity: object = None,
    category: object = None,
    tags: object = None,
    tracker: object = None,
) -> TorrentSnapshot:
    client_id, client_name, client_kind = _client_fields(client)
    safe_tags = _safe_tags(tags)
    return TorrentSnapshot(
        client_id,
        client_name,
        client_kind,
        info_hash,
        _safe_text(name),
        state,
        datetime.now(tz=UTC),
        progress=_progress(progress),
        total_bytes=_nonnegative_int(total),
        downloaded_bytes=_nonnegative_int(downloaded),
        uploaded_bytes=_nonnegative_int(uploaded),
        ratio=_nonnegative_float(ratio),
        seeding_time_seconds=_nonnegative_int(seed_time),
        download_speed_bytes_per_second=_nonnegative_int(down_speed),
        upload_speed_bytes_per_second=_nonnegative_int(up_speed),
        eta_seconds=_eta(eta),
        added_at=_timestamp(added),
        completed_at=_timestamp(completed),
        activity_at=_timestamp(activity),
        category=_safe_text(category, limit=64),
        tags=safe_tags,
        tracker_summary=_safe_tracker(tracker),
        freshness=ListingFreshness.FRESH,
        ownership=TorrentOwnership.UNKNOWN,
    )


def _transmission_snapshot(item: object, *, modern: bool, client: Any) -> TorrentSnapshot | None:
    if not isinstance(item, dict):
        return None

    def key(snake: str, camel: str) -> str:
        return snake if modern else camel

    info_hash = _normalize_single_hash(str(item.get(key("hash_string", "hashString"), "")))
    if not info_hash:
        return None
    status = _optional_int(item.get("status"))
    state = {
        0: TorrentState.STOPPED,
        1: TorrentState.CHECKING,
        2: TorrentState.CHECKING,
        3: TorrentState.QUEUED,
        4: TorrentState.DOWNLOADING,
        5: TorrentState.QUEUED,
        6: TorrentState.SEEDING,
    }.get(status if status is not None else -1, TorrentState.UNKNOWN)
    trackers = item.get(key("tracker_stats", "trackerStats"))
    tracker = (
        next(
            (
                candidate.get("announce")
                for candidate in trackers
                if isinstance(candidate, dict) and candidate.get("announce")
            ),
            None,
        )
        if isinstance(trackers, list)
        else None
    )
    labels = item.get("labels")
    tags = labels.split(",") if isinstance(labels, str) else labels
    return _snapshot(
        client,
        info_hash,
        name=item.get("name"),
        state=state,
        progress=_fraction(item.get(key("percent_done", "percentDone"))),
        total=item.get(key("total_size", "totalSize")),
        downloaded=item.get(key("have_valid", "haveValid")),
        uploaded=item.get(key("uploaded_ever", "uploadedEver")),
        ratio=item.get(key("upload_ratio", "uploadRatio")),
        seed_time=item.get(key("seconds_seeding", "secondsSeeding")),
        down_speed=item.get(key("rate_download", "rateDownload")),
        up_speed=item.get(key("rate_upload", "rateUpload")),
        eta=item.get("eta"),
        added=item.get(key("added_date", "addedDate")),
        completed=item.get(key("done_date", "doneDate")),
        activity=item.get(key("activity_date", "activityDate")),
        tags=tags,
        tracker=tracker,
    )


def _deluge_snapshot(torrent_id: object, item: object, *, client: Any) -> TorrentSnapshot | None:
    if not isinstance(item, dict):
        return None
    info_hash = _normalize_single_hash(str(torrent_id))
    if not info_hash:
        return None
    state_raw = str(item.get("state") or "").casefold()
    state = (
        TorrentState.STOPPED
        if "paused" in state_raw
        else TorrentState.SEEDING
        if "seeding" in state_raw
        else TorrentState.DOWNLOADING
        if "downloading" in state_raw
        else TorrentState.CHECKING
        if "check" in state_raw
        else TorrentState.QUEUED
        if "queue" in state_raw
        else TorrentState.ERROR
        if "error" in state_raw
        else TorrentState.UNKNOWN
    )
    return _snapshot(
        client,
        info_hash,
        name=item.get("name"),
        state=state,
        progress=item.get("progress"),
        total=item.get("total_size"),
        downloaded=item.get("total_done"),
        uploaded=item.get("total_uploaded"),
        ratio=item.get("ratio"),
        seed_time=item.get("seeding_time"),
        down_speed=item.get("download_payload_rate"),
        up_speed=item.get("upload_payload_rate"),
        eta=item.get("eta"),
        added=item.get("time_added"),
        completed=item.get("completed_time"),
        activity=item.get("last_seen_complete"),
        category=item.get("label"),
        tracker=item.get("tracker"),
    )


def _rtorrent_snapshot(info_hash: str, values: Sequence[object], *, client: Any) -> TorrentSnapshot:
    (
        name,
        raw_state,
        raw_active,
        completed,
        total,
        uploaded,
        ratio,
        finished,
        down_speed,
        up_speed,
        added,
        activity,
        category,
        tracker,
    ) = values
    state_value = _optional_int(raw_state)
    active = _optional_int(raw_active)
    completed_bytes = _nonnegative_int(completed)
    total_bytes = _nonnegative_int(total)
    raw_ratio = _nonnegative_float(ratio)
    state = (
        TorrentState.STOPPED
        if state_value == 0 or active == 0
        else TorrentState.SEEDING
        if state_value == 1 and active == 1 and completed_bytes == total_bytes
        else TorrentState.DOWNLOADING
        if state_value == 1 and active == 1
        else TorrentState.UNKNOWN
    )
    return _snapshot(
        client,
        info_hash,
        name=name,
        state=state,
        progress=completed_bytes / total_bytes
        if completed_bytes is not None and total_bytes is not None and total_bytes > 0
        else None,
        total=total,
        downloaded=completed,
        uploaded=uploaded,
        ratio=raw_ratio / 1000 if raw_ratio is not None else None,
        down_speed=down_speed,
        up_speed=up_speed,
        added=added,
        activity=activity,
        completed=finished,
        category=category,
        tracker=tracker,
    )


def _normalize_hashes(hashes: Sequence[str]) -> list[str]:
    return list(dict.fromkeys(hash_value.strip().upper() for hash_value in hashes if hash_value.strip()))


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
