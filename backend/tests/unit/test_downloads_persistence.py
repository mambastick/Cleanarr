import asyncio
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from cleanarr.application.downloads import DownloadsService
from cleanarr.domain.config import GeneralConfig, SeedingStopPolicyConfig
from cleanarr.domain.downloads import (
    DownloadActionStatus,
    DownloadControlAction,
    DownloadControlOutcome,
    DownloaderControlResult,
    DownloaderListing,
    DownloaderReadFailure,
    ListingFreshness,
    TorrentOwnership,
    TorrentSnapshot,
    TorrentState,
)
from cleanarr.infrastructure.downloads_repository import DownloadsRepository


def _snapshot(client_id: str = "client-a", info_hash: str = "A" * 40) -> TorrentSnapshot:
    return TorrentSnapshot(
        client_id=client_id,
        client_name="Client",
        client_kind="qbittorrent",
        info_hash=info_hash,
        display_name="Title",
        state=TorrentState.SEEDING,
        observed_at=datetime.now(UTC),
        freshness=ListingFreshness.FRESH,
        ratio=2.0,
    )


def test_partial_refresh_only_stales_rows_for_complete_clients(tmp_path: Path) -> None:
    repository = DownloadsRepository(tmp_path / "cleanarr.db")
    first = _snapshot()
    second = _snapshot(client_id="client-b", info_hash="B" * 40)
    repository.save_listing((first, second), {"client-a", "client-b"})
    repository.save_listing((first,), {"client-a"})
    by_key = {(item.client_id, item.info_hash): item for item in repository.list_snapshots()}
    assert by_key[("client-a", first.info_hash)].freshness is ListingFreshness.FRESH
    assert by_key[("client-b", second.info_hash)].freshness is ListingFreshness.STALE


def test_action_claim_is_canonical_and_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "cleanarr.db"
    repository = DownloadsRepository(db_path)
    key = "00000000-0000-0000-0000-000000000001"
    request = '{"action":"pause","client_id":"client-a","info_hash":"' + "A" * 40 + '"}'
    first = repository.claim_action(
        idempotency_key=key,
        canonical_request=request,
        client_id="client-a",
        info_hash="A" * 40,
        action=DownloadControlAction.PAUSE,
        max_attempts=1,
    )
    duplicate = repository.claim_action(
        idempotency_key=key,
        canonical_request=request,
        client_id="client-a",
        info_hash="A" * 40,
        action=DownloadControlAction.PAUSE,
        max_attempts=1,
    )
    conflict = repository.claim_action(
        idempotency_key=key,
        canonical_request=request.replace("pause", "resume"),
        client_id="client-a",
        info_hash="A" * 40,
        action=DownloadControlAction.RESUME,
        max_attempts=1,
    )
    assert first.action_id == duplicate.action_id
    assert duplicate.status is DownloadActionStatus.QUEUED
    assert conflict.conflict is True
    with sqlite3.connect(db_path) as db:
        assert db.execute("SELECT COUNT(*) FROM download_actions").fetchone() == (1,)


def test_failed_refresh_stales_managed_row_and_policy_does_not_mutate(tmp_path: Path) -> None:
    class FailedFleet:
        mutations = 0

        def configured_client_ids(self) -> set[str]:
            return {"client-a"}

        async def list_torrents(self) -> DownloaderListing:
            return DownloaderListing(
                failures=(DownloaderReadFailure("client-a", "Client", "qbittorrent", "client_read_failed"),)
            )

        async def control_torrent(self, client_id: str, info_hash: str, *, action: DownloadControlAction):
            self.mutations += 1
            raise AssertionError("stale policy target must not mutate")

    repository = DownloadsRepository(tmp_path / "cleanarr.db")
    item = _snapshot()
    managed = item.__class__(**{**item.__dict__, "ownership": TorrentOwnership.MANAGED})
    repository.save_listing((managed,), {"client-a"})
    fleet = FailedFleet()
    service = DownloadsService(repository=repository, downloader=fleet, execution_lock=asyncio.Lock())
    config = GeneralConfig(
        seeding_stop_policy=SeedingStopPolicyConfig(enabled=True, min_ratio=1),
    )
    asyncio.run(service.refresh(config=config, arr_history_hashes={item.info_hash}))
    asyncio.run(service.evaluate_and_apply_policy(config=config))
    assert repository.get_snapshot("client-a", item.info_hash).freshness is ListingFreshness.STALE
    assert fleet.mutations == 0


