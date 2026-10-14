"""Destructive downloader data-scope safety contracts."""

import asyncio
from dataclasses import dataclass, field

import pytest

from cleanarr.application.data_safety import assess_content_inventory, content_safety_skip_reason
from cleanarr.domain import (
    DownloaderContentInventory,
    DownloaderContentInventoryFailure,
    DownloaderContentScope,
    DownloaderRemovalResult,
)
from cleanarr.infrastructure.downloaders import DownloaderTarget, MultiDownloaderClient


@dataclass
class InventoryDownloader:
    inventory: DownloaderContentInventory | Exception
    calls: list[tuple[tuple[str, ...], bool, bool]] = field(default_factory=list)

    async def close(self) -> None:
        return None

    async def ping(self) -> None:
        return None

    async def get_version(self) -> str:
        return "fixture"

    async def list_content_inventory(self) -> DownloaderContentInventory:
        if isinstance(self.inventory, Exception):
            raise self.inventory
        return self.inventory

    async def delete_hashes(
        self, hashes: list[str], *, delete_files: bool, dry_run: bool = False
    ) -> list[DownloaderRemovalResult]:
        self.calls.append((tuple(hashes), delete_files, dry_run))
        return [
            DownloaderRemovalResult(hash_value=value, existed=True, client_kind="fixture", delete_files=delete_files)
            for value in hashes
        ]


def _fleet(*clients: tuple[str, InventoryDownloader]) -> MultiDownloaderClient:
    return MultiDownloaderClient(
        [DownloaderTarget(id=client_id, name=client_id, kind="fixture", client=client) for client_id, client in clients]
    )


def _scope(info_hash: str, *paths: str) -> DownloaderContentScope:
    return DownloaderContentScope(info_hash=info_hash, paths=paths)


@pytest.mark.asyncio
async def test_exclusive_scope_allows_delete_files_and_preserves_dry_run() -> None:
    target_hash = "A" * 40
    client = InventoryDownloader(
        DownloaderContentInventory(scopes=(_scope(target_hash, "/data/torrents/Movie/file.mkv"),))
    )
    fleet = _fleet(("client", client))

    result = await fleet.delete_hashes([target_hash], delete_files=True, dry_run=True)

    assert client.calls == [((target_hash,), True, True)]
    assert result[0].delete_files is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "other_path",
    [
        "/data/torrents/Movie/file.mkv",
        "/data/torrents/Movie",
        "/data/torrents/Movie/file.mkv/child",
    ],
)
async def test_equal_ancestor_and_descendant_scopes_skip_target(other_path: str) -> None:
    target_hash = "A" * 40
    other_hash = "B" * 40
    target = InventoryDownloader(
        DownloaderContentInventory(scopes=(_scope(target_hash, "/data/torrents/Movie/file.mkv"),))
    )
    other = InventoryDownloader(DownloaderContentInventory(scopes=(_scope(other_hash, other_path),)))
    fleet = _fleet(("target-client", target), ("other-client", other))

    result = await fleet.delete_hashes([target_hash], delete_files=True)

    assert target.calls == []
    assert result[0].skip_reason == "shared_path"
    assert result[0].delete_files is False


@pytest.mark.asyncio
async def test_same_hash_on_another_client_is_not_treated_as_exclusive() -> None:
    target_hash = "A" * 40
    first = InventoryDownloader(DownloaderContentInventory(scopes=(_scope(target_hash, "/data/torrents/Movie"),)))
    second = InventoryDownloader(DownloaderContentInventory(scopes=(_scope(target_hash, "/data/torrents/Movie"),)))

    result = await _fleet(("first", first), ("second", second)).delete_hashes([target_hash], delete_files=True)

    assert not first.calls and not second.calls
    assert len(result) == 2
    assert all(item.skip_reason == "shared_path" and item.delete_files is False for item in result)


@pytest.mark.asyncio
async def test_hybrid_alias_requested_v2_detects_canonical_v1_shared_path() -> None:
    v1_hash = "A" * 40
    v2_hash = "B" * 64
    target = InventoryDownloader(
        DownloaderContentInventory(
            scopes=(
                DownloaderContentScope(
                    info_hash=v1_hash,
                    hash_aliases=(v2_hash,),
                    paths=("/data/torrents/Movie",),
                ),
            )
        )
    )
    other = InventoryDownloader(DownloaderContentInventory(scopes=(_scope("C" * 40, "/data/torrents/Movie"),)))

    result = await _fleet(("target", target), ("other", other)).delete_hashes([v2_hash], delete_files=True)

    assert not target.calls and not other.calls
    assert result[0].hash_value == v2_hash
    assert result[0].skip_reason == "shared_path"
    assert result[0].delete_files is False


