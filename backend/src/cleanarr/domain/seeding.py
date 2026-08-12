"""Pure torrent-removal policy evaluation."""

from __future__ import annotations

from dataclasses import dataclass

from cleanarr.domain.config import TorrentRemovalPolicy


@dataclass(frozen=True)
class TorrentSeedingStatus:
    """Normalized share statistics reported by a torrent client."""

    ratio: float | None = None
    seeding_time_seconds: int | None = None


def seeding_policy_skip_reason(
    policy: TorrentRemovalPolicy,
    *,
    min_seed_ratio: float | None,
    min_seed_time_minutes: int | None,
    status: TorrentSeedingStatus,
) -> str | None:
    """Return why removal must be skipped, or ``None`` when it may proceed.

    When both deferred thresholds are configured, both must be satisfied. This
    deliberately favors continued seeding over premature data removal.
    """

    if policy is TorrentRemovalPolicy.IMMEDIATE:
        return None
    if policy is TorrentRemovalPolicy.KEEP:
        return "Torrent retained by the configured keep policy."

    unmet: list[str] = []
    if min_seed_ratio is not None:
        if status.ratio is None:
            unmet.append(f"seed ratio is unavailable (required {min_seed_ratio:g})")
        elif status.ratio < min_seed_ratio:
            unmet.append(f"seed ratio is {status.ratio:g} (required {min_seed_ratio:g})")

    if min_seed_time_minutes is not None:
        required_seconds = min_seed_time_minutes * 60
        if status.seeding_time_seconds is None:
            unmet.append(f"seed time is unavailable (required {min_seed_time_minutes} min)")
        elif status.seeding_time_seconds < required_seconds:
            actual_minutes = status.seeding_time_seconds // 60
            unmet.append(f"seed time is {actual_minutes} min (required {min_seed_time_minutes} min)")

    if unmet:
        return "Torrent removal deferred: " + "; ".join(unmet) + "."
    return None