class _ControlFleet:
    def __init__(self, result: DownloaderControlResult) -> None:
        self.result = result
        self.calls = 0

    def configured_client_ids(self) -> set[str]:
        return {"client-a"}

    async def list_torrents(self) -> DownloaderListing:
        return DownloaderListing()

    async def control_torrent(self, client_id: str, info_hash: str, *, action: DownloadControlAction):
        self.calls += 1
        return self.result


def _eligible_config(*, dry_run: bool, max_attempts: int = 1) -> GeneralConfig:
    return GeneralConfig(
        dry_run=dry_run,
        seeding_stop_policy=SeedingStopPolicyConfig(enabled=True, min_ratio=1, max_attempts=max_attempts),
    )


def _applied_result(item: TorrentSnapshot) -> DownloaderControlResult:
    return DownloaderControlResult(
        client_id=item.client_id,
        client_name=item.client_name,
        client_kind=item.client_kind,
        info_hash=item.info_hash,
        action=DownloadControlAction.PAUSE,
        outcome=DownloadControlOutcome.APPLIED,
        before=item,
        after=item.__class__(**{**item.__dict__, "state": TorrentState.STOPPED}),
        code="applied",
    )


def test_policy_dry_run_then_live_uses_distinct_durable_action(tmp_path: Path) -> None:
    repository = DownloadsRepository(tmp_path / "cleanarr.db")
    item = _snapshot()
    repository.save_listing((item.__class__(**{**item.__dict__, "ownership": TorrentOwnership.MANAGED}),), {"client-a"})
    fleet = _ControlFleet(_applied_result(item))
    service = DownloadsService(repository=repository, downloader=fleet, execution_lock=asyncio.Lock())

    asyncio.run(service.evaluate_and_apply_policy(config=_eligible_config(dry_run=True)))
    asyncio.run(service.evaluate_and_apply_policy(config=_eligible_config(dry_run=False)))

    assert fleet.calls == 1
    with sqlite3.connect(tmp_path / "cleanarr.db") as db:
        rows = db.execute("SELECT status, source, attempt_count FROM download_actions ORDER BY created_at").fetchall()
    assert rows == [("simulated", "policy", 1), ("succeeded", "policy", 1)]


def test_policy_retries_only_safe_pre_mutation_failure_until_bound(tmp_path: Path) -> None:
    repository = DownloadsRepository(tmp_path / "cleanarr.db")
    item = _snapshot()
    managed = item.__class__(**{**item.__dict__, "ownership": TorrentOwnership.MANAGED})
    repository.save_listing((managed,), {"client-a"})
    fleet = _ControlFleet(
        DownloaderControlResult(
            client_id=item.client_id,
            client_name=item.client_name,
            client_kind=item.client_kind,
            info_hash=item.info_hash,
            action=DownloadControlAction.PAUSE,
            outcome=DownloadControlOutcome.UNKNOWN,
            code="pre_read_failed",
        )
    )
    service = DownloadsService(repository=repository, downloader=fleet, execution_lock=asyncio.Lock())
    config = _eligible_config(dry_run=False, max_attempts=3)
    for _ in range(5):
        asyncio.run(service.evaluate_and_apply_policy(config=config))

    assert fleet.calls == 3
    with sqlite3.connect(tmp_path / "cleanarr.db") as db:
        assert db.execute("SELECT status, code, attempt_count, max_attempts FROM download_actions").fetchone() == (
            "failed",
            "pre_read_failed",
            3,
            3,
        )


def test_policy_never_retries_ambiguous_or_successful_actions(tmp_path: Path) -> None:
    for code, outcome, expected_status in (
        ("mutation_or_post_read_failed", DownloadControlOutcome.UNKNOWN, "uncertain"),
        ("applied", DownloadControlOutcome.APPLIED, "succeeded"),
    ):
        repository = DownloadsRepository(tmp_path / f"{expected_status}.db")
        item = _snapshot()
        repository.save_listing(
            (item.__class__(**{**item.__dict__, "ownership": TorrentOwnership.MANAGED}),), {"client-a"}
        )
        fleet = _ControlFleet(
            DownloaderControlResult(
                client_id=item.client_id,
                client_name=item.client_name,
                client_kind=item.client_kind,
                info_hash=item.info_hash,
                action=DownloadControlAction.PAUSE,
                outcome=outcome,
                code=code,
            )
        )
        service = DownloadsService(repository=repository, downloader=fleet, execution_lock=asyncio.Lock())
        config = _eligible_config(dry_run=False, max_attempts=3)
        asyncio.run(service.evaluate_and_apply_policy(config=config))
        asyncio.run(service.evaluate_and_apply_policy(config=config))
        assert fleet.calls == 1


