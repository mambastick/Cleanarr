"""Tests for conservative Sonarr cleanup safety rules."""

from cleanarr.application.safety import SonarrDeletionSafetyAnalyzer
from cleanarr.domain import (
    FailureReason,
    ItemType,
    MediaDeletionEvent,
    MediaFingerprint,
    SonarrEpisode,
    SonarrHistoryRecord,
)


def test_episode_cleanup_keeps_files_when_torrent_is_a_pack() -> None:
    analyzer = SonarrDeletionSafetyAnalyzer()
    event = MediaDeletionEvent(
        notification_type="ItemDeleted",
        item_type=ItemType.EPISODE,
        item_id="episode-1",
        name="Episode 1",
        fingerprint=MediaFingerprint(tvdb_id=42),
        season_number=1,
        episode_number=1,
    )
    episodes = [
        SonarrEpisode(
            id=10, series_id=1, season_number=1, episode_number=1, episode_file_id=101, has_file=True, monitored=True
        ),
        SonarrEpisode(
            id=11, series_id=1, season_number=1, episode_number=2, episode_file_id=102, has_file=True, monitored=True
        ),
    ]
    history = [
        SonarrHistoryRecord(
            id=1,
            series_id=1,
            episode_id=10,
            event_type="grabbed",
            download_id="PACKHASH",
            imported_path=None,
            release_type="MultiEpisode",
        ),
        SonarrHistoryRecord(
            id=2,
            series_id=1,
            episode_id=11,
            event_type="grabbed",
            download_id="PACKHASH",
            imported_path=None,
            release_type="MultiEpisode",
        ),
    ]

    decision = analyzer.analyze(event, episodes, history)

    assert decision.episode_ids_to_unmonitor == frozenset({10})
    assert decision.episode_file_ids_to_delete == frozenset()
    assert decision.hashes_to_delete == frozenset()
    assert {note.reason for note in decision.notes} == {FailureReason.PACK_TORRENT}


def test_season_cleanup_deletes_only_hashes_fully_contained_in_scope() -> None:
    analyzer = SonarrDeletionSafetyAnalyzer()
    event = MediaDeletionEvent(
        notification_type="ItemDeleted",
        item_type=ItemType.SEASON,
        item_id="season-2",
        name="Season 2",
        fingerprint=MediaFingerprint(tvdb_id=42),
        season_number=2,
    )
    episodes = [
        SonarrEpisode(
            id=20, series_id=1, season_number=2, episode_number=1, episode_file_id=201, has_file=True, monitored=True
        ),
        SonarrEpisode(
            id=21, series_id=1, season_number=2, episode_number=2, episode_file_id=202, has_file=True, monitored=True
        ),
        SonarrEpisode(
            id=30, series_id=1, season_number=1, episode_number=1, episode_file_id=301, has_file=True, monitored=True
        ),
    ]
    history = [
        SonarrHistoryRecord(
            id=1,
            series_id=1,
            episode_id=20,
            event_type="grabbed",
            download_id="S2A",
            imported_path=None,
            release_type=None,
        ),
        SonarrHistoryRecord(
            id=2,
            series_id=1,
            episode_id=21,
            event_type="grabbed",
            download_id="S2B",
            imported_path=None,
            release_type=None,
        ),
        SonarrHistoryRecord(
            id=3,
            series_id=1,
            episode_id=30,
            event_type="grabbed",
            download_id="S1",
            imported_path=None,
            release_type=None,
        ),
    ]

    decision = analyzer.analyze(event, episodes, history)

    assert decision.episode_ids_to_unmonitor == frozenset({20, 21})
    assert decision.episode_file_ids_to_delete == frozenset({201, 202})
    assert decision.hashes_to_delete == frozenset({"S2A", "S2B"})
