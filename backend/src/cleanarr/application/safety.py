"""Conservative Sonarr partial deletion safety analysis."""

from __future__ import annotations

from collections import defaultdict

from cleanarr.domain import (
    FailureReason,
    ItemType,
    MediaDeletionEvent,
    SafetyDecision,
    SafetyNote,
    SonarrEpisode,
    SonarrHistoryRecord,
)


class SonarrDeletionSafetyAnalyzer:
    """Determine what can be safely cleaned for TV partial deletions."""

    def analyze(
        self,
        event: MediaDeletionEvent,
        episodes: list[SonarrEpisode],
        history_records: list[SonarrHistoryRecord],
    ) -> SafetyDecision:
        target_episode_ids = self._resolve_target_episode_ids(event, episodes)
        if not target_episode_ids:
            return SafetyDecision(
                target_episode_ids=frozenset(),
                episode_ids_to_unmonitor=frozenset(),
                episode_file_ids_to_delete=frozenset(),
                hashes_to_delete=frozenset(),
                notes=(
                    SafetyNote(
                        reason=FailureReason.NO_MATCH,
                        message="No Sonarr episodes matched the requested deletion scope.",
                    ),
                ),
            )

        file_to_episode_ids: dict[int, set[int]] = defaultdict(set)
        for episode in episodes:
            if episode.episode_file_id:
                file_to_episode_ids[episode.episode_file_id].add(episode.id)

        safe_file_ids: set[int] = set()
        notes: list[SafetyNote] = []
        for file_id, file_episode_ids in file_to_episode_ids.items():
            if not (file_episode_ids & target_episode_ids):
                continue
            if file_episode_ids <= target_episode_ids:
                safe_file_ids.add(file_id)
                continue
            notes.append(
                SafetyNote(
                    reason=FailureReason.SHARED_FILE,
                    message="Episode file spans content outside the requested deletion scope.",
                    details={
                        "episode_file_id": file_id,
                        "episode_ids": sorted(file_episode_ids),
                    },
                )
            )

        hash_to_episode_ids: dict[str, set[int]] = defaultdict(set)
        for record in history_records:
            if record.event_type != "grabbed" or not record.download_id or record.episode_id is None:
                continue
            hash_to_episode_ids[record.download_id.upper()].add(record.episode_id)

        safe_hashes: set[str] = set()
        pack_blocked_episode_ids: set[int] = set()
        for hash_value, hash_episode_ids in hash_to_episode_ids.items():
            if not (hash_episode_ids & target_episode_ids):
                continue
            if hash_episode_ids <= target_episode_ids:
                safe_hashes.add(hash_value)
                continue
            pack_blocked_episode_ids.update(hash_episode_ids & target_episode_ids)
            notes.append(
                SafetyNote(
                    reason=FailureReason.PACK_TORRENT,
                    message="Torrent hash spans episodes outside the requested deletion scope.",
                    details={
                        "hash": hash_value,
                        "episode_ids": sorted(hash_episode_ids),
                    },
                )
            )

        if pack_blocked_episode_ids:
            allowed_file_ids: set[int] = set()
            for file_id in safe_file_ids:
                file_episode_ids = file_to_episode_ids[file_id]
                if file_episode_ids & pack_blocked_episode_ids:
                    notes.append(
                        SafetyNote(
                            reason=FailureReason.PACK_TORRENT,
                            message="Episode file is kept because its backing torrent is part of a larger pack.",
                            details={
                                "episode_file_id": file_id,
                                "episode_ids": sorted(file_episode_ids),
                            },
                        )
                    )
                    continue
                allowed_file_ids.add(file_id)
            safe_file_ids = allowed_file_ids

        episode_ids_to_unmonitor = target_episode_ids if event.item_type is not ItemType.SERIES else frozenset()
        return SafetyDecision(
            target_episode_ids=target_episode_ids,
            episode_ids_to_unmonitor=episode_ids_to_unmonitor,
            episode_file_ids_to_delete=frozenset(sorted(safe_file_ids)),
            hashes_to_delete=frozenset(sorted(safe_hashes)),
            notes=tuple(notes),
        )

    @staticmethod
    def _resolve_target_episode_ids(
        event: MediaDeletionEvent,
        episodes: list[SonarrEpisode],
    ) -> frozenset[int]:
        if event.item_type is ItemType.SERIES:
            return frozenset(episode.id for episode in episodes)

        if event.season_number is None:
            return frozenset()

        season_episodes = [episode for episode in episodes if episode.season_number == event.season_number]
        if event.item_type is ItemType.SEASON:
            return frozenset(episode.id for episode in season_episodes)

        if event.item_type is not ItemType.EPISODE:
            return frozenset()

        target_numbers = event.episode_numbers
        return frozenset(episode.id for episode in season_episodes if episode.episode_number in target_numbers)
