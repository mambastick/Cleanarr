from __future__ import annotations

import time

import jwt
import pytest
import respx
from cryptography.hazmat.primitives.asymmetric import rsa
from httpx import Response

from cleanarr.infrastructure.oidc import (
    OIDCError,
    OIDCMetadata,
    create_pkce_challenge,
    discover_oidc_provider,
    validate_id_token,
)


def _signing_material() -> tuple[rsa.RSAPrivateKey, dict[str, object]]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_jwk = jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key(), as_dict=True)
    public_jwk.update({"kid": "cleanarr-test-key", "alg": "RS256", "use": "sig"})
    return private_key, public_jwk


def _metadata() -> OIDCMetadata:
    return OIDCMetadata(
        issuer="https://id.example/realms/cleanarr",
        authorization_endpoint="https://id.example/authorize",
        token_endpoint="https://id.example/token",
        jwks_uri="https://id.example/jwks",
        signing_algorithms=frozenset({"RS256"}),
        token_endpoint_auth_methods=frozenset({"client_secret_basic"}),
    )


def _token(private_key: rsa.RSAPrivateKey, **overrides: object) -> str:
    now = int(time.time())
    claims: dict[str, object] = {
        "iss": _metadata().issuer,
        "sub": "subject-1",
        "aud": "cleanarr",
        "iat": now,
        "exp": now + 300,
        "nonce": "expected-nonce",
        "preferred_username": "admin",
    }
    claims.update(overrides)
    return jwt.encode(
        claims,
        private_key,
        algorithm="RS256",
        headers={"kid": "cleanarr-test-key"},
    )


def test_pkce_s256_matches_rfc_7636_vector() -> None:
    assert create_pkce_challenge("dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk") == (
        "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"
    )


def test_id_token_requires_valid_signature_audience_issuer_expiry_and_nonce() -> None:
    private_key, public_jwk = _signing_material()
    token = _token(private_key)

    claims = validate_id_token(
        token,
        jwks={"keys": [public_jwk]},
        metadata=_metadata(),
        client_id="cleanarr",
        expected_nonce="expected-nonce",
    )

    assert claims["sub"] == "subject-1"

    for override, expected_message in (
        ({"aud": "other-client"}, "validation failed"),
        ({"iss": "https://attacker.example"}, "validation failed"),
        ({"exp": int(time.time()) - 60}, "validation failed"),
        ({"nonce": "wrong"}, "nonce validation failed"),
    ):
        with pytest.raises(OIDCError, match=expected_message):
            validate_id_token(
                _token(private_key, **override),
                jwks={"keys": [public_jwk]},
                metadata=_metadata(),
                client_id="cleanarr",
                expected_nonce="expected-nonce",
            )


def test_multiple_audiences_require_matching_authorized_party() -> None:
    private_key, public_jwk = _signing_material()

    with pytest.raises(OIDCError, match="authorized party"):
        validate_id_token(
            _token(private_key, aud=["cleanarr", "other"], azp="other"),
            jwks={"keys": [public_jwk]},
            metadata=_metadata(),
            client_id="cleanarr",
            expected_nonce="expected-nonce",
        )


@pytest.mark.asyncio
async def test_discovery_rejects_insecure_mismatched_and_oversized_metadata() -> None:
    issuer = "https://id.example/realms/cleanarr"
    discovery_url = f"{issuer}/.well-known/openid-configuration"
    valid_endpoints = {
        "authorization_endpoint": "https://id.example/authorize",
        "token_endpoint": "https://id.example/token",
        "jwks_uri": "https://id.example/jwks",
    }

    with pytest.raises(OIDCError, match="must use HTTPS"):
        await discover_oidc_provider("http://id.example/realms/cleanarr")

    with respx.mock:
        respx.get(discovery_url).mock(
            return_value=Response(200, json={"issuer": "https://attacker.example", **valid_endpoints})
        )
        with pytest.raises(OIDCError, match="does not exactly match"):
            await discover_oidc_provider(issuer)

    with respx.mock:
        respx.get(discovery_url).mock(return_value=Response(200, content=b'{"padding":"' + b"x" * 300_000 + b'"}'))
        with pytest.raises(OIDCError, match="too large"):
            await discover_oidc_provider(issuer)
