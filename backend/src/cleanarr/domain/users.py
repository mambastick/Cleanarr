"""CleanArr user identities and authorization roles."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class UserRole(StrEnum):
    """Roles exposed by the authenticated workspace."""

    ADMIN = "admin"
    VIEWER = "viewer"


class UserAuthSource(StrEnum):
    """Identity providers known to CleanArr."""

    LOCAL = "local"
    SSO = "sso"


@dataclass(frozen=True)
class UserAccount:
    """Privacy-safe persisted user projection."""

    username: str
    role: UserRole
    auth_source: UserAuthSource
    created_at: str
    last_seen_at: str | None
    updated_at: str
