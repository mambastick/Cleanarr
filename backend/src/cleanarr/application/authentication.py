"""Admin authentication and first-run registration flow."""

from __future__ import annotations

from dataclasses import dataclass
import secrets
from threading import Lock
import time

from cleanarr.application.configuration import RuntimeConfigurationService
from cleanarr.infrastructure.auth import InMemorySessionStore, PasswordHasher
from cleanarr.domain.config import GeneralConfig, SSOAuthMode


@dataclass(frozen=True)
class AuthStatus:
    """Serialized auth state for the UI."""

    admin_configured: bool
    requires_registration: bool
    authenticated: bool
    username: str | None
    sso_enabled: bool
    sso_mode: SSOAuthMode
    sso_configured: bool


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
        sso_state_ttl_seconds: int = 60 * 5,
    ) -> None:
        self._config_service = config_service
        self._password_hasher = password_hasher
        self._session_store = session_store
        self._sso_state_ttl_seconds = sso_state_ttl_seconds
        self._sso_states: dict[str, float] = {}
        self._sso_state_lock = Lock()

    @staticmethod
    def _pick_username_from_token_payload(payload: dict[str, object]) -> str | None:
        for key in ("preferred_username", "name", "email", "upn", "sub"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    def get_status(self, session_token: str | None) -> AuthStatus:
        config = self._config_service.get_config()
        admin = config.admin
        username = self.resolve_session(session_token)
        configured = admin.configured
        sso_configured = self.is_sso_configured(config.general)
        local_auth_enabled = self.is_password_auth_enabled(config.general)
        return AuthStatus(
            admin_configured=configured,
            requires_registration=not configured and not sso_configured,
            authenticated=username is not None,
            username=username,
            sso_enabled=local_auth_enabled,
            sso_mode=config.general.sso_mode,
            sso_configured=sso_configured,
        )

    def resolve_session(self, session_token: str | None) -> str | None:
        if not session_token:
            return None
        return self._session_store.resolve_session(session_token)

    def create_session_for_user(self, username: str) -> str:
        return self._session_store.create_session(username)

    def register_admin(self, *, username: str, password: str) -> AuthSession:
        config = self._config_service.get_config()
        if not self.is_password_auth_enabled(config.general):
            raise PermissionError("Local authentication is disabled.")
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
        if not self.is_password_auth_enabled(config.general):
            raise PermissionError("Local authentication is disabled.")
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

    def create_sso_state(self) -> str:
        state = secrets.token_urlsafe(32)
        with self._sso_state_lock:
            self._sso_states[state] = time.time()
        return state

    def consume_sso_state(self, state: str | None) -> bool:
        if not state:
            return False
        now = time.time()
        with self._sso_state_lock:
            created_at = self._sso_states.pop(state, None)
        if created_at is None:
            return False
        if now - created_at > self._sso_state_ttl_seconds:
            return False
        return True

    def is_sso_configured(self, general: GeneralConfig) -> bool:
        if not self.is_sso_auth_enabled(general):
            return False
        if not general.sso_issuer_url:
            return False
        if not general.sso_client_id:
            return False
        if not general.sso_client_secret:
            return False
        return True

    def is_password_auth_enabled(self, general: GeneralConfig) -> bool:
        return general.local_auth_enabled()

    def is_sso_auth_enabled(self, general: GeneralConfig) -> bool:
        return general.sso_auth_enabled()

    def is_sso_mode_both(self, general: GeneralConfig) -> bool:
        return general.sso_mode == SSOAuthMode.BOTH

    def is_sso_mode_sso_only(self, general: GeneralConfig) -> bool:
        return general.sso_mode == SSOAuthMode.SSO_ONLY

    def is_password_only_mode(self, general: GeneralConfig) -> bool:
        return general.sso_mode == SSOAuthMode.PASSWORD_ONLY

    def logout(self, session_token: str | None) -> None:
        if session_token:
            self._session_store.revoke_session(session_token)
