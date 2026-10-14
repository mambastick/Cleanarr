"""Pure helpers for private downloader content ownership evidence."""

from __future__ import annotations

import asyncio
import posixpath
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import PurePosixPath
from typing import Protocol, cast

from cleanarr.domain import ContentScopeBlocker, DownloaderContentInventory, DownloaderContentScope

CONTENT_INVENTORY_TIMEOUT_SECONDS = 10.0
MAX_CONTENT_INVENTORY_SCOPES = 20_000
MAX_CONTENT_INVENTORY_PATHS = 200_000
_INFO_HASH_RE = re.compile(r"^[0-9A-F]{40}(?:[0-9A-F]{24})?$")


class _ContentInventoryReader(Protocol):
    async def list_content_inventory(self) -> DownloaderContentInventory: ...


@dataclass(frozen=True)
class ContentSafetyAssessment:
    """Completeness and overlap result for one or more private inventories."""

    complete: bool
    conflicts: frozenset[tuple[str, str]] = frozenset()
    missing_known: frozenset[tuple[str, str]] = frozenset()
    observed: frozenset[tuple[str, str]] = frozenset()
    uncertain: frozenset[tuple[str, str]] = frozenset()
    scope_paths: tuple[tuple[str, str, tuple[str, ...], str | None], ...] = ()
    uncertainty_codes: tuple[tuple[str, str, str], ...] = ()
    sibling_scope_blockers: tuple[tuple[str, str, tuple[ContentScopeBlocker, ...]], ...] = ()
    inventories: tuple[tuple[str, DownloaderContentInventory], ...] = field(default=(), repr=False)


def validate_scope_path(value: object, *, minimum_parts: int = 3) -> str | None:
    """Accept only an absolute, normalized POSIX path with a bounded root."""

    if not isinstance(value, str) or not value or len(value) > 4096 or not value.isprintable() or "\x00" in value:
        return None
    if "://" in value or "\\" in value or value.startswith("//"):
        return None
    path = PurePosixPath(value)
    if not path.is_absolute() or ".." in path.parts or len(path.parts) < minimum_parts:
        return None
    return str(path)


def join_scope_path(root: object, relative: object, *, minimum_root_parts: int = 3) -> str | None:
    """Join a downloader root and a validated relative file path safely."""

    root_path = validate_scope_path(root, minimum_parts=minimum_root_parts)
    if root_path is None or not isinstance(relative, str) or not relative or len(relative) > 4096 or "\x00" in relative:
        return None
    if "://" in relative or "\\" in relative:
        return None
    relative_path = PurePosixPath(relative)
    if relative_path.is_absolute() or ".." in relative_path.parts:
        return None
    joined = posixpath.normpath(posixpath.join(root_path, str(relative_path)))
    return joined if joined.startswith(f"{root_path}/") else None


def scope_paths_overlap(left: str, right: str) -> bool:
    """Return whether two exact files or directory scopes overlap."""

    return left == right or left.startswith(f"{right}/") or right.startswith(f"{left}/")


