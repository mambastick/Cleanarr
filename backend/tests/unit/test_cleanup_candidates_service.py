from __future__ import annotations

import asyncio

import pytest

from cleanarr.application.cleanup_candidates import CleanupCandidatesService
from cleanarr.domain import (
    CleanupMediaType,
    JellyfinCleanupItem,
    PlaybackObservation,
    RadarrHistoryRecord,
    RadarrMovie,
)
from cleanarr.domain.config import GeneralConfig


class Repository:
    def list_snapshots(self):  # type: ignore[no-untyped-def]
        return []


class Playback:
    def __init__(self, marker: str) -> None:
        self.marker = marker

    async def list_cleanup_items(self, **_: object):  # type: ignore[no-untyped-def]
        return (
            JellyfinCleanupItem(self.marker, self.marker, CleanupMediaType.MOVIE, None, None, None, tmdb_id=7),
        ), False

    async def list_playback_users(self, **_: object):  # type: ignore[no-untyped-def]
        return ("private-user",), False

    async def list_user_playback(self, *, user_id: str, item_ids: tuple[str, ...], **_: object):  # type: ignore[no-untyped-def]
        return tuple(PlaybackObservation(user_id, item_id, False, 0, None) for item_id in item_ids)


class Arr:
    def __init__(self, history: list[RadarrHistoryRecord] | None = None) -> None:
        self.history = history or []
        self.deletes = 0

    async def list_movies(self):  # type: ignore[no-untyped-def]
        return [RadarrMovie(1, "private path movie", "/private/path", 7, None)]

    async def list_movie_history(self, _: int):  # type: ignore[no-untyped-def]
        return self.history

    async def delete_movie(self, *args: object, **kwargs: object) -> None:
        self.deletes += 1


class Sonarr:
    def __init__(self) -> None:
        self.deletes = 0

    async def list_series(self):  # type: ignore[no-untyped-def]
        return []

    async def list_series_history(self, _: int):  # type: ignore[no-untyped-def]
        return []

    async def delete_series(self, *args: object, **kwargs: object) -> None:
        self.deletes += 1


def service(playback: Playback, arr: Arr | None = None, sonarr: Sonarr | None = None) -> CleanupCandidatesService:
    return CleanupCandidatesService(
        playback=playback,
        radarr=arr or Arr(),
        sonarr=sonarr or Sonarr(),
        downloads_repository=Repository(),  # type: ignore[arg-type]
    )


@pytest.mark.asyncio
async def test_request_local_sources_do_not_cross_mix_overlapping_reads() -> None:
    base = service(Playback("base"))
    first = base.with_sources(playback=Playback("first"), radarr=Arr(), sonarr=Sonarr())
    second = base.with_sources(playback=Playback("second"), radarr=Arr(), sonarr=Sonarr())
    results = await asyncio.gather(
        first.list_candidates(
            accept_language="en",
            jellyfin_configured=True,
            radarr_configured=True,
            sonarr_configured=False,
            config=GeneralConfig(),
        ),
        second.list_candidates(
            accept_language="ru",
            jellyfin_configured=True,
            radarr_configured=True,
            sonarr_configured=False,
            config=GeneralConfig(),
        ),
    )
    assert [result.candidates[0].item.item_id for result in results] == ["first", "second"]


@pytest.mark.asyncio
async def test_history_at_transport_cap_is_partial_and_unknown_but_999_is_not_truncated() -> None:
    record = RadarrHistoryRecord(1, 1, "event", None, None)
    client = service(Playback("one"), Arr([record] * 999))
    _, _, codes, truncated = await client._resolve_arr(  # noqa: SLF001
        (JellyfinCleanupItem("one", "one", CleanupMediaType.MOVIE, None, None, None, tmdb_id=7),), True, False
    )
    assert "arr_history_truncated" not in codes and not truncated
    capped = service(Playback("one"), Arr([record] * 1000))
    _, histories, codes, truncated = await capped._resolve_arr(  # noqa: SLF001
        (JellyfinCleanupItem("one", "one", CleanupMediaType.MOVIE, None, None, None, tmdb_id=7),), True, False
    )
    assert histories["one"] is None
    assert "arr_history_truncated" in codes and truncated


