"""Read-only cleanup-candidate orchestration.

Playback is a recommendation signal.  This service has no deletion port and
does not refresh, pause, resume, or otherwise mutate downloader state.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from cleanarr.application.download_policy import PolicyDecision, evaluate_seeding_stop_policy
from cleanarr.application.ports import (
    DownloadsRepositoryPort,
    JellyfinPlaybackReadPort,
    RadarrClientPort,
    SonarrClientPort,
)
from cleanarr.domain import (
    CleanupCandidate,
    CleanupDeletionLink,
    CleanupMediaType,
    JellyfinCleanupItem,
    LibraryEnrichment,
    LibraryItem,
    LibraryMediaType,
    ListingFreshness,
    PlaybackAggregate,
    PlaybackObservation,
    PlaybackStatus,
    RadarrHistoryRecord,
    RadarrMovie,
    SeedingSummary,
    SonarrHistoryRecord,
    SonarrSeries,
    TorrentOwnership,
    TorrentSnapshot,
    reduce_playback,
    unknown_playback,
)
from cleanarr.domain.config import GeneralConfig

MAX_CANDIDATES = 200
MAX_USERS = 20
PLAYBACK_CHUNK_SIZE = 50
MAX_CONCURRENCY = 4
MAX_HISTORY_CANDIDATES = 50
ARR_HISTORY_RECORD_CAP = 1000


class CleanupCandidatesError(ValueError):
    pass


class CandidateSourcePort(JellyfinPlaybackReadPort, Protocol):
    """Named extension point for future Playback Reporting/Jellystat adapters."""


@dataclass(frozen=True)
class CleanupCandidatesResult:
    candidates: tuple[CleanupCandidate, ...]
    source_status: str
    failure_codes: tuple[str, ...]
    truncated: bool


def _identifier(value: int | str | None, *, numeric: bool) -> str | None:
    """Normalize only an exact provider representation; never coerce aliases."""

    if numeric:
        return str(value) if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None
    if not isinstance(value, str):
        return None
    normalized = value.strip().casefold()
    return normalized if normalized.startswith("tt") and normalized[2:].isdigit() else None


def _provider_match(
    left: tuple[int | str | None, int | str | None, int | str | None],
    right: tuple[int | str | None, int | str | None, int | str | None],
) -> bool:
    """Require an overlap and reject any conflicting shared provider identity."""

    overlap = False
    for index, numeric in enumerate((True, True, False)):
        left_value = _identifier(left[index], numeric=numeric)
        right_value = _identifier(right[index], numeric=numeric)
        if left_value is not None and right_value is not None:
            if left_value != right_value:
                return False
            overlap = True
    return overlap


def _map_movie(item: JellyfinCleanupItem, movies: Sequence[RadarrMovie]) -> RadarrMovie | None:
    matches = [
        movie
        for movie in movies
        if _provider_match((item.tmdb_id, None, item.imdb_id), (movie.tmdb_id, None, movie.imdb_id))
    ]
    return matches[0] if len(matches) == 1 else None


def _map_series(item: JellyfinCleanupItem, series: Sequence[SonarrSeries]) -> SonarrSeries | None:
    matches = [
        candidate
        for candidate in series
        if _provider_match(
            (item.tvdb_id, item.tmdb_id, item.imdb_id),
            (candidate.tvdb_id, candidate.tmdb_id, candidate.imdb_id),
        )
    ]
    return matches[0] if len(matches) == 1 else None


def _download_ids(records: Sequence[RadarrHistoryRecord | SonarrHistoryRecord]) -> set[str] | None:
    values: set[str] = set()
    for record in records:
        event = record.event_type.casefold()
        if "grab" not in event and "import" not in event:
            continue
        if record.download_id is None:
            # A relevant history event without an exact download identity is
            # not evidence of absence; reject the seeding projection instead.
            return None
        normalized = record.download_id.strip().upper()
        if len(normalized) not in {40, 64} or any(character not in "0123456789ABCDEF" for character in normalized):
            return None
        values.add(normalized)
    return values


def _seeding_summary(
    *,
    history: Sequence[RadarrHistoryRecord | SonarrHistoryRecord] | None,
    snapshots: Sequence[TorrentSnapshot],
    config: GeneralConfig,
) -> SeedingSummary:
    if history is None:
        return SeedingSummary(
            "unknown", "unknown", "arr_history_unavailable", unavailable_reason="arr_history_unavailable"
        )
    if len(history) >= ARR_HISTORY_RECORD_CAP:
        return SeedingSummary(
            "unknown", "unknown", "arr_history_incomplete", unavailable_reason="arr_history_incomplete"
        )
    hashes = _download_ids(history)
    if hashes is None:
        return SeedingSummary(
            "unknown", "unknown", "arr_history_incomplete", unavailable_reason="arr_history_incomplete"
        )
    if not hashes:
        return SeedingSummary(
            "not_present", "disabled" if not config.seeding_stop_policy.enabled else "blocked", "no_arr_hashes", 0
        )
    by_hash: dict[str, list[TorrentSnapshot]] = {}
    for snapshot in snapshots:
        by_hash.setdefault(snapshot.info_hash.upper(), []).append(snapshot)
    selected: list[TorrentSnapshot] = []
    for info_hash in hashes:
        matches = by_hash.get(info_hash, [])
        if len(matches) != 1:
            return SeedingSummary(
                "unknown", "unknown", "downloader_mapping_ambiguous", unavailable_reason="downloader_mapping_ambiguous"
            )
        snapshot = matches[0]
        if snapshot.freshness is not ListingFreshness.FRESH:
            return SeedingSummary(
                "unknown", "unknown", "downloader_snapshot_stale", unavailable_reason="downloader_snapshot_stale"
            )
        if snapshot.ownership is not TorrentOwnership.MANAGED:
            return SeedingSummary(
                "unknown", "unknown", "downloader_ownership_unknown", unavailable_reason="downloader_ownership_unknown"
            )
        selected.append(snapshot)
    ratios = [item.ratio for item in selected]
    times = [item.seeding_time_seconds for item in selected]
    ratio_values = [value for value in ratios if value is not None]
    time_values = [value for value in times if value is not None]
    state_values = {item.state.value for item in selected}
    torrent_state = next(iter(state_values)) if len(state_values) == 1 else "mixed"
    if "unknown" in state_values:
        torrent_state = "unknown"
    policy = config.seeding_stop_policy
    if torrent_state == "unknown":
        readiness, reason = "unknown", "torrent_state_unknown"
    elif not policy.enabled:
        readiness, reason = "disabled", "policy_disabled"
    elif (policy.min_ratio is not None and len(ratio_values) != len(selected)) or (
        policy.min_seeding_minutes is not None and len(time_values) != len(selected)
    ):
        readiness, reason = "unknown", "required_metric_unknown"
    else:
        evaluations = tuple(evaluate_seeding_stop_policy(policy, snapshot) for snapshot in selected)
        if any(item.decision is PolicyDecision.EXCLUDED for item in evaluations):
            readiness, reason = "excluded", "excluded_scope"
        elif all(item.decision is PolicyDecision.ELIGIBLE for item in evaluations):
            readiness, reason = "eligible", "thresholds_met"
        else:
            readiness = "blocked"
            reason = next(
                (item.reason_code for item in evaluations if item.decision is not PolicyDecision.ELIGIBLE), "blocked"
            )
    return SeedingSummary(
        torrent_state,
        readiness,
        reason,
        torrent_count=len(selected),
        ratio=min(ratio_values) if len(ratio_values) == len(selected) else None,
        seeding_time_seconds=min(time_values) if len(time_values) == len(selected) else None,
    )


class CleanupCandidatesService:
    def __init__(
        self,
        *,
        playback: CandidateSourcePort,
        radarr: RadarrClientPort,
        sonarr: SonarrClientPort,
        downloads_repository: DownloadsRepositoryPort,
    ) -> None:
        self._playback = playback
        self._radarr = radarr
        self._sonarr = sonarr
        self._downloads_repository = downloads_repository

    def with_sources(
        self, *, playback: CandidateSourcePort, radarr: RadarrClientPort, sonarr: SonarrClientPort
    ) -> CleanupCandidatesService:
        """Create a request-local, immutable capture of one runtime graph."""

        return CleanupCandidatesService(
            playback=playback,
            radarr=radarr,
            sonarr=sonarr,
            downloads_repository=self._downloads_repository,
        )

    async def enrich_library_item(
        self,
        item: LibraryItem,
        *,
        accept_language: str | None,
        config: GeneralConfig,
    ) -> LibraryEnrichment:
        """Read bounded detail evidence for one library item.

        The list endpoint deliberately never calls this method.  A detail
        request may perform one Jellyfin user/playback scope read and one Arr
        history read, while the downloader repository is already a bounded,
        independently refreshed snapshot.  Any incomplete evidence remains
        unknown and carries its machine-readable reason.
        """

        failure_codes: list[str] = []
        playback = unknown_playback("jellyfin_item_unavailable")
        if item.jellyfin_item_id:
            cleanup_item = JellyfinCleanupItem(
                item_id=item.jellyfin_item_id,
                display_name=item.jellyfin_title or item.title,
                media_type=(
                    CleanupMediaType.MOVIE if item.media_type is LibraryMediaType.MOVIE else CleanupMediaType.SERIES
                ),
                created_at=None,
                added_at=item.added_at,
                size_bytes=item.size_bytes,
            )
            try:
                aggregates, playback_codes, _ = await self._playback_aggregates(
                    (cleanup_item,), accept_language=accept_language
                )
                playback = aggregates.get(item.jellyfin_item_id, playback)
                failure_codes.extend(playback_codes)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - detail evidence is advisory
                playback = unknown_playback("jellyfin_playback_unavailable")
                failure_codes.append("jellyfin_playback_unavailable")
        else:
            failure_codes.append("jellyfin_item_unavailable")

        history: Sequence[RadarrHistoryRecord | SonarrHistoryRecord] | None
        try:
            if item.media_type is LibraryMediaType.MOVIE:
                history = await asyncio.wait_for(self._radarr.list_movie_history(item.legacy_id), timeout=10)
            else:
                history = await asyncio.wait_for(self._sonarr.list_series_history(item.legacy_id), timeout=10)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - missing history is not no-seeding
            history = None
            failure_codes.append("arr_history_unavailable")
        try:
            seeding = _seeding_summary(
                history=history,
                snapshots=self._downloads_repository.list_snapshots(),
                config=config,
            )
        except Exception:  # noqa: BLE001 - malformed evidence remains unknown
            seeding = SeedingSummary(
                "unknown",
                "unknown",
                "seeding_evidence_invalid",
                unavailable_reason="seeding_evidence_invalid",
            )
            failure_codes.append("seeding_evidence_invalid")

        if playback.unavailable_reason:
            failure_codes.append(playback.unavailable_reason)
        if seeding.unavailable_reason:
            failure_codes.append(seeding.unavailable_reason)
        playback_freshness = "unknown" if playback.status is PlaybackStatus.UNKNOWN else "fresh"
        return LibraryEnrichment(
            playback_status=playback.status.value,
            playback_freshness=playback_freshness,
            play_count=playback.play_count,
            last_played_at=playback.last_played_at,
            playback_reason=playback.unavailable_reason,
            seeding_state=seeding.torrent_state,
            seeding_readiness=seeding.readiness,
            seeding_ratio=seeding.ratio,
            seeding_time_seconds=seeding.seeding_time_seconds,
            seeding_reason=seeding.unavailable_reason or seeding.readiness_reason,
            failure_codes=tuple(sorted(set(failure_codes))),
        )

    async def list_candidates(
        self,
        *,
        accept_language: str | None,
        jellyfin_configured: bool,
        radarr_configured: bool,
        sonarr_configured: bool,
        config: GeneralConfig,
    ) -> CleanupCandidatesResult:
        if not jellyfin_configured:
            return CleanupCandidatesResult((), "unavailable", ("jellyfin_not_configured",), False)
        try:
            items, catalog_truncated = await asyncio.wait_for(
                self._playback.list_cleanup_items(accept_language=accept_language, max_items=MAX_CANDIDATES), timeout=30
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            return CleanupCandidatesResult((), "unavailable", ("jellyfin_catalog_unavailable",), False)
        if catalog_truncated:
            # A truncated catalog cannot be represented as a globally complete
            # filter/sort result.  The returned prefix remains explicitly partial.
            failure_codes: list[str] = ["jellyfin_catalog_truncated"]
        else:
            failure_codes = []
        aggregates, playback_codes, playback_truncated = await self._playback_aggregates(
            items, accept_language=accept_language
        )
        failure_codes.extend(playback_codes)
        mappings, histories, mapping_codes, history_truncated = await self._resolve_arr(
            items, radarr_configured, sonarr_configured
        )
        failure_codes.extend(mapping_codes)
        snapshots = self._downloads_repository.list_snapshots()
        now = datetime.now(tz=UTC)
        candidates: list[CleanupCandidate] = []
        for item in items:
            arr_id = mappings.get(item.item_id)
            link = (
                CleanupDeletionLink(
                    item_type="Movie" if item.media_type is CleanupMediaType.MOVIE else "Series",
                    radarr_movie_id=arr_id if item.media_type is CleanupMediaType.MOVIE else None,
                    sonarr_series_id=arr_id if item.media_type is CleanupMediaType.SERIES else None,
                    jellyfin_item_id=item.item_id,
                    display_name=item.display_name,
                )
                if arr_id is not None
                else None
            )
            candidates.append(
                CleanupCandidate(
                    item=item,
                    playback=aggregates.get(item.item_id, unknown_playback("playback_observation_incomplete")),
                    seeding=_seeding_summary(history=histories.get(item.item_id), snapshots=snapshots, config=config)
                    if arr_id is not None
                    else SeedingSummary(
                        "unknown", "unknown", "arr_mapping_unknown", unavailable_reason="arr_mapping_unknown"
                    ),
                    mapped_arr_id=arr_id,
                    deletion_link=link,
                    source="jellyfin_standard",
                    fetched_at=now,
                    unavailable_reason=None,
                )
            )
        truncated = catalog_truncated or playback_truncated or history_truncated
        source_status = "partial" if truncated or failure_codes else "complete"
        return CleanupCandidatesResult(tuple(candidates), source_status, tuple(sorted(set(failure_codes))), truncated)

    async def _playback_aggregates(
        self, items: tuple[JellyfinCleanupItem, ...], *, accept_language: str | None
    ) -> tuple[dict[str, PlaybackAggregate], tuple[str, ...], bool]:
        try:
            users, users_truncated = await asyncio.wait_for(
                self._playback.list_playback_users(max_users=MAX_USERS), timeout=15
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            return (
                {item.item_id: unknown_playback("playback_users_unavailable") for item in items},
                ("jellyfin_users_unavailable",),
                False,
            )
        if users_truncated or not users:
            return (
                {item.item_id: unknown_playback("playback_scope_incomplete") for item in items},
                ("jellyfin_users_truncated" if users_truncated else "jellyfin_users_unavailable",),
                users_truncated,
            )
        chunks = tuple(
            tuple(item.item_id for item in items[index : index + PLAYBACK_CHUNK_SIZE])
            for index in range(0, len(items), PLAYBACK_CHUNK_SIZE)
        )
        semaphore = asyncio.Semaphore(MAX_CONCURRENCY)

        async def read(user_id: str, item_ids: tuple[str, ...]) -> tuple[PlaybackObservation, ...]:
            async with semaphore:
                return await self._playback.list_user_playback(
                    user_id=user_id, item_ids=item_ids, accept_language=accept_language
                )

        try:
            groups = await asyncio.wait_for(
                asyncio.gather(*(read(user_id, chunk) for user_id in users for chunk in chunks)), timeout=45
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            return (
                {item.item_id: unknown_playback("playback_read_failed") for item in items},
                ("jellyfin_playback_unavailable",),
                False,
            )
        observations = tuple(value for group in groups for value in group)
        expected_items = {item.item_id for item in items}
        if any(
            observation.user_id not in users or observation.item_id not in expected_items
            for observation in observations
        ):
            return (
                {item.item_id: unknown_playback("playback_observation_conflict") for item in items},
                ("jellyfin_playback_partial",),
                False,
            )
        aggregates = {
            item.item_id: reduce_playback(
                expected_user_ids=users, item_id=item.item_id, observations=observations, scope_complete=True
            )
            for item in items
        }
        codes = (
            ("jellyfin_playback_partial",)
            if any(aggregate.status is PlaybackStatus.UNKNOWN for aggregate in aggregates.values())
            else ()
        )
        return aggregates, codes, False

    async def _resolve_arr(
        self,
        items: tuple[JellyfinCleanupItem, ...],
        radarr_configured: bool,
        sonarr_configured: bool,
    ) -> tuple[
        dict[str, int],
        dict[str, Sequence[RadarrHistoryRecord | SonarrHistoryRecord] | None],
        tuple[str, ...],
        bool,
    ]:
        movies: Sequence[RadarrMovie] = ()
        series: Sequence[SonarrSeries] = ()
        codes: list[str] = []
        if radarr_configured:
            try:
                movies = await asyncio.wait_for(self._radarr.list_movies(), timeout=15)
            except asyncio.CancelledError:
                raise
            except Exception:
                codes.append("radarr_catalog_unavailable")
        if sonarr_configured:
            try:
                series = await asyncio.wait_for(self._sonarr.list_series(), timeout=15)
            except asyncio.CancelledError:
                raise
            except Exception:
                codes.append("sonarr_catalog_unavailable")
        mapped: dict[str, int] = {}
        mapped_types: dict[str, CleanupMediaType] = {}
        for item in items:
            target = (
                _map_movie(item, movies) if item.media_type is CleanupMediaType.MOVIE else _map_series(item, series)
            )
            if target is not None:
                mapped[item.item_id] = target.id
                mapped_types[item.item_id] = item.media_type
        selected_mapping_items = tuple(mapped.items())[:MAX_HISTORY_CANDIDATES]
        skipped = tuple(item_id for item_id in mapped if item_id not in dict(selected_mapping_items))
        histories: dict[str, Sequence[RadarrHistoryRecord | SonarrHistoryRecord] | None] = {
            item_id: None for item_id in skipped
        }
        history_truncated = bool(skipped)
        if history_truncated:
            codes.append("arr_history_truncated")
        semaphore = asyncio.Semaphore(MAX_CONCURRENCY)

        async def history(
            item_id: str, arr_id: int
        ) -> tuple[str, Sequence[RadarrHistoryRecord | SonarrHistoryRecord] | None]:
            try:
                result: Sequence[RadarrHistoryRecord | SonarrHistoryRecord]
                async with semaphore:
                    if mapped_types[item_id] is CleanupMediaType.MOVIE:
                        result = await asyncio.wait_for(self._radarr.list_movie_history(arr_id), timeout=10)
                    else:
                        result = await asyncio.wait_for(self._sonarr.list_series_history(arr_id), timeout=10)
                return item_id, result
            except asyncio.CancelledError:
                raise
            except Exception:
                return item_id, None

        pairs: Sequence[tuple[str, Sequence[RadarrHistoryRecord | SonarrHistoryRecord] | None]] = ()
        try:
            pairs = await asyncio.wait_for(
                asyncio.gather(*(history(item_id, arr_id) for item_id, arr_id in selected_mapping_items)), timeout=40
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            histories.update({item_id: None for item_id, _ in selected_mapping_items})
            codes.append("arr_history_unavailable")
        history_limit_hits = {
            item_id for item_id, records in pairs if records is not None and len(records) >= ARR_HISTORY_RECORD_CAP
        }
        if history_limit_hits:
            history_truncated = True
            codes.append("arr_history_truncated")
        histories.update({item_id: None if item_id in history_limit_hits else records for item_id, records in pairs})
        if any(value is None for value in histories.values()):
            codes.append("arr_history_unavailable")
        return mapped, histories, tuple(codes), history_truncated
