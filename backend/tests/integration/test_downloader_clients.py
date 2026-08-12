"""Contract tests for torrent download-client HTTP adapters."""

from __future__ import annotations

import json
from typing import Any
from xmlrpc.client import dumps, loads

import httpx
import pytest
import respx

from cleanarr.domain import AuthenticationError, ExternalServiceError
from cleanarr.domain.config import TorrentRemovalPolicy
from cleanarr.infrastructure.downloaders import DelugeClient, RTorrentClient, TransmissionClient


@pytest.mark.asyncio
@respx.mock
async def test_transmission_legacy_rpc_negotiates_session_and_removes_existing_hashes() -> None:
    calls: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        calls.append(payload)
        if request.headers.get("X-Transmission-Session-Id") != "session-1":
            return httpx.Response(409, headers={"X-Transmission-Session-Id": "session-1"})
        if payload["method"] == "session_get":
            return httpx.Response(200, json={"result": "method name not recognized", "arguments": {}})
        if payload["method"] == "session-get":
            return httpx.Response(200, json={"result": "success", "arguments": {"version": "4.0.6"}})
        if payload["method"] == "torrent-get":
            return httpx.Response(
                200,
                json={
                    "result": "success",
                    "arguments": {"torrents": [{"id": 7, "hashString": "AA"}]},
                },
            )
        return httpx.Response(200, json={"result": "success", "arguments": {}})

    respx.post("http://transmission/transmission/rpc").mock(side_effect=handler)
    client = TransmissionClient(
        base_url="http://transmission/transmission/rpc",
        username="user",
        password="pass",
        timeout_seconds=5,
    )
    try:
        results = await client.delete_hashes(["aa", "bb"], delete_files=False)
    finally:
        await client.close()

    removal = next(call for call in calls if call["method"] == "torrent-remove")
    assert removal["arguments"] == {"ids": [7], "delete-local-data": False}
    assert [(result.hash_value, result.existed) for result in results] == [("AA", True), ("BB", False)]


@pytest.mark.asyncio
@respx.mock
async def test_transmission_json_rpc_uses_snake_case_methods() -> None:
    calls: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        calls.append(payload)
        method = payload["method"]
        if method == "session_get":
            result: dict[str, Any] = {"version": "4.1.0", "rpc_version_semver": "6.0.0"}
        elif method == "torrent_get":
            result = {"torrents": [{"id": 9, "hash_string": "BB"}]}
        else:
            result = {}
        return httpx.Response(200, json={"jsonrpc": "2.0", "result": result, "id": payload["id"]})

    respx.post("http://transmission/transmission/rpc").mock(side_effect=handler)
    client = TransmissionClient(
        base_url="http://transmission/transmission/rpc",
        username="",
        password="",
        timeout_seconds=5,
    )
    try:
        assert await client.get_version() == "4.1.0"
        results = await client.delete_hashes(["BB"], delete_files=True)
    finally:
        await client.close()

    removal = next(call for call in calls if call["method"] == "torrent_remove")
    assert removal["params"] == {"ids": [9], "delete_local_data": True}
    assert results[0].existed is True


@pytest.mark.asyncio
@respx.mock
async def test_transmission_reports_authentication_failure() -> None:
    respx.post("http://transmission/transmission/rpc").respond(status_code=401)
    client = TransmissionClient(
        base_url="http://transmission/transmission/rpc",
        username="bad",
        password="bad",
        timeout_seconds=5,
    )
    try:
        with pytest.raises(AuthenticationError, match="rejected"):
            await client.ping()
    finally:
        await client.close()


@pytest.mark.asyncio
@respx.mock
async def test_transmission_defers_removal_until_seed_ratio_is_met() -> None:
    calls: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        calls.append(payload)
        if payload["method"] == "session_get":
            result: dict[str, Any] = {"version": "4.1.0"}
        else:
            result = {"torrents": [{"id": 9, "hash_string": "AA", "upload_ratio": 0.5, "seconds_seeding": 7_200}]}
        return httpx.Response(200, json={"jsonrpc": "2.0", "result": result, "id": payload["id"]})

    respx.post("http://transmission/transmission/rpc").mock(side_effect=handler)
    client = TransmissionClient(
        base_url="http://transmission/transmission/rpc",
        username="",
        password="",
        timeout_seconds=5,
        seeding_policy=TorrentRemovalPolicy.DEFER,
        min_seed_ratio=1.0,
    )
    try:
        results = await client.delete_hashes(["AA"], delete_files=True)
    finally:
        await client.close()

    assert all(call["method"] != "torrent_remove" for call in calls)
    assert results[0].existed is True
    assert results[0].skip_reason == "Torrent removal deferred: seed ratio is 0.5 (required 1)."


@pytest.mark.asyncio
@respx.mock
async def test_deluge_web_rpc_authenticates_and_uses_batch_removal() -> None:
    calls: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        calls.append(payload)
        method = payload["method"]
        results: dict[str, Any] = {
            "auth.login": "session-id",
            "web.connected": True,
            "daemon.get_version": "2.2.0",
            "core.get_session_state": ["aa", "cc"],
            "core.remove_torrents": [],
        }
        return httpx.Response(200, json={"id": payload["id"], "result": results[method], "error": None})

    respx.post("http://deluge/json").mock(side_effect=handler)
    client = DelugeClient(base_url="http://deluge/json", password="secret", timeout_seconds=5)
    try:
        assert await client.get_version() == "2.2.0"
        results = await client.delete_hashes(["AA", "BB"], delete_files=True)
    finally:
        await client.close()

    removal = next(call for call in calls if call["method"] == "core.remove_torrents")
    assert removal["params"] == [["AA"], True]
    assert [(result.hash_value, result.existed) for result in results] == [("AA", True), ("BB", False)]


