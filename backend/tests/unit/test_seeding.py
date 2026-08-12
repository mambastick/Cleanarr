from cleanarr.domain.config import TorrentRemovalPolicy
from cleanarr.domain.seeding import TorrentSeedingStatus, seeding_policy_skip_reason


def test_deferred_policy_requires_every_configured_threshold() -> None:
    reason = seeding_policy_skip_reason(
        TorrentRemovalPolicy.DEFER,
        min_seed_ratio=1.5,
        min_seed_time_minutes=60,
        status=TorrentSeedingStatus(ratio=2.0, seeding_time_seconds=3_000),
    )

    assert reason == "Torrent removal deferred: seed time is 50 min (required 60 min)."


def test_keep_policy_never_removes_an_existing_torrent() -> None:
    reason = seeding_policy_skip_reason(
        TorrentRemovalPolicy.KEEP,
        min_seed_ratio=None,
        min_seed_time_minutes=None,
        status=TorrentSeedingStatus(ratio=10.0, seeding_time_seconds=1_000_000),
    )

    assert reason == "Torrent retained by the configured keep policy."
