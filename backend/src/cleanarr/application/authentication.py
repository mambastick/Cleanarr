"""Admin authentication and first-run registration flow."""

from __future__ import annotations

import secrets
import time
from collections import deque
from dataclasses import dataclass
from math import ceil
from threading import Lock
from typing import Any, Protocol

from cleanarr.application.configuration import RuntimeConfigurationService
from cleanarr.domain.config import GeneralConfig, SSOAuthMode


class PasswordHashResult(Protocol):
    """Result returned by the injected password-hashing adapter."""

    @property
    def salt(self) -> str: ...

    @property
    def digest(self) -> str: ...


class PasswordHasherPort(Protocol):
    """Application port for password hashing and verification."""

    def hash_password(self, password: str) -> PasswordHashResult: ...

    def verify_password(self, password: str, *, salt: str, digest: str) -> bool: ...


class SessionRecordPort(Protocol):
    """Application view of a resolved session."""

    @property
    def username(self) -> str: ...

    @property
    def csrf_token(self) -> str: ...


class SessionStorePort(Protocol):
    """Application port for local session lifecycle."""

    def create_session(self, username: str) -> str: ...

    def resolve_session(self, token: str) -> SessionRecordPort | None: ...

    def revoke_session(self, token: str) -> None: ...


@dataclass(frozen=True)
class AuthStatus:
    """Serialized auth state for the UI."""

    admin_configured: bool
    requires_registration: bool
    authenticated: bool
    username: str | None
    csrf_token: str | None
    sso_enabled: bool
    sso_mode: SSOAuthMode
    sso_configured: bool


@dataclass(frozen=True)
class AuthSession:
    """Successful admin login/registration result."""

    username: str
    token: str
    csrf_token: str


@dataclass(frozen=True)
class SSOAuthorizationState:
    """One-time OIDC state bound to nonce and PKCE verifier."""

    nonce: str
    code_verifier: str
    created_at: float


class LoginThrottledError(RuntimeError):
    """Raised when a source or account exceeds the local login budget."""

    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__("Too many login attempts. Try again later.")
        self.retry_after_seconds = retry_after_seconds


