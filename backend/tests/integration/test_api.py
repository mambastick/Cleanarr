"""API-level tests."""

from __future__ import annotations

from pathlib import Path

import pytest
import respx
from httpx import ASGITransport, AsyncClient

from cleanarr.api.app import create_app
from cleanarr.domain import (
    ActionResult,
    ActionStatus,
    ItemType,
    MediaDeletionEvent,
    MediaFingerprint,
    OverallStatus,
    ProcessingResult,
)
from cleanarr.domain.config import GeneralConfig, RuntimeConfig
from cleanarr.infrastructure.container import ServiceContainer
from cleanarr.infrastructure.settings import Settings
from tests.fakes import FakeService


class FakeAuthService:
    """Minimal auth service for API tests."""

    def resolve_session(self, session_token: str | None) -> str | None:
        if session_token == "session-token":
            return "admin"
        return None

    def get_status(self, session_token: str | None):  # type: ignore[no-untyped-def]
        username = self.resolve_session(session_token)
        return type(
            "Status",
            (),
            {
                "admin_configured": True,
                "requires_registration": False,
                "authenticated": username is not None,
                "username": username,
            },
        )()

    def register_admin(self, *, username: str, password: str):  # type: ignore[no-untyped-def]
        return type("Session", (), {"username": username, "token": "session-token"})()

    def login(self, *, username: str, password: str):  # type: ignore[no-untyped-def]
        return type("Session", (), {"username": username, "token": "session-token"})()

    def logout(self, session_token: str | None) -> None:
        return None


class FakeContainer:
    """Minimal container for API tests."""

    def __init__(self, service: FakeService) -> None:
        self.settings = Settings.model_construct(
            log_level="INFO",
            dry_run=True,
            webhook_shared_token="secret-token",
            http_timeout_seconds=5.0,
            radarr_url="http://radarr",
            radarr_api_key="radarr-key",
            sonarr_url="http://sonarr",
            sonarr_api_key="sonarr-key",
            jellyseerr_url="http://jellyseerr",
            jellyseerr_api_key="jellyseerr-key",
            downloader_kind="qbittorrent",
            qbittorrent_url="http://qbt",
            qbittorrent_username="user",
            qbittorrent_password="pass",
            admin_shared_token="admin-token",
            config_state_path="/tmp/test-runtime-config.json",
        )
        self.config = RuntimeConfig(
            general=GeneralConfig(
                dry_run=True,
                log_level="INFO",
                webhook_shared_token="secret-token",
                http_timeout_seconds=5.0,
            )
        )
        self.service = service
        self.admin_shared_token = "admin-token"
        self.webhook_shared_token = "secret-token"
        self.config_service = None
        self.auth_service = FakeAuthService()

    async def close(self) -> None:
        return None


@pytest.mark.asyncio
async def test_webhook_endpoint_accepts_array_payloads() -> None:
    result = ProcessingResult(
        event=MediaDeletionEvent(
            notification_type="ItemDeleted",
            item_type=ItemType.MOVIE,
            item_id="m1",
            name="Movie",
            fingerprint=MediaFingerprint(tmdb_id=1),
        ),
        status=OverallStatus.SUCCESS,
        actions=(ActionResult(system="radarr", action="delete_movie", status=ActionStatus.DELETED, message="ok"),),
    )
    service = FakeService(results=[result, result])
    app = create_app(container=FakeContainer(service))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/webhook/jellyfin",
            headers={"X-Webhook-Token": "secret-token"},
            json=[
                {
                    "notification_type": "ItemDeleted",
                    "item_type": "Movie",
                    "item_id": "m1",
                    "name": "Movie",
                    "tmdb_id": 1,
                },
                {
                    "notification_type": "ItemDeleted",
                    "item_type": "Movie",
                    "item_id": "m2",
                    "name": "Movie 2",
                    "tmdb_id": 2,
                },
            ],
        )

    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert len(service.seen_events) == 2


@pytest.mark.asyncio
async def test_webhook_endpoint_rejects_bad_token() -> None:
    service = FakeService(results=[])
    app = create_app(container=FakeContainer(service))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/webhook/jellyfin",
            headers={"X-Webhook-Token": "bad-token"},
            json={
                "notification_type": "ItemDeleted",
                "item_type": "Movie",
                "item_id": "m1",
                "name": "Movie",
                "tmdb_id": 1,
            },
        )
        dashboard_response = await client.get("/api/dashboard")

    assert response.status_code == 401
    assert dashboard_response.status_code == 200
    assert dashboard_response.json()["webhook_status"]["outcome"] == "rejected_auth"
    assert dashboard_response.json()["webhook_status"]["http_status"] == 401


