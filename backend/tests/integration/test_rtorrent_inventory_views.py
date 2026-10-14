"""Complete rTorrent main snapshots retain bounded sibling evidence."""

import asyncio
from collections.abc import Callable
from typing import Any
from xmlrpc.client import dumps, loads

import httpx
import pytest
import respx

from cleanarr.application.data_safety import assess_content_inventory, content_safety_skip_reason
from cleanarr.domain import DownloaderContentInventory, DownloaderContentScope
from cleanarr.infrastructure.clients import QbittorrentClient
from cleanarr.infrastructure.downloaders import DownloaderTarget, MultiDownloaderClient, RTorrentClient

A, B, C = (letter * 40 for letter in "ABC")


def _rtorrent_mock(rows: list[Any], listed: list[Any], calls: list[str]) -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        params, method = loads(request.content)
        calls.append(method)
        if method == "download_list":
            assert params == ("", "main")
            result: object = listed
        elif method == "d.multicall2":
            assert params == ("", "main", "d.hash=", "d.base_path=", "d.directory=", "d.name=", "d.is_multi_file=")
            result = rows
        elif method == "d.base_path":
            result = next(row[1] for row in rows if isinstance(row, list) and len(row) > 1 and row[0] == params[0])
        else:
            result = {
                "directory.default": "/srv/torrents",
                "d.base_path": "/srv/torrents/Movie",
                "d.name": "Movie",
                "d.ratio": 0,
                "d.timestamp.finished": 1,
                "d.stop": 0,
                "d.close": 0,
                "execute.throw": 0,
                "d.erase": 0,
            }[method]
        return httpx.Response(200, content=dumps((result,), methodresponse=True, allow_none=True))

    respx.post("http://rtorrent/RPC2").mock(side_effect=handler)
    return handler


@pytest.mark.asyncio
@respx.mock
@pytest.mark.parametrize("sibling", ["unrelated", "shared", "uncertain", "unreadable"])
async def test_fleet_refresh_barrier_protects_other_client_before_mutation(sibling: str) -> None:
    calls: list[str] = []
    rows = [[A, "/srv/torrents/Movie", "/srv/torrents", "Movie", False]]
    listed = [A]
    _rtorrent_mock(rows, listed, calls)
    rt_ready = asyncio.Event()

    class SignalledRTorrent(RTorrentClient):
        async def list_content_inventory(self) -> DownloaderContentInventory:
            inventory = await super().list_content_inventory()
            rt_ready.set()
            return inventory

    class DelayedQbt(QbittorrentClient):
        async def list_content_inventory(self) -> DownloaderContentInventory:
            await rt_ready.wait()
            inventory = await super().list_content_inventory()
            path = "/downloads/Separate" if sibling != "unrelated" else "/downloads/Other"
            rows.append(
                [B]
                if sibling == "unreadable"
                else [B, path]
                if sibling == "uncertain"
                else [B, path, "/downloads", "New", False]
            )
            listed.append(B)
            return inventory

    respx.post("http://qbt/api/v2/auth/login").respond(text="Ok.")
    respx.get("http://qbt/api/v2/torrents/info").respond(
        json=[{"hash": C, "name": "Qbt target", "content_path": "/downloads/Separate"}]
    )
    remove = respx.post("http://qbt/api/v2/torrents/delete").respond(status_code=204)
    rt = SignalledRTorrent(
        base_url="http://rtorrent/RPC2", username="", password="", timeout_seconds=5, service_id="rt"
    )
    qbt = DelayedQbt(base_url="http://qbt", username="", password="", timeout_seconds=5, service_id="qbt")
    fleet = MultiDownloaderClient(
        [DownloaderTarget("rt", "rTorrent", "rtorrent", rt), DownloaderTarget("qbt", "qBittorrent", "qbittorrent", qbt)]
    )
    try:
        results = await fleet.delete_hashes([A, C], delete_files=True)
    finally:
        await fleet.close()
    assert calls.count("d.multicall2") == 2
    assert remove.call_count == (1 if sibling == "unrelated" else 0)
    if sibling == "unreadable":
        assert all(result.skip_reason == "ownership_unverifiable" for result in results)
        assert "execute.throw" not in calls and "d.erase" not in calls
    else:
        qbt_result = next(result for result in results if result.client_id == "qbt" and result.hash_value == C)
        assert (
            qbt_result.skip_reason
            == {"unrelated": None, "shared": "shared_path", "uncertain": "sibling_scope_unknown"}[sibling]
        )
        assert calls.count("execute.throw") == calls.count("d.erase") == 1


