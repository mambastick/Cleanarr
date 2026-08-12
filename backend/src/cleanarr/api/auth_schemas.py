"""Schemas for admin auth endpoints."""

from __future__ import annotations

from pydantic import BaseModel, Field

from cleanarr.application.authentication import AuthSession, AuthStatus
from cleanarr.domain.config import SSOAuthMode


class AuthStatusResponse(BaseModel):
    """Current admin auth state."""

    admin_configured: bool
    requires_registration: bool
    authenticated: bool
    username: str | None = None
    csrf_token: str | None = None
    sso_enabled: bool
    sso_mode: SSOAuthMode
    sso_configured: bool
    ui_language: str

    @classmethod
    def from_domain(
        cls,
        status: AuthStatus,
        *,
        ui_language: str,
    ) -> AuthStatusResponse:
        return cls.model_validate({**status.__dict__, "ui_language": ui_language})


class SSOLoginResponse(BaseModel):
    """Information for redirecting the browser into the provider."""

    authorize_url: str


class AdminCredentialsRequest(BaseModel):
    """Login/register payload."""

    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8, max_length=256)


class AuthSessionResponse(BaseModel):
    """Authenticated browser response without exposing the session identifier."""

    username: str
    csrf_token: str

    @classmethod
    def from_domain(cls, session: AuthSession) -> AuthSessionResponse:
        return cls(username=session.username, csrf_token=session.csrf_token)
