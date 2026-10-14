"""Durable projections for torrents retained by a seeding policy."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from cleanarr.domain.config import TorrentRemovalPolicy


@dataclass(frozen=True)
class RetainedTorrent:
    """Minimal retention evidence kept independently of download activity."""

    client_id: str
    info_hash: str
    policy: TorrentRemovalPolicy
    correlation_id: str
    provider_ids: dict[str, int | str]
    item_scope: str
    retained_at: datetime
    min_seed_ratio: float | None = None
    min_seed_time_minutes: int | None = None