@pytest.mark.asyncio
async def test_dashboard_endpoint_exposes_recent_activity() -> None:
    result = ProcessingResult(
        event=MediaDeletionEvent(
            notification_type="ItemDeleted",
            item_type=ItemType.EPISODE,
            item_id="ep1",
            name="Pilot",
            fingerprint=MediaFingerprint(tvdb_id=7),
            season_number=1,
            episode_number=1,
        ),
        status=OverallStatus.PARTIAL_FAILURE,
        actions=(
            ActionResult(system="sonarr", action="unmonitor_episodes", status=ActionStatus.DELETED, message="ok"),
            ActionResult(
                system="downloader",
                action="delete_hash",
                status=ActionStatus.SKIPPED,
                message="pack torrent",
            ),
        ),
    )
    service = FakeService(results=[result])
    app = create_app(container=FakeContainer(service))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        webhook_response = await client.post(
            "/webhook/jellyfin",
            headers={"X-Webhook-Token": "secret-token"},
            json={
                "notification_type": "ItemDeleted",
                "item_type": "Episode",
                "item_id": "ep1",
                "name": "Pilot",
                "tvdb_id": 7,
                "season_number": 1,
                "episode_number": 1,
            },
        )
        dashboard_response = await client.get("/api/dashboard")

    assert webhook_response.status_code == 200
    assert dashboard_response.status_code == 200

    payload = dashboard_response.json()
    assert payload["service"]["name"] == "CleanArr"
    assert payload["service"]["dry_run"] is True
    assert payload["downstream"][0]["name"] == "Radarr"
    assert '"notification_type": "{{json_encode NotificationType}}"' in payload["jellyfin_template"]
    assert len(payload["recent_activity"]) == 1
    assert payload["recent_activity"][0]["result"]["item_id"] == "ep1"
    assert payload["recent_activity"][0]["action_summary"]["deleted"] == 1
    assert payload["recent_activity"][0]["action_summary"]["skipped"] == 1
    assert payload["webhook_status"]["outcome"] == "processed"
    assert payload["webhook_status"]["item_name"] == "Pilot"
    assert payload["webhook_status"]["item_type"] == "Episode"
    assert payload["webhook_status"]["result_status"] == "partial_failure"


@pytest.mark.asyncio
async def test_webhook_endpoint_accepts_jellyfin_locale_datetime() -> None:
    result = ProcessingResult(
        event=MediaDeletionEvent(
            notification_type="ItemDeleted",
            item_type=ItemType.MOVIE,
            item_id="m-locale",
            name="Locale Movie",
            fingerprint=MediaFingerprint(tmdb_id=14160, imdb_id="tt1049413"),
        ),
        status=OverallStatus.IGNORED,
        actions=(
            ActionResult(
                system="radarr",
                action="resolve_movie",
                status=ActionStatus.SKIPPED,
                message="No strict Radarr movie match was found.",
            ),
        ),
    )
    service = FakeService(results=[result])
    app = create_app(container=FakeContainer(service))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/webhook/jellyfin",
            headers={"X-Webhook-Token": "secret-token"},
            json={
                "notification_type": "ItemDeleted",
                "item_type": "Movie",
                "item_id": "m-locale",
                "name": "Locale Movie",
                "tmdb_id": 14160,
                "imdb_id": "tt1049413",
                "occurred_at": "03/14/2026 19:12:34",
            },
        )

    assert response.status_code == 200
    assert response.json()["status"] == "ignored"
    assert service.seen_events[0].occurred_at is not None


@pytest.mark.asyncio
async def test_dashboard_endpoint_exposes_invalid_payload_webhook_status() -> None:
    service = FakeService(results=[])
    app = create_app(container=FakeContainer(service))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        webhook_response = await client.post(
            "/webhook/jellyfin",
            headers={"X-Webhook-Token": "secret-token"},
            json={"notification_type": "ItemDeleted"},
        )
        dashboard_response = await client.get("/api/dashboard")

    assert webhook_response.status_code == 422
    assert dashboard_response.status_code == 200
    assert dashboard_response.json()["webhook_status"]["outcome"] == "invalid_payload"
    assert dashboard_response.json()["webhook_status"]["http_status"] == 422


