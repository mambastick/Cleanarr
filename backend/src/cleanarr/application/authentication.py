"""Admin authentication and first-run registration flow."""

from __future__ import annotations

from dataclasses import dataclass

from cleanarr.application.configuration import RuntimeConfigurationService
from cleanarr.infrastructure.auth import InMemorySessionStore, PasswordHasher


@dataclass(frozen=True)
class AuthStatus:
    """Serialized auth state for the UI."""

    admin_configured: bool
    requires_registration: bool
    authenticated: bool
    username: str | None


@dataclass(frozen=True)
class AuthSession:
    """Successful admin login/registration result."""

    username: str
    token: str


class AuthenticationService:
    """Own first-run registration and admin sessions."""

    def __init__(
        self,
        *,
        config_service: RuntimeConfigurationService,
        password_hasher: PasswordHasher,
        session_store: InMemorySessionStore,
    ) -> None:
        self._config_service = config_service
        self._password_hasher = password_hasher
        self._session_store = session_store

    def get_status(self, session_token: str | None) -> AuthStatus:
        config = self._config_service.get_config()
        admin = config.admin
        username = self.resolve_session(session_token)
        configured = admin.configured
        return AuthStatus(
            admin_configured=configured,
            requires_registration=not configured,
            authenticated=username is not None,
            username=username,
        )

    def resolve_session(self, session_token: str | None) -> str | None:
        if not session_token:
            return None
        return self._session_store.resolve_session(session_token)

    def register_admin(self, *, username: str, password: str) -> AuthSession:
        config = self._config_service.get_config()
        if config.admin.configured:
            raise ValueError("Admin account is already configured.")

        password_hash = self._password_hasher.hash_password(password)
        self._config_service.set_admin_credentials(
            username=username,
            password_salt=password_hash.salt,
            password_hash=password_hash.digest,
        )
        token = self._session_store.create_session(username)
        return AuthSession(username=username, token=token)

    def login(self, *, username: str, password: str) -> AuthSession:
        config = self._config_service.get_config()
        admin = config.admin
        if not admin.configured or admin.username is None or admin.password_salt is None or admin.password_hash is None:
            raise LookupError("Admin account is not configured yet.")
        if admin.username != username:
            raise PermissionError("Invalid username or password.")
        if not self._password_hasher.verify_password(
            password,
            salt=admin.password_salt,
            digest=admin.password_hash,
        ):
            raise PermissionError("Invalid username or password.")
        token = self._session_store.create_session(admin.username)
        return AuthSession(username=admin.username, token=token)

    def logout(self, session_token: str | None) -> None:
        if session_token:
            self._session_store.revoke_session(session_token)
