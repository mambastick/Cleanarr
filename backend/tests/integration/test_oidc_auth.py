from __future__ import annotations

import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import jwt
import pytest
import respx
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient, Response

from cleanarr.api.app import create_app
from cleanarr.domain.config import GeneralConfig, SSOAuthMode
from cleanarr.infrastructure.container import ServiceContainer
from cleanarr.infrastructure.settings import Settings


@asynccontextmanager
async def app_client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client


def _settings(tmp_path: Path) -> Settings:
    return Settings.model_construct(
        db_path=str(tmp_path / "cleanarr.db"),
        config_state_path=str(tmp_path / "runtime-config.json"),
        admin_shared_token=None,
        log_level="INFO",
        dry_run=True,
        webhook_shared_token="secret-token",
        http_timeout_seconds=5.0,
        radarr_url=None,
        radarr_api_key=None,
        sonarr_url=None,
        sonarr_api_key=None,
        seerr_url=None,
        seerr_api_key=None,
        downloader_kind="qbittorrent",
        qbittorrent_url=None,
        qbittorrent_username=None,
        qbittorrent_password=None,
    )


@pytest.mark.asyncio
async def test_oidc_code_flow_uses_pkce_nonce_jwks_and_explicit_access_policy(tmp_path: Path) -> None:
    issuer = "https://id.example/realms/cleanarr"
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_jwk = jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key(), as_dict=True)
    public_jwk.update({"kid": "oidc-test-key", "alg": "RS256", "use": "sig"})
    metadata = {
        "issuer": issuer,
        "authorization_endpoint": "https://id.example/authorize",
        "token_endpoint": "https://id.example/token",
        "jwks_uri": "https://id.example/jwks",
        "id_token_signing_alg_values_supported": ["RS256"],
        "token_endpoint_auth_methods_supported": ["client_secret_basic"],
        "code_challenge_methods_supported": ["S256"],
    }

    container = ServiceContainer.from_settings(_settings(tmp_path))
    container.config_service.update_general(
        GeneralConfig(
            sso_mode=SSOAuthMode.SSO_ONLY,
            sso_issuer_url=issuer,
            sso_client_id="cleanarr",
            sso_client_secret="client-secret",
            sso_redirect_uri="http://test/api/auth/sso/callback",
            sso_allowed_users=["admin@example.com"],
        )
    )
    await container.refresh_runtime()
    app = create_app(container=container)

    with respx.mock:
        discovery = respx.get(f"{issuer}/.well-known/openid-configuration").mock(
            return_value=Response(200, json=metadata)
        )
        token_route = respx.post("https://id.example/token")
        respx.get("https://id.example/jwks").mock(return_value=Response(200, json={"keys": [public_jwk]}))

        async with app_client(app) as client:
            start = await client.get("/api/auth/sso/start")
            authorize_query = parse_qs(urlsplit(start.json()["authorize_url"]).query)
            now = int(time.time())
            id_token = jwt.encode(
                {
                    "iss": issuer,
                    "sub": "subject-1",
                    "aud": "cleanarr",
                    "iat": now,
                    "exp": now + 300,
                    "nonce": authorize_query["nonce"][0],
                    "preferred_username": "admin",
                    "email": "admin@example.com",
                },
                private_key,
                algorithm="RS256",
                headers={"kid": "oidc-test-key"},
            )
            token_route.mock(return_value=Response(200, json={"id_token": id_token}))

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as other_browser:
                unbound_callback = await other_browser.get(
                    "/api/auth/sso/callback",
                    params={"code": "authorization-code", "state": authorize_query["state"][0]},
                )
            callback = await client.get(
                "/api/auth/sso/callback",
                params={"code": "authorization-code", "state": authorize_query["state"][0]},
            )
            status = await client.get("/api/auth/status")

    assert start.status_code == 200
    assert authorize_query["code_challenge_method"] == ["S256"]
    assert authorize_query["code_challenge"][0]
    assert authorize_query["nonce"][0]
    assert "cleanarr_sso_state=" in start.headers["set-cookie"]
    assert "HttpOnly" in start.headers["set-cookie"]
    assert "SameSite=lax" in start.headers["set-cookie"]
    assert "Path=/api/auth/sso/callback" in start.headers["set-cookie"]
    assert unbound_callback.status_code == 303
    assert "Invalid%20or%20expired%20SSO%20browser%20state" in unbound_callback.headers["location"]
    assert callback.status_code == 303
    assert callback.headers["location"] == "/"
    callback_cookies = callback.headers.get_list("set-cookie")
    assert any(cookie.startswith("cleanarr_session=") and "HttpOnly" in cookie for cookie in callback_cookies)
    assert any(cookie.startswith("cleanarr_sso_state=") and "Max-Age=0" in cookie for cookie in callback_cookies)
    assert status.json()["authenticated"] is True
    assert status.json()["username"] == "admin"
    assert status.json()["csrf_token"]
    assert discovery.call_count == 2
    token_request = token_route.calls[0].request
    token_body = parse_qs(token_request.content.decode())
    assert token_body["code_verifier"][0]
    assert token_body["redirect_uri"] == ["http://test/api/auth/sso/callback"]
    assert token_request.headers["authorization"].startswith("Basic ")
    assert token_route.call_count == 1

    await container.close()