@pytest.mark.asyncio
async def test_runtime_config_endpoints_persist_and_rebuild(tmp_path: Path) -> None:
    settings = Settings.model_construct(
        config_state_path=str(tmp_path / "runtime-config.json"),
        admin_shared_token="admin-token",
        log_level="INFO",
        dry_run=True,
        webhook_shared_token="secret-token",
        http_timeout_seconds=5.0,
        radarr_url=None,
        radarr_api_key=None,
        sonarr_url=None,
        sonarr_api_key=None,
        jellyseerr_url=None,
        jellyseerr_api_key=None,
        downloader_kind="qbittorrent",
        qbittorrent_url=None,
        qbittorrent_username=None,
        qbittorrent_password=None,
    )
    container = ServiceContainer.from_settings(settings)
    app = create_app(container=container)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        initial = await client.get("/api/config", headers={"X-Admin-Token": "admin-token"})
        create_radarr = await client.post(
            "/api/config/radarr",
            headers={"X-Admin-Token": "admin-token"},
            json={
                "name": "Movies",
                "url": "http://radarr.example/api/v3",
                "api_key": "radarr-key",
                "enabled": True,
                "is_default": True,
            },
        )
        update_general = await client.put(
            "/api/config/general",
            headers={"X-Admin-Token": "admin-token"},
            json={
                "dry_run": False,
                "log_level": "debug",
                "webhook_shared_token": "next-token",
                "http_timeout_seconds": 17,
            },
        )
        created_id = create_radarr.json()["radarr"][0]["id"]
        delete_radarr = await client.delete(
            f"/api/config/radarr/{created_id}",
            headers={"X-Admin-Token": "admin-token"},
        )

    assert initial.status_code == 200
    assert initial.json()["radarr"] == []
    assert create_radarr.status_code == 200
    assert create_radarr.json()["radarr"][0]["name"] == "Movies"
    assert update_general.status_code == 200
    assert update_general.json()["general"]["dry_run"] is False
    assert update_general.json()["general"]["log_level"] == "DEBUG"
    assert delete_radarr.status_code == 204
    assert container.webhook_shared_token == "next-token"

    await container.close()


@pytest.mark.asyncio
async def test_first_run_config_does_not_seed_integrations_from_env(tmp_path: Path) -> None:
    settings = Settings.model_construct(
        config_state_path=str(tmp_path / "runtime-config.json"),
        admin_shared_token="admin-token",
        log_level="INFO",
        dry_run=True,
        webhook_shared_token="secret-token",
        http_timeout_seconds=5.0,
        radarr_url="http://radarr.example/api/v3",
        radarr_api_key="radarr-key",
        sonarr_url="http://sonarr.example/api/v3",
        sonarr_api_key="sonarr-key",
        jellyseerr_url="http://jellyseerr.example/api/v1",
        jellyseerr_api_key="jellyseerr-key",
        downloader_kind="qbittorrent",
        qbittorrent_url="http://qbt.example",
        qbittorrent_username="user",
        qbittorrent_password="pass",
    )
    container = ServiceContainer.from_settings(settings)
    app = create_app(container=container)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/config", headers={"X-Admin-Token": "admin-token"})

    assert response.status_code == 200
    assert response.json()["radarr"] == []
    assert response.json()["sonarr"] == []
    assert response.json()["jellyseerr"] == []
    assert response.json()["downloaders"] == []
    assert response.json()["general"]["webhook_shared_token"] == "secret-token"

    await container.close()


@pytest.mark.asyncio
@respx.mock
async def test_runtime_config_connection_test_returns_structured_failure(tmp_path: Path) -> None:
    settings = Settings.model_construct(
        config_state_path=str(tmp_path / "runtime-config.json"),
        admin_shared_token="admin-token",
        log_level="INFO",
        dry_run=True,
        webhook_shared_token="secret-token",
        http_timeout_seconds=5.0,
        radarr_url=None,
        radarr_api_key=None,
        sonarr_url=None,
        sonarr_api_key=None,
        jellyseerr_url=None,
        jellyseerr_api_key=None,
        downloader_kind="qbittorrent",
        qbittorrent_url=None,
        qbittorrent_username=None,
        qbittorrent_password=None,
    )
    container = ServiceContainer.from_settings(settings)
    app = create_app(container=container)
    respx.post("http://qbt/api/v2/auth/login").respond(status_code=403, text="Fails.")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/config/downloaders/qbittorrent/test",
            headers={"X-Admin-Token": "admin-token"},
            json={
                "name": "qBittorrent",
                "url": "http://qbt",
                "username": "bad-user",
                "password": "bad-pass",
                "enabled": True,
                "is_default": True,
            },
        )

    assert response.status_code == 200
    assert response.json()["ok"] is False
    assert "rejected the configured credentials" in response.json()["message"]

    await container.close()


