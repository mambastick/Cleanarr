"""Destructive downloader data-scope safety contracts."""

import asyncio
from dataclasses import dataclass, field

import pytest

from cleanarr.application.data_safety import (
    ContentSafetyAssessment,
    assess_content_inventory,
    content_safety_blockers,
    content_safety_skip_reason,
    refresh_content_inventory,
)
from cleanarr.domain import (
    ContentScopeBlocker,
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
    inventory_reads: int = 0

    async def close(self) -> None:
        return None

    async def ping(self) -> None:
        return None

    async def get_version(self) -> str:
        return "fixture"

    async def list_content_inventory(self) -> DownloaderContentInventory:
        self.inventory_reads += 1
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

    async def _delete_hashes_with_assessment(
        self,
        hashes: list[str],
        *,
        delete_files: bool,
        dry_run: bool = False,
        assessment: ContentSafetyAssessment | None = None,
        assessment_client_id: str | None = None,
    ) -> list[DownloaderRemovalResult]:
        if assessment is not None:
            client_id = assessment_client_id or "client"
            reasons = {value: content_safety_skip_reason(assessment, client_id, value) for value in hashes}
            if any(reason is not None for reason in reasons.values()):
                return [
                    DownloaderRemovalResult(
                        hash_value=value,
                        existed=(client_id, value) in assessment.observed,
                        client_id=client_id,
                        skip_reason=reasons[value],
                        delete_files=False,
                    )
                    for value in hashes
                ]
        return await self.delete_hashes(hashes, delete_files=delete_files, dry_run=dry_run)


@dataclass
class LegacyInventoryDownloader:
    inventory: DownloaderContentInventory
    calls: list[tuple[tuple[str, ...], bool, bool]] = field(default_factory=list)

    async def close(self) -> None:
        return None

    async def ping(self) -> None:
        return None

    async def get_version(self) -> str:
        return "fixture"

    async def list_content_inventory(self) -> DownloaderContentInventory:
        return self.inventory

    async def delete_hashes(
        self, hashes: list[str], *, delete_files: bool, dry_run: bool = False
    ) -> list[DownloaderRemovalResult]:
        self.calls.append((tuple(hashes), delete_files, dry_run))
        return [
            DownloaderRemovalResult(hash_value=value, existed=True, client_kind="legacy", delete_files=delete_files)
            for value in hashes
        ]


def _fleet(*clients: tuple[str, InventoryDownloader]) -> MultiDownloaderClient:
    return MultiDownloaderClient(
        [DownloaderTarget(id=client_id, name=client_id, kind="fixture", client=client) for client_id, client in clients]
    )


def _legacy_fleet(*clients: tuple[str, LegacyInventoryDownloader]) -> MultiDownloaderClient:
    return MultiDownloaderClient(
        [DownloaderTarget(id=client_id, name=client_id, kind="legacy", client=client) for client_id, client in clients]
    )


def _scope(info_hash: str, *paths: str, torrent_name: str | None = None) -> DownloaderContentScope:
    return DownloaderContentScope(info_hash=info_hash, paths=paths, torrent_name=torrent_name)


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


def test_refresh_preserves_qbt_aliases_empty_scope_and_reassesses_rt_path() -> None:
    qbt_v1 = "A" * 40
    qbt_v2 = "B" * 64
    verified_empty = "C" * 40
    rt_hash = "D" * 40
    qbt_inventory = DownloaderContentInventory(
        scopes=(
            DownloaderContentScope(
                info_hash=qbt_v1,
                hash_aliases=(qbt_v2,),
                paths=("/data/shared",),
            ),
            DownloaderContentScope(info_hash=verified_empty, paths=(), empty_verified=True),
        )
    )
    rt_inventory = DownloaderContentInventory(scopes=(_scope(rt_hash, "/data/rt"),))
    assessment = assess_content_inventory(
        [("qbt", qbt_inventory), ("rt", rt_inventory)],
        [qbt_v1, qbt_v2, verified_empty, rt_hash],
    )

    assert assessment.complete is True
    assert assessment.inventories == (("qbt", qbt_inventory), ("rt", rt_inventory))
    assert "inventories=" not in repr(assessment)

    refreshed_rt = DownloaderContentInventory(scopes=(_scope(rt_hash, "/data/shared"),))
    refreshed = refresh_content_inventory(assessment, "rt", refreshed_rt, [qbt_v2, verified_empty, rt_hash])

    assert refreshed.complete is True
    assert ("qbt", qbt_v1) in refreshed.observed
    assert ("qbt", qbt_v2) in refreshed.observed
    assert content_safety_skip_reason(refreshed, "qbt", qbt_v2) == "shared_path"
    assert content_safety_skip_reason(refreshed, "rt", rt_hash) == "shared_path"
    assert content_safety_skip_reason(refreshed, "qbt", verified_empty) is None


def test_refresh_marks_new_uncertain_rt_overlap_as_sibling_unknown_for_qbt_alias() -> None:
    qbt_v1 = "A" * 40
    qbt_v2 = "B" * 64
    rt_hash = "D" * 40
    qbt_inventory = DownloaderContentInventory(
        scopes=(DownloaderContentScope(info_hash=qbt_v1, hash_aliases=(qbt_v2,), paths=("/data/shared",)),)
    )
    assessment = assess_content_inventory(
        [("qbt", qbt_inventory), ("rt", DownloaderContentInventory())], [qbt_v2, rt_hash]
    )

    refreshed = refresh_content_inventory(
        assessment,
        "rt",
        DownloaderContentInventory(
            scopes=(
                DownloaderContentScope(
                    info_hash=rt_hash,
                    paths=("/data/shared/new",),
                    uncertain=True,
                    torrent_name="RT uncertain",
                ),
            )
        ),
        [qbt_v2, rt_hash],
    )

    assert refreshed.complete is True
    assert content_safety_skip_reason(refreshed, "rt", rt_hash) == "ownership_unverifiable"
    assert content_safety_skip_reason(refreshed, "qbt", qbt_v2) == "sibling_scope_unknown"
    assert content_safety_blockers(refreshed, "qbt", qbt_v2) == (ContentScopeBlocker("rt", rt_hash, "RT uncertain"),)


def test_refresh_preserves_original_known_missing_hash_as_blocked() -> None:
    target_hash = "A" * 40
    original = assess_content_inventory(
        [("qbt", DownloaderContentInventory())],
        [target_hash],
        known_existing={"qbt": (target_hash,)},
    )
    refreshed = refresh_content_inventory(
        original,
        "qbt",
        DownloaderContentInventory(scopes=(_scope(target_hash, "/data/torrents/Movie"),)),
        [target_hash],
    )

    assert refreshed.complete is True
    assert ("qbt", target_hash) in refreshed.missing_known
    assert content_safety_skip_reason(refreshed, "qbt", target_hash) == "ownership_unverifiable"


def test_refresh_marks_removed_known_requested_target_missing() -> None:
    target_hash = "A" * 40
    original_inventory = DownloaderContentInventory(scopes=(_scope(target_hash, "/data/torrents/Movie"),))
    original = assess_content_inventory(
        [("qbt", original_inventory)], [target_hash], known_existing={"qbt": (target_hash,)}
    )
    refreshed = refresh_content_inventory(original, "qbt", DownloaderContentInventory(), [target_hash])

    assert refreshed.complete is True
    assert ("qbt", target_hash) in refreshed.missing_known
    assert ("qbt", target_hash) not in refreshed.observed
    assert content_safety_skip_reason(refreshed, "qbt", target_hash) == "ownership_unverifiable"


@pytest.mark.parametrize(
    "assessment, client_id, inventory",
    [
        (
            assess_content_inventory([("qbt", None)], ["A" * 40]),
            "qbt",
            DownloaderContentInventory(),
        ),
        (
            assess_content_inventory([("rt", DownloaderContentInventory())], ["A" * 40]),
            "qbt",
            DownloaderContentInventory(),
        ),
        (
            assess_content_inventory([("qbt", DownloaderContentInventory())], ["A" * 40]),
            "qbt",
            DownloaderContentInventory(failures=(DownloaderContentInventoryFailure("read_failed"),)),
        ),
    ],
)
def test_refresh_invalid_incomplete_or_missing_private_inventory_fails_closed(
    assessment: ContentSafetyAssessment,
    client_id: str,
    inventory: DownloaderContentInventory,
) -> None:
    refreshed = refresh_content_inventory(assessment, client_id, inventory, ["A" * 40])

    assert refreshed.complete is False
    assert content_safety_skip_reason(refreshed, client_id, "A" * 40) == "ownership_unverifiable"


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
    assert len(result) == 1
    assert result[0].existed is None
    assert result[0].skip_reason == "ownership_unverifiable" and result[0].delete_files is False


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


@pytest.mark.asyncio
async def test_bounded_uncertain_unrelated_scope_does_not_block_target() -> None:
    target_hash = "A" * 40
    unknown_hash = "B" * 40
    target = InventoryDownloader(
        DownloaderContentInventory(scopes=(_scope(target_hash, "/data/torrents/target/file.mkv"),))
    )
    unknown = InventoryDownloader(
        DownloaderContentInventory(
            scopes=(DownloaderContentScope(info_hash=unknown_hash, paths=("/data/other",), uncertain=True),)
        )
    )

    result = await _fleet(("target", target), ("unknown", unknown)).delete_hashes([target_hash], delete_files=True)

    assert target.calls == [((target_hash,), True, False)]
    assert target.inventory_reads == 1
    assert unknown.inventory_reads == 1
    assert result[0].existed is True
    assert result[0].skip_reason is None


@pytest.mark.asyncio
async def test_legacy_fallback_blocks_observed_shared_scope_before_mutation() -> None:
    target_hash = "A" * 40
    target = LegacyInventoryDownloader(
        DownloaderContentInventory(scopes=(_scope(target_hash, "/data/torrents/Movie"),))
    )
    other = LegacyInventoryDownloader(DownloaderContentInventory(scopes=(_scope("B" * 40, "/data/torrents/Movie"),)))

    result = await _legacy_fleet(("target", target), ("other", other)).delete_hashes([target_hash], delete_files=True)

    assert target.calls == []
    assert other.calls == []
    assert result[0].skip_reason == "shared_path"
    assert result[0].delete_files is False
    assert result[0].existed is True


def test_empty_scope_requires_explicit_no_payload_evidence() -> None:
    target_hash = "A" * 40
    incomplete = assess_content_inventory(
        [("client", DownloaderContentInventory(scopes=(_scope(target_hash),)))], [target_hash]
    )
    verified = assess_content_inventory(
        [
            (
                "client",
                DownloaderContentInventory(
                    scopes=(DownloaderContentScope(info_hash=target_hash, paths=(), empty_verified=True),)
                ),
            )
        ],
        [target_hash],
    )

    assert incomplete.complete is False
    assert verified.complete is True
    assert content_safety_skip_reason(verified, "client", target_hash) is None


def test_shallow_non_root_scope_is_valid() -> None:
    target_hash = "A" * 40
    assessment = assess_content_inventory(
        [("client", DownloaderContentInventory(scopes=(_scope(target_hash, "/downloads"),)))], [target_hash]
    )

    assert assessment.complete is True
    assert content_safety_skip_reason(assessment, "client", target_hash) is None


def test_uncertain_parent_scope_overlaps_other_client_and_blocks_both() -> None:
    target_hash = "A" * 40
    unknown_hash = "B" * 40
    assessment = assess_content_inventory(
        [
            (
                "unknown",
                DownloaderContentInventory(
                    scopes=(
                        DownloaderContentScope(
                            info_hash=unknown_hash,
                            paths=("/data/torrents",),
                            uncertain=True,
                            torrent_name="Unknown payload",
                        ),
                    )
                ),
            ),
            ("target", DownloaderContentInventory(scopes=(_scope(target_hash, "/data/torrents/Movie"),))),
        ],
        [target_hash, unknown_hash],
    )

    assert assessment.complete is True
    assert content_safety_skip_reason(assessment, "unknown", unknown_hash) == "ownership_unverifiable"
    assert content_safety_skip_reason(assessment, "target", target_hash) == "sibling_scope_unknown"
    assert assessment.sibling_scope_blockers == (
        ("target", target_hash, (ContentScopeBlocker("unknown", unknown_hash, "Unknown payload"),)),
    )
    assert content_safety_blockers(assessment, "target", target_hash) == (
        ContentScopeBlocker("unknown", unknown_hash, "Unknown payload"),
    )


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
