"""Strict OpenID Connect discovery, code exchange, and ID-token validation."""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import httpx
import jwt

_SAFE_ID_TOKEN_ALGORITHMS = frozenset(
    {
        "RS256",
        "RS384",
        "RS512",
        "PS256",
        "PS384",
        "PS512",
        "ES256",
        "ES384",
        "ES512",
        "EdDSA",
    }
)
_MAX_METADATA_BYTES = 256 * 1024
_MAX_JWKS_BYTES = 1024 * 1024


class OIDCError(RuntimeError):
    """Raised when discovery, exchange, or validation fails closed."""


@dataclass(frozen=True)
class OIDCMetadata:
    """Validated provider endpoints and advertised capabilities."""

    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    jwks_uri: str
    signing_algorithms: frozenset[str]
    token_endpoint_auth_methods: frozenset[str]


def create_pkce_challenge(code_verifier: str) -> str:
    """Create an RFC 7636 S256 challenge without base64 padding."""

    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


async def discover_oidc_provider(issuer_url: str) -> OIDCMetadata:
    """Fetch discovery metadata and bind it to the configured issuer exactly."""

    _validate_oidc_url(issuer_url, label="issuer")
    discovery_url = f"{issuer_url.rstrip('/')}/.well-known/openid-configuration"
    payload = await _get_json(discovery_url, max_bytes=_MAX_METADATA_BYTES)

    discovered_issuer = payload.get("issuer")
    if not isinstance(discovered_issuer, str) or discovered_issuer != issuer_url:
        raise OIDCError("OpenID discovery issuer does not exactly match the configured issuer.")

    authorization_endpoint = _required_endpoint(payload, "authorization_endpoint")
    token_endpoint = _required_endpoint(payload, "token_endpoint")
    jwks_uri = _required_endpoint(payload, "jwks_uri")

    advertised_algorithms = _string_set(payload.get("id_token_signing_alg_values_supported"))
    signing_algorithms = frozenset(advertised_algorithms.intersection(_SAFE_ID_TOKEN_ALGORITHMS))
    if not advertised_algorithms:
        signing_algorithms = frozenset({"RS256"})
    if not signing_algorithms:
        raise OIDCError("OpenID provider does not advertise a supported asymmetric ID-token algorithm.")

    auth_methods = _string_set(payload.get("token_endpoint_auth_methods_supported"))
    if not auth_methods:
        auth_methods = {"client_secret_basic"}
    supported_auth_methods = frozenset(auth_methods.intersection({"client_secret_basic", "client_secret_post"}))
    if not supported_auth_methods:
        raise OIDCError("OpenID provider does not advertise a supported client authentication method.")

    return OIDCMetadata(
        issuer=discovered_issuer,
        authorization_endpoint=authorization_endpoint,
        token_endpoint=token_endpoint,
        jwks_uri=jwks_uri,
        signing_algorithms=signing_algorithms,
        token_endpoint_auth_methods=supported_auth_methods,
    )


async def exchange_authorization_code(
    metadata: OIDCMetadata,
    *,
    code: str,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    code_verifier: str,
) -> dict[str, Any]:
    """Exchange one authorization code while binding it to the PKCE verifier."""

    data = {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "code_verifier": code_verifier,
    }
    auth: tuple[str, str] | None = None
    if "client_secret_basic" in metadata.token_endpoint_auth_methods:
        auth = (client_id, client_secret)
    else:
        data["client_secret"] = client_secret

    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=False) as client:
            if auth is None:
                request = client.stream(
                    "POST",
                    metadata.token_endpoint,
                    data=data,
                    headers={"Accept": "application/json"},
                )
            else:
                request = client.stream(
                    "POST",
                    metadata.token_endpoint,
                    data=data,
                    auth=auth,
                    headers={"Accept": "application/json"},
                )
            async with request as response:
                response.raise_for_status()
                payload = await _read_json_response(response, max_bytes=_MAX_METADATA_BYTES)
    except httpx.HTTPError as exc:
        raise OIDCError("OpenID token exchange failed.") from exc

    if not isinstance(payload, dict):
        raise OIDCError("OpenID token response must be an object.")
    return payload