@pytest.mark.asyncio
async def test_candidate_read_does_not_invoke_mutation_ports() -> None:
    radarr, sonarr = Arr(), Sonarr()
    result = await service(Playback("one"), radarr, sonarr).list_candidates(
        accept_language="en",
        jellyfin_configured=True,
        radarr_configured=True,
        sonarr_configured=False,
        config=GeneralConfig(),
    )
    assert result.candidates and radarr.deletes == sonarr.deletes == 0


@pytest.mark.asyncio
async def test_unmapped_movie_gets_direct_jellyfin_link_only_after_complete_radarr_catalog() -> None:
    class EmptyArr(Arr):
        async def list_movies(self):  # type: ignore[no-untyped-def]
            return []

    complete = await service(Playback("one"), EmptyArr()).list_candidates(
        accept_language="en",
        jellyfin_configured=True,
        radarr_configured=True,
        sonarr_configured=False,
        config=GeneralConfig(),
    )
    assert complete.candidates[0].deletion_link is not None
    assert complete.candidates[0].deletion_link.jellyfin_only is True

    class BrokenArr(Arr):
        async def list_movies(self):  # type: ignore[no-untyped-def]
            raise RuntimeError("unavailable")

    unavailable = await service(Playback("one"), BrokenArr()).list_candidates(
        accept_language="en",
        jellyfin_configured=True,
        radarr_configured=True,
        sonarr_configured=False,
        config=GeneralConfig(),
    )
    assert unavailable.candidates[0].deletion_link is None
    assert "radarr_catalog_unavailable" in unavailable.failure_codes

    class NoProviderIdentity(Playback):
        async def list_cleanup_items(self, **_: object):  # type: ignore[no-untyped-def]
            return (JellyfinCleanupItem("one", "one", CleanupMediaType.MOVIE, None, None, None),), False

    unprovable = await service(NoProviderIdentity("one"), EmptyArr()).list_candidates(
        accept_language="en",
        jellyfin_configured=True,
        radarr_configured=True,
        sonarr_configured=False,
        config=GeneralConfig(),
    )
    assert unprovable.candidates[0].deletion_link is None


@pytest.mark.asyncio
async def test_cancelled_playback_read_propagates() -> None:
    class Cancelled(Playback):
        async def list_cleanup_items(self, **_: object):  # type: ignore[no-untyped-def]
            raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await service(Cancelled("x")).list_candidates(
            accept_language="en",
            jellyfin_configured=True,
            radarr_configured=False,
            sonarr_configured=False,
            config=GeneralConfig(),
        )


@pytest.mark.asyncio
async def test_playback_uses_chunks_of_at_most_fifty_items() -> None:
    class Many(Playback):
        def __init__(self) -> None:
            super().__init__("marker")
            self.chunks: list[int] = []

        async def list_cleanup_items(self, **_: object):  # type: ignore[no-untyped-def]
            return (
                tuple(
                    JellyfinCleanupItem(str(index), str(index), CleanupMediaType.MOVIE, None, None, None)
                    for index in range(51)
                ),
                False,
            )

        async def list_user_playback(self, *, user_id: str, item_ids: tuple[str, ...], **_: object):  # type: ignore[no-untyped-def]
            self.chunks.append(len(item_ids))
            return tuple(PlaybackObservation(user_id, item_id, False, 0, None) for item_id in item_ids)

    many = Many()
    result = await service(many).list_candidates(
        accept_language="en",
        jellyfin_configured=True,
        radarr_configured=False,
        sonarr_configured=False,
        config=GeneralConfig(),
    )
    assert len(result.candidates) == 51
    assert sorted(many.chunks) == [1, 50]