@pytest.mark.asyncio
@respx.mock
@pytest.mark.parametrize("overlap", [False, True])
async def test_outside_root_inventory_preserves_unrelated_rtorrent_and_qbt_removal(overlap: bool) -> None:
    calls: list[str] = []
    _rtorrent_mock(
        [
            [A, "/srv/torrents/Movie", "/srv/torrents", "Movie", False],
            [B, "/mnt/disk2/Other", "/mnt/disk2", "Other", False],
        ],
        [A, B],
        calls,
    )
    path = "/mnt/disk2/Other" if overlap else "/downloads/Separate"
    respx.post("http://qbt/api/v2/auth/login").respond(text="Ok.")
    respx.get("http://qbt/api/v2/torrents/info").respond(json=[{"hash": C, "name": "Qbt target", "content_path": path}])
    remove = respx.post("http://qbt/api/v2/torrents/delete").respond(status_code=204)
    rt = RTorrentClient(base_url="http://rtorrent/RPC2", username="", password="", timeout_seconds=5, service_id="rt")
    qbt = QbittorrentClient(base_url="http://qbt", username="", password="", timeout_seconds=5, service_id="qbt")
    fleet = MultiDownloaderClient(
        [DownloaderTarget("rt", "rTorrent", "rtorrent", rt), DownloaderTarget("qbt", "qBittorrent", "qbittorrent", qbt)]
    )
    try:
        results = await fleet.delete_hashes([A, C], delete_files=True)
    finally:
        await fleet.close()
    rt_result = next(result for result in results if result.client_id == "rt" and result.hash_value == A)
    qbt_result = next(result for result in results if result.client_id == "qbt" and result.hash_value == C)
    assert rt_result.skip_reason is None
    assert calls.count("execute.throw") == calls.count("d.erase") == 1
    assert qbt_result.skip_reason == ("shared_path" if overlap else None)
    assert remove.call_count == (0 if overlap else 1)


@pytest.mark.asyncio
@respx.mock
@pytest.mark.parametrize("listed", [[A, B], [], [A, A], [A, "invalid"]])
async def test_main_hash_mismatch_or_invalid_sibling_blocks_mutation(listed: list[str]) -> None:
    calls: list[str] = []
    _rtorrent_mock([[A, "/srv/torrents/Movie", "/srv/torrents", "Movie", False]], listed, calls)
    client = RTorrentClient(base_url="http://rtorrent/RPC2", username="", password="", timeout_seconds=5)
    try:
        inventory = await client.list_content_inventory()
        assessment = assess_content_inventory([("rt", inventory)], [A])
        results = await client._delete_hashes_with_assessment(
            [A], delete_files=True, assessment=assessment, assessment_client_id="rt"
        )
    finally:
        await client.close()
    assert not assessment.complete
    assert inventory.failures
    assert results[0].skip_reason == "ownership_unverifiable"
    assert "execute.throw" not in calls and "d.erase" not in calls


@pytest.mark.asyncio
@respx.mock
@pytest.mark.parametrize("row", [[B, "/mnt/disk2/Other"], [B, "", "/mnt/disk2", "Other", "bad-flag"]])
async def test_recoverable_malformed_row_blocks_only_overlapping_scope(row: list[Any]) -> None:
    calls: list[str] = []
    _rtorrent_mock([row], [B], calls)
    client = RTorrentClient(base_url="http://rtorrent/RPC2", username="", password="", timeout_seconds=5)
    try:
        inventory = await client.list_content_inventory()
    finally:
        await client.close()
    other = DownloaderContentInventory(
        scopes=(
            DownloaderContentScope(A, ("/srv/torrents/Movie",)),
            DownloaderContentScope(C, ("/mnt/disk2/Other/file.mkv",)),
        )
    )
    assessment = assess_content_inventory([("rt", inventory), ("qbt", other)], [A, C])
    assert assessment.complete
    assert content_safety_skip_reason(assessment, "qbt", A) is None
    assert content_safety_skip_reason(assessment, "qbt", C) == "sibling_scope_unknown"


@pytest.mark.asyncio
@respx.mock
@pytest.mark.parametrize("row", [[B], ["bad", "/mnt/disk2/Other"], [B, "/../Other", "/mnt/disk2", "Other", False]])
async def test_unreadable_identity_or_unbounded_scope_cannot_be_dropped(row: list[Any]) -> None:
    calls: list[str] = []
    _rtorrent_mock([row], [B], calls)
    client = RTorrentClient(base_url="http://rtorrent/RPC2", username="", password="", timeout_seconds=5)
    try:
        inventory = await client.list_content_inventory()
    finally:
        await client.close()
    assert inventory.failures
    assert not assess_content_inventory([("rt", inventory)], [A]).complete


@pytest.mark.asyncio
@respx.mock
async def test_outside_default_root_target_is_not_authorized_for_rm() -> None:
    calls: list[str] = []
    _rtorrent_mock([[B, "/mnt/disk2/Other", "/mnt/disk2", "Other", False]], [B], calls)
    client = RTorrentClient(base_url="http://rtorrent/RPC2", username="", password="", timeout_seconds=5)
    try:
        result = (await client.delete_hashes([B], delete_files=True))[0]
    finally:
        await client.close()
    assert result.skip_reason == "ownership_unverifiable"
    assert "execute.throw" not in calls and "d.erase" not in calls


