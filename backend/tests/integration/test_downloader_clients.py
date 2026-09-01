"""Contract tests for torrent download-client HTTP adapters."""

from __future__ import annotations

import json
from typing import Any
from xmlrpc.client import Fault, dumps, loads

import httpx
import pytest
import respx

from cleanarr.domain import (
    AuthenticationError,
    DownloadControlAction,
    DownloadControlOutcome,
    ExternalServiceError,
    TorrentState,
)
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
    assert removal["params"] == [["aa"], True]
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
    assert removal["params"] == [["aa"], False]
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

    assert ("execute.throw", ("", "/bin/rm", "-rf", "--", "/downloads/movies/Movie")) in calls
    assert calls.index(("execute.throw", ("", "/bin/rm", "-rf", "--", "/downloads/movies/Movie"))) < calls.index(
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


@pytest.mark.asyncio
@respx.mock
async def test_transmission_read_and_pause_use_hash_identity_and_verify_post_state() -> None:
    info_hash = "A" * 40
    calls: list[dict[str, Any]] = []
    stopped = False
    stale_reads = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal stale_reads, stopped
        payload = json.loads(request.content)
        calls.append(payload)
        method = payload["method"]
        if method == "session_get":
            result: dict[str, Any] = {"version": "4.1.0"}
        elif method == "torrent_stop":
            stopped = True
            stale_reads = 1
            result = {}
        else:
            visible_stopped = not stopped if stale_reads else stopped
            stale_reads = max(0, stale_reads - 1)
            result = {
                "torrents": [
                    {
                        "id": 99,
                        "hash_string": info_hash,
                        "name": "safe title",
                        "status": 0 if visible_stopped else 4,
                        "percent_done": 1.2,
                        "total_size": -1,
                        "upload_ratio": "bad",
                    }
                ]
            }
        return httpx.Response(200, json={"jsonrpc": "2.0", "result": result, "id": payload["id"]})

    respx.post("http://transmission/transmission/rpc").mock(side_effect=handler)
    client = TransmissionClient(
        base_url="http://transmission/transmission/rpc", username="", password="", timeout_seconds=5
    )
    try:
        listing = await client.list_torrents()
        result = await client.control_torrent(info_hash, action=DownloadControlAction.PAUSE)
    finally:
        await client.close()

    assert listing.torrents[0].state is TorrentState.DOWNLOADING
    assert listing.torrents[0].progress is None
    assert listing.torrents[0].total_bytes is None
    assert listing.torrents[0].ratio is None
    assert result.outcome is DownloadControlOutcome.APPLIED
    assert [call["method"] for call in calls].count("torrent_stop") == 1
    assert all(call.get("params", {}).get("ids") != [99] for call in calls if call["method"] != "torrent_stop")


@pytest.mark.asyncio
@respx.mock
@pytest.mark.parametrize(
    ("modern", "action", "initial_stopped", "control_method"),
    [
        (True, DownloadControlAction.PAUSE, False, "torrent_stop"),
        (True, DownloadControlAction.RESUME, True, "torrent_start"),
        (False, DownloadControlAction.PAUSE, False, "torrent-stop"),
        (False, DownloadControlAction.RESUME, True, "torrent-start"),
    ],
)
async def test_transmission_control_protocol_matrix(
    modern: bool, action: DownloadControlAction, initial_stopped: bool, control_method: str
) -> None:
    info_hash = "3" * 40
    stopped = initial_stopped
    calls: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal stopped
        payload = json.loads(request.content)
        calls.append(payload)
        method = payload["method"]
        if not modern and method == "session_get":
            return httpx.Response(200, json={"result": "method name not recognized", "arguments": {}})
        if method in {"session_get", "session-get"}:
            result: dict[str, Any] = {"version": "4.1.0" if modern else "4.0.6"}
        elif method == control_method:
            assert (payload["params"] if modern else payload["arguments"])["ids"] == [info_hash]
            stopped = action is DownloadControlAction.PAUSE
            result = {}
        else:
            result = {
                "torrents": [
                    {
                        "id": 77,
                        "hash_string" if modern else "hashString": info_hash,
                        "status": 0 if stopped else 4,
                    }
                ]
            }
        if modern:
            return httpx.Response(200, json={"jsonrpc": "2.0", "result": result, "id": payload["id"]})
        return httpx.Response(200, json={"result": "success", "arguments": result})

    respx.post("http://transmission/transmission/rpc").mock(side_effect=handler)
    client = TransmissionClient(
        base_url="http://transmission/transmission/rpc", username="", password="", timeout_seconds=5
    )
    try:
        result = await client.control_torrent(info_hash, action=action)
    finally:
        await client.close()

    methods = [call["method"] for call in calls]
    assert result.outcome is DownloadControlOutcome.APPLIED
    assert methods.count(control_method) == 1
    assert "torrent_remove" not in methods and "torrent-remove" not in methods


@pytest.mark.asyncio
@respx.mock
async def test_deluge_resume_invalid_hash_is_structured_and_does_not_mutate() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        calls.append(payload["method"])
        return httpx.Response(200, json={"id": payload["id"], "result": "session", "error": None})

    respx.post("http://deluge/json").mock(side_effect=handler)
    client = DelugeClient(base_url="http://deluge/json", password="secret", timeout_seconds=5)
    try:
        result = await client.control_torrent("not-a-hash", action=DownloadControlAction.RESUME)
    finally:
        await client.close()

    assert result.outcome is DownloadControlOutcome.UNKNOWN
    assert result.code == "invalid_identifier"
    assert calls == []


@pytest.mark.asyncio
@respx.mock
@pytest.mark.parametrize(
    ("action", "initial_state", "control_method"),
    [
        (DownloadControlAction.PAUSE, "Downloading", "core.pause_torrent"),
        (DownloadControlAction.RESUME, "Paused", "core.resume_torrent"),
    ],
)
async def test_deluge_control_protocol_matrix(
    action: DownloadControlAction, initial_state: str, control_method: str
) -> None:
    info_hash = "4" * 40
    state = initial_state
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal state
        payload = json.loads(request.content)
        method = payload["method"]
        calls.append(method)
        if method == control_method:
            assert payload["params"] == [[info_hash.lower()]]
            state = "Paused" if action is DownloadControlAction.PAUSE else "Downloading"
            result: object = None
        elif method == "auth.login":
            result = "session"
        elif method == "core.get_session_state":
            result = [info_hash.lower()]
        else:
            result = {info_hash.lower(): {"state": state, "name": "torrent"}}
        return httpx.Response(200, json={"id": payload["id"], "result": result, "error": None})

    respx.post("http://deluge/json").mock(side_effect=handler)
    client = DelugeClient(base_url="http://deluge/json", password="secret", timeout_seconds=5)
    try:
        result = await client.control_torrent(info_hash, action=action)
    finally:
        await client.close()

    assert result.outcome is DownloadControlOutcome.APPLIED
    assert calls.count(control_method) == 1
    assert "core.remove_torrents" not in calls


@pytest.mark.asyncio
@respx.mock
async def test_deluge_listing_keeps_unknown_state_and_malformed_entry_as_structured_data() -> None:
    info_hash = "E" * 40

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        result: object = (
            "session"
            if payload["method"] == "auth.login"
            else {
                info_hash: {
                    "name": "release",
                    "state": "unrecognised",
                    "progress": 101,
                    "total_size": "broken",
                    "tracker": "https://tracker.example/announce",
                },
                "not a hash": {"name": "malformed"},
            }
        )
        return httpx.Response(200, json={"id": payload["id"], "result": result, "error": None})

    respx.post("http://deluge/json").mock(side_effect=handler)
    client = DelugeClient(base_url="http://deluge/json", password="secret", timeout_seconds=5)
    try:
        listing = await client.list_torrents()
    finally:
        await client.close()

    assert listing.torrents[0].state is TorrentState.UNKNOWN
    assert listing.torrents[0].progress is None
    assert listing.torrents[0].total_bytes is None
    assert listing.torrents[0].tracker_summary == "tracker.example"
    assert listing.failures[0].code == "malformed_torrent"


@pytest.mark.asyncio
@respx.mock
@pytest.mark.parametrize(
    ("action", "initial_active", "control_method"),
    [
        (DownloadControlAction.PAUSE, 1, "d.pause"),
        (DownloadControlAction.RESUME, 0, "d.resume"),
    ],
)
async def test_rtorrent_control_protocol_matrix(
    action: DownloadControlAction, initial_active: int, control_method: str
) -> None:
    info_hash = "B" * 40
    calls: list[tuple[str, tuple[Any, ...]]] = []
    active = initial_active

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal active
        params, method = loads(request.content)
        assert method is not None
        calls.append((method, params))
        if method == control_method:
            assert params == (info_hash,)
            active = 0 if action is DownloadControlAction.PAUSE else 1
            value: object = 0
        else:
            values: dict[str, object] = {
                "download_list": [info_hash],
                "d.name": "Torrent",
                "d.state": 1,
                "d.is_active": active,
                "d.completed_bytes": 10,
                "d.size_bytes": 10,
                "d.up.total": 1,
                "d.ratio": 1000,
                "d.timestamp.finished": 1,
                "d.down.rate": 0,
                "d.up.rate": 1,
                "d.timestamp.started": 1,
                "d.timestamp.last_active": 2,
                "d.custom1": "",
                "d.tracker": "https://tracker.example/announce",
            }
            value = values[method]
        return httpx.Response(200, content=dumps((value,), methodresponse=True, allow_none=True))

    respx.post("http://rtorrent/RPC2").mock(side_effect=handler)
    client = RTorrentClient(base_url="http://rtorrent/RPC2", username="", password="", timeout_seconds=5)
    try:
        result = await client.control_torrent(info_hash, action=action)
    finally:
        await client.close()

    methods = [method for method, _ in calls]
    assert result.outcome is DownloadControlOutcome.APPLIED
    assert result.after is not None and result.after.state is (
        TorrentState.STOPPED if action is DownloadControlAction.PAUSE else TorrentState.SEEDING
    )
    assert methods.count(control_method) == 1
    assert not ({"d.stop", "d.close", "d.erase", "execute.throw"} & set(methods))


@pytest.mark.asyncio
@respx.mock
async def test_rtorrent_optional_metric_fault_keeps_required_state_snapshot() -> None:
    info_hash = "1" * 40

    def handler(request: httpx.Request) -> httpx.Response:
        _, method = loads(request.content)
        assert method is not None
        if method == "d.ratio":
            return httpx.Response(200, content=dumps(Fault(1, "unsupported")))
        values: dict[str, object] = {
            "download_list": [info_hash],
            "d.state": 1,
            "d.is_active": 1,
            "d.name": "torrent",
            "d.completed_bytes": 1,
            "d.size_bytes": 2,
            "d.up.total": 0,
            "d.timestamp.finished": 0,
            "d.down.rate": 1,
            "d.up.rate": 0,
            "d.timestamp.started": 1,
            "d.timestamp.last_active": 1,
            "d.custom1": "",
            "d.tracker": "",
        }
        return httpx.Response(200, content=dumps((values[method],), methodresponse=True, allow_none=True))

    respx.post("http://rtorrent/RPC2").mock(side_effect=handler)
    client = RTorrentClient(base_url="http://rtorrent/RPC2", username="", password="", timeout_seconds=5)
    try:
        listing = await client.list_torrents()
    finally:
        await client.close()

    assert listing.torrents[0].state is TorrentState.DOWNLOADING
    assert listing.torrents[0].ratio is None
    assert listing.torrents[0].unavailable_reason == "optional_metrics_unavailable"