def assess_content_inventory(
    inventories: Sequence[tuple[str, DownloaderContentInventory | None]],
    hashes: Sequence[str],
    *,
    known_existing: Mapping[str, Sequence[str]] | None = None,
) -> ContentSafetyAssessment:
    """Validate complete inventories and find overlapping torrent scopes."""

    normalized_hashes = set(hashes)
    scoped: list[tuple[str, DownloaderContentScope, frozenset[str]]] = []
    path_owners: dict[str, set[tuple[str, str, frozenset[str], bool, str | None, str | None]]] = {}
    seen: set[tuple[str, str]] = set()
    total_paths = 0
    observed: set[tuple[str, str]] = set()
    uncertain: set[tuple[str, str]] = set()
    scope_paths: list[tuple[str, str, tuple[str, ...], str | None]] = []
    uncertainty_codes: list[tuple[str, str, str]] = []
    for client_id, inventory in inventories:
        if not isinstance(inventory, DownloaderContentInventory):
            return ContentSafetyAssessment(complete=False)
        if (
            not isinstance(inventory.scopes, tuple)
            or not isinstance(inventory.failures, tuple)
            or inventory.failures
            or len(inventory.scopes) > MAX_CONTENT_INVENTORY_SCOPES
        ):
            return ContentSafetyAssessment(complete=False)
        for scope in inventory.scopes:
            if (
                not isinstance(scope, DownloaderContentScope)
                or not isinstance(scope.info_hash, str)
                or _INFO_HASH_RE.fullmatch(scope.info_hash) is None
                or not isinstance(scope.paths, tuple)
                or not isinstance(scope.hash_aliases, tuple)
                or not isinstance(scope.uncertain, bool)
                or not isinstance(scope.empty_verified, bool)
                or (scope.uncertainty_code is not None and not isinstance(scope.uncertainty_code, str))
                or (scope.torrent_name is not None and not isinstance(scope.torrent_name, str))
                or (not scope.paths and not scope.empty_verified)
                or (scope.empty_verified and bool(scope.paths))
            ):
                return ContentSafetyAssessment(complete=False)
            alias_values = (scope.info_hash, *scope.hash_aliases)
            if any(not isinstance(alias, str) or _INFO_HASH_RE.fullmatch(alias) is None for alias in alias_values):
                return ContentSafetyAssessment(complete=False)
            alias_set = frozenset(alias_values)
            if len(alias_set) != len(alias_values):
                return ContentSafetyAssessment(complete=False)
            if any((client_id, alias) in seen for alias in alias_set):
                return ContentSafetyAssessment(complete=False)
            seen.update((client_id, alias) for alias in alias_set)
            if any(validate_scope_path(path, minimum_parts=2) != path for path in scope.paths):
                return ContentSafetyAssessment(complete=False)
            total_paths += len(scope.paths)
            if total_paths > MAX_CONTENT_INVENTORY_PATHS:
                return ContentSafetyAssessment(complete=False)
            scoped.append((client_id, scope, alias_set))
            observed.update((client_id, alias) for alias in alias_set)
            scope_paths.extend((client_id, alias, scope.paths, scope.torrent_name) for alias in alias_set)
            if scope.uncertain:
                uncertain.update((client_id, alias) for alias in alias_set)
                if scope.uncertainty_code is not None:
                    uncertainty_codes.extend((client_id, alias, scope.uncertainty_code) for alias in alias_set)
            for path in scope.paths:
                path_owners.setdefault(path, set()).add(
                    (
                        client_id,
                        scope.info_hash,
                        alias_set,
                        scope.uncertain,
                        scope.uncertainty_code,
                        scope.torrent_name,
                    )
                )

    conflicts: set[tuple[str, str]] = set()
    active: list[tuple[str, set[tuple[str, str, frozenset[str], bool, str | None, str | None]]]] = []
    sibling_scope_blockers: dict[tuple[str, str], set[ContentScopeBlocker]] = {}
    for path in sorted(path_owners, key=lambda value: PurePosixPath(value).parts):
        while active and not (path == active[-1][0] or path.startswith(f"{active[-1][0]}/")):
            active.pop()
        owners: set[tuple[str, str, frozenset[str], bool, str | None, str | None]] = set(path_owners[path])
        for _ancestor, ancestor_owners in active:
            owners.update(ancestor_owners)
        if len(owners) > 1:
            uncertain_owners = tuple(owner for owner in owners if owner[3])
            for client_id, _canonical_hash, aliases, owner_uncertain, _uncertainty_code, _torrent_name in owners:
                requested_aliases = aliases.intersection(normalized_hashes)
                if owner_uncertain:
                    uncertain.update((client_id, hash_value) for hash_value in requested_aliases)
                elif uncertain_owners:
                    for hash_value in requested_aliases:
                        sibling_scope_blockers.setdefault((client_id, hash_value), set()).update(
                            ContentScopeBlocker(
                                client_id=blocker_client,
                                info_hash=blocker_hash,
                                torrent_name=blocker_name,
                            )
                            for (
                                blocker_client,
                                blocker_hash,
                                _aliases,
                                _uncertain,
                                _code,
                                blocker_name,
                            ) in uncertain_owners
                        )
                else:
                    conflicts.update((client_id, hash_value) for hash_value in requested_aliases)
        active.append((path, path_owners[path]))
    missing_known: set[tuple[str, str]] = set()
    if known_existing is not None:
        aliases_by_client = {
            client_id: frozenset(
                alias for scope_client, _scope, aliases in scoped if scope_client == client_id for alias in aliases
            )
            for client_id, _inventory in inventories
        }
        for client_id, known_hashes in known_existing.items():
            for known_hash in known_hashes:
                if not isinstance(known_hash, str) or _INFO_HASH_RE.fullmatch(known_hash) is None:
                    return ContentSafetyAssessment(complete=False)
                if known_hash not in aliases_by_client.get(client_id, frozenset()):
                    missing_known.add((client_id, known_hash))
    return ContentSafetyAssessment(
        complete=True,
        conflicts=frozenset(conflicts),
        missing_known=frozenset(missing_known),
        observed=frozenset(observed),
        uncertain=frozenset(uncertain),
        scope_paths=tuple(scope_paths),
        uncertainty_codes=tuple(sorted(set(uncertainty_codes))),
        sibling_scope_blockers=tuple(
            sorted(
                (
                    client_id,
                    hash_value,
                    tuple(
                        sorted(
                            blockers,
                            key=lambda blocker: (
                                blocker.client_id,
                                blocker.info_hash,
                                blocker.torrent_name or "",
                            ),
                        )
                    ),
                )
                for (client_id, hash_value), blockers in sibling_scope_blockers.items()
            )
        ),
        inventories=tuple(
            (client_id, cast(DownloaderContentInventory, inventory)) for client_id, inventory in inventories
        ),
    )


