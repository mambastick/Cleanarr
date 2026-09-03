"""Multi-instance routers for Arr services."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, replace
from math import isqrt
from typing import Protocol

from cleanarr.application.ports import RadarrClientPort, SonarrClientPort
from cleanarr.domain import (
    RadarrHistoryRecord,
    RadarrMovie,
    SonarrEpisode,
    SonarrEpisodeFile,
    SonarrHistoryRecord,
    SonarrSeries,
    StorageDiskSpace,
    StorageProfileListing,
    StorageRootFolder,
)


class ManagedRadarrClientPort(RadarrClientPort, Protocol):
    """Radarr operations plus runtime lifecycle methods."""

    async def close(self) -> None: ...

    async def ping(self) -> None: ...

    async def get_version(self) -> str: ...

    async def list_root_folders(self) -> Sequence[StorageRootFolder]: ...

    async def list_disk_space(self) -> Sequence[StorageDiskSpace]: ...


class ManagedSonarrClientPort(SonarrClientPort, Protocol):
    """Sonarr operations plus runtime lifecycle methods."""

    async def close(self) -> None: ...

    async def ping(self) -> None: ...

    async def get_version(self) -> str: ...

    async def list_root_folders(self) -> Sequence[StorageRootFolder]: ...

    async def list_disk_space(self) -> Sequence[StorageDiskSpace]: ...


@dataclass(frozen=True)
class RadarrTarget:
    id: str
    name: str
    client: ManagedRadarrClientPort


@dataclass(frozen=True)
class SonarrTarget:
    id: str
    name: str
    client: ManagedSonarrClientPort


class MultiRadarrClient:
    """Aggregate Radarr catalogs while preserving the owning instance."""

    def __init__(self, targets: Sequence[RadarrTarget]) -> None:
        self._targets = tuple(targets)

    async def close(self) -> None:
        await asyncio.gather(*(target.client.close() for target in self._targets))

    async def ping(self) -> None:
        await asyncio.gather(*(target.client.ping() for target in self._targets))

    async def get_version(self) -> str:
        versions = await asyncio.gather(*(target.client.get_version() for target in self._targets))
        return ", ".join(sorted(set(versions)))

    async def list_movies(self) -> Sequence[RadarrMovie]:
        catalogs = await asyncio.gather(*(target.client.list_movies() for target in self._targets))
        return [
            replace(
                movie,
                id=_encode_id(target_index, movie.id),
                service_id=self._targets[target_index].id,
                service_name=self._targets[target_index].name,
            )
            for target_index, catalog in enumerate(catalogs)
            for movie in catalog
        ]

    async def list_storage(self) -> Sequence[StorageProfileListing]:
        """Read each Radarr profile independently for storage health."""

        results = await asyncio.gather(
            *(self._target_storage(target, "radarr") for target in self._targets),
        )
        return results

    @staticmethod
    async def _target_storage(target: RadarrTarget, service_kind: str) -> StorageProfileListing:
        try:
            roots, disk_spaces = await asyncio.gather(
                target.client.list_root_folders(),
                target.client.list_disk_space(),
            )
            tagged_roots = tuple(replace(root, service_id=target.id, service_name=target.name) for root in roots)
            return StorageProfileListing(
                service_kind=service_kind,  # type: ignore[arg-type]
                service_id=target.id,
                service_name=target.name,
                roots=tagged_roots,
                disk_spaces=tuple(disk_spaces),
            )
        except Exception:  # noqa: BLE001 - one profile must not hide another's health
            return StorageProfileListing(
                service_kind=service_kind,  # type: ignore[arg-type]
                service_id=target.id,
                service_name=target.name,
                roots=(),
                disk_spaces=(),
                error_code="profile_unavailable",
            )

    async def list_movie_history(self, movie_id: int) -> Sequence[RadarrHistoryRecord]:
        target_index, raw_movie_id = _decode_id(movie_id, target_count=len(self._targets))
        records = await self._targets[target_index].client.list_movie_history(raw_movie_id)
        return [
            replace(
                record,
                id=_encode_id(target_index, record.id),
                movie_id=movie_id,
            )
            for record in records
        ]

    async def delete_movie(
        self,
        movie_id: int,
        *,
        delete_files: bool,
        add_import_exclusion: bool,
    ) -> None:
        target_index, raw_movie_id = _decode_id(movie_id, target_count=len(self._targets))
        await self._targets[target_index].client.delete_movie(
            raw_movie_id,
            delete_files=delete_files,
            add_import_exclusion=add_import_exclusion,
        )


class MultiSonarrClient:
    """Aggregate Sonarr catalogs while preserving all mutable ID ownership."""

    def __init__(self, targets: Sequence[SonarrTarget]) -> None:
        self._targets = tuple(targets)

    async def close(self) -> None:
        await asyncio.gather(*(target.client.close() for target in self._targets))

    async def ping(self) -> None:
        await asyncio.gather(*(target.client.ping() for target in self._targets))

    async def get_version(self) -> str:
        versions = await asyncio.gather(*(target.client.get_version() for target in self._targets))
        return ", ".join(sorted(set(versions)))

    async def list_series(self) -> Sequence[SonarrSeries]:
        catalogs = await asyncio.gather(*(target.client.list_series() for target in self._targets))
        return [
            replace(
                series,
                id=_encode_id(target_index, series.id),
                service_id=self._targets[target_index].id,
                service_name=self._targets[target_index].name,
            )
            for target_index, catalog in enumerate(catalogs)
            for series in catalog
        ]

    async def list_storage(self) -> Sequence[StorageProfileListing]:
        """Read each Sonarr profile independently for storage health."""

        return await asyncio.gather(*(self._target_storage(target, "sonarr") for target in self._targets))

    @staticmethod
    async def _target_storage(target: SonarrTarget, service_kind: str) -> StorageProfileListing:
        try:
            roots, disk_spaces = await asyncio.gather(
                target.client.list_root_folders(),
                target.client.list_disk_space(),
            )
            tagged_roots = tuple(replace(root, service_id=target.id, service_name=target.name) for root in roots)
            return StorageProfileListing(
                service_kind=service_kind,  # type: ignore[arg-type]
                service_id=target.id,
                service_name=target.name,
                roots=tagged_roots,
                disk_spaces=tuple(disk_spaces),
            )
        except Exception:  # noqa: BLE001 - one profile must not hide another's health
            return StorageProfileListing(
                service_kind=service_kind,  # type: ignore[arg-type]
                service_id=target.id,
                service_name=target.name,
                roots=(),
                disk_spaces=(),
                error_code="profile_unavailable",
            )

    async def list_series_history(self, series_id: int) -> Sequence[SonarrHistoryRecord]:
        target_index, raw_series_id = _decode_id(series_id, target_count=len(self._targets))
        records = await self._targets[target_index].client.list_series_history(raw_series_id)
        return [
            replace(
                record,
                id=_encode_id(target_index, record.id),
                series_id=series_id,
                episode_id=(_encode_id(target_index, record.episode_id) if record.episode_id is not None else None),
            )
            for record in records
        ]

    async def list_episodes(self, series_id: int) -> Sequence[SonarrEpisode]:
        target_index, raw_series_id = _decode_id(series_id, target_count=len(self._targets))
        episodes = await self._targets[target_index].client.list_episodes(raw_series_id)
        return [
            replace(
                episode,
                id=_encode_id(target_index, episode.id),
                series_id=series_id,
                episode_file_id=(
                    _encode_id(target_index, episode.episode_file_id) if episode.episode_file_id is not None else None
                ),
            )
            for episode in episodes
        ]

    async def list_episode_files(self, series_id: int) -> Sequence[SonarrEpisodeFile]:
        target_index, raw_series_id = _decode_id(series_id, target_count=len(self._targets))
        files = await self._targets[target_index].client.list_episode_files(raw_series_id)
        return [replace(file, id=_encode_id(target_index, file.id)) for file in files]

    async def unmonitor_episodes(self, episode_ids: Sequence[int]) -> None:
        grouped: dict[int, list[int]] = defaultdict(list)
        for episode_id in episode_ids:
            target_index, raw_episode_id = _decode_id(episode_id, target_count=len(self._targets))
            grouped[target_index].append(raw_episode_id)
        await asyncio.gather(
            *(
                self._targets[target_index].client.unmonitor_episodes(raw_ids)
                for target_index, raw_ids in grouped.items()
            )
        )

    async def unmonitor_season(self, series_id: int, season_number: int) -> None:
        target_index, raw_series_id = _decode_id(series_id, target_count=len(self._targets))
        await self._targets[target_index].client.unmonitor_season(raw_series_id, season_number)

    async def delete_episode_file(self, episode_file_id: int) -> None:
        target_index, raw_episode_file_id = _decode_id(episode_file_id, target_count=len(self._targets))
        await self._targets[target_index].client.delete_episode_file(raw_episode_file_id)

    async def delete_series(
        self,
        series_id: int,
        *,
        delete_files: bool,
        add_import_list_exclusion: bool,
    ) -> None:
        target_index, raw_series_id = _decode_id(series_id, target_count=len(self._targets))
        await self._targets[target_index].client.delete_series(
            raw_series_id,
            delete_files=delete_files,
            add_import_list_exclusion=add_import_list_exclusion,
        )


def _encode_id(target_index: int, raw_id: int) -> int:
    if target_index < 0 or raw_id < 0:
        raise ValueError("Service and resource IDs must be non-negative.")
    paired = (target_index + raw_id) * (target_index + raw_id + 1) // 2 + raw_id
    return -(paired + 1)


def _decode_id(value: int, *, target_count: int) -> tuple[int, int]:
    if value >= 0:
        raise ValueError(f"Expected a routed service ID, got {value}.")
    paired = -value - 1
    diagonal = (isqrt(8 * paired + 1) - 1) // 2
    diagonal_start = diagonal * (diagonal + 1) // 2
    raw_id = paired - diagonal_start
    target_index = diagonal - raw_id
    if target_index < 0 or target_index >= target_count:
        raise ValueError(f"Routed service ID {value} references an unknown target.")
    return target_index, raw_id


def decode_routed_id(value: int, *, target_count: int) -> tuple[int, int]:
    """Public adapter for library projections that need raw Arr IDs."""

    return _decode_id(value, target_count=target_count)
