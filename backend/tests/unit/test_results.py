"""Tests for action collection progress observation."""

from cleanarr.application.results import ActionCollector, observe_actions
from cleanarr.domain import ActionStatus, ItemType, MediaDeletionEvent, MediaFingerprint


def test_action_collector_notifies_scoped_observer() -> None:
    event = MediaDeletionEvent(
        notification_type="ItemDeleted",
        item_type=ItemType.MOVIE,
        item_id="movie-1",
        name="Movie",
        fingerprint=MediaFingerprint(tmdb_id=1),
    )
    observed_messages: list[str] = []

    with observe_actions(lambda action: observed_messages.append(action.message)):
        collector = ActionCollector(event)
        collector.add("radarr", "delete_movie", ActionStatus.DELETED, "Movie deleted.")

    collector.add("seerr", "delete_media", ActionStatus.DELETED, "Media deleted.")

    assert observed_messages == ["Movie deleted."]