@pytest.mark.asyncio
@pytest.mark.parametrize("dry_run", [False, True])
async def test_missing_or_failed_inventory_blocks_every_client_before_mutation(dry_run: bool) -> None:
    target_hash = "A" * 40
    target = InventoryDownloader(DownloaderContentInventory(scopes=(_scope(target_hash, "/data/torrents/Movie"),)))
    missing = InventoryDownloader(
        DownloaderContentInventory(failures=(DownloaderContentInventoryFailure("invalid_content_scope"),))
    )
    fleet = _fleet(("target", target), ("missing", missing))

    result = await fleet.delete_hashes([target_hash], delete_files=True, dry_run=dry_run)

    assert not target.calls and not missing.calls
    assert len(result) == 2
    assert all(item.skip_reason == "ownership_unverifiable" and item.delete_files is False for item in result)


@pytest.mark.asyncio
async def test_inventory_read_exception_fails_closed() -> None:
    target_hash = "A" * 40
    target = InventoryDownloader(DownloaderContentInventory(scopes=(_scope(target_hash, "/data/torrents/Movie"),)))
    broken = InventoryDownloader(RuntimeError("fixture read failed"))

    result = await _fleet(("target", target), ("broken", broken)).delete_hashes([target_hash], delete_files=True)

    assert not target.calls
    assert all(item.skip_reason == "ownership_unverifiable" for item in result)


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["", "relative/file.mkv", "/data/torrents/Movie/../other"])
async def test_invalid_scope_path_fails_closed(path: str) -> None:
    target_hash = "A" * 40
    client = InventoryDownloader(DownloaderContentInventory(scopes=(_scope(target_hash, path),)))

    result = await _fleet(("client", client)).delete_hashes([target_hash], delete_files=True)

    assert client.calls == []
    assert result[0].skip_reason == "ownership_unverifiable"
    assert result[0].delete_files is False


@pytest.mark.asyncio
async def test_noncanonical_scope_hash_fails_closed() -> None:
    client = InventoryDownloader(DownloaderContentInventory(scopes=(_scope(("A" * 39) + "a", "/data/torrents/Movie"),)))

    result = await _fleet(("client", client)).delete_hashes(["A" * 40], delete_files=True)

    assert client.calls == []
    assert result[0].skip_reason == "ownership_unverifiable"


@pytest.mark.asyncio
async def test_duplicate_scope_hash_in_one_inventory_fails_closed() -> None:
    target_hash = "A" * 40
    client = InventoryDownloader(
        DownloaderContentInventory(
            scopes=(
                _scope(target_hash, "/data/torrents/Movie/one.mkv"),
                _scope(target_hash, "/data/torrents/Movie/two.mkv"),
            )
        )
    )

    result = await _fleet(("client", client)).delete_hashes([target_hash], delete_files=True)

    assert client.calls == []
    assert result[0].skip_reason == "ownership_unverifiable"


def test_known_existing_hash_missing_from_inventory_is_unknown() -> None:
    target_hash = "A" * 40
    assessment = assess_content_inventory(
        [("client", DownloaderContentInventory())],
        [target_hash],
        known_existing={"client": (target_hash,)},
    )

    assert content_safety_skip_reason(assessment, "client", target_hash) == "ownership_unverifiable"


@pytest.mark.asyncio
async def test_inventory_timeout_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    class HangingDownloader(InventoryDownloader):
        async def list_content_inventory(self) -> DownloaderContentInventory:
            await asyncio.sleep(1)
            return (
                self.inventory
                if isinstance(self.inventory, DownloaderContentInventory)
                else DownloaderContentInventory()
            )

    import cleanarr.application.data_safety as data_safety

    monkeypatch.setattr(data_safety, "CONTENT_INVENTORY_TIMEOUT_SECONDS", 0.001)
    target_hash = "A" * 40
    client = HangingDownloader(DownloaderContentInventory(scopes=(_scope(target_hash, "/data/torrents/Movie"),)))

    result = await _fleet(("client", client)).delete_hashes([target_hash], delete_files=True)

    assert client.calls == []
    assert result[0].skip_reason == "ownership_unverifiable"


async def test_intervening_lexical_sibling_does_not_hide_ancestor_conflict() -> None:
    target_hash = "A" * 40
    client = InventoryDownloader(
        DownloaderContentInventory(
            scopes=(
                _scope(target_hash, "/data/torrents/A"),
                _scope("B" * 40, "/data/torrents/A-extra"),
                _scope("C" * 40, "/data/torrents/A/movie.mkv"),
            )
        )
    )
    result = await _fleet(("client", client)).delete_hashes([target_hash], delete_files=True)
    assert client.calls == []
    assert result[0].skip_reason == "shared_path"