def refresh_content_inventory(
    assessment: ContentSafetyAssessment,
    client_id: str,
    inventory: DownloaderContentInventory | None,
    hashes: Sequence[str],
) -> ContentSafetyAssessment:
    """Replace one private snapshot without dropping other clients' ownership evidence."""

    if not assessment.complete or sum(key == client_id for key, _value in assessment.inventories) != 1:
        return ContentSafetyAssessment(complete=False)
    known_existing: dict[str, list[str]] = {}
    requested = set(hashes)
    for key, value in assessment.missing_known | frozenset(
        (key, value) for key, value in assessment.observed if value in requested
    ):
        known_existing.setdefault(key, []).append(value)
    refreshed = assess_content_inventory(
        tuple((key, inventory if key == client_id else original) for key, original in assessment.inventories),
        hashes,
        known_existing=known_existing,
    )
    blockers: dict[tuple[str, str], set[ContentScopeBlocker]] = {}
    for key, value, scopes in (*assessment.sibling_scope_blockers, *refreshed.sibling_scope_blockers):
        blockers.setdefault((key, value), set()).update(scopes)
    return replace(
        refreshed,
        conflicts=refreshed.conflicts | assessment.conflicts,
        missing_known=refreshed.missing_known | assessment.missing_known,
        uncertain=refreshed.uncertain | assessment.uncertain,
        uncertainty_codes=tuple(sorted(set((*assessment.uncertainty_codes, *refreshed.uncertainty_codes)))),
        sibling_scope_blockers=tuple(
            (
                key,
                value,
                tuple(sorted(scopes, key=lambda scope: (scope.client_id, scope.info_hash, scope.torrent_name or ""))),
            )
            for (key, value), scopes in sorted(blockers.items())
        ),
    )


def content_safety_skip_reason(
    assessment: ContentSafetyAssessment,
    client_id: str,
    info_hash: str,
) -> str | None:
    """Map private evidence to the structured removal skip reason."""

    if not assessment.complete:
        return "ownership_unverifiable"
    if (client_id, info_hash) in assessment.missing_known:
        return "ownership_unverifiable"
    if (client_id, info_hash) not in assessment.observed:
        return "ownership_unverifiable"
    uncertainty_code = next(
        (
            code
            for snapshot_client, snapshot_hash, code in assessment.uncertainty_codes
            if snapshot_client == client_id and snapshot_hash == info_hash
        ),
        None,
    )
    if uncertainty_code == "torrent_closed":
        return "torrent_closed"
    if any(
        snapshot_client == client_id and snapshot_hash == info_hash
        for snapshot_client, snapshot_hash, _blockers in assessment.sibling_scope_blockers
    ):
        return "sibling_scope_unknown"
    if (client_id, info_hash) in assessment.uncertain:
        return "ownership_unverifiable"
    if (client_id, info_hash) in assessment.conflicts:
        return "shared_path"
    return None


def content_safety_blockers(
    assessment: ContentSafetyAssessment,
    client_id: str,
    info_hash: str,
) -> tuple[ContentScopeBlocker, ...]:
    """Return immutable sibling identities responsible for an unknown-scope block."""

    for snapshot_client, snapshot_hash, blockers in assessment.sibling_scope_blockers:
        if snapshot_client == client_id and snapshot_hash == info_hash:
            return blockers
    return ()


def content_scope_matches(
    assessment: ContentSafetyAssessment,
    client_id: str,
    info_hash: str,
    path: str,
    *,
    exact: bool = False,
) -> bool:
    """Check that fresh destructive metadata remains within its inventory snapshot."""

    if not assessment.complete or (client_id, info_hash) not in assessment.observed:
        return False
    if (client_id, info_hash) in assessment.uncertain:
        return False
    normalized_path = validate_scope_path(path, minimum_parts=2)
    if normalized_path is None:
        return False
    recorded = [
        paths
        for snapshot_client, snapshot_hash, paths, _torrent_name in assessment.scope_paths
        if snapshot_client == client_id and snapshot_hash == info_hash
    ]
    if len(recorded) != 1:
        return False
    snapshot_paths = recorded[0]
    if exact:
        return snapshot_paths == (normalized_path,)
    return bool(snapshot_paths) and all(
        snapshot_path == normalized_path or snapshot_path.startswith(f"{normalized_path}/")
        for snapshot_path in snapshot_paths
    )


async def read_content_inventory(client: object) -> DownloaderContentInventory | None:
    """Read private evidence with a bounded wait; timeout is unknown ownership."""

    try:
        inventory = await asyncio.wait_for(
            cast(_ContentInventoryReader, client).list_content_inventory(),
            timeout=CONTENT_INVENTORY_TIMEOUT_SECONDS,
        )
    except Exception:
        return None
    return inventory if isinstance(inventory, DownloaderContentInventory) else None
