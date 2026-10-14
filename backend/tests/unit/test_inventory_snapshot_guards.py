from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from cleanarr.application.data_safety import (
    assess_content_inventory,
    content_safety_skip_reason,
    content_scope_matches,
)
from cleanarr.domain import DownloaderContentInventory, DownloaderContentScope
from cleanarr.infrastructure.downloaders import (
    DelugeClient,
    TransmissionClient,
    _deluge_empty_verified,
    _transmission_empty_verified,
)


def test_content_scope_snapshot_accepts_original_folder_and_rejects_changed_path() -> None:
    info_hash = "A" * 40
    assessment = assess_content_inventory(
        [
            (
                "transmission",
                DownloaderContentInventory(
                    scopes=(
                        DownloaderContentScope(
                            info_hash=info_hash,
                            paths=("/downloads/Movie/file.mkv",),
                        ),
                    )
                ),
            )
        ],
        [info_hash],
    )

    assert content_scope_matches(assessment, "transmission", info_hash, "/downloads")
    assert not content_scope_matches(assessment, "transmission", info_hash, "/downloads/Other")
    assert not content_scope_matches(assessment, "transmission", info_hash, "/downloads", exact=True)


@pytest.mark.asyncio
async def test_transmission_path_change_after_inventory_blocks_removal() -> None:
    info_hash = "A" * 40
    client = TransmissionClient(
        base_url="http://transmission/transmission/rpc", username="", password="", timeout_seconds=5
    )
    client._modern = True
    old_inventory = DownloaderContentInventory(
        scopes=(DownloaderContentScope(info_hash=info_hash, paths=("/downloads/old/file.mkv",)),)
    )
    monkey_get_version = AsyncMock(return_value="4.1.0")
    monkey_call = AsyncMock(
        return_value={
            "torrents": [
                {
                    "id": 1,
                    "hash_string": info_hash,
                    "download_dir": "/downloads/new",
                    "name": "changed",
                }
            ]
        }
    )
    monkey_inventory = AsyncMock(return_value=old_inventory)
    client.get_version = monkey_get_version
    client._call_generation = monkey_call
    client.list_content_inventory = monkey_inventory
    try:
        result = (await client.delete_hashes([info_hash], delete_files=True))[0]
    finally:
        await client.close()

    assert result.existed is True
    assert result.skip_reason == "ownership_unverifiable"
    assert result.delete_files is False
    assert all(call.kwargs.get("method") != "torrent_remove" for call in monkey_call.await_args_list)


@pytest.mark.asyncio
async def test_transmission_empty_file_list_is_uncertain_and_blocks_delete() -> None:
    info_hash = "A" * 40
    client = TransmissionClient(
        base_url="http://transmission/transmission/rpc", username="", password="", timeout_seconds=5
    )
    client._modern = True
    monkeypatch_get_version = AsyncMock(return_value="4.1.0")
    monkeypatch_call = AsyncMock(
        return_value={
            "torrents": [
                {
                    "hash_string": info_hash,
                    "download_dir": "/downloads",
                    "files": [],
                }
            ]
        }
    )
    client.get_version = monkeypatch_get_version
    client._call_generation = monkeypatch_call
    try:
        inventory = await client.list_content_inventory()
    finally:
        await client.close()

    assert inventory.failures == ()
    assert inventory.scopes[0].uncertain is True
    assessment = assess_content_inventory([("transmission", inventory)], [info_hash])
    assert content_safety_skip_reason(assessment, "transmission", info_hash) == "ownership_unverifiable"


def test_protocol_zero_payload_evidence_requires_all_fields_and_supports_generations() -> None:
    modern = {
        "total_size": 0,
        "have_valid": 0,
        "have_unchecked": 0,
        "metadata_percent_complete": 0.0,
    }
    legacy = {
        "totalSize": 0,
        "haveValid": 0,
        "haveUnchecked": 0,
        "metadataPercentComplete": 0,
    }

    assert _transmission_empty_verified(modern, modern=True)
    assert _transmission_empty_verified(legacy, modern=False)
    assert not _transmission_empty_verified({**modern, "have_valid": True}, modern=True)
    assert not _transmission_empty_verified({**modern, "metadata_percent_complete": 1.0}, modern=True)
    assert _deluge_empty_verified({"total_size": 0, "total_done": 0})
    assert not _deluge_empty_verified({"total_size": 0, "total_done": False})


@pytest.mark.asyncio
async def test_zero_payload_magnet_does_not_block_valid_same_root_target() -> None:
    zero_hash = "A" * 40
    target_hash = "B" * 40
    client = TransmissionClient(
        base_url="http://transmission/transmission/rpc", username="", password="", timeout_seconds=5
    )
    client._modern = True
    client.get_version = AsyncMock(return_value="4.1.0")
    client._call_generation = AsyncMock(
        return_value={
            "torrents": [
                {
                    "hash_string": zero_hash,
                    "download_dir": "/downloads",
                    "files": [],
                    "total_size": 0,
                    "have_valid": 0,
                    "have_unchecked": 0,
                    "metadata_percent_complete": 0.0,
                },
                {
                    "hash_string": target_hash,
                    "download_dir": "/downloads",
                    "files": [{"name": "Movie/file.mkv"}],
                },
            ]
        }
    )
    try:
        inventory = await client.list_content_inventory()
    finally:
        await client.close()

    assessment = assess_content_inventory([("transmission", inventory)], [target_hash])
    assert content_safety_skip_reason(assessment, "transmission", target_hash) is None


@pytest.mark.asyncio
async def test_deluge_inventory_requests_zero_payload_status_fields() -> None:
    client = DelugeClient(base_url="http://deluge/json", password="secret", timeout_seconds=5)
    client._login = AsyncMock()
    client._rpc = AsyncMock(return_value={})
    try:
        inventory = await client.list_content_inventory()
    finally:
        await client.close()

    assert inventory.failures == ()
    client._rpc.assert_awaited_once_with(
        "core.get_torrents_status", [{}, ["save_path", "files", "total_size", "total_done"]]
    )
