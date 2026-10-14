"""Fleet evidence is reused once and bound to fresh qBittorrent scope metadata."""

import httpx
import pytest
import respx

from cleanarr.infrastructure.clients import QbittorrentClient
from cleanarr.infrastructure.downloaders import DownloaderTarget, MultiDownloaderClient


@pytest.mark.asyncio
@pytest.mark.parametrize("fresh_path", ["/downloads/Movie", "/downloads", "/downloads/Other"])
@respx.mock
async def test_qbittorrent_fleet_reads_one_inventory_and_rejects_changed_scope(fresh_path: str) -> None:
    info_hash = "A" * 40
    full_reads = 0
    target_reads = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal full_reads, target_reads
        if "hashes" in request.url.params:
            target_reads += 1
            assert request.url.params["hashes"] == info_hash
            path = fresh_path
        else:
            full_reads += 1
            path = "/downloads/Movie"
        return httpx.Response(200, json=[{"hash": info_hash, "content_path": path, "name": "Movie"}])

    respx.post("http://qbt/api/v2/auth/login").respond(text="Ok.")
    respx.get("http://qbt/api/v2/torrents/info").mock(side_effect=handler)
    remove = respx.post("http://qbt/api/v2/torrents/delete").respond(status_code=204)
    client = QbittorrentClient(base_url="http://qbt", username="", password="", timeout_seconds=5, service_id="qbt")
    fleet = MultiDownloaderClient([DownloaderTarget("qbt", "qBittorrent", "qbittorrent", client)])
    try:
        results = await fleet.delete_hashes([info_hash], delete_files=True)
    finally:
        await fleet.close()

    assert full_reads == target_reads == 1
    assert results[0].existed is True
    if fresh_path == "/downloads/Movie":
        assert results[0].skip_reason is None
        assert remove.call_count == 1
    else:
        assert results[0].skip_reason == "ownership_unverifiable"
        assert remove.call_count == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("unknown_root", ["/other", "/downloads"])
@respx.mock
async def test_qbittorrent_missing_metadata_is_bounded_by_a_valid_save_path(unknown_root: str) -> None:
    info_hash = "A" * 40

    def handler(request: httpx.Request) -> httpx.Response:
        target = {"hash": info_hash, "content_path": "/downloads/Movie", "name": "Movie"}
        records = [target]
        if "hashes" not in request.url.params:
            records.append({"hash": "B" * 40, "content_path": "", "save_path": unknown_root})
        return httpx.Response(200, json=records)

    respx.post("http://qbt/api/v2/auth/login").respond(text="Ok.")
    respx.get("http://qbt/api/v2/torrents/info").mock(side_effect=handler)
    remove = respx.post("http://qbt/api/v2/torrents/delete").respond(status_code=204)
    client = QbittorrentClient(base_url="http://qbt", username="", password="", timeout_seconds=5, service_id="qbt")
    fleet = MultiDownloaderClient([DownloaderTarget("qbt", "qBittorrent", "qbittorrent", client)])
    try:
        results = await fleet.delete_hashes([info_hash], delete_files=True)
    finally:
        await fleet.close()

    assert results[0].existed is True
    assert remove.call_count == (1 if unknown_root == "/other" else 0)
    assert results[0].skip_reason == (None if unknown_root == "/other" else "shared_path")


@pytest.mark.asyncio
@pytest.mark.parametrize("downloaded", [0, 1, False])
@respx.mock
async def test_qbittorrent_zero_payload_magnet_requires_explicit_counters(downloaded: object) -> None:
    info_hash = "A" * 40

    def handler(request: httpx.Request) -> httpx.Response:
        target = {"hash": info_hash, "content_path": "/downloads/Movie", "name": "Movie"}
        records = [target]
        if "hashes" not in request.url.params:
            records.append(
                {
                    "hash": "B" * 40,
                    "content_path": "",
                    "save_path": "/downloads",
                    "state": "metaDL",
                    "total_size": 0,
                    "completed": 0,
                    "downloaded": downloaded,
                }
            )
        return httpx.Response(200, json=records)

    respx.post("http://qbt/api/v2/auth/login").respond(text="Ok.")
    respx.get("http://qbt/api/v2/torrents/info").mock(side_effect=handler)
    remove = respx.post("http://qbt/api/v2/torrents/delete").respond(status_code=204)
    client = QbittorrentClient(base_url="http://qbt", username="", password="", timeout_seconds=5, service_id="qbt")
    fleet = MultiDownloaderClient([DownloaderTarget("qbt", "qBittorrent", "qbittorrent", client)])
    try:
        results = await fleet.delete_hashes([info_hash], delete_files=True)
    finally:
        await fleet.close()

    verified_empty = isinstance(downloaded, int) and not isinstance(downloaded, bool) and downloaded == 0
    assert remove.call_count == (1 if verified_empty else 0)
    assert results[0].skip_reason == (None if verified_empty else "shared_path")
