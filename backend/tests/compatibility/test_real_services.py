"""Live contracts for the digest-pinned 1.0 compatibility stack."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import os
from collections.abc import AsyncIterator
from typing import Any
from xmlrpc.client import Binary, dumps, loads

import httpx
import pytest

from cleanarr.domain import AuthenticationError
from cleanarr.infrastructure.clients import (
    JellyfinServerClient,
    QbittorrentClient,
    RadarrClient,
    SeerrClient,
    SonarrClient,
)
from cleanarr.infrastructure.downloaders import DelugeClient, RTorrentClient, TransmissionClient

pytestmark = [
    pytest.mark.compatibility,
    pytest.mark.skipif(
        os.environ.get("CLEANARR_REAL_COMPATIBILITY") != "1",
        reason="requires compatibility/run.py and its pinned real-service stack",
    ),
]

PASSWORD = "compat-password"
MISSING_HASH = "0" * 40
CONTENT = b"CleanArr compatibility fixture\n"


def _bencode(value: object) -> bytes:
    if isinstance(value, bytes):
        return str(len(value)).encode() + b":" + value
    if isinstance(value, str):
        return _bencode(value.encode())
    if isinstance(value, int):
        return b"i" + str(value).encode() + b"e"
    if isinstance(value, list):
        return b"l" + b"".join(_bencode(item) for item in value) + b"e"
    if isinstance(value, dict):
        encoded_items = []
        for key in sorted(value):
            encoded_items.extend((_bencode(key), _bencode(value[key])))
        return b"d" + b"".join(encoded_items) + b"e"
    raise TypeError(f"Unsupported bencode value: {type(value)!r}")


INFO = {
    b"length": len(CONTENT),
    b"name": b"cleanarr-compatibility.bin",
    b"piece length": 16384,
    b"pieces": hashlib.sha1(CONTENT).digest(),  # noqa: S324 - BitTorrent v1 protocol identifier
}
TORRENT_BYTES = _bencode(
    {
        b"announce": b"http://127.0.0.1:1/announce",
        b"created by": b"CleanArr compatibility suite",
        b"info": INFO,
    }
)
TORRENT_HASH = hashlib.sha1(_bencode(INFO)).hexdigest().upper()  # noqa: S324 - BitTorrent v1 infohash


async def _eventually_version(client: Any, expected: str) -> None:
    last_error: Exception | None = None
    for _ in range(45):
        try:
            assert (await client.get_version()).startswith(expected)
            return
        except Exception as exc:  # service initialization is deliberately asynchronous
            last_error = exc
            await asyncio.sleep(2)
    assert last_error is None, str(last_error)


async def _eventually_find_torrent(client: Any) -> None:
    for _ in range(30):
        result = (await client.delete_hashes([TORRENT_HASH], delete_files=False, dry_run=True))[0]
        if result.existed:
            return
        await asyncio.sleep(0.2)
    pytest.fail(f"{client.__class__.__name__} did not expose the added compatibility torrent")


async def _qbittorrent_add(password: str) -> None:
    async with httpx.AsyncClient(base_url="http://127.0.0.1:18080", timeout=15) as client:
        response = await client.post(
            "/api/v2/auth/login",
            data={"username": "admin", "password": password},
        )
        assert response.status_code in {200, 204}
        assert response.text.strip() in {"", "Ok."}
        response = await client.post(
            "/api/v2/torrents/add",
            files={"torrents": ("cleanarr.torrent", TORRENT_BYTES, "application/x-bittorrent")},
            data={"savepath": "/downloads"},
        )
        assert response.status_code == 200


async def _transmission_call(base_url: str, *, modern: bool, method: str, params: dict[str, Any]) -> Any:
    payload = (
        {"jsonrpc": "2.0", "method": method, "params": params, "id": 1}
        if modern
        else {"method": method, "arguments": params, "tag": 1}
    )
    headers: dict[str, str] = {}
    async with httpx.AsyncClient(auth=("cleanarr", PASSWORD), timeout=15) as client:
        response = await client.post(base_url, json=payload, headers=headers)
        if response.status_code == 409:
            headers["X-Transmission-Session-Id"] = response.headers["X-Transmission-Session-Id"]
            response = await client.post(base_url, json=payload, headers=headers)
        response.raise_for_status()
        body = response.json()
        if modern:
            assert body.get("error") is None
            return body["result"]
        assert body["result"] == "success"
        return body["arguments"]


async def _transmission_add(base_url: str, *, modern: bool) -> None:
    method = "torrent_add" if modern else "torrent-add"
    await _transmission_call(
        base_url,
        modern=modern,
        method=method,
        params={"metainfo": base64.b64encode(TORRENT_BYTES).decode(), "download_dir": "/downloads"}
        if modern
        else {"metainfo": base64.b64encode(TORRENT_BYTES).decode(), "download-dir": "/downloads"},
    )


async def _deluge_call(client: httpx.AsyncClient, method: str, params: list[Any], request_id: int) -> Any:
    response = await client.post("/json", json={"method": method, "params": params, "id": request_id})
    response.raise_for_status()
    body = response.json()
    assert body["error"] is None
    return body["result"]


async def _deluge_add() -> None:
    async with httpx.AsyncClient(base_url="http://127.0.0.1:18112", timeout=15) as client:
        assert await _deluge_call(client, "auth.login", ["deluge"], 1) is True
        assert await _deluge_call(client, "web.connected", [], 2) is True
        result = await _deluge_call(
            client,
            "core.add_torrent_file",
            [
                "cleanarr.torrent",
                base64.b64encode(TORRENT_BYTES).decode(),
                {"download_location": "/downloads"},
            ],
            3,
        )
        assert str(result).upper() == TORRENT_HASH


async def _rtorrent_call(method: str, *params: Any, auth: tuple[str, str] = ("cleanarr", PASSWORD)) -> Any:
    request = dumps(params, methodname=method, allow_none=True)
    async with httpx.AsyncClient(auth=auth, timeout=15) as client:
        response = await client.post(
            "http://127.0.0.1:18000",
            content=request,
            headers={"Content-Type": "text/xml"},
        )
        response.raise_for_status()
        values, _ = loads(response.content)
        return values[0] if values else None


async def _rtorrent_add() -> None:
    await _rtorrent_call("load.raw_start", "", Binary(TORRENT_BYTES))


@pytest.fixture
async def qbittorrent() -> AsyncIterator[QbittorrentClient]:
    client = QbittorrentClient(
        base_url="http://127.0.0.1:18080",
        username="admin",
        password=os.environ["CLEANARR_COMPAT_QBITTORRENT_PASSWORD"],
        timeout_seconds=15,
    )
    yield client
    await client.close()


@pytest.mark.asyncio
async def test_qbittorrent_5_2_contract(qbittorrent: QbittorrentClient) -> None:
    password = os.environ["CLEANARR_COMPAT_QBITTORRENT_PASSWORD"]
    assert await qbittorrent.get_version() == "v5.2.3"
    assert (await qbittorrent.delete_hashes([MISSING_HASH], delete_files=False))[0].existed is False

    await _qbittorrent_add(password)
    await _eventually_find_torrent(qbittorrent)
    assert (await qbittorrent.delete_hashes([TORRENT_HASH], delete_files=False))[0].existed is True
    assert (await qbittorrent.delete_hashes([TORRENT_HASH], delete_files=False))[0].existed is False

    await _qbittorrent_add(password)
    assert (await qbittorrent.delete_hashes([TORRENT_HASH], delete_files=True))[0].existed is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("port", "expected_version", "modern"),
    ((19091, "4.0.6", False), (19092, "4.1.3", True)),
)
async def test_transmission_generations(port: int, expected_version: str, modern: bool) -> None:
    base_url = f"http://127.0.0.1:{port}/transmission/rpc"
    client = TransmissionClient(
        base_url=base_url,
        username="cleanarr",
        password=PASSWORD,
        timeout_seconds=15,
    )
    try:
        await _eventually_version(client, expected_version)
        assert client._modern is modern
        assert (await client.delete_hashes([MISSING_HASH], delete_files=False))[0].existed is False

        await _transmission_add(base_url, modern=modern)
        assert (await client.delete_hashes([TORRENT_HASH], delete_files=False, dry_run=True))[0].existed is True
        assert (await client.delete_hashes([TORRENT_HASH], delete_files=False))[0].existed is True
        assert (await client.delete_hashes([TORRENT_HASH], delete_files=False))[0].existed is False

        await _transmission_add(base_url, modern=modern)
        assert (await client.delete_hashes([TORRENT_HASH], delete_files=True))[0].existed is True
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_deluge_2_2_contract() -> None:
    client = DelugeClient(base_url="http://127.0.0.1:18112/json", password="deluge", timeout_seconds=15)
    try:
        await _eventually_version(client, "2.2.0")
        assert (await client.delete_hashes([MISSING_HASH], delete_files=False))[0].existed is False

        await _deluge_add()
        assert (await client.delete_hashes([TORRENT_HASH], delete_files=False, dry_run=True))[0].existed is True
        assert (await client.delete_hashes([TORRENT_HASH], delete_files=False))[0].existed is True
        assert (await client.delete_hashes([TORRENT_HASH], delete_files=False))[0].existed is False

        await _deluge_add()
        assert (await client.delete_hashes([TORRENT_HASH], delete_files=True))[0].existed is True
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_rtorrent_0_16_xmlrpc_contract() -> None:
    client = RTorrentClient(
        base_url="http://127.0.0.1:18000",
        username="cleanarr",
        password=PASSWORD,
        timeout_seconds=15,
    )
    try:
        await _eventually_version(client, "0.16.17")
        assert (await client.delete_hashes([MISSING_HASH], delete_files=False))[0].existed is False

        await _rtorrent_add()
        assert (await client.delete_hashes([TORRENT_HASH], delete_files=False, dry_run=True))[0].existed is True
        assert (await client.delete_hashes([TORRENT_HASH], delete_files=False))[0].existed is True
        assert (await client.delete_hashes([TORRENT_HASH], delete_files=False))[0].existed is False

        await _rtorrent_add()
        assert (await client.delete_hashes([TORRENT_HASH], delete_files=True))[0].existed is True
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_media_dependency_contracts() -> None:
    api_key = os.environ["CLEANARR_COMPAT_ARR_API_KEY"]
    jellyfin_token = os.environ["CLEANARR_COMPAT_JELLYFIN_TOKEN"]
    seerr_api_key = os.environ["CLEANARR_COMPAT_SEERR_API_KEY"]
    clients = [
        RadarrClient(base_url="http://127.0.0.1:17878/api/v3", api_key=api_key, timeout_seconds=15),
        SonarrClient(base_url="http://127.0.0.1:18989/api/v3", api_key=api_key, timeout_seconds=15),
        JellyfinServerClient(base_url="http://127.0.0.1:18096", api_key=jellyfin_token, timeout_seconds=15),
        SeerrClient(base_url="http://127.0.0.1:15055/api/v1", api_key=seerr_api_key, timeout_seconds=15),
    ]
    radarr, sonarr, jellyfin, seerr = clients
    try:
        assert await radarr.get_version() == "6.3.0.10514"
        assert await sonarr.get_version() == "4.0.19.2979"
        assert await jellyfin.get_version() == "10.11.11"
        assert await seerr.get_version() == "3.4.1"
        assert await radarr.list_movies() == []
        assert await sonarr.list_series() == []
        assert await jellyfin.list_items(include_types=["Movie", "Series"]) == []
        assert await seerr.list_media() == []
        assert await seerr.list_requests() == []
        assert await seerr.list_issues() == []
    finally:
        for client in clients:
            await client.close()


@pytest.mark.asyncio
async def test_real_services_reject_invalid_credentials() -> None:
    clients = [
        (
            "qBittorrent",
            QbittorrentClient(
                base_url="http://127.0.0.1:18080",
                username="admin",
                password="wrong-password",
                timeout_seconds=15,
            ),
        ),
        (
            "Transmission",
            TransmissionClient(
                base_url="http://127.0.0.1:19092/transmission/rpc",
                username="cleanarr",
                password="wrong-password",
                timeout_seconds=15,
            ),
        ),
        (
            "Deluge",
            DelugeClient(base_url="http://127.0.0.1:18112/json", password="wrong-password", timeout_seconds=15),
        ),
        (
            "rTorrent",
            RTorrentClient(
                base_url="http://127.0.0.1:18000",
                username="cleanarr",
                password="wrong-password",
                timeout_seconds=15,
            ),
        ),
        ("Radarr", RadarrClient(base_url="http://127.0.0.1:17878/api/v3", api_key="wrong", timeout_seconds=15)),
        ("Sonarr", SonarrClient(base_url="http://127.0.0.1:18989/api/v3", api_key="wrong", timeout_seconds=15)),
        (
            "Jellyfin",
            JellyfinServerClient(base_url="http://127.0.0.1:18096", api_key="wrong", timeout_seconds=15),
        ),
        ("Seerr", SeerrClient(base_url="http://127.0.0.1:15055/api/v1", api_key="wrong", timeout_seconds=15)),
    ]
    try:
        for label, client in clients:
            try:
                await client.ping()
            except AuthenticationError:
                continue
            pytest.fail(f"{label} accepted invalid compatibility credentials")
    finally:
        for _, client in clients:
            await client.close()
