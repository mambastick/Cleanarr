"""Password hashing and in-memory admin sessions."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass
from threading import Lock


@dataclass(frozen=True)
class PasswordHash:
    """Serialized password hash payload."""

    salt: str
    digest: str


class PasswordHasher:
    """Hash passwords with scrypt."""

    def hash_password(self, password: str) -> PasswordHash:
        salt = secrets.token_bytes(16)
        digest = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=2**14,
            r=8,
            p=1,
        )
        return PasswordHash(salt=salt.hex(), digest=digest.hex())

    def verify_password(self, password: str, *, salt: str, digest: str) -> bool:
        computed = hashlib.scrypt(
            password.encode("utf-8"),
            salt=bytes.fromhex(salt),
            n=2**14,
            r=8,
            p=1,
        )
        return hmac.compare_digest(computed.hex(), digest)


@dataclass(frozen=True)
class SessionRecord:
    """In-memory admin session."""

    username: str
    expires_at: float


class InMemorySessionStore:
    """Minimal in-memory session registry for the single-replica UI."""

    def __init__(self, *, ttl_seconds: int = 60 * 60 * 24 * 7) -> None:
        self._ttl_seconds = ttl_seconds
        self._sessions: dict[str, SessionRecord] = {}
        self._lock = Lock()

    def create_session(self, username: str) -> str:
        token = secrets.token_urlsafe(32)
        with self._lock:
            self._sessions[token] = SessionRecord(
                username=username,
                expires_at=time.time() + self._ttl_seconds,
            )
        return token

    def resolve_session(self, token: str) -> str | None:
        with self._lock:
            record = self._sessions.get(token)
            if record is None:
                return None
            if record.expires_at <= time.time():
                self._sessions.pop(token, None)
                return None
            return record.username

    def revoke_session(self, token: str) -> None:
        with self._lock:
            self._sessions.pop(token, None)
