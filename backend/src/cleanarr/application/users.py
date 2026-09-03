"""Application use cases for user discovery and role administration."""

from __future__ import annotations

from typing import Protocol

from cleanarr.domain.users import UserAccount, UserAuthSource, UserRole


class LastAdministratorError(RuntimeError):
    """Raised when a mutation would leave CleanArr without an administrator."""


class UserNotFoundError(LookupError):
    """Raised when a role mutation targets an unknown identity."""


class UserAccountStorePort(Protocol):
    """Persistence contract shared by authentication and user administration."""

    def ensure_user(self, username: str, auth_source: UserAuthSource, default_role: UserRole) -> UserAccount: ...

    def ensure_sso_user(self, username: str) -> UserAccount: ...

    def touch_user(self, username: str) -> UserAccount | None: ...

    def get_role(self, username: str) -> UserRole | None: ...

    def list_users(self) -> tuple[UserAccount, ...]: ...

    def update_role(self, username: str, role: UserRole) -> UserAccount: ...


class UserAdministrationService:
    """Expose bounded user listing and safe role changes."""

    def __init__(self, store: UserAccountStorePort) -> None:
        self._store = store

    def list_users(self) -> tuple[UserAccount, ...]:
        return self._store.list_users()

    def update_role(self, username: str, role: UserRole) -> UserAccount:
        return self._store.update_role(username, role)