@pytest.mark.asyncio
@respx.mock
async def test_changed_membership_after_inventory_is_checked_before_removal() -> None:
    calls: list[str] = []
    listed = [A]
    _rtorrent_mock([[A, "/srv/torrents/Movie", "/srv/torrents", "Movie", False]], listed, calls)
    client = RTorrentClient(base_url="http://rtorrent/RPC2", username="", password="", timeout_seconds=5)
    try:
        inventory = await client.list_content_inventory()
        assessment = assess_content_inventory([("rt", inventory)], [A])
        assert assessment.complete
        listed.append(B)
        result = (
            await client._delete_hashes_with_assessment(
                [A], delete_files=True, assessment=assessment, assessment_client_id="rt"
            )
        )[0]
    finally:
        await client.close()
    assert result.skip_reason == "ownership_unverifiable"
    assert calls.count("d.multicall2") == 2
    assert "execute.throw" not in calls and "d.erase" not in calls


@pytest.mark.asyncio
@respx.mock
@pytest.mark.parametrize(
    ("sibling", "reason"),
    [
        (None, None),
        ([B, "/srv/torrents/Other", "/srv/torrents", "Other", False], None),
        ([B, "/srv/torrents/Movie", "/srv/torrents", "Other", False], "shared_path"),
        ([B, "/srv/torrents/Movie/Other", "/srv/torrents/Movie", "Other", False], "shared_path"),
        ([B, "/srv/torrents/Movie"], "sibling_scope_unknown"),
    ],
)
async def test_membership_change_gets_one_inventory_refresh(sibling: list[Any] | None, reason: str | None) -> None:
    calls: list[str] = []
    rows = [[A, "/srv/torrents/Movie", "/srv/torrents", "Movie", False]]
    listed = [A]
    if sibling is None:
        rows.append([B, "/srv/torrents/Other", "/srv/torrents", "Other", False])
        listed.append(B)
    _rtorrent_mock(rows, listed, calls)
    client = RTorrentClient(base_url="http://rtorrent/RPC2", username="", password="", timeout_seconds=5)
    try:
        assessment = assess_content_inventory([("rt", await client.list_content_inventory())], [A])
        if sibling is None:
            rows.pop()
            listed.pop()
        else:
            rows.append(sibling)
            listed.append(B)
        result = (
            await client._delete_hashes_with_assessment(
                [A], delete_files=True, assessment=assessment, assessment_client_id="rt"
            )
        )[0]
    finally:
        await client.close()
    assert result.skip_reason == reason
    assert calls.count("d.multicall2") == 2
    assert calls.count("download_list") == 4
    assert calls.count("execute.throw") == calls.count("d.erase") == (1 if reason is None else 0)
    if reason == "sibling_scope_unknown":
        assert [(value.client_id, value.info_hash) for value in result.blocking_torrents] == [("rt", B)]


@pytest.mark.asyncio
@respx.mock
@pytest.mark.parametrize("change", ["churn", "target_added", "target_removed", "target_path"])
async def test_refresh_does_not_authorize_changed_target_or_repeated_churn(change: str) -> None:
    calls: list[str] = []
    original_rows = [[A, "/srv/torrents/Movie", "/srv/torrents", "Movie", False]]
    rows = [] if change == "target_added" else original_rows
    listed = [] if change == "target_added" else [A]
    original_handler = _rtorrent_mock(rows, listed, calls)
    client = RTorrentClient(base_url="http://rtorrent/RPC2", username="", password="", timeout_seconds=5)
    try:
        assessment = assess_content_inventory([("rt", await client.list_content_inventory())], [A])
        if change == "target_added":
            rows.extend(original_rows)
            listed.append(A)
        elif change == "target_removed":
            rows.clear()
            listed.clear()
        elif change == "target_path":
            rows[0][1] = "/srv/torrents/NewMovie"
        rows.append([B, "/srv/torrents/Other", "/srv/torrents", "Other", False])
        listed.append(B)
        if change == "churn":
            # The two reads inside the refreshed inventory agree, then a third torrent arrives.
            route = respx.post("http://rtorrent/RPC2")

            def handler(request: httpx.Request) -> httpx.Response:
                _params, method = loads(request.content)
                if method == "download_list" and calls.count(method) == 3:
                    listed.append(C)
                return original_handler(request)

            route.mock(side_effect=handler)
        result = (
            await client._delete_hashes_with_assessment(
                [A], delete_files=True, assessment=assessment, assessment_client_id="rt"
            )
        )[0]
    finally:
        await client.close()
    assert result.skip_reason == "ownership_unverifiable"
    assert calls.count("d.multicall2") == 2
    assert "execute.throw" not in calls and "d.erase" not in calls


@pytest.mark.asyncio
@respx.mock
async def test_default_root_is_an_uncertain_sibling_envelope() -> None:
    calls: list[str] = []
    _rtorrent_mock([[B, "/srv/torrents", "/srv/torrents", "Root", False]], [B], calls)
    client = RTorrentClient(base_url="http://rtorrent/RPC2", username="", password="", timeout_seconds=5)
    try:
        inventory = await client.list_content_inventory()
    finally:
        await client.close()
    other = DownloaderContentInventory(scopes=(DownloaderContentScope(A, ("/srv/torrents/Movie",)),))
    assessment = assess_content_inventory([("rt", inventory), ("qbt", other)], [A])
    assert assessment.complete
    assert content_safety_skip_reason(assessment, "qbt", A) == "sibling_scope_unknown"
