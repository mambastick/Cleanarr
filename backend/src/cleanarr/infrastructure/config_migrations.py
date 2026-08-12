"""Ordered, forward-only migrations for the persisted runtime-config payload."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from cleanarr.domain.config import CURRENT_CONFIG_SCHEMA_VERSION


class UnsupportedConfigSchemaVersionError(RuntimeError):
    """Raised before a newer configuration can be interpreted or rewritten."""


@dataclass(frozen=True)
class ConfigMigration:
    """One deterministic migration between adjacent config schema versions."""

    version: int
    migrate: Callable[[dict[str, Any]], dict[str, Any]]


def _migrate_v1(payload: dict[str, Any]) -> dict[str, Any]:
    """Canonicalize the legacy Jellyseerr collection without dropping profiles."""

    canonical = payload.get("seerr")
    legacy = payload.get("jellyseerr")
    if canonical is not None and not isinstance(canonical, list):
        raise ValueError("Runtime configuration seerr profiles must be a list.")
    if legacy is not None and not isinstance(legacy, list):
        raise ValueError("Runtime configuration jellyseerr profiles must be a list.")
    canonical_profiles = list(canonical) if isinstance(canonical, list) else []
    legacy_profiles = list(legacy) if isinstance(legacy, list) else []
    known_ids = {
        profile.get("id")
        for profile in canonical_profiles
        if isinstance(profile, dict) and profile.get("id") is not None
    }
    payload["seerr"] = [
        *canonical_profiles,
        *[
            profile
            for profile in legacy_profiles
            if not isinstance(profile, dict) or profile.get("id") not in known_ids
        ],
    ]
    payload.pop("jellyseerr", None)
    return payload


def _migrate_v2(payload: dict[str, Any]) -> dict[str, Any]:
    """Add the explicit fail-closed OIDC access-policy shape."""

    general = payload.get("general")
    if isinstance(general, dict):
        general.setdefault("sso_allowed_users", [])
        general.setdefault("sso_allowed_groups", [])
        general.setdefault("sso_group_claim", "groups")
        general.setdefault("sso_required_claim", None)
        general.setdefault("sso_required_value", None)
    return payload


CONFIG_MIGRATIONS = (
    ConfigMigration(version=1, migrate=_migrate_v1),
    ConfigMigration(version=2, migrate=_migrate_v2),
)


def migrate_config_payload(raw_payload: object) -> dict[str, Any]:
    """Return a migrated copy, rejecting invalid or future schema versions."""

    if not isinstance(raw_payload, dict):
        raise ValueError("Runtime configuration must be a JSON object.")

    raw_version = raw_payload.get("config_schema_version", 0)
    if isinstance(raw_version, bool) or not isinstance(raw_version, int) or raw_version < 0:
        raise ValueError("Runtime configuration schema version must be a non-negative integer.")
    if raw_version > CURRENT_CONFIG_SCHEMA_VERSION:
        raise UnsupportedConfigSchemaVersionError(
            f"Runtime configuration schema {raw_version} is newer than supported schema "
            f"{CURRENT_CONFIG_SCHEMA_VERSION}."
        )

    payload = deepcopy(raw_payload)
    current_version = raw_version
    for migration in CONFIG_MIGRATIONS:
        if migration.version <= current_version:
            continue
        if migration.version != current_version + 1:
            raise RuntimeError(f"Configuration migration chain is not contiguous at version {migration.version}.")
        payload = migration.migrate(payload)
        payload["config_schema_version"] = migration.version
        current_version = migration.version

    if current_version != CURRENT_CONFIG_SCHEMA_VERSION:
        raise RuntimeError("Configuration migration chain did not reach the current schema version.")
    return payload
