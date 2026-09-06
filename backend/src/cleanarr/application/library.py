"""Bounded Arr-backed library read model and stable resource resolution."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from collections import Counter
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from math import isqrt
from typing import Literal, cast

from cleanarr.application.library_identity import (
    duplicate_jellyfin_item_ids,
    matching_jellyfin_items,
    matching_jellyfin_seasons,
)
from cleanarr.application.ports import JellyfinServerClientPort, RadarrClientPort, SonarrClientPort
from cleanarr.domain import (
    ArtworkData,
    JellyfinItem,
    LibraryDetail,
    LibraryEnrichment,
    LibraryEpisode,
    LibraryFile,
    LibraryItem,
    LibraryMediaType,
    LibraryPage,
    LibraryReadState,
    LibraryResourceError,
    RadarrMovie,
    SonarrEpisode,
    SonarrEpisodeFile,
    SonarrSeries,
    decode_library_cursor,
    decode_library_resource,
    encode_library_cursor,
    encode_library_resource,
)
from cleanarr.domain.config import RuntimeConfig

_logger = logging.getLogger("cleanarr.library")
_CACHE_SECONDS = 30.0
_MAX_DETAIL_ROWS = 500
_MAX_ARTWORK_BYTES = 5 * 1024 * 1024
_ARTWORK_MEDIA_TYPES = frozenset({"image/jpeg", "image/png", "image/webp", "image/avif"})


class LibraryCursorError(ValueError):
    """A cursor is malformed or belongs to a different library revision."""

    code = "invalid_cursor"

    def __init__(self, message: str, *, code: str = "invalid_cursor") -> None:
        super().__init__(message)
        self.code = code


class LibraryItemNotFoundError(LookupError):
    """A stable resource no longer exists in the current Arr topology."""

    code = "library_item_not_found"


class LibraryUnavailableError(RuntimeError):
    """The selected library source cannot currently be read."""

    code = "library_unavailable"


class LibraryArtworkError(RuntimeError):
    """Artwork could not be safely proxied."""

    def __init__(self, code: str, message: str = "Artwork is unavailable.") -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class _CacheEntry:
    created_monotonic: float
    revision: str
    items: tuple[LibraryItem, ...]
    state: LibraryReadState
    error_code: str | None


class LibraryService:
    """Read Arr catalogs once per bounded cache key and never per card."""

    def __init__(
        self,
        *,
        config: Callable[[], RuntimeConfig],
        radarr: Callable[[], object],
        sonarr: Callable[[], object],
        jellyfin: Callable[[], object],
        detail_enricher: Callable[[LibraryItem], Awaitable[LibraryEnrichment]] | None = None,
        now: Callable[[], float] | None = None,
    ) -> None:
        self._config = config
        self._radarr = radarr
        self._sonarr = sonarr
        self._jellyfin = jellyfin
        self._detail_enricher = detail_enricher
        self._now = now or time.monotonic
        self._cache: dict[str, _CacheEntry] = {}
        self._lock = asyncio.Lock()

    async def list_items(
        self,
        *,
        media_type: LibraryMediaType,
        query: str = "",
        sort: Literal["added", "title", "size"] = "title",
        direction: Literal["asc", "desc"] = "asc",
        limit: int = 50,
        cursor: str | None = None,
        refresh: bool = False,
    ) -> LibraryPage:
        media_type = LibraryMediaType(media_type)
        if not 1 <= limit <= 50:
            raise ValueError("limit must be between 1 and 50.")
        normalized_query = " ".join(query.split()).casefold()
        entry = await self._load(media_type, refresh=refresh)
        page_key = _page_key(media_type, normalized_query, sort, direction)
        filtered = [
            item
            for item in entry.items
            if not normalized_query
            or any(
                normalized_query in value.casefold() for value in (item.title, item.jellyfin_title) if value is not None
            )
        ]
        filtered.sort(key=lambda item: _sort_key(item, sort), reverse=direction == "desc")
        offset = 0
        if cursor:
            try:
                cursor_revision, cursor_key, offset = decode_library_cursor(cursor)
            except LibraryResourceError as exc:
                raise LibraryCursorError("The library cursor is invalid or malformed.") from exc
            if cursor_revision != entry.revision or cursor_key != page_key:
                raise LibraryCursorError(
                    "The library changed; refresh the list before continuing.", code="catalog_changed"
                )
        if offset > len(filtered):
            raise LibraryCursorError("The library cursor is no longer valid.", code="catalog_changed")
        selected = tuple(filtered[offset : offset + limit])
        next_cursor = (
            encode_library_cursor(revision=entry.revision, key=page_key, offset=offset + limit)
            if offset + limit < len(filtered)
            else None
        )
        return LibraryPage(
            items=selected,
            state=entry.state,
            revision=entry.revision,
            next_cursor=next_cursor,
            error_code=entry.error_code,
        )

    async def get_item(self, resource_id: str, *, refresh: bool = False) -> LibraryDetail:
        try:
            resource = decode_library_resource(resource_id)
        except LibraryResourceError as exc:
            raise LibraryItemNotFoundError("The library item identifier is invalid.") from exc
        entry = await self._load(resource.media_type, refresh=refresh)
        item = next((candidate for candidate in entry.items if candidate.resource_id == resource_id), None)
        if item is None:
            if entry.state is LibraryReadState.UNAVAILABLE:
                raise LibraryUnavailableError("The library source is unavailable.")
            raise LibraryItemNotFoundError("The library item is no longer available.")
        if item.media_type is LibraryMediaType.MOVIE:
            enriched_item, enrichment_error = await self._enrich_detail(item)
            return LibraryDetail(
                item=enriched_item,
                state=LibraryReadState.PARTIAL if enrichment_error else entry.state,
                revision=entry.revision,
                error_code=entry.error_code or enrichment_error,
            )

        sonarr = cast(SonarrClientPort, self._sonarr())
        results = await asyncio.gather(
            sonarr.list_episodes(item.legacy_id),
            sonarr.list_episode_files(item.legacy_id),
            self._enrich_detail(item),
            self._season_items(item),
            return_exceptions=True,
        )
        episodes: tuple[LibraryEpisode, ...] = ()
        files: tuple[LibraryFile, ...] = ()
        detail_error = entry.error_code
        if isinstance(results[0], asyncio.CancelledError) or isinstance(results[1], asyncio.CancelledError):
            raise asyncio.CancelledError
        if isinstance(results[0], BaseException) or isinstance(results[1], BaseException):
            _logger.warning("Series detail read failed without recording downstream data")
            detail_error = detail_error or "series_detail_unavailable"
        else:
            try:
                episodes = tuple(_episode_projection(value) for value in list(results[0])[:_MAX_DETAIL_ROWS])
                files = tuple(_file_projection(value) for value in list(results[1])[:_MAX_DETAIL_ROWS])
            except Exception:  # noqa: BLE001 - malformed detail remains unavailable
                _logger.warning("Series detail metadata was malformed")
                detail_error = detail_error or "series_detail_unavailable"
        if isinstance(results[2], asyncio.CancelledError):
            raise asyncio.CancelledError
        if isinstance(results[2], BaseException):
            detail_error = detail_error or "detail_enrichment_unavailable"
            enriched_item = item
        else:
            enriched_item, enrichment_error = results[2]
            detail_error = detail_error or enrichment_error
        if isinstance(results[3], asyncio.CancelledError):
            raise asyncio.CancelledError
        season_ids: list[tuple[int, str]] = []
        if isinstance(results[3], BaseException):
            detail_error = detail_error or "season_jellyfin_unavailable"
        elif item.jellyfin_item_id:
            numbers = {episode.season_number for episode in episodes} | {
                file.season_number for file in files if file.season_number is not None
            }
            for number in sorted(numbers):
                matches = matching_jellyfin_seasons(item.jellyfin_item_id, number, results[3])
                if len(matches) == 1:
                    season_ids.append((number, matches[0].id))
        return LibraryDetail(
            item=enriched_item,
            state=LibraryReadState.PARTIAL if detail_error else entry.state,
            revision=entry.revision,
            error_code=detail_error,
            episodes=episodes,
            files=files,
            season_jellyfin_ids=tuple(season_ids),
        )

    async def _season_items(self, item: LibraryItem) -> tuple[JellyfinItem, ...]:
        if not item.jellyfin_item_id:
            return ()
        jellyfin = cast(JellyfinServerClientPort, self._jellyfin())
        value = await asyncio.wait_for(jellyfin.list_items(include_types=["Season"]), timeout=60)
        if (
            not isinstance(value, Sequence)
            or isinstance(value, (str, bytes, bytearray))
            or any(not isinstance(candidate, JellyfinItem) for candidate in value)
        ):
            raise ValueError("Season catalogue is unavailable.")
        return tuple(value)

    async def _enrich_detail(self, item: LibraryItem) -> tuple[LibraryItem, str | None]:
        """Run optional bounded detail enrichment without touching list cards."""

        if self._detail_enricher is None:
            return item, None
        try:
            enrichment = await asyncio.wait_for(self._detail_enricher(item), timeout=60)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - unknown is safer than an empty claim
            _logger.warning("Library detail enrichment failed without recording downstream details")
            return item, "detail_enrichment_unavailable"
        if not isinstance(enrichment, LibraryEnrichment):
            return item, "detail_enrichment_invalid"
        enriched_item = replace(
            item,
            playback_status=enrichment.playback_status,
            playback_freshness=enrichment.playback_freshness,
            play_count=enrichment.play_count,
            last_played_at=enrichment.last_played_at,
            playback_reason=enrichment.playback_reason,
            seeding_state=enrichment.seeding_state,
            seeding_readiness=enrichment.seeding_readiness,
            seeding_ratio=enrichment.seeding_ratio,
            seeding_time_seconds=enrichment.seeding_time_seconds,
            seeding_reason=enrichment.seeding_reason,
        )
        return enriched_item, (enrichment.failure_codes[0] if enrichment.failure_codes else None)

    async def artwork(self, resource_id: str, *, refresh: bool = False) -> ArtworkData:
        """Resolve the current Jellyfin item then return validated image bytes."""

        try:
            resource = decode_library_resource(resource_id)
        except LibraryResourceError as exc:
            raise LibraryItemNotFoundError("The library item identifier is invalid.") from exc
        entry = await self._load(resource.media_type, refresh=refresh)
        item = next((candidate for candidate in entry.items if candidate.resource_id == resource_id), None)
        if item is None:
            if entry.state is LibraryReadState.UNAVAILABLE:
                raise LibraryUnavailableError("The library source is unavailable.")
            raise LibraryItemNotFoundError("The library item is no longer available.")
        if not item.jellyfin_item_id:
            raise LibraryArtworkError("artwork_not_found")
        client = self._jellyfin()
        getter = getattr(client, "get_primary_artwork", None)
        if not callable(getter):
            raise LibraryArtworkError("artwork_unavailable")
        try:
            artwork = await getter(item.jellyfin_item_id)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - never expose downstream URL/body
            _logger.warning("Artwork proxy read failed without recording downstream details")
            raise LibraryArtworkError("artwork_unavailable") from None
        if artwork is None:
            raise LibraryArtworkError("artwork_not_found")
        if isinstance(artwork, ArtworkData):
            return _validate_artwork(artwork)
        if isinstance(artwork, tuple) and len(artwork) == 2 and isinstance(artwork[0], bytes):
            return _validate_artwork(ArtworkData(content=artwork[0], media_type=str(artwork[1])))
        if isinstance(artwork, bytes):
            return _validate_artwork(ArtworkData(content=artwork, media_type="image/jpeg"))
        raise LibraryArtworkError("artwork_invalid")

    async def _load(
        self,
        media_type: LibraryMediaType,
        *,
        refresh: bool,
    ) -> _CacheEntry:
        key = self._cache_key(media_type)
        if not refresh:
            cached = self._cache.get(key)
            if cached is not None and self._now() - cached.created_monotonic < _CACHE_SECONDS:
                return cached
        async with self._lock:
            if not refresh:
                cached = self._cache.get(key)
                if cached is not None and self._now() - cached.created_monotonic < _CACHE_SECONDS:
                    return cached
            entry = await self._read(media_type, key)
            self._cache[key] = entry
            return entry

    def _cache_key(self, media_type: LibraryMediaType) -> str:
        config = self._config()
        payload = {
            "config": hashlib.sha256(config.model_dump_json().encode()).hexdigest(),
            "language": config.general.jellyfin_language,
            "media_type": media_type.value,
        }
        return hashlib.sha256(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()).hexdigest()

    async def _read(
        self,
        media_type: LibraryMediaType,
        cache_key: str,
    ) -> _CacheEntry:
        config = self._config()
        raw_items: Sequence[RadarrMovie | SonarrSeries]
        try:
            if media_type is LibraryMediaType.MOVIE:
                radarr = cast(RadarrClientPort, self._radarr())
                raw_items = list(await radarr.list_movies())
            else:
                sonarr = cast(SonarrClientPort, self._sonarr())
                raw_items = list(await sonarr.list_series())
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - make external read unavailable, not destructive
            _logger.warning("Library %s catalog is unavailable", media_type.value)
            return self._entry(cache_key, (), LibraryReadState.UNAVAILABLE, "catalog_unavailable")

        jellyfin_items: tuple[JellyfinItem, ...] = ()
        jellyfin_failed = False
        try:
            jf_types = ["Movie"] if media_type is LibraryMediaType.MOVIE else ["Series"]
            jellyfin = cast(JellyfinServerClientPort, self._jellyfin())
            value = await jellyfin.list_items(
                include_types=jf_types,
                accept_language=config.general.jellyfin_language,
            )
            if (
                not isinstance(value, Sequence)
                or isinstance(value, (str, bytes, bytearray))
                or any(not isinstance(item, JellyfinItem) for item in value)
            ):
                raise ValueError("malformed Jellyfin library response")
            jellyfin_items = tuple(value)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - Arr catalog remains useful as partial state
            jellyfin_failed = True
            _logger.warning("Jellyfin library cross-reference is unavailable")

        profile_map = {
            profile.id: profile
            for profile in (config.radarr if media_type is LibraryMediaType.MOVIE else config.sonarr)
            if profile.enabled
        }
        fetched_at = datetime.now(UTC)
        result: list[LibraryItem] = []
        ambiguous_profile = False
        # Duplicate opaque IDs are ambiguous even when only one duplicate row
        # happens to share the Arr provider ID used for projection.
        ambiguous_jellyfin = bool(duplicate_jellyfin_item_ids(jellyfin_items))
        for raw in raw_items:
            candidate, duplicate_match = _library_item_projection(
                raw,
                media_type=media_type,
                profiles=profile_map,
                profile_count=len(profile_map),
                jellyfin_items=jellyfin_items,
            )
            if candidate is None:
                ambiguous_profile = True
                continue
            ambiguous_jellyfin = ambiguous_jellyfin or duplicate_match
            # A successful Jellyfin catalogue read proves a missing match;
            # a failed read must remain unknown so the UI never presents an
            # unavailable cross-reference as an authoritative absence.
            candidate = replace(
                candidate,
                artwork_status=(
                    "unknown" if jellyfin_failed else ("available" if candidate.jellyfin_item_id else "missing")
                ),
                fetched_at=fetched_at,
            )
            result.append(candidate)
        duplicate_resources = {
            resource_id for resource_id, count in Counter(item.resource_id for item in result).items() if count > 1
        }
        if duplicate_resources:
            ambiguous_profile = True
            result = [item for item in result if item.resource_id not in duplicate_resources]
        duplicate_jellyfin_ids = {
            item_id
            for item_id, count in Counter(
                item.jellyfin_item_id for item in result if item.jellyfin_item_id is not None
            ).items()
            if count > 1
        }
        if duplicate_jellyfin_ids:
            ambiguous_jellyfin = True
            result = [
                replace(item, jellyfin_item_id=None, jellyfin_title=None, artwork_status="missing")
                if item.jellyfin_item_id in duplicate_jellyfin_ids
                else item
                for item in result
            ]
        result.sort(key=lambda item: item.resource_id)
        state = (
            LibraryReadState.PARTIAL
            if jellyfin_failed or ambiguous_profile or ambiguous_jellyfin
            else LibraryReadState.COMPLETE
        )
        error_code = (
            "jellyfin_unavailable"
            if jellyfin_failed
            else (
                "ambiguous_profile"
                if ambiguous_profile
                else ("ambiguous_jellyfin_match" if ambiguous_jellyfin else None)
            )
        )
        return self._entry(cache_key, tuple(result), state, error_code)

    def _entry(
        self,
        cache_key: str,
        items: tuple[LibraryItem, ...],
        state: LibraryReadState,
        error_code: str | None,
    ) -> _CacheEntry:
        revision_payload = {
            "cache": cache_key,
            "state": state.value,
            "error": error_code,
            "items": [_catalog_revision_item(item) for item in items],
        }
        revision = hashlib.sha256(
            json.dumps(revision_payload, separators=(",", ":"), sort_keys=True).encode()
        ).hexdigest()
        return _CacheEntry(self._now(), revision, items, state, error_code)


def _library_item(
    raw: object,
    *,
    media_type: LibraryMediaType,
    profiles: Mapping[str, object],
    profile_count: int,
    jellyfin_items: Sequence[JellyfinItem],
) -> LibraryItem | None:
    """Compatibility wrapper for the unit-level projection contract."""

    return _library_item_projection(
        raw,
        media_type=media_type,
        profiles=profiles,
        profile_count=profile_count,
        jellyfin_items=jellyfin_items,
    )[0]


def _library_item_projection(
    raw: object,
    *,
    media_type: LibraryMediaType,
    profiles: Mapping[str, object],
    profile_count: int,
    jellyfin_items: Sequence[JellyfinItem],
) -> tuple[LibraryItem | None, bool]:
    if media_type is LibraryMediaType.MOVIE and not isinstance(raw, RadarrMovie):
        return None, False
    if media_type is LibraryMediaType.SERIES and not isinstance(raw, SonarrSeries):
        return None, False
    service_id = getattr(raw, "service_id", None)
    legacy_id = getattr(raw, "id", None)
    if isinstance(legacy_id, bool) or not isinstance(legacy_id, int):
        return None, False
    if legacy_id < 0 and not service_id:
        return None, False
    routed = _routed_parts(legacy_id, profile_count) if legacy_id < 0 else None
    if routed is not None and isinstance(service_id, str) and service_id:
        profile_ids = tuple(profiles)
        if routed[0] >= len(profile_ids) or profile_ids[routed[0]] != service_id:
            return None, False
    if legacy_id < 0 and routed is None:
        return None, False
    raw_id = routed[1] if routed is not None else legacy_id
    if not isinstance(service_id, str) or not service_id:
        if len(profiles) != 1:
            return None, False
        service_id = next(iter(profiles))
    profile = profiles.get(service_id)
    if profile is None:
        return None, False
    title = getattr(raw, "title", "")
    if not isinstance(title, str) or not title.strip():
        return None, False
    matches = matching_jellyfin_items(raw, media_type, jellyfin_items)
    jf = matches[0] if len(matches) == 1 else None
    return LibraryItem(
        resource_id=encode_library_resource(media_type, service_id, raw_id),
        media_type=media_type,
        profile_id=service_id,
        profile_name=_safe_text(getattr(profile, "name", None)),
        raw_id=raw_id,
        legacy_id=legacy_id,
        title=title.strip(),
        added_at=getattr(raw, "added_at", None),
        size_bytes=_optional_nonnegative_int(getattr(raw, "size_on_disk", None)),
        has_file=getattr(raw, "has_file", None) if isinstance(getattr(raw, "has_file", None), bool) else None,
        jellyfin_item_id=jf.id if jf else None,
        jellyfin_title=jf.name.strip() if jf and isinstance(jf.name, str) and jf.name.strip() else None,
        year=_optional_nonnegative_int(getattr(raw, "year", None)),
        episode_count=(
            _optional_nonnegative_int(getattr(raw, "episode_count", None))
            if media_type is LibraryMediaType.SERIES
            else None
        ),
        episode_file_count=(
            _optional_nonnegative_int(getattr(raw, "episode_file_count", None))
            if media_type is LibraryMediaType.SERIES
            else None
        ),
        artwork_status="available" if jf is not None else "unknown",
    ), len(matches) > 1


def _sort_key(item: LibraryItem, sort: str) -> tuple[object, str]:
    if sort == "added":
        return (item.added_at or datetime.min.replace(tzinfo=UTC), item.resource_id)
    if sort == "size":
        return (item.size_bytes if item.size_bytes is not None else -1, item.resource_id)
    return ((item.jellyfin_title or item.title).casefold(), item.resource_id)


def _page_key(
    media_type: LibraryMediaType,
    query: str,
    sort: Literal["added", "title", "size"],
    direction: Literal["asc", "desc"],
) -> str:
    """Bind a cursor to one normalized view without retaining search text."""

    payload = {
        "media_type": media_type.value,
        "query": query,
        "sort": sort,
        "direction": direction,
    }
    return hashlib.sha256(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()).hexdigest()


def _catalog_revision_item(item: LibraryItem) -> dict[str, object]:
    """Return the privacy-safe list projection that defines a catalog revision."""

    return {
        "resource_id": item.resource_id,
        "profile_name": item.profile_name,
        "title": item.title,
        "added_at": item.added_at.isoformat() if item.added_at is not None else None,
        "size_bytes": item.size_bytes,
        "has_file": item.has_file,
        "jellyfin_item_id": item.jellyfin_item_id,
        "jellyfin_title": item.jellyfin_title,
        "year": item.year,
        "episode_count": item.episode_count,
        "episode_file_count": item.episode_file_count,
        "artwork_status": item.artwork_status,
    }


def _raw_id(value: int, profile_count: int) -> int | None:
    if value >= 0 or profile_count <= 0:
        return value if value >= 0 else None
    routed = _routed_parts(value, profile_count)
    return routed[1] if routed is not None else None


def _routed_parts(value: int, profile_count: int) -> tuple[int, int] | None:
    if value >= 0 or profile_count <= 0:
        return None
    paired = -value - 1
    diagonal = (isqrt(8 * paired + 1) - 1) // 2
    diagonal_start = diagonal * (diagonal + 1) // 2
    raw_id = paired - diagonal_start
    target_index = diagonal - raw_id
    return (target_index, raw_id) if 0 <= target_index < profile_count else None


def _safe_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = " ".join(value.split()).strip()
    return normalized[:160] or None


def _optional_nonnegative_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, float) and value.is_integer() and value >= 0:
        return int(value)
    return None


def _episode_projection(value: object) -> LibraryEpisode:
    if not isinstance(value, SonarrEpisode):
        raise ValueError("Malformed episode metadata")
    return LibraryEpisode(
        id=value.id,
        season_number=value.season_number,
        episode_number=value.episode_number,
        has_file=value.has_file,
        episode_file_id=value.episode_file_id,
        monitored=value.monitored,
    )


def _file_projection(value: object) -> LibraryFile:
    if not isinstance(value, SonarrEpisodeFile):
        raise ValueError("Malformed episode-file metadata")
    return LibraryFile(id=value.id, season_number=value.season_number, size_bytes=value.size)


def _topology_revision(config: RuntimeConfig) -> str:
    payload = {
        "radarr": [
            {
                "id": profile.id,
                "name": profile.name,
                "url": profile.url,
                "enabled": profile.enabled,
                "default": profile.is_default,
            }
            for profile in config.radarr
        ],
        "sonarr": [
            {
                "id": profile.id,
                "name": profile.name,
                "url": profile.url,
                "enabled": profile.enabled,
                "default": profile.is_default,
            }
            for profile in config.sonarr
        ],
    }
    return hashlib.sha256(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()).hexdigest()


def _validate_artwork(artwork: ArtworkData) -> ArtworkData:
    if len(artwork.content) > _MAX_ARTWORK_BYTES:
        raise LibraryArtworkError("artwork_too_large")
    media_type = artwork.media_type.split(";", 1)[0].strip().casefold()
    if media_type not in _ARTWORK_MEDIA_TYPES:
        raise LibraryArtworkError("artwork_invalid_mime")
    return ArtworkData(content=artwork.content, media_type=media_type)