def test_exact_duplicate_terminal_outcome_and_code_are_replayed(tmp_path: Path) -> None:
    repository = DownloadsRepository(tmp_path / "cleanarr.db")
    item = _snapshot()
    repository.save_listing((item,), {"client-a"})
    fleet = _ControlFleet(_applied_result(item))
    service = DownloadsService(repository=repository, downloader=fleet, execution_lock=asyncio.Lock())
    key = str(uuid4())
    first = asyncio.run(
        service.control(
            client_id=item.client_id,
            info_hash=item.info_hash,
            action=DownloadControlAction.PAUSE,
            idempotency_key=key,
        )
    )
    duplicate = asyncio.run(
        service.control(
            client_id=item.client_id,
            info_hash=item.info_hash,
            action=DownloadControlAction.PAUSE,
            idempotency_key=key,
        )
    )
    assert duplicate == first
    assert fleet.calls == 1


def test_unsupported_client_version_remains_structured_and_non_retryable(tmp_path: Path) -> None:
    repository = DownloadsRepository(tmp_path / "cleanarr.db")
    item = _snapshot()
    repository.save_listing((item,), {"client-a"})
    fleet = _ControlFleet(
        DownloaderControlResult(
            client_id=item.client_id,
            client_name=item.client_name,
            client_kind=item.client_kind,
            info_hash=item.info_hash,
            action=DownloadControlAction.PAUSE,
            outcome=DownloadControlOutcome.UNKNOWN,
            code="unsupported_client_version",
        )
    )
    service = DownloadsService(repository=repository, downloader=fleet, execution_lock=asyncio.Lock())
    key = str(uuid4())
    first = asyncio.run(
        service.control(
            client_id=item.client_id,
            info_hash=item.info_hash,
            action=DownloadControlAction.PAUSE,
            idempotency_key=key,
            allow_retry=True,
            max_attempts=3,
        )
    )
    duplicate = asyncio.run(
        service.control(
            client_id=item.client_id,
            info_hash=item.info_hash,
            action=DownloadControlAction.PAUSE,
            idempotency_key=key,
            allow_retry=True,
            max_attempts=3,
        )
    )
    assert first[1:] == (DownloadActionStatus.FAILED, "unsupported_client_version")
    assert duplicate == first
    assert fleet.calls == 1


def test_concurrent_duplicate_control_mutates_once(tmp_path: Path) -> None:
    repository = DownloadsRepository(tmp_path / "cleanarr.db")
    item = _snapshot()
    repository.save_listing((item,), {"client-a"})
    started = asyncio.Event()
    release = asyncio.Event()

    class BlockingFleet(_ControlFleet):
        async def control_torrent(self, client_id: str, info_hash: str, *, action: DownloadControlAction):
            self.calls += 1
            started.set()
            await release.wait()
            return self.result

    fleet = BlockingFleet(_applied_result(item))
    service = DownloadsService(repository=repository, downloader=fleet, execution_lock=asyncio.Lock())

    async def run() -> tuple[
        tuple[str, DownloadActionStatus, str | None], tuple[str, DownloadActionStatus, str | None]
    ]:
        key = str(uuid4())
        tasks = [
            asyncio.create_task(
                service.control(
                    client_id=item.client_id,
                    info_hash=item.info_hash,
                    action=DownloadControlAction.PAUSE,
                    idempotency_key=key,
                )
            )
            for _ in range(2)
        ]
        await started.wait()
        release.set()
        return await asyncio.gather(*tasks)

    first, second = asyncio.run(run())
    assert first[0] == second[0]
    assert {first[1], second[1]} <= {DownloadActionStatus.SUCCEEDED, DownloadActionStatus.RUNNING}
    assert fleet.calls == 1


def test_running_action_recovers_without_remutation(tmp_path: Path) -> None:
    repository = DownloadsRepository(tmp_path / "cleanarr.db")
    item = _snapshot()
    repository.save_listing((item,), {"client-a"})
    key = str(uuid4())
    claim = repository.claim_action(
        idempotency_key=key,
        canonical_request=(
            '{"action":"pause","client_id":"client-a","execution_mode":"live",'
            '"info_hash":"AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"}'
        ),
        client_id="client-a",
        info_hash="A" * 40,
        action=DownloadControlAction.PAUSE,
        max_attempts=1,
    )
    repository.update_action(claim.action_id, DownloadActionStatus.RUNNING, code="running")
    assert repository.recover_running_actions() == 1
    fleet = _ControlFleet(_applied_result(item))
    service = DownloadsService(repository=repository, downloader=fleet, execution_lock=asyncio.Lock())
    outcome = asyncio.run(
        service.control(
            client_id="client-a",
            info_hash="A" * 40,
            action=DownloadControlAction.PAUSE,
            idempotency_key=key,
        )
    )
    assert outcome[1:] == (DownloadActionStatus.RECONCILE_REQUIRED, "restart_recovery")
    assert fleet.calls == 0