@pytest.mark.asyncio
@respx.mock
async def test_sonarr_test_endpoint_normalizes_plain_base_url_to_api_v3(tmp_path: Path) -> None:
    settings = Settings.model_construct(
        config_state_path=str(tmp_path / "runtime-config.json"),
        admin_shared_token="admin-token",
        log_level="INFO",
        dry_run=True,
        webhook_shared_token="secret-token",
        http_timeout_seconds=5.0,
        radarr_url=None,
        radarr_api_key=None,
        sonarr_url=None,
        sonarr_api_key=None,
        jellyseerr_url=None,
        jellyseerr_api_key=None,
        downloader_kind="qbittorrent",
        qbittorrent_url=None,
        qbittorrent_username=None,
        qbittorrent_password=None,
    )
    container = ServiceContainer.from_settings(settings)
    app = create_app(container=container)
    route = respx.get("https://sonarr.example.com/api/v3/series").respond(status_code=200, json=[])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/config/sonarr/test",
            headers={"X-Admin-Token": "admin-token"},
            json={
                "name": "Sonarr",
                "url": "https://sonarr.example.com",
                "api_key": "key",
                "enabled": True,
                "is_default": True,
            },
        )

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert route.called

    await container.close()


@pytest.mark.asyncio
@respx.mock
async def test_jellyseerr_test_endpoint_normalizes_plain_base_url_to_api_v1(tmp_path: Path) -> None:
    settings = Settings.model_construct(
        config_state_path=str(tmp_path / "runtime-config.json"),
        admin_shared_token="admin-token",
        log_level="INFO",
        dry_run=True,
        webhook_shared_token="secret-token",
        http_timeout_seconds=5.0,
        radarr_url=None,
        radarr_api_key=None,
        sonarr_url=None,
        sonarr_api_key=None,
        jellyseerr_url=None,
        jellyseerr_api_key=None,
        downloader_kind="qbittorrent",
        qbittorrent_url=None,
        qbittorrent_username=None,
        qbittorrent_password=None,
    )
    container = ServiceContainer.from_settings(settings)
    app = create_app(container=container)
    route = respx.get("https://jellyseerr.example.com/api/v1/media").respond(
        status_code=200,
        json={"pageInfo": {"results": 0}, "results": []},
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/config/jellyseerr/test",
            headers={"X-Admin-Token": "admin-token"},
            json={
                "name": "Jellyseerr",
                "url": "https://jellyseerr.example.com",
                "api_key": "key",
                "enabled": True,
                "is_default": True,
            },
        )

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert route.called

    await container.close()


@pytest.mark.asyncio
async def test_first_run_admin_registration_enables_session_auth(tmp_path: Path) -> None:
    settings = Settings.model_construct(
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
        jellyseerr_url=None,
        jellyseerr_api_key=None,
        downloader_kind="qbittorrent",
        qbittorrent_url=None,
        qbittorrent_username=None,
        qbittorrent_password=None,
    )
    container = ServiceContainer.from_settings(settings)
    app = create_app(container=container)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        status_before = await client.get("/api/auth/status")
        register = await client.post(
            "/api/auth/register",
            json={"username": "admin", "password": "super-secret-123"},
        )
        session_token = register.json()["token"]
        status_after = await client.get(
            "/api/auth/status",
            headers={"Authorization": f"Bearer {session_token}"},
        )
        config_response = await client.get(
            "/api/config",
            headers={"Authorization": f"Bearer {session_token}"},
        )

    assert status_before.status_code == 200
    assert status_before.json()["requires_registration"] is True
    assert register.status_code == 200
    assert status_after.status_code == 200
    assert status_after.json()["authenticated"] is True
    assert status_after.json()["username"] == "admin"
    assert config_response.status_code == 200

    await container.close()