async def fetch_jwks(metadata: OIDCMetadata) -> dict[str, Any]:
    """Fetch the provider signing-key set from its validated discovery URI."""

    return await _get_json(metadata.jwks_uri, max_bytes=_MAX_JWKS_BYTES)


def validate_id_token(
    raw_token: object,
    *,
    jwks: dict[str, Any],
    metadata: OIDCMetadata,
    client_id: str,
    expected_nonce: str,
) -> dict[str, Any]:
    """Validate signature, algorithm, standard claims, audience, and nonce."""

    if not isinstance(raw_token, str) or not raw_token:
        raise OIDCError("OpenID token response does not include an ID token.")
    try:
        header = jwt.get_unverified_header(raw_token)
    except jwt.PyJWTError as exc:
        raise OIDCError("OpenID ID token header is invalid.") from exc

    algorithm = header.get("alg")
    key_id = header.get("kid")
    if not isinstance(algorithm, str) or algorithm not in metadata.signing_algorithms:
        raise OIDCError("OpenID ID token uses an unsupported signing algorithm.")
    if not isinstance(key_id, str) or not key_id:
        raise OIDCError("OpenID ID token does not identify a signing key.")

    try:
        key_set = jwt.PyJWKSet.from_dict(jwks)
    except (jwt.PyJWTError, ValueError, TypeError) as exc:
        raise OIDCError("OpenID signing-key set is invalid.") from exc
    matching_keys = [key for key in key_set.keys if key.key_id == key_id and key.algorithm_name == algorithm]
    if len(matching_keys) != 1:
        raise OIDCError("OpenID signing key is missing or ambiguous.")

    try:
        claims = jwt.decode(
            raw_token,
            matching_keys[0],
            algorithms=[algorithm],
            audience=client_id,
            issuer=metadata.issuer,
            leeway=30,
            options={"require": ["iss", "sub", "aud", "exp", "iat", "nonce"]},
        )
    except jwt.PyJWTError as exc:
        raise OIDCError("OpenID ID token validation failed.") from exc

    nonce = claims.get("nonce")
    if not isinstance(nonce, str) or nonce != expected_nonce:
        raise OIDCError("OpenID ID token nonce validation failed.")

    audience = claims.get("aud")
    if isinstance(audience, list) and len(audience) > 1:
        authorized_party = claims.get("azp")
        if not isinstance(authorized_party, str) or authorized_party != client_id:
            raise OIDCError("OpenID ID token authorized party is invalid.")

    return claims


async def _get_json(url: str, *, max_bytes: int) -> dict[str, Any]:
    _validate_oidc_url(url, label="provider endpoint")
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=False) as client:
            async with client.stream("GET", url, headers={"Accept": "application/json"}) as response:
                response.raise_for_status()
                payload = await _read_json_response(response, max_bytes=max_bytes)
    except httpx.HTTPError as exc:
        raise OIDCError("Could not fetch OpenID provider metadata.") from exc
    if not isinstance(payload, dict):
        raise OIDCError("OpenID provider response must be an object.")
    return payload


async def _read_json_response(response: httpx.Response, *, max_bytes: int) -> object:
    content = bytearray()
    async for chunk in response.aiter_bytes():
        content.extend(chunk)
        if len(content) > max_bytes:
            raise OIDCError("OpenID provider response is too large.")
    try:
        return json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OIDCError("OpenID provider response is not valid JSON.") from exc


def _required_endpoint(payload: dict[str, Any], name: str) -> str:
    value = payload.get(name)
    if not isinstance(value, str) or not value:
        raise OIDCError(f"OpenID provider does not expose {name}.")
    _validate_oidc_url(value, label=name)
    return value


def _validate_oidc_url(value: str, *, label: str) -> None:
    parsed = urlsplit(value)
    if parsed.username or parsed.password or parsed.query or parsed.fragment or not parsed.hostname:
        raise OIDCError(f"OpenID {label} URL is invalid.")
    is_loopback = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    if parsed.scheme != "https" and not (parsed.scheme == "http" and is_loopback):
        raise OIDCError(f"OpenID {label} URL must use HTTPS (HTTP is allowed only for loopback development).")


def _string_set(value: object) -> set[str]:
    if not isinstance(value, list):
        return set()
    return {entry for entry in value if isinstance(entry, str) and entry}
