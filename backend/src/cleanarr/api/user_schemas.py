"""Transport schemas for user administration."""

from __future__ import annotations

from pydantic import BaseModel

from cleanarr.domain.users import UserAccount, UserAuthSource, UserRole


class UserAccountResponse(BaseModel):
    username: str
    role: UserRole
    auth_source: UserAuthSource
    created_at: str
    last_seen_at: str | None

    @classmethod
    def from_domain(cls, account: UserAccount) -> UserAccountResponse:
        return cls(
            username=account.username,
            role=account.role,
            auth_source=account.auth_source,
            created_at=account.created_at,
            last_seen_at=account.last_seen_at,
        )


class UserAccountListResponse(BaseModel):
    users: list[UserAccountResponse]


class UserRoleUpdateRequest(BaseModel):
    role: UserRole