def test_action_result_and_policy_projection_are_bounded_and_latest(tmp_path: Path) -> None:
    repository = DownloadsRepository(tmp_path / "cleanarr.db")
    item = _snapshot()
    managed = item.__class__(**{**item.__dict__, "ownership": TorrentOwnership.MANAGED})
    repository.save_listing((managed,), {"client-a"})
    repository.record_policy_evaluation(
        revision="rev",
        snapshot=managed,
        facts={"ratio": 2.0, "freshness": "fresh", "ownership": "managed"},
        reason_code="thresholds_met",
        decision="eligible",
    )
    assert repository.latest_policy_evaluations()[("client-a", item.info_hash)]["decision"] == "eligible"
    assert repository.latest_policy_evaluations()[("client-a", item.info_hash)]["facts"] == {
        "ratio": 2.0,
        "freshness": "fresh",
        "ownership": "managed",
    }
    repository.update_action(
        "missing",
        DownloadActionStatus.SUCCEEDED,
        code="applied",
        result={"outcome": "applied", "before_state": "seeding", "after_state": "stopped", "path": "/private"},
    )
    claim = repository.claim_action(
        idempotency_key=str(uuid4()),
        canonical_request="{}",
        client_id="client-a",
        info_hash=item.info_hash,
        action=DownloadControlAction.PAUSE,
        max_attempts=1,
        source="policy",
    )
    repository.update_action(
        claim.action_id,
        DownloadActionStatus.SUCCEEDED,
        code="applied",
        result={"outcome": "applied", "before_state": "seeding", "after_state": "stopped", "path": "/private"},
    )
    projection = repository.latest_action_projections({("client-a", item.info_hash)})[("client-a", item.info_hash)]
    assert projection["source"] == "policy"
    assert projection["result"] == {
        "after_state": "stopped",
        "before_state": "seeding",
        "code": "applied",
        "outcome": "applied",
    }
    assert "path" not in projection["result"]
    with pytest.raises(ValueError, match="At most 50"):
        repository.latest_action_projections({("client-a", f"{index:040x}") for index in range(51)})

    with sqlite3.connect(tmp_path / "cleanarr.db") as db:
        for index in range(5001):
            db.execute(
                "INSERT OR REPLACE INTO policy_evaluations(policy_revision,client_id,info_hash,observation_key,facts_json,reason_code,decision,evaluated_at) VALUES (?,?,?,?,?,?,?,?)",
                ("old", "client", f"{index:040x}", f"client:{index}", "{}", "x", "blocked", f"{index:06d}"),
            )
        db.commit()
    repository.record_policy_evaluation(
        revision="new",
        snapshot=managed,
        facts={"ratio": 2.0},
        reason_code="thresholds_met",
        decision="eligible",
    )
    with sqlite3.connect(tmp_path / "cleanarr.db") as db:
        assert db.execute("SELECT COUNT(*) FROM policy_evaluations").fetchone() == (5000,)


def test_partial_fleet_refresh_marks_failed_rows_stale_and_blocks_policy(tmp_path: Path) -> None:
    repository = DownloadsRepository(tmp_path / "cleanarr.db")
    old = _snapshot(client_id="client-b", info_hash="B" * 40)
    repository.save_listing((old,), {"client-b"})
    matching = _snapshot(client_id="client-a", info_hash="A" * 40)

    class PartialFleet:
        calls = 0

        def configured_client_ids(self) -> set[str]:
            return {"client-a", "client-b"}

        async def list_torrents(self) -> DownloaderListing:
            return DownloaderListing(
                torrents=(matching,),
                failures=(DownloaderReadFailure("client-b", "Client B", "qbittorrent", "client_read_failed"),),
            )

        async def control_torrent(self, client_id: str, info_hash: str, *, action: DownloadControlAction):
            self.calls += 1
            raise AssertionError("incomplete fleet must not apply policy")

    fleet = PartialFleet()
    service = DownloadsService(repository=repository, downloader=fleet, execution_lock=asyncio.Lock())
    config = _eligible_config(dry_run=False)
    asyncio.run(service.refresh(config=config, arr_history_hashes={matching.info_hash}))
    asyncio.run(service.evaluate_and_apply_policy(config=config))

    assert repository.get_snapshot("client-a", matching.info_hash).ownership is TorrentOwnership.UNKNOWN
    assert repository.get_snapshot("client-b", old.info_hash).freshness is ListingFreshness.STALE
    assert fleet.calls == 0
