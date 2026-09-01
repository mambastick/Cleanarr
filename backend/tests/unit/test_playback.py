from datetime import UTC, datetime

from cleanarr.domain import PlaybackObservation, PlaybackStatus, reduce_playback


def observation(
    user: str,
    *,
    played: bool = False,
    count: int = 0,
    item: str = "item",
    valid: bool = True,
) -> PlaybackObservation:
    return PlaybackObservation(
        user_id=user,
        item_id=item,
        played=played,
        play_count=count,
        last_played_at=datetime(2026, 1, 1, tzinfo=UTC) if played else None,
        valid=valid,
    )


def test_reducer_never_watched_requires_complete_nonempty_scope() -> None:
    aggregate = reduce_playback(
        expected_user_ids=("one", "two"),
        item_id="item",
        observations=(observation("one"), observation("two")),
        scope_complete=True,
    )
    assert (aggregate.status, aggregate.play_count, aggregate.watched_user_count) == (
        PlaybackStatus.NEVER_WATCHED,
        0,
        0,
    )


def test_reducer_watched_sums_counts_and_uses_latest_date() -> None:
    later = datetime(2026, 2, 1, tzinfo=UTC)
    aggregate = reduce_playback(
        expected_user_ids=("one", "two"),
        item_id="item",
        observations=(
            observation("one", played=True, count=2),
            PlaybackObservation("two", "item", True, 3, later),
        ),
        scope_complete=True,
    )
    assert aggregate.status is PlaybackStatus.WATCHED
    assert (aggregate.play_count, aggregate.watched_user_count, aggregate.last_played_at) == (5, 2, later)


def test_reducer_fails_closed_for_zero_users_missing_duplicate_contradiction_and_malformed() -> None:
    cases = (
        ((), (), True),
        (("one",), (), True),
        (("one",), (observation("one"), observation("one")), True),
        (("one",), (observation("one", played=False, count=1),), True),
        (("one",), (PlaybackObservation("one", "item", False, 0, datetime(2026, 1, 1, tzinfo=UTC)),), True),
        (("one",), (observation("one", played=True, count=-1),), True),
        (("one",), (observation("one", valid=False),), True),
        (("one",), (observation("one"),), False),
    )
    for users, observations, complete in cases:
        aggregate = reduce_playback(
            expected_user_ids=users, item_id="item", observations=observations, scope_complete=complete
        )
        assert aggregate.status is PlaybackStatus.UNKNOWN
        assert (aggregate.play_count, aggregate.watched_user_count, aggregate.last_played_at) == (None, None, None)
