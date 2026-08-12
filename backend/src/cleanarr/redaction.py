"""Shared credential redaction for logs and persisted/API diagnostic data."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

_URL_USERINFO_RE = re.compile(r"(?P<scheme>https?://)[^/@\s]+@", re.IGNORECASE)
_AUTHORIZATION_RE = re.compile(r"(?i)(\bauthorization\b\s*[:=]\s*(?:bearer\s+)?|\bbearer\b\s+)[^\s,;]+")
_SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)(\b(?:api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret|password|token)\b"
    r"[\"']?\s*[:=]\s*[\"']?)[^\s,;\"'}]+"
)
_SECRET_QUERY_RE = re.compile(
    r"(?i)([?&](?:api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret|password|token)=)[^&\s]+"
)
_SECRET_KEY_RE = re.compile(r"[^a-z0-9]+")


def redact_sensitive_text(value: str) -> str:
    """Best-effort defense against credentials reaching diagnostics."""

    redacted = _URL_USERINFO_RE.sub(r"\g<scheme>[redacted]@", value)
    redacted = _SECRET_QUERY_RE.sub(r"\1[redacted]", redacted)
    redacted = _AUTHORIZATION_RE.sub(r"\1[redacted]", redacted)
    return _SECRET_ASSIGNMENT_RE.sub(r"\1[redacted]", redacted)


def redact_sensitive_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    """Recursively redact secret-bearing keys and credential-looking strings."""

    return {key: _redact_value(item, key=key) for key, item in value.items()}


def _redact_value(value: Any, *, key: str | None = None) -> Any:
    if key is not None and _is_secret_key(key):
        return "[redacted]"
    if isinstance(value, str):
        return redact_sensitive_text(value)
    if isinstance(value, Mapping):
        return redact_sensitive_mapping(value)
    if isinstance(value, list):
        return [_redact_value(item) for item in value]
    if isinstance(value, tuple):
        return [_redact_value(item) for item in value]
    return value


def _is_secret_key(value: str) -> bool:
    normalized = _SECRET_KEY_RE.sub("", value.casefold())
    return normalized in {"authorization", "cookie", "setcookie"} or normalized.endswith(
        ("apikey", "password", "secret", "token")
    )
