from datetime import UTC, datetime

from cleanarr.application.download_policy import PolicyDecision, evaluate_seeding_stop_policy
from cleanarr.application.downloads import resolve_snapshot_ownership
from cleanarr.domain.config import SeedingStopPolicyConfig, SeedingStopPolicyMode
from cleanarr.domain.downloads import ListingFreshness, TorrentOwnership, TorrentSnapshot, TorrentState


def _snapshot(**changes: object) -> TorrentSnapshot:
    values: dict[str, object] = {
        "client_id": "client-a",
        "client_name": "Client A",
        "client_kind": "qbittorrent",
        "info_hash": "A" * 40,
        "display_name": "title",
        "state": TorrentState.SEEDING,
        "observed_at": datetime.now(UTC),
        "freshness": ListingFreshness.FRESH,
        "ownership": TorrentOwnership.MANAGED,
        "ratio": 2.0,
        "seeding_time_seconds": 7200,
    }
    values.update(changes)
    return TorrentSnapshot(**values)


def test_any_with_missing_configured_metric_is_blocked() -> None:
    policy = SeedingStopPolicyConfig(enabled=True, mode=SeedingStopPolicyMode.ANY, min_ratio=3, min_seeding_minutes=30)
    result = evaluate_seeding_stop_policy(policy, _snapshot(ratio=4, seeding_time_seconds=None))
    assert result.decision is PolicyDecision.BLOCKED
    assert result.reason_code == "required_metric_unknown"


def test_scope_exclusion_wins_and_ownership_is_fail_closed() -> None:
    policy = SeedingStopPolicyConfig(enabled=True, min_ratio=1, exclude_tags=["keep"])
    excluded = evaluate_seeding_stop_policy(policy, _snapshot(tags=("keep",)))
    unknown = evaluate_seeding_stop_policy(policy, _snapshot(ownership=TorrentOwnership.UNKNOWN))
    assert excluded.decision is PolicyDecision.EXCLUDED
    assert unknown.reason_code == "ownership_not_managed"


def test_exact_history_and_duplicate_client_identity_control_ownership() -> None:
    one = _snapshot()
    two = _snapshot(client_id="client-b")
    managed = resolve_snapshot_ownership((one,), arr_history_hashes={one.info_hash})
    conflict = resolve_snapshot_ownership((one, two), arr_history_hashes={one.info_hash})
    failed = resolve_snapshot_ownership((one,), arr_history_hashes=None, arr_source_failed=True)
    assert managed[0].ownership is TorrentOwnership.MANAGED
    assert {item.ownership for item in conflict} == {TorrentOwnership.CONFLICT}
    assert failed[0].ownership is TorrentOwnership.UNKNOWN


def test_incomplete_downloader_fleet_cannot_mark_arr_match_managed() -> None:
    item = _snapshot()
    result = resolve_snapshot_ownership((item,), arr_history_hashes={item.info_hash}, downloader_complete=False)
    assert result[0].ownership is TorrentOwnership.UNKNOWN