@pytest.mark.asyncio
@respx.mock
async def test_deluge_rejects_invalid_web_password() -> None:
    respx.post("http://deluge/json").respond(json={"id": 1, "result": False, "error": None})
    client = DelugeClient(base_url="http://deluge/json", password="bad", timeout_seconds=5)
    try:
        with pytest.raises(AuthenticationError, match="password"):
            await client.ping()
    finally:
        await client.close()


@pytest.mark.asyncio
@respx.mock
async def test_deluge_removes_only_after_all_seeding_thresholds_are_met() -> None:
    calls: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        calls.append(payload)
        results: dict[str, Any] = {
            "auth.login": "session-id",
            "core.get_session_state": ["aa"],
            "core.get_torrents_status": {"aa": {"ratio": 2.0, "seeding_time": 7_200}},
            "core.remove_torrents": [],
        }
        return httpx.Response(200, json={"id": payload["id"], "result": results[payload["method"]], "error": None})

    respx.post("http://deluge/json").mock(side_effect=handler)
    client = DelugeClient(
        base_url="http://deluge/json",
        password="secret",
        timeout_seconds=5,
        seeding_policy=TorrentRemovalPolicy.DEFER,
        min_seed_ratio=1.5,
        min_seed_time_minutes=60,
    )
    try:
        results = await client.delete_hashes(["AA"], delete_files=False)
    finally:
        await client.close()

    removal = next(call for call in calls if call["method"] == "core.remove_torrents")
    assert removal["params"] == [["AA"], False]
    assert results[0].skip_reason is None
    assert results[0].ratio == 2.0
    assert results[0].seeding_time_seconds == 7_200


@pytest.mark.asyncio
@respx.mock
async def test_rtorrent_xmlrpc_removes_data_only_from_validated_absolute_path() -> None:
    calls: list[tuple[str, tuple[Any, ...]]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        params, method = loads(request.content)
        assert method is not None
        calls.append((method, params))
        results: dict[str, Any] = {
            "system.client_version": "0.15.5",
            "download_list": ["AA"],
            "d.base_path": "/downloads/movies/Movie",
            "d.stop": 0,
            "d.close": 0,
            "execute.throw": 0,
            "d.erase": 0,
        }
        body = dumps((results[method],), methodresponse=True, allow_none=True)
        return httpx.Response(200, content=body, headers={"Content-Type": "text/xml"})

    respx.post("http://rtorrent/RPC2").mock(side_effect=handler)
    client = RTorrentClient(
        base_url="http://rtorrent/RPC2",
        username="user",
        password="pass",
        timeout_seconds=5,
    )
    try:
        assert await client.get_version() == "0.15.5"
        results = await client.delete_hashes(["AA", "BB"], delete_files=True)
    finally:
        await client.close()

    assert ("execute.throw", ("/bin/rm", "-rf", "--", "/downloads/movies/Movie")) in calls
    assert calls.index(("execute.throw", ("/bin/rm", "-rf", "--", "/downloads/movies/Movie"))) < calls.index(
        ("d.erase", ("AA",))
    )
    assert [(result.hash_value, result.existed) for result in results] == [("AA", True), ("BB", False)]


@pytest.mark.asyncio
@respx.mock
async def test_rtorrent_refuses_unsafe_data_path() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        _, method = loads(request.content)
        results: dict[str, Any] = {"download_list": ["AA"], "d.base_path": "/"}
        return httpx.Response(200, content=dumps((results[method],), methodresponse=True, allow_none=True))

    respx.post("http://rtorrent/RPC2").mock(side_effect=handler)
    client = RTorrentClient(
        base_url="http://rtorrent/RPC2",
        username="",
        password="",
        timeout_seconds=5,
    )
    try:
        with pytest.raises(ExternalServiceError, match="unsafe data path"):
            await client.delete_hashes(["AA"], delete_files=True)
    finally:
        await client.close()


@pytest.mark.asyncio
@respx.mock
async def test_rtorrent_defers_removal_using_scaled_ratio() -> None:
    calls: list[tuple[str, tuple[Any, ...]]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        params, method = loads(request.content)
        assert method is not None
        calls.append((method, params))
        results: dict[str, Any] = {
            "download_list": ["AA"],
            "d.ratio": 750,
            "d.timestamp.finished": 1,
        }
        return httpx.Response(
            200,
            content=dumps((results[method],), methodresponse=True, allow_none=True),
        )

    respx.post("http://rtorrent/RPC2").mock(side_effect=handler)
    client = RTorrentClient(
        base_url="http://rtorrent/RPC2",
        username="",
        password="",
        timeout_seconds=5,
        seeding_policy=TorrentRemovalPolicy.DEFER,
        min_seed_ratio=1.0,
    )
    try:
        results = await client.delete_hashes(["AA"], delete_files=True)
    finally:
        await client.close()

    assert ("d.erase", ("AA",)) not in calls
    assert results[0].ratio == 0.75
    assert results[0].skip_reason == "Torrent removal deferred: seed ratio is 0.75 (required 1)."
