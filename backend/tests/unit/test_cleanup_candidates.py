from datetime import UTC, datetime

from cleanarr.api.cleanup_candidates import _sorted
from cleanarr.application.cleanup_candidates import _map_movie, _map_series, _seeding_summary
from cleanarr.domain import (
    CleanupCandidate,
    CleanupMediaType,
    JellyfinCleanupItem,
    ListingFreshness,
    PlaybackAggregate,
    PlaybackStatus,
    RadarrMovie,
    SeedingSummary,
    SonarrSeries,
    TorrentOwnership,
    TorrentSnapshot,
    TorrentState,
)
from cleanarr.domain.config import GeneralConfig, SeedingStopPolicyConfig


def candidate(kind: CleanupMediaType, *, tmdb: int | None = None, tvdb: int | None = None) -> JellyfinCleanupItem:
    return JellyfinCleanupItem("item", "Title", kind, None, None, None, tmdb_id=tmdb, tvdb_id=tvdb)


def snapshot(
    info_hash: str, *, ratio: float | None = 2.0, state: TorrentState = TorrentState.SEEDING
) -> TorrentSnapshot:
    return TorrentSnapshot(
        "client",
        "Client",
        "qbittorrent",
        info_hash,
        "Torrent",
        state,
        datetime.now(UTC),
        ratio=ratio,
        seeding_time_seconds=3600,
        freshness=ListingFreshness.FRESH,
        ownership=TorrentOwnership.MANAGED,
    )


def test_arr_mapping_requires_one_exact_stable_provider_identity() -> None:
    movie = RadarrMovie(1, "M", "/private", 7, "tt7")
    assert _map_movie(candidate(CleanupMediaType.MOVIE, tmdb=7), [movie]) is movie
    assert _map_movie(candidate(CleanupMediaType.MOVIE, tmdb=7), [movie, movie]) is None
    assert _map_movie(candidate(CleanupMediaType.MOVIE, tmdb=8), [movie]) is None
    conflicting_movie = JellyfinCleanupItem("item", "Title", CleanupMediaType.MOVIE, None, None, None, 7, None, "tt2")
    assert _map_movie(conflicting_movie, [movie]) is None
    series = SonarrSeries(2, "S", "/private", 9, 10, "tt999")
    assert _map_series(candidate(CleanupMediaType.SERIES, tvdb=9), [series]) is series
    assert _map_series(candidate(CleanupMediaType.SERIES, tvdb=9), [series, series]) is None
    assert _map_series(candidate(CleanupMediaType.SERIES, tvdb=8), [series]) is None
    conflicting_series = JellyfinCleanupItem("item", "Title", CleanupMediaType.SERIES, None, None, None, 10, 9, "tt2")
    assert _map_series(conflicting_series, [series]) is None


def test_seeding_summary_is_conservative_and_policy_is_not_implicit_readiness() -> None:
    info_hash = "A" * 40
    policy = SeedingStopPolicyConfig(enabled=True, min_ratio=1)
    config = GeneralConfig(seeding_stop_policy=policy)
    ready = _seeding_summary(history=[], snapshots=[], config=config)
    assert (ready.torrent_state, ready.readiness) == ("not_present", "blocked")
    from cleanarr.domain import RadarrHistoryRecord

    history = [RadarrHistoryRecord(1, 1, "grabbed", info_hash, None)]
    eligible = _seeding_summary(history=history, snapshots=[snapshot(info_hash)], config=config)
    assert (eligible.torrent_state, eligible.readiness) == ("seeding", "eligible")
    missing_metric = _seeding_summary(history=history, snapshots=[snapshot(info_hash, ratio=None)], config=config)
    assert missing_metric.readiness == "unknown"
    disabled = _seeding_summary(history=history, snapshots=[snapshot(info_hash)], config=GeneralConfig())
    assert disabled.readiness == "disabled"


def test_seed_readiness_sort_keeps_unknown_last_in_both_directions() -> None:
    def item(item_id: str, readiness: str) -> CleanupCandidate:
        return CleanupCandidate(
            JellyfinCleanupItem(item_id, item_id, CleanupMediaType.MOVIE, None, None, None),
            PlaybackAggregate(PlaybackStatus.UNKNOWN, None, None, None),
            SeedingSummary("seeding", readiness),
            None,
            None,
            "jellyfin_standard",
            datetime.now(UTC),
        )

    values = [item("unknown", "unknown"), item("eligible", "eligible"), item("blocked", "blocked")]
    assert [value.item.item_id for value in _sorted(values, sort="seed_readiness", direction="desc")] == [
        "eligible",
        "blocked",
        "unknown",
    ]
    assert [value.item.item_id for value in _sorted(values, sort="seed_readiness", direction="asc")] == [
        "blocked",
        "eligible",
        "unknown",
    ]