class AuthenticationService:
    """Own first-run registration and admin sessions."""

    def __init__(
        self,
        *,
        config_service: RuntimeConfigurationService,
        password_hasher: PasswordHasherPort,
        session_store: SessionStorePort,
        sso_state_ttl_seconds: int = 60 * 5,
        login_window_seconds: int = 60 * 5,
        login_max_failures: int = 5,
        login_lockout_seconds: int = 60 * 5,
    ) -> None:
        self._config_service = config_service
        self._password_hasher = password_hasher
        self._session_store = session_store
        self._sso_state_ttl_seconds = sso_state_ttl_seconds
        self._sso_states: dict[str, SSOAuthorizationState] = {}
        self._sso_state_lock = Lock()
        self._login_window_seconds = login_window_seconds
        self._login_max_failures = login_max_failures
        self._login_lockout_seconds = login_lockout_seconds
        self._login_failures: dict[str, deque[float]] = {}
        self._login_blocked_until: dict[str, float] = {}
        self._login_lock = Lock()

    @staticmethod
    def _pick_username_from_token_payload(payload: dict[str, Any]) -> str | None:
        for key in ("preferred_username", "email", "upn", "sub", "name"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    def get_status(self, session_token: str | None) -> AuthStatus:
        config = self._config_service.get_config()
        admin = config.admin
        session = self._session_store.resolve_session(session_token) if session_token else None
        username = session.username if session else None
        configured = admin.configured
        sso_configured = self.is_sso_configured(config.general)
        return AuthStatus(
            admin_configured=configured,
            requires_registration=(
                not configured and not sso_configured and self.is_password_auth_enabled(config.general)
            ),
            authenticated=username is not None,
            username=username,
            csrf_token=session.csrf_token if session else None,
            sso_enabled=self.is_sso_auth_enabled(config.general),
            sso_mode=config.general.sso_mode,
            sso_configured=sso_configured,
        )

    def resolve_session(self, session_token: str | None) -> str | None:
        if not session_token:
            return None
        record = self._session_store.resolve_session(session_token)
        return record.username if record else None

    def verify_csrf_token(self, session_token: str | None, csrf_token: str | None) -> bool:
        if not session_token or not csrf_token:
            return False
        record = self._session_store.resolve_session(session_token)
        return bool(record and _constant_time_equal(record.csrf_token, csrf_token))

    def create_session_for_user(self, username: str) -> AuthSession:
        return self._create_session(username)

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
        return self._create_session(username)

    def login(self, *, username: str, password: str, source: str = "unknown") -> AuthSession:
        config = self._config_service.get_config()
        if not self.is_password_auth_enabled(config.general):
            raise PermissionError("Local authentication is disabled.")
        throttle_keys = self._login_throttle_keys(username, source)
        self._check_login_throttle(throttle_keys)
        admin = config.admin
        if not admin.configured or admin.username is None or admin.password_salt is None or admin.password_hash is None:
            raise LookupError("Admin account is not configured yet.")
        if admin.username != username:
            self._record_login_failure(throttle_keys)
            raise PermissionError("Invalid username or password.")
        if not self._password_hasher.verify_password(
            password,
            salt=admin.password_salt,
            digest=admin.password_hash,
        ):
            self._record_login_failure(throttle_keys)
            raise PermissionError("Invalid username or password.")
        self._clear_login_failures(throttle_keys)
        return self._create_session(admin.username)

    def create_sso_state(self) -> tuple[str, SSOAuthorizationState]:
        state = secrets.token_urlsafe(32)
        authorization = SSOAuthorizationState(
            nonce=secrets.token_urlsafe(32),
            code_verifier=secrets.token_urlsafe(64),
            created_at=time.time(),
        )
        with self._sso_state_lock:
            self._purge_sso_states_locked(authorization.created_at)
            if len(self._sso_states) >= 256:
                oldest = min(self._sso_states, key=lambda key: self._sso_states[key].created_at)
                self._sso_states.pop(oldest, None)
            self._sso_states[state] = authorization
        return state, authorization

    def consume_sso_state(self, state: str | None) -> SSOAuthorizationState | None:
        if not state:
            return None
        now = time.time()
        with self._sso_state_lock:
            self._purge_sso_states_locked(now)
            return self._sso_states.pop(state, None)

    def is_sso_configured(self, general: GeneralConfig) -> bool:
        if not self.is_sso_auth_enabled(general):
            return False
        if not general.sso_issuer_url:
            return False
        if not general.sso_client_id:
            return False
        if not general.sso_client_secret:
            return False
        return general.has_sso_access_policy()

    def authorize_sso_identity(self, general: GeneralConfig, claims: dict[str, Any]) -> str:
        """Apply the explicit user/group/claim policy to validated ID-token claims."""

        username = self._pick_username_from_token_payload(claims)
        if not username or not general.has_sso_access_policy():
            raise PermissionError("SSO access policy denied this identity.")

        allowed_users = {value.casefold() for value in general.sso_allowed_users}
        identity_values = {
            value.strip().casefold()
            for key in ("preferred_username", "email", "upn", "sub")
            if isinstance((value := claims.get(key)), str) and value.strip()
        }
        user_match = bool(allowed_users.intersection(identity_values)) if allowed_users else False

        allowed_groups = {value.casefold() for value in general.sso_allowed_groups}
        group_values = _claim_values(claims.get(general.sso_group_claim))
        group_match = bool(allowed_groups.intersection(group_values)) if allowed_groups else False

        has_identity_allowlist = bool(allowed_users or allowed_groups)
        if has_identity_allowlist and not (user_match or group_match):
            raise PermissionError("SSO access policy denied this identity.")

        if general.sso_required_claim and general.sso_required_value:
            required_values = _claim_values(claims.get(general.sso_required_claim))
            if general.sso_required_value.casefold() not in required_values:
                raise PermissionError("SSO access policy denied this identity.")

        return username

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

    def _create_session(self, username: str) -> AuthSession:
        token = self._session_store.create_session(username)
        record = self._session_store.resolve_session(token)
        if record is None:  # pragma: no cover - created under the same lock-backed store
            raise RuntimeError("Could not create admin session.")
        return AuthSession(username=username, token=token, csrf_token=record.csrf_token)

    def _purge_sso_states_locked(self, now: float) -> None:
        expired = [
            state for state, record in self._sso_states.items() if now - record.created_at > self._sso_state_ttl_seconds
        ]
        for state in expired:
            self._sso_states.pop(state, None)

    @staticmethod
    def _login_throttle_keys(username: str, source: str) -> tuple[str, str]:
        return (f"source:{source.strip().casefold() or 'unknown'}", f"account:{username.strip().casefold()}")

    def _check_login_throttle(self, keys: tuple[str, str]) -> None:
        now = time.time()
        with self._login_lock:
            retry_after = max((self._login_blocked_until.get(key, 0.0) - now for key in keys), default=0.0)
            if retry_after > 0:
                raise LoginThrottledError(max(1, ceil(retry_after)))
            for key in keys:
                self._login_blocked_until.pop(key, None)
                failures = self._login_failures.get(key)
                if failures is not None:
                    self._purge_login_failures_locked(failures, now)

    def _record_login_failure(self, keys: tuple[str, str]) -> None:
        now = time.time()
        with self._login_lock:
            for key in keys:
                failures = self._login_failures.setdefault(key, deque())
                self._purge_login_failures_locked(failures, now)
                failures.append(now)
                if len(failures) >= self._login_max_failures:
                    self._login_blocked_until[key] = now + self._login_lockout_seconds

    def _clear_login_failures(self, keys: tuple[str, str]) -> None:
        with self._login_lock:
            for key in keys:
                self._login_failures.pop(key, None)
                self._login_blocked_until.pop(key, None)

    def _purge_login_failures_locked(self, failures: deque[float], now: float) -> None:
        cutoff = now - self._login_window_seconds
        while failures and failures[0] < cutoff:
            failures.popleft()


def _claim_values(value: object) -> set[str]:
    if isinstance(value, str):
        return {value.strip().casefold()} if value.strip() else set()
    if isinstance(value, (list, tuple, set)):
        return {entry.strip().casefold() for entry in value if isinstance(entry, str) and entry.strip()}
    return set()


def _constant_time_equal(expected: str, provided: str) -> bool:
    return secrets.compare_digest(expected.encode("utf-8"), provided.encode("utf-8"))
