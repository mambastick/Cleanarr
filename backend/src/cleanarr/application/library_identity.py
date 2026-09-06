"""Shared fail-closed identity matching for Arr and Jellyfin catalogue items."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence

from cleanarr.domain import JellyfinItem, LibraryMediaType


def matching_jellyfin_items(
    raw: object,
    media_type: LibraryMediaType,
    items: Sequence[JellyfinItem],
) -> tuple[JellyfinItem, ...]:
    """Return every Jellyfin item with one agreeing and no conflicting provider ID.

    Callers must require exactly one result before using the relationship. In
    particular, shared identifiers must all agree and returning every remaining
    match keeps duplicate remote rows from silently selecting whichever arrived
    first.
    """

    fields = ("tmdb_id", "imdb_id") if media_type is LibraryMediaType.MOVIE else ("tvdb_id", "tmdb_id", "imdb_id")
    identifiers: list[tuple[str, int | str]] = []
    for field in fields:
        normalized = _normalized_identifier(getattr(raw, field, None))
        if normalized is not None:
            identifiers.append((field, normalized))
    if not identifiers:
        return ()

    ambiguous_ids = duplicate_jellyfin_item_ids(items)
    expected_type = "movie" if media_type is LibraryMediaType.MOVIE else "series"
    matches: list[JellyfinItem] = []
    for item in items:
        if not isinstance(item, JellyfinItem) or item.type.strip().casefold() != expected_type:
            continue
        item_id = normalized_jellyfin_item_id(item)
        if item_id is None or item_id in ambiguous_ids:
            continue
        overlap = False
        conflicting = False
        for field, expected in identifiers:
            observed = _normalized_identifier(getattr(item, field, None))
            if observed is None:
                continue
            if observed != expected:
                conflicting = True
                break
            overlap = True
        if overlap and not conflicting:
            matches.append(item)
    return tuple(matches)


def duplicate_jellyfin_item_ids(items: Sequence[JellyfinItem]) -> frozenset[str]:
    """Return normalized remote IDs that cannot identify one unique item."""

    counts = Counter(
        item_id
        for item in items
        if isinstance(item, JellyfinItem) and (item_id := normalized_jellyfin_item_id(item)) is not None
    )
    return frozenset(item_id for item_id, count in counts.items() if count > 1)


def matching_jellyfin_seasons(
    parent_id: str, season_number: int, items: Sequence[JellyfinItem]
) -> tuple[JellyfinItem, ...]:
    """Require exact parent and season scope; callers must require one match."""

    parent = parent_id.strip().casefold()
    ambiguous_ids = duplicate_jellyfin_item_ids(items)
    candidates = tuple(
        item
        for item in items
        if item.type.strip().casefold() == "season"
        and item.parent_id is not None
        and item.parent_id.strip().casefold() == parent
        and item.season_number == season_number
    )
    # Invalid/duplicate IDs must not hide a second child in the requested scope.
    if len(candidates) != 1:
        return ()
    item_id = normalized_jellyfin_item_id(candidates[0])
    return candidates if item_id and item_id != parent and item_id not in ambiguous_ids else ()


def normalized_jellyfin_item_id(item: JellyfinItem) -> str | None:
    """Normalize an opaque Jellyfin ID only for equality and duplicate checks."""

    if not isinstance(item.id, str):
        return None
    normalized = item.id.strip().casefold()
    return normalized or None


def _normalized_identifier(value: object) -> int | str | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, str):
        normalized = value.strip().casefold()
        return normalized or None
    return None
