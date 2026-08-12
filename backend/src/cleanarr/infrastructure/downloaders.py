"""Torrent download-client adapters."""

from __future__ import annotations

import asyncio
import posixpath
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, cast
from xmlrpc.client import Fault, dumps, loads

import httpx

from cleanarr.application.ports import DownloaderClientPort
from cleanarr.domain import AuthenticationError, DownloaderRemovalResult, ExternalServiceError
from cleanarr.domain.config import TorrentRemovalPolicy
from cleanarr.domain.seeding import TorrentSeedingStatus, seeding_policy_skip_reason


@dataclass(frozen=True)
class DownloaderTarget:
    """A configured downloader client plus its stable runtime identity."""

    id: str
    name: str
    kind: str
    client: DownloaderClientPort


class MultiDownloaderClient:
    """Fan out hash ownership checks and removals to every enabled downloader."""

    def __init__(self, targets: Sequence[DownloaderTarget]) -> None:
        self._targets = tuple(targets)

    async def close(self) -> None:
        await asyncio.gather(*(target.client.close() for target in self._targets))

    async def ping(self) -> None:
        await asyncio.gather(*(target.client.ping() for target in self._targets))

    async def get_version(self) -> str:
        versions = await asyncio.gather(*(target.client.get_version() for target in self._targets))
        return ", ".join(f"{target.name}={version}" for target, version in zip(self._targets, versions, strict=True))

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
            if isinstance(outcome, BaseException):
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
            results.extend(outcome)
        return results


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
                    raise _UnsupportedTransmissionRpc(message)
                raise ExternalServiceError(self._system, f"Transmission RPC failed: {message}")
            result = body.get("result")
            if not isinstance(result, dict):
                raise _UnsupportedTransmissionRpc("Transmission did not accept JSON-RPC 2.0.")
            return cast(dict[str, Any], result)

        rpc_result = body.get("result")
        if rpc_result != "success":
            message = str(rpc_result or "unknown legacy RPC error")
            raise ExternalServiceError(self._system, f"Transmission RPC failed: {message}")
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
            raise ExternalServiceError(self._system, f"Transmission request failed: {exc}") from exc

        if response.status_code in {401, 403}:
            raise AuthenticationError(self._system, "Transmission rejected the configured credentials.")
        if response.status_code >= 400:
            raise ExternalServiceError(
                self._system,
                f"Transmission returned unexpected status {response.status_code}: {response.text}",
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
        existing = {str(torrent_id).upper() for torrent_id in torrent_ids if str(torrent_id).upper() in normalized}
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
            errors = await self._rpc("core.remove_torrents", [sorted(removable), delete_files])
            if errors:
                raise ExternalServiceError(self._system, f"Deluge failed to remove torrents: {errors}")
        return [
            self._result(
                hash_value,
                existed=hash_value in existing,
                status=statuses.get(hash_value),
                skip_reason=decisions.get(hash_value),
            )
            for hash_value in normalized
        ]

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
            raise ExternalServiceError(self._system, f"Deluge request failed: {exc}") from exc

        if response.status_code in {401, 403}:
            raise AuthenticationError(self._system, "Deluge rejected the configured credentials.")
        if response.status_code >= 400:
            raise ExternalServiceError(
                self._system,
                f"Deluge returned unexpected status {response.status_code}: {response.text}",
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
            raise ExternalServiceError(self._system, f"Deluge RPC failed: {error}")
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
                await self._rpc("execute.throw", "/bin/rm", "-rf", "--", data_path)
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
            raise ExternalServiceError(self._system, f"rTorrent request failed: {exc}") from exc

        if response.status_code in {401, 403}:
            raise AuthenticationError(self._system, "rTorrent rejected the configured credentials.")
        if response.status_code >= 400:
            raise ExternalServiceError(
                self._system,
                f"rTorrent returned unexpected status {response.status_code}: {response.text}",
            )
        try:
            values, _ = loads(response.content)
        except Fault as exc:
            raise ExternalServiceError(self._system, f"rTorrent RPC failed: {exc.faultString}") from exc
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
