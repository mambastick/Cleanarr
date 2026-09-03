"""Focused tests for the v2 storage and library read contracts."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import pytest

from cleanarr.api.library_schemas import LibraryDetailResponse, LibraryItemResponse, LibraryItemsResponse
from cleanarr.api.storage import StorageResponse
from cleanarr.application.deletion_models import ManualDeleteRequest
from cleanarr.application.library import LibraryCursorError, LibraryService, _library_item
from cleanarr.application.manual_deletion import LibraryItemChangedError, ManualDeletionService, _resource_matches_item
from cleanarr.application.storage import (
    StorageRefreshThrottledError,
    StorageService,
    headline_status,
    rendered_volumes,
    storage_freshness,
    volume_freshness,
)
from cleanarr.domain import (
    ArtworkData,
    ItemType,
    JellyfinItem,
    LibraryDetail,
    LibraryMediaType,
    LibraryReadState,
    RadarrMovie,
    SonarrEpisode,
    SonarrEpisodeFile,
    SonarrSeries,
    StorageDiskSpace,
    StorageProfileListing,
    StorageRootFolder,
    StorageSnapshot,
    StorageVolume,
    decode_library_resource,
    encode_library_resource,
)
from cleanarr.domain.config import GeneralConfig, RadarrServiceConfig, RuntimeConfig, SonarrServiceConfig


def _config(
    *,
    radarr: list[RadarrServiceConfig] | None = None,
    sonarr: list[SonarrServiceConfig] | None = None,
    warning: float = 15.0,
    critical: float = 5.0,
) -> RuntimeConfig:
    return RuntimeConfig(
        general=GeneralConfig(
            storage_warning_free_percent=warning,
            storage_critical_free_percent=critical,
        ),
        radarr=radarr or [],
        sonarr=sonarr or [],
    )


def _radarr_profile(profile_id: str = "radarr-one", name: str = "Radarr") -> RadarrServiceConfig:
    return RadarrServiceConfig(id=profile_id, name=name, url="http://radarr/api/v3", api_key="key")


def _sonarr_profile(profile_id: str = "sonarr-one", name: str = "Sonarr") -> SonarrServiceConfig:
    return SonarrServiceConfig(id=profile_id, name=name, url="http://sonarr/api/v3", api_key="key")


class StorageFake:
    def __init__(self, listings: tuple[StorageProfileListing, ...], gate: asyncio.Event | None = None) -> None:
        self.listings = listings
        self.gate = gate
        self.calls = 0

    async def list_storage(self) -> tuple[StorageProfileListing, ...]:
        self.calls += 1
        if self.gate is not None:
            await self.gate.wait()
        return self.listings


def _listing(
    service: str,
    profile_id: str,
    *,
    roots: tuple[StorageRootFolder, ...],
    spaces: tuple[StorageDiskSpace, ...],
) -> StorageProfileListing:
    return StorageProfileListing(
        service_kind=service,  # type: ignore[arg-type]
        service_id=profile_id,
        service_name=profile_id,
        roots=roots,
        disk_spaces=spaces,
    )


@pytest.mark.asyncio
async def test_storage_exact_thresholds_keep_service_volumes_and_mark_duplicates() -> None:
    roots = tuple(
        StorageRootFolder(path=path, folder_id=index)
        for index, path in enumerate(("/data/healthy", "/data/warning", "/data/critical"))
    )
    spaces = (
        StorageDiskSpace(path="/data/healthy", free_bytes=15, total_bytes=100),
        StorageDiskSpace(path="/data/warning", free_bytes=5, total_bytes=100),
        StorageDiskSpace(path="/data/critical", free_bytes=4, total_bytes=100),
    )
    radarr = StorageFake((_listing("radarr", "radarr-one", roots=roots, spaces=spaces),))
    sonarr = StorageFake(
        (
            _listing(
                "sonarr",
                "sonarr-one",
                roots=(StorageRootFolder(path="/data/healthy", folder_id=99),),
                spaces=spaces,
            ),
        )
    )
    service = StorageService(
        config=lambda: _config(radarr=[_radarr_profile()], sonarr=[_sonarr_profile()]),
        radarr=lambda: radarr,
        sonarr=lambda: sonarr,
    )

    snapshot = await service.get()

    assert [volume.status for volume in snapshot.volumes[:3]] == ["healthy", "warning", "critical"]
    assert len(snapshot.volumes) == 4
    assert all(volume.possible_duplicate for volume in snapshot.volumes if volume.root_folder_id in {0, 99})
    assert {volume.service_kind for volume in snapshot.volumes} == {"radarr", "sonarr"}
    assert headline_status(snapshot) == "critical"
    assert all(volume.display_label and "/data" not in volume.display_label for volume in snapshot.volumes)


@pytest.mark.asyncio
async def test_storage_matching_is_segment_safe_and_missing_data_is_unknown() -> None:
    roots = (
        StorageRootFolder(path="/data/movie", folder_id=1),
        StorageRootFolder(path="/other/missing", folder_id=2),
    )
    spaces = (
        StorageDiskSpace(path="/data/movies", free_bytes=1, total_bytes=100),
        StorageDiskSpace(path="/data", free_bytes=15, total_bytes=100),
    )
    radarr = StorageFake((_listing("radarr", "radarr-one", roots=roots, spaces=spaces),))
    service = StorageService(
        config=lambda: _config(radarr=[_radarr_profile()]),
        radarr=lambda: radarr,
        sonarr=lambda: StorageFake(()),
    )

    snapshot = await service.get()

    assert snapshot.volumes[0].status == "healthy"
    assert snapshot.volumes[0].free_percent == 15.0
    assert snapshot.volumes[0].error_code is None
    assert snapshot.volumes[1].status == "unknown"
    assert snapshot.volumes[1].error_code == "disk_space_missing"
    assert snapshot.partial is True


@pytest.mark.asyncio
async def test_storage_refresh_coalesces_and_manual_refresh_is_throttled() -> None:
    gate = asyncio.Event()
    listing = _listing(
        "radarr",
        "radarr-one",
        roots=(StorageRootFolder(path="/data", folder_id=1),),
        spaces=(StorageDiskSpace(path="/data", free_bytes=20, total_bytes=100),),
    )
    radarr = StorageFake((listing,), gate)
    sonarr = StorageFake((), gate)
    service = StorageService(
        config=lambda: _config(radarr=[_radarr_profile()]),
        radarr=lambda: radarr,
        sonarr=lambda: sonarr,
    )

    first = asyncio.create_task(service.refresh())
    for _ in range(20):
        if radarr.calls:
            break
        await asyncio.sleep(0)
    second = asyncio.create_task(service.refresh())
    gate.set()
    await asyncio.gather(first, second)

    assert radarr.calls == 1
    assert sonarr.calls == 1
    with pytest.raises(StorageRefreshThrottledError):
        await service.refresh()


@pytest.mark.asyncio
async def test_manual_refresh_joining_automatic_collection_still_starts_throttle_window() -> None:
    gate = asyncio.Event()
    listing = _listing(
        "radarr",
        "radarr-one",
        roots=(StorageRootFolder(path="/data", folder_id=1),),
        spaces=(StorageDiskSpace(path="/data", free_bytes=20, total_bytes=100),),
    )
    radarr = StorageFake((listing,), gate)
    sonarr = StorageFake((), gate)
    service = StorageService(
        config=lambda: _config(radarr=[_radarr_profile()]),
        radarr=lambda: radarr,
        sonarr=lambda: sonarr,
    )

    automatic = asyncio.create_task(service.get())
    for _ in range(20):
        if radarr.calls:
            break
        await asyncio.sleep(0)
    first_manual = asyncio.create_task(service.refresh())
    second_manual = asyncio.create_task(service.refresh())
    gate.set()
    await asyncio.gather(automatic, first_manual, second_manual)

    assert radarr.calls == 1
    with pytest.raises(StorageRefreshThrottledError):
        await service.refresh()


@pytest.mark.asyncio
async def test_storage_cache_invalidates_for_endpoint_or_credential_rotation() -> None:
    clock = [0.0]
    config = _config(radarr=[_radarr_profile()])
    radarr = StorageFake(
        (
            _listing(
                "radarr",
                "radarr-one",
                roots=(StorageRootFolder(path="/data", folder_id=1),),
                spaces=(StorageDiskSpace(path="/data", free_bytes=20, total_bytes=100),),
            ),
        )
    )
    service = StorageService(
        config=lambda: config,
        radarr=lambda: radarr,
        sonarr=lambda: StorageFake(()),
        now=lambda: clock[0],
    )

    await service.get()
    config = _config(
        radarr=[
            RadarrServiceConfig(
                id="radarr-one",
                name="Radarr",
                url="http://new-radarr/api/v3",
                api_key="rotated-key",
            )
        ]
    )
    await service.get()

    assert radarr.calls == 2


@pytest.mark.asyncio
async def test_storage_missing_routed_profile_is_partial_unknown_and_dot_segments_do_not_prefix_match() -> None:
    radarr = StorageFake(
        (
            _listing(
                "radarr",
                "radarr-one",
                roots=(StorageRootFolder(path="/data/../private/movie", folder_id=1),),
                spaces=(StorageDiskSpace(path="/data", free_bytes=50, total_bytes=100),),
            ),
        )
    )
    service = StorageService(
        config=lambda: _config(radarr=[_radarr_profile(), _radarr_profile("radarr-two")]),
        radarr=lambda: radarr,
        sonarr=lambda: StorageFake(()),
    )

    snapshot = await service.get()

    assert snapshot.partial is True
    assert "profile_unavailable" in snapshot.error_codes
    assert snapshot.volumes[0].status == "unknown"
    assert snapshot.volumes[0].error_code == "disk_space_missing"
    assert headline_status(snapshot) == "unknown"


@pytest.mark.asyncio
async def test_failed_profile_refresh_retains_numbers_as_stale_and_keeps_fresh_critical_headline() -> None:
    clock = [0.0]
    radarr = StorageFake(
        (
            _listing(
                "radarr",
                "radarr-one",
                roots=(StorageRootFolder(path="/movies", folder_id=1),),
                spaces=(StorageDiskSpace(path="/movies", free_bytes=4, total_bytes=100),),
            ),
        )
    )
    sonarr = StorageFake(
        (
            _listing(
                "sonarr",
                "sonarr-one",
                roots=(StorageRootFolder(path="/shows", folder_id=2),),
                spaces=(StorageDiskSpace(path="/shows", free_bytes=40, total_bytes=100),),
            ),
        )
    )
    service = StorageService(
        config=lambda: _config(radarr=[_radarr_profile()], sonarr=[_sonarr_profile()]),
        radarr=lambda: radarr,
        sonarr=lambda: sonarr,
        now=lambda: clock[0],
    )
    first = await service.get()
    old_sonarr = next(volume for volume in first.volumes if volume.service_kind == "sonarr")

    sonarr.listings = (
        StorageProfileListing(
            service_kind="sonarr",
            service_id="sonarr-one",
            service_name="Sonarr",
            roots=(),
            disk_spaces=(),
            error_code="profile_unavailable",
        ),
    )
    clock[0] = 11.0
    refreshed = await service.refresh()

    retained = next(volume for volume in refreshed.volumes if volume.service_kind == "sonarr")
    critical = next(volume for volume in refreshed.volumes if volume.service_kind == "radarr")
    assert refreshed.partial is True
    assert retained.free_bytes == old_sonarr.free_bytes == 40
    assert retained.collected_at == old_sonarr.collected_at
    assert retained.status == "unknown"
    assert retained.error_code == "profile_unavailable"
    assert volume_freshness(retained) == "stale"
    assert volume_freshness(critical) == "fresh"
    assert storage_freshness(refreshed) == "stale"
    assert headline_status(refreshed) == "critical"

    response = StorageResponse.from_snapshot(refreshed)
    assert {volume.service: volume.freshness for volume in response.volumes} == {
        "radarr": "fresh",
        "sonarr": "stale",
    }

    healthy_snapshot = replace(
        refreshed,
        volumes=tuple(
            replace(volume, status="healthy", free_bytes=40, free_percent=40.0)
            if volume.service_kind == "radarr"
            else volume
            for volume in refreshed.volumes
        ),
    )
    assert headline_status(healthy_snapshot) == "unknown"


def test_storage_stale_observations_cannot_drive_a_healthy_or_warning_headline() -> None:
    collected_at = datetime.now(UTC) - timedelta(seconds=121)
    volume = StorageVolume(
        volume_id="v1_test",
        service_kind="radarr",
        profile_id="radarr-one",
        profile_name="Radarr",
        root_folder_id=1,
        free_bytes=1,
        total_bytes=100,
        free_percent=1.0,
        status="critical",
        collected_at=collected_at,
        display_label="Radarr · root 1",
    )
    snapshot = StorageSnapshot((volume,), collected_at, partial=False)

    rendered = rendered_volumes(snapshot)

    assert storage_freshness(snapshot) == "stale"
    assert rendered[0].status == "unknown"
    assert rendered[0].error_code == "stale_observation"
    assert headline_status(snapshot) == "unknown"
    fresh_volume = StorageVolume(
        volume_id=volume.volume_id,
        service_kind=volume.service_kind,
        profile_id=volume.profile_id,
        profile_name=volume.profile_name,
        root_folder_id=volume.root_folder_id,
        free_bytes=volume.free_bytes,
        total_bytes=volume.total_bytes,
        free_percent=volume.free_percent,
        status=volume.status,
        collected_at=datetime.now(UTC),
        display_label=volume.display_label,
    )
    assert headline_status(StorageSnapshot((fresh_volume,), fresh_volume.collected_at, partial=True)) == "critical"


def test_storage_without_a_sample_is_explicitly_unknown() -> None:
    snapshot = StorageSnapshot((), datetime.now(UTC), partial=True, error_codes=("storage_unavailable",))

    assert storage_freshness(snapshot) == "unknown"
    assert headline_status(snapshot) == "unknown"


class LibraryRadarrFake:
    def __init__(self, movies: list[RadarrMovie]) -> None:
        self.movies = movies
        self.catalog_calls = 0
        self.history_calls = 0

    async def list_movies(self) -> list[RadarrMovie]:
        self.catalog_calls += 1
        return list(self.movies)

    async def list_movie_history(self, movie_id: int) -> list[object]:
        self.history_calls += 1
        return []


class LibraryJellyfinFake:
    def __init__(self, items: list[JellyfinItem], artwork: ArtworkData | None = None) -> None:
        self.items = items
        self.artwork_value = artwork
        self.catalog_calls = 0
        self.artwork_calls = 0

    async def list_items(self, *, include_types: list[str], accept_language: str | None = None) -> list[JellyfinItem]:
        self.catalog_calls += 1
        return list(self.items)

    async def get_primary_artwork(self, item_id: str) -> ArtworkData | None:
        self.artwork_calls += 1
        return self.artwork_value


class LibrarySonarrFake:
    def __init__(self, series: list[SonarrSeries]) -> None:
        self.series = series
        self.catalog_calls = 0
        self.episode_calls = 0
        self.file_calls = 0

    async def list_series(self) -> list[SonarrSeries]:
        self.catalog_calls += 1
        return list(self.series)

    async def list_episodes(self, series_id: int) -> list[SonarrEpisode]:
        self.episode_calls += 1
        return [SonarrEpisode(1, series_id, 1, 1, 7, True, True)]

    async def list_episode_files(self, series_id: int) -> list[SonarrEpisodeFile]:
        self.file_calls += 1
        return [SonarrEpisodeFile(7, "/private/show.mkv", "show.mkv", 1, 100)]


def _movie(raw_id: int, title: str, *, added: datetime, size: int, tmdb_id: int) -> RadarrMovie:
    # Routed IDs are the negative triangular values produced by MultiRadarrClient.
    paired = raw_id * (raw_id + 1) // 2 + raw_id
    return RadarrMovie(
        id=-(paired + 1),
        title=title,
        path=f"/private/{title.casefold()}",
        tmdb_id=tmdb_id,
        imdb_id=None,
        size_on_disk=size,
        has_file=True,
        service_id="radarr-one",
        added_at=added,
        year=2020 + raw_id,
    )


@pytest.mark.asyncio
async def test_library_list_is_cached_sorted_revision_bound_and_does_not_read_histories() -> None:
    movies = [
        _movie(1, "Zulu", added=datetime(2025, 1, 1, tzinfo=UTC), size=20, tmdb_id=2),
        _movie(2, "Alpha", added=datetime(2025, 2, 1, tzinfo=UTC), size=10, tmdb_id=3),
    ]
    radarr = LibraryRadarrFake(movies)
    jellyfin = LibraryJellyfinFake(
        [
            JellyfinItem(id="jf-zulu", name="Zulu display", type="Movie", tmdb_id=2),
            JellyfinItem(id="jf-alpha", name="Alpha display", type="Movie", tmdb_id=3),
        ]
    )
    service = LibraryService(
        config=lambda: _config(radarr=[_radarr_profile()]),
        radarr=lambda: radarr,
        sonarr=lambda: object(),
        jellyfin=lambda: jellyfin,
    )

    first = await service.list_items(
        media_type=LibraryMediaType.MOVIE,
        sort="title",
        direction="asc",
        limit=1,
    )
    cached = await service.list_items(media_type=LibraryMediaType.MOVIE, sort="title", direction="asc", limit=1)
    second = await service.list_items(
        media_type=LibraryMediaType.MOVIE,
        sort="title",
        direction="asc",
        limit=1,
        cursor=first.next_cursor,
    )

    assert first.items[0].title == "Alpha"
    assert second.items[0].title == "Zulu"
    assert cached.revision == first.revision
    assert radarr.catalog_calls == 1
    assert jellyfin.catalog_calls == 1
    assert radarr.history_calls == 0
    assert first.items[0].year == 2022
    assert first.items[0].episode_count is None
    assert first.items[0].artwork_status == "available"

    searched = await service.list_items(
        media_type=LibraryMediaType.MOVIE,
        query=" zULu ",
        sort="size",
        direction="desc",
    )
    assert [item.title for item in searched.items] == ["Zulu"]
    assert searched.revision == first.revision
    assert radarr.catalog_calls == 1
    assert jellyfin.catalog_calls == 1

    refreshed = await service.list_items(
        media_type=LibraryMediaType.MOVIE,
        sort="title",
        direction="asc",
        limit=1,
        refresh=True,
    )
    assert refreshed.revision == first.revision

    radarr.movies.append(_movie(3, "Beta", added=datetime(2025, 3, 1, tzinfo=UTC), size=30, tmdb_id=4))
    changed_catalog = await service.list_items(
        media_type=LibraryMediaType.MOVIE,
        sort="title",
        direction="asc",
        limit=1,
        refresh=True,
    )
    assert changed_catalog.revision != first.revision
    with pytest.raises(LibraryCursorError) as changed:
        await service.list_items(
            media_type=LibraryMediaType.MOVIE,
            sort="title",
            direction="asc",
            limit=1,
            cursor=first.next_cursor,
        )
    assert changed.value.code == "catalog_changed"
    with pytest.raises(LibraryCursorError) as malformed:
        await service.list_items(media_type=LibraryMediaType.MOVIE, cursor="c1_!")
    assert malformed.value.code == "invalid_cursor"


@pytest.mark.asyncio
async def test_library_duplicate_jellyfin_provider_ids_are_partial_and_never_bound() -> None:
    movie = _movie(1, "Ambiguous", added=datetime(2025, 1, 1, tzinfo=UTC), size=20, tmdb_id=44)
    service = LibraryService(
        config=lambda: _config(radarr=[_radarr_profile()]),
        radarr=lambda: LibraryRadarrFake([movie]),
        sonarr=lambda: object(),
        jellyfin=lambda: LibraryJellyfinFake(
            [
                JellyfinItem(id="wrong-first", name="Wrong", type="Movie", tmdb_id=44),
                JellyfinItem(id="correct-second", name="Correct", type="Movie", tmdb_id=44),
            ]
        ),
    )

    page = await service.list_items(media_type=LibraryMediaType.MOVIE)

    assert page.state is LibraryReadState.PARTIAL
    assert page.error_code == "ambiguous_jellyfin_match"
    assert page.items[0].jellyfin_item_id is None
    assert page.items[0].artwork_status == "missing"


@pytest.mark.asyncio
async def test_library_duplicate_remote_id_with_conflicting_providers_is_partial_and_never_bound() -> None:
    movie = _movie(1, "Ambiguous", added=datetime(2025, 1, 1, tzinfo=UTC), size=20, tmdb_id=44)
    service = LibraryService(
        config=lambda: _config(radarr=[_radarr_profile()]),
        radarr=lambda: LibraryRadarrFake([movie]),
        sonarr=lambda: object(),
        jellyfin=lambda: LibraryJellyfinFake(
            [
                JellyfinItem(id="same-jf-id", name="Expected", type="Movie", tmdb_id=44),
                JellyfinItem(id=" SAME-JF-ID ", name="Conflicting", type="Movie", tmdb_id=55),
            ]
        ),
    )

    page = await service.list_items(media_type=LibraryMediaType.MOVIE)

    assert page.state is LibraryReadState.PARTIAL
    assert page.error_code == "ambiguous_jellyfin_match"
    assert page.items[0].jellyfin_item_id is None
    assert page.items[0].artwork_status == "missing"


@pytest.mark.asyncio
async def test_library_conflicting_jellyfin_provider_ids_never_bind() -> None:
    movie = replace(
        _movie(1, "Conflicting", added=datetime(2025, 1, 1, tzinfo=UTC), size=20, tmdb_id=44),
        imdb_id="tt0044",
    )
    service = LibraryService(
        config=lambda: _config(radarr=[_radarr_profile()]),
        radarr=lambda: LibraryRadarrFake([movie]),
        sonarr=lambda: object(),
        jellyfin=lambda: LibraryJellyfinFake(
            [JellyfinItem(id="jf-conflict", name="Wrong", type="Movie", tmdb_id=44, imdb_id="tt9999")]
        ),
    )

    page = await service.list_items(media_type=LibraryMediaType.MOVIE)

    assert page.state is LibraryReadState.COMPLETE
    assert page.error_code is None
    assert page.items[0].jellyfin_item_id is None
    assert page.items[0].artwork_status == "missing"


@pytest.mark.asyncio
async def test_library_shared_jellyfin_item_across_arr_profiles_is_partial_and_unbound() -> None:
    first = replace(
        _movie(1, "First owner", added=datetime(2025, 1, 1, tzinfo=UTC), size=20, tmdb_id=44),
        service_id="radarr-one",
    )
    second = replace(first, id=-5, title="Second owner", path="/private/second", service_id="radarr-two")
    service = LibraryService(
        config=lambda: _config(radarr=[_radarr_profile(), _radarr_profile("radarr-two")]),
        radarr=lambda: LibraryRadarrFake([first, second]),
        sonarr=lambda: object(),
        jellyfin=lambda: LibraryJellyfinFake([JellyfinItem(id="jf-shared", name="Shared", type="Movie", tmdb_id=44)]),
    )

    page = await service.list_items(media_type=LibraryMediaType.MOVIE)

    assert page.state is LibraryReadState.PARTIAL
    assert page.error_code == "ambiguous_jellyfin_match"
    assert len(page.items) == 2
    assert all(item.jellyfin_item_id is None for item in page.items)
    assert all(item.artwork_status == "missing" for item in page.items)


@pytest.mark.asyncio
async def test_library_malformed_jellyfin_boundary_is_partial_and_unknown() -> None:
    movie = _movie(1, "Unknown", added=datetime(2025, 1, 1, tzinfo=UTC), size=20, tmdb_id=44)
    jellyfin = LibraryJellyfinFake([])
    jellyfin.items = cast(Any, [object()])
    service = LibraryService(
        config=lambda: _config(radarr=[_radarr_profile()]),
        radarr=lambda: LibraryRadarrFake([movie]),
        sonarr=lambda: object(),
        jellyfin=lambda: jellyfin,
    )

    page = await service.list_items(media_type=LibraryMediaType.MOVIE)

    assert page.state is LibraryReadState.PARTIAL
    assert page.error_code == "jellyfin_unavailable"
    assert page.items[0].artwork_status == "unknown"


@pytest.mark.asyncio
async def test_library_movie_detail_and_artwork_are_bounded_and_privacy_safe() -> None:
    movie = _movie(1, "Artwork Movie", added=datetime(2025, 1, 1, tzinfo=UTC), size=20, tmdb_id=4)
    radarr = LibraryRadarrFake([movie])
    jellyfin = LibraryJellyfinFake(
        [JellyfinItem(id="jf-art", name="Artwork Movie", type="Movie", tmdb_id=4)],
        artwork=ArtworkData(content=b"png", media_type="image/png"),
    )
    service = LibraryService(
        config=lambda: _config(radarr=[_radarr_profile()]),
        radarr=lambda: radarr,
        sonarr=lambda: object(),
        jellyfin=lambda: jellyfin,
    )

    page = await service.list_items(media_type=LibraryMediaType.MOVIE)
    detail = await service.get_item(page.items[0].resource_id)
    artwork = await service.artwork(page.items[0].resource_id)

    assert detail.state is LibraryReadState.COMPLETE
    assert detail.item.resource_id.startswith("r1_")
    assert "/private/" not in repr(detail)
    assert artwork == ArtworkData(content=b"png", media_type="image/png")
    assert jellyfin.artwork_calls == 1


@pytest.mark.asyncio
async def test_library_series_detail_fetches_one_bounded_episode_file_pair_and_keeps_unknown_safety_facts() -> None:
    paired = 1 * 2 // 2 + 1
    series = SonarrSeries(
        id=-(paired + 1),
        title="Bounded Show",
        path="/private/show",
        tvdb_id=44,
        tmdb_id=None,
        imdb_id=None,
        service_id="sonarr-one",
        size_on_disk=100,
        has_file=True,
        year=2024,
        episode_count=10,
        episode_file_count=1,
    )
    sonarr = LibrarySonarrFake([series])
    jellyfin = LibraryJellyfinFake([JellyfinItem(id="jf-show", name="Bounded Show", type="Series", tvdb_id=44)])
    service = LibraryService(
        config=lambda: _config(sonarr=[_sonarr_profile()]),
        radarr=lambda: object(),
        sonarr=lambda: sonarr,
        jellyfin=lambda: jellyfin,
    )

    page = await service.list_items(media_type=LibraryMediaType.SERIES)
    detail = await service.get_item(page.items[0].resource_id)

    assert detail.state is LibraryReadState.COMPLETE
    assert len(detail.episodes) == 1
    assert len(detail.files) == 1
    assert sonarr.catalog_calls == 1
    assert sonarr.episode_calls == 1
    assert sonarr.file_calls == 1
    assert detail.item.playback_status == "unknown"
    assert detail.item.playback_reason == "playback_not_loaded"
    assert detail.item.seeding_state == "unknown"
    assert detail.item.seeding_reason == "seeding_not_loaded"


def test_library_api_schema_is_flat_and_preserves_unknown_detail_facts() -> None:
    item = _movie(1, "Schema Movie", added=datetime(2025, 1, 1, tzinfo=UTC), size=20, tmdb_id=4)
    library_item = _library_item(
        item,
        media_type=LibraryMediaType.MOVIE,
        profiles={"radarr-one": _radarr_profile()},
        profile_count=1,
        jellyfin_items=(),
    )
    assert library_item is not None
    library_item = replace(library_item, artwork_status="missing")
    domain_item = LibraryItemResponse.from_domain(
        # Use the service projection so this assertion covers the same fields
        # that the authenticated list route serializes.
        item=library_item,
        catalog_revision="revision-1",
    )
    payload = domain_item.model_dump()

    assert {
        "resource_id",
        "media_type",
        "display_name",
        "title",
        "year",
        "size",
        "has_file",
        "counts",
        "added_at",
        "artwork",
        "delete_target",
        "fetched_at",
        "catalog_revision",
    } <= payload.keys()
    assert payload["size"] == 20
    assert payload["artwork"]["status"] == "missing"
    assert "/private" not in repr(payload)
    assert "profile_id" not in payload
    assert "raw_id" not in payload

    detail_domain = LibraryDetail(
        item=replace(
            library_item,
            playback_status="unknown",
            playback_reason="playback_users_unavailable",
            seeding_reason="arr_history_unavailable",
        ),
        state=LibraryReadState.PARTIAL,
        revision="revision-1",
        error_code="detail_enrichment_unavailable",
    )
    detail_payload = LibraryDetailResponse.from_domain(detail_domain).model_dump()
    assert detail_payload["playback"]["watched"] == "unknown"
    assert detail_payload["playback"]["freshness"] == "unknown"
    assert detail_payload["seeding"]["readiness"] == "unknown"
    assert detail_payload["safety"] == {"status": "unknown", "reason": "safety_preflight_required"}
    assert "detail_enrichment_unavailable" in detail_payload["unknown_reasons"]

    page = LibraryItemsResponse(
        items=[domain_item],
        next_cursor=None,
        source_status="partial",
        source_failures=[{"source": "jellyfin", "code": "jellyfin_unavailable"}],
        catalog_revision="revision-1",
    )
    assert page.model_dump()["source_failures"][0]["source"] == "jellyfin"


def test_library_resource_id_rejects_legacy_route_after_profile_reorder() -> None:
    resource_id = encode_library_resource(LibraryMediaType.MOVIE, "radarr-two", 1)
    resource = decode_library_resource(resource_id)
    # -3 is the routed ID for raw movie 1 on target index 0.  If the
    # profiles were reordered after preview, it must not be accepted as the
    # stable resource that belonged to target index 1.
    movie = RadarrMovie(
        id=-3,
        title="Reordered Movie",
        path="/private/movie",
        tmdb_id=1,
        imdb_id=None,
        service_id="radarr-two",
    )

    assert not _resource_matches_item(
        movie,
        resource,
        [_radarr_profile("radarr-one"), _radarr_profile("radarr-two")],
        profile_count=2,
    )


@pytest.mark.asyncio
async def test_manual_deletion_resource_id_matches_profile_and_raw_arr_id_before_preflight() -> None:
    movie = _movie(1, "Stable Movie", added=datetime(2025, 1, 1, tzinfo=UTC), size=20, tmdb_id=4)
    radarr = LibraryRadarrFake([movie])
    service = ManualDeletionService(
        radarr=lambda: cast(Any, radarr),
        sonarr=lambda: cast(Any, object()),
        jellyfin=lambda: cast(Any, object()),
        strategy_factory=lambda: cast(Any, object()),
        is_dry_run=lambda: True,
        activity_recorder=cast(Any, object()),
        config=lambda: _config(radarr=[_radarr_profile()]),
    )
    resource_id = encode_library_resource(LibraryMediaType.MOVIE, "radarr-one", 1)

    event = await service.resolve(
        ManualDeleteRequest(
            item_type=ItemType.MOVIE,
            radarr_movie_id=movie.id,
            library_resource_id=resource_id,
        )
    )
    assert event.name == "Stable Movie"

    # Legacy clients remain compatible when they omit the additive identity.
    legacy_event = await service.resolve(ManualDeleteRequest(item_type=ItemType.MOVIE, radarr_movie_id=movie.id))
    assert legacy_event.name == "Stable Movie"

    with pytest.raises(LibraryItemChangedError) as changed_profile:
        await service.resolve(
            ManualDeleteRequest(
                item_type=ItemType.MOVIE,
                radarr_movie_id=movie.id,
                library_resource_id=encode_library_resource(LibraryMediaType.MOVIE, "radarr-other", 1),
            )
        )
    assert changed_profile.value.code == "library_item_changed"

    with pytest.raises(LibraryItemChangedError):
        await service.resolve(
            ManualDeleteRequest(
                item_type=ItemType.MOVIE,
                radarr_movie_id=movie.id,
                library_resource_id=encode_library_resource(LibraryMediaType.MOVIE, "radarr-one", 2),
            )
        )


@pytest.mark.asyncio
async def test_manual_deletion_binds_caller_jellyfin_id_to_the_stable_arr_resource() -> None:
    movie = _movie(1, "Bound Movie", added=datetime(2025, 1, 1, tzinfo=UTC), size=20, tmdb_id=55)
    radarr = LibraryRadarrFake([movie])
    jellyfin = LibraryJellyfinFake([JellyfinItem(id="jf-bound", name="Bound Movie", type="Movie", tmdb_id=55)])
    service = ManualDeletionService(
        radarr=lambda: cast(Any, radarr),
        sonarr=lambda: cast(Any, object()),
        jellyfin=lambda: cast(Any, jellyfin),
        strategy_factory=lambda: cast(Any, object()),
        is_dry_run=lambda: True,
        activity_recorder=cast(Any, object()),
        config=lambda: _config(radarr=[_radarr_profile()]),
    )
    resource_id = encode_library_resource(LibraryMediaType.MOVIE, "radarr-one", 1)

    verified = await service.resolve(
        ManualDeleteRequest(
            item_type=ItemType.MOVIE,
            radarr_movie_id=movie.id,
            jellyfin_item_id="jf-bound",
            library_resource_id=resource_id,
        )
    )
    assert verified.name == "Bound Movie"

    with pytest.raises(LibraryItemChangedError) as unrelated:
        await service.resolve(
            ManualDeleteRequest(
                item_type=ItemType.MOVIE,
                radarr_movie_id=movie.id,
                jellyfin_item_id="jf-unrelated",
                library_resource_id=resource_id,
            )
        )
    assert unrelated.value.code == "library_item_changed"

    jellyfin.items.append(JellyfinItem(id="jf-duplicate", name="Duplicate", type="Movie", tmdb_id=55))
    with pytest.raises(LibraryItemChangedError):
        await service.resolve(
            ManualDeleteRequest(
                item_type=ItemType.MOVIE,
                radarr_movie_id=movie.id,
                jellyfin_item_id="jf-bound",
                library_resource_id=resource_id,
            )
        )


@pytest.mark.asyncio
async def test_manual_deletion_rejects_malformed_jellyfin_boundary_during_binding() -> None:
    movie = _movie(1, "Bound Movie", added=datetime(2025, 1, 1, tzinfo=UTC), size=20, tmdb_id=55)
    radarr = LibraryRadarrFake([movie])
    jellyfin = LibraryJellyfinFake([JellyfinItem(id="jf-bound", name="Bound Movie", type="Movie", tmdb_id=55)])
    jellyfin.items = cast(Any, [*jellyfin.items, object()])
    service = ManualDeletionService(
        radarr=lambda: cast(Any, radarr),
        sonarr=lambda: cast(Any, object()),
        jellyfin=lambda: cast(Any, jellyfin),
        strategy_factory=lambda: cast(Any, object()),
        is_dry_run=lambda: True,
        activity_recorder=cast(Any, object()),
        config=lambda: _config(radarr=[_radarr_profile()]),
    )

    with pytest.raises(LibraryItemChangedError) as changed:
        await service.resolve(
            ManualDeleteRequest(
                item_type=ItemType.MOVIE,
                radarr_movie_id=movie.id,
                jellyfin_item_id="jf-bound",
                library_resource_id=encode_library_resource(LibraryMediaType.MOVIE, "radarr-one", 1),
            )
        )
    assert changed.value.code == "library_item_changed"


@pytest.mark.asyncio
async def test_manual_deletion_rejects_duplicate_remote_id_with_conflicting_providers() -> None:
    movie = _movie(1, "Bound Movie", added=datetime(2025, 1, 1, tzinfo=UTC), size=20, tmdb_id=55)
    radarr = LibraryRadarrFake([movie])
    jellyfin = LibraryJellyfinFake(
        [
            JellyfinItem(id="same-jf-id", name="Expected", type="Movie", tmdb_id=55),
            JellyfinItem(id=" SAME-JF-ID ", name="Conflicting", type="Movie", tmdb_id=99),
        ]
    )
    service = ManualDeletionService(
        radarr=lambda: cast(Any, radarr),
        sonarr=lambda: cast(Any, object()),
        jellyfin=lambda: cast(Any, jellyfin),
        strategy_factory=lambda: cast(Any, object()),
        is_dry_run=lambda: True,
        activity_recorder=cast(Any, object()),
        config=lambda: _config(radarr=[_radarr_profile()]),
    )

    with pytest.raises(LibraryItemChangedError):
        await service.resolve(
            ManualDeleteRequest(
                item_type=ItemType.MOVIE,
                radarr_movie_id=movie.id,
                jellyfin_item_id="same-jf-id",
                library_resource_id=encode_library_resource(LibraryMediaType.MOVIE, "radarr-one", 1),
            )
        )


@pytest.mark.asyncio
async def test_manual_deletion_rejects_one_jellyfin_item_owned_by_multiple_arr_resources() -> None:
    first = replace(
        _movie(1, "First owner", added=datetime(2025, 1, 1, tzinfo=UTC), size=20, tmdb_id=55),
        service_id="radarr-one",
    )
    second = replace(first, id=-5, title="Second owner", path="/private/second", service_id="radarr-two")
    radarr = LibraryRadarrFake([first, second])
    jellyfin = LibraryJellyfinFake([JellyfinItem(id="jf-shared", name="Shared", type="Movie", tmdb_id=55)])
    service = ManualDeletionService(
        radarr=lambda: cast(Any, radarr),
        sonarr=lambda: cast(Any, object()),
        jellyfin=lambda: cast(Any, jellyfin),
        strategy_factory=lambda: cast(Any, object()),
        is_dry_run=lambda: True,
        activity_recorder=cast(Any, object()),
        config=lambda: _config(radarr=[_radarr_profile(), _radarr_profile("radarr-two")]),
    )

    with pytest.raises(LibraryItemChangedError):
        await service.resolve(
            ManualDeleteRequest(
                item_type=ItemType.MOVIE,
                radarr_movie_id=first.id,
                jellyfin_item_id="jf-shared",
                library_resource_id=encode_library_resource(LibraryMediaType.MOVIE, "radarr-one", 1),
            )
        )
