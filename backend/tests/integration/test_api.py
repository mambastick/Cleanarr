"""API-level tests."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
import respx
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from cleanarr.api.app import create_app
from cleanarr.application.strategies import DeletionStrategyFactory
from cleanarr.domain import (
    ActionResult,
    ActionStatus,
    FailureReason,
    ItemType,
    MediaDeletionEvent,
    MediaFingerprint,
    OverallStatus,
    ProcessingResult,
    RadarrHistoryRecord,
    RadarrMovie,
)
from cleanarr.domain.config import GeneralConfig, RadarrServiceConfig, RuntimeConfig
from cleanarr.infrastructure.container import ServiceContainer
from cleanarr.infrastructure.settings import Settings
from tests.fakes import (
    FakeDownloaderClient,
    FakeRadarrClient,
    FakeSeerrClient,
    FakeService,
    FakeSonarrClient,
)


@asynccontextmanager
async def app_client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    """Run the application lifespan around an in-process HTTP client."""

    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client


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
                "csrf_token": "csrf-token" if username else None,
                "sso_enabled": False,
                "sso_mode": "password_only",
                "sso_configured": False,
            },
        )()

    def register_admin(self, *, username: str, password: str):  # type: ignore[no-untyped-def]
        return type(
            "Session",
            (),
            {"username": username, "token": "session-token", "csrf_token": "csrf-token"},
        )()

    def login(self, *, username: str, password: str, source: str = "unknown"):  # type: ignore[no-untyped-def]
        return type(
            "Session",
            (),
            {"username": username, "token": "session-token", "csrf_token": "csrf-token"},
        )()

    def verify_csrf_token(self, session_token: str | None, csrf_token: str | None) -> bool:
        return session_token == "session-token" and csrf_token == "csrf-token"

    def logout(self, session_token: str | None) -> None:
        return None


class FakeContainer:
    """Minimal container for API tests."""

    def __init__(self, service: FakeService, *, db_path: Path) -> None:
        self.settings = Settings.model_construct(
            db_path=str(db_path),
            log_level="INFO",
            dry_run=True,
            webhook_shared_token="secret-token",
            http_timeout_seconds=5.0,
            radarr_url="http://radarr",
            radarr_api_key="radarr-key",
            sonarr_url="http://sonarr",
            sonarr_api_key="sonarr-key",
            seerr_url="http://seerr",
            seerr_api_key="seerr-key",
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
async def test_operational_endpoints_are_authenticated_and_privacy_safe(tmp_path: Path) -> None:
    container = FakeContainer(FakeService(results=[]), db_path=tmp_path / "cleanarr.db")
    container.config = RuntimeConfig(
        general=GeneralConfig(
            dry_run=True,
            webhook_shared_token="webhook-super-secret",
        ),
        radarr=[
            RadarrServiceConfig(
                name="Private Radarr Name",
                url="https://url-user:url-password@radarr.private/api/v3?api_key=query-secret",
                api_key="radarr-super-secret",
            )
        ],
    )
    app = create_app(container=container)
    result = ProcessingResult(
        event=MediaDeletionEvent(
            notification_type="ItemDeleted",
            item_type=ItemType.MOVIE,
            item_id="private-media-id",
            name="Top Secret Movie",
            fingerprint=MediaFingerprint(path="/private/media/top-secret.mkv"),
        ),
        status=OverallStatus.PARTIAL_FAILURE,
        actions=(
            ActionResult(
                system="radarr",
                action="delete_movie",
                status=ActionStatus.FAILED,
                message="Failure mentions radarr-super-secret",
                reason=FailureReason.DOWNSTREAM_ERROR,
                details={"url": "https://radarr.private", "api_key": "detail-super-secret"},
            ),
        ),
        correlation_id="0123456789abcdef0123456789abcdef",
    )

    async with app_client(app) as client:
        await app.state.activity_store.record(result)
        app.state.webhook_attempt_store.record(
            outcome="failed",
            http_status=502,
            message="Top Secret Movie failed with webhook-super-secret",
            item_name="Top Secret Movie",
        )
        app.state.health_probe_store.update("Radarr", "healthy", version="5.0.0 secret-version-payload")
        app.state.health_probe_store.update(
            "Attacker supplied service name",
            "healthy",
            version="secret-version-payload",
        )
        unauthorized_metrics = await client.get("/metrics")
        metrics = await client.get("/metrics", headers={"X-Admin-Token": "admin-token"})
        support = await client.get("/api/support/bundle", headers={"X-Admin-Token": "admin-token"})

    assert unauthorized_metrics.status_code in {401, 403}
    assert metrics.status_code == 200
    assert metrics.headers["content-type"].startswith("text/plain; version=0.0.4")
    assert 'cleanarr_configured_services{service="radarr"} 1' in metrics.text
    assert 'cleanarr_retained_operations{item_type="Movie",status="partial_failure"} 1' in metrics.text
    assert support.status_code == 200
    assert support.json()["recent_errors"][0]["correlation_id"] == "0123456789abcdef0123456789abcdef"
    assert support.json()["recent_errors"][0]["actions"] == [
        {
            "system": "radarr",
            "action": "delete_movie",
            "status": "failed",
            "reason": "downstream_error",
        }
    ]
    combined = metrics.text + support.text
    for sensitive_value in (
        "Top Secret Movie",
        "private-media-id",
        "/private/media/top-secret.mkv",
        "Private Radarr Name",
        "radarr.private",
        "url-password",
        "query-secret",
        "radarr-super-secret",
        "webhook-super-secret",
        "detail-super-secret",
        "Attacker supplied service name",
        "secret-version-payload",
    ):
        assert sensitive_value not in combined


@pytest.mark.asyncio
async def test_manual_delete_requires_and_persists_exact_preflight(tmp_path: Path) -> None:
    service = FakeService(results=[])
    container = FakeContainer(service, db_path=tmp_path / "cleanarr.db")
    radarr = FakeRadarrClient(
        movies=[
            RadarrMovie(
                id=7,
                title="Preflight Movie",
                path="/media/preflight-movie",
                tmdb_id=700,
                imdb_id="tt700",
            )
        ],
        history_by_movie={
            7: [
                RadarrHistoryRecord(
                    id=70,
                    movie_id=7,
                    event_type="grabbed",
                    download_id="HASH700",
                    imported_path=None,
                )
            ]
        },
    )
    sonarr = FakeSonarrClient(
        series=[],
        history_by_series={},
        episodes_by_series={},
        episode_files_by_series={},
    )
    seerr = FakeSeerrClient(media=[], requests=[], issues=[])
    downloader = FakeDownloaderClient(existing_hashes={"HASH700"})
    container.radarr = radarr  # type: ignore[attr-defined]
    container.sonarr = sonarr  # type: ignore[attr-defined]
    container.seerr = seerr  # type: ignore[attr-defined]
    container.downloader = downloader  # type: ignore[attr-defined]
    container.strategy_factory = DeletionStrategyFactory(  # type: ignore[attr-defined]
        dry_run=True,
        logger=logging.getLogger("tests.integration.manual-delete"),
        radarr=radarr,
        sonarr=sonarr,
        seerr=seerr,
        downloader=downloader,
    )
    app = create_app(container=container)
    request = {"item_type": "Movie", "radarr_movie_id": 7}
    headers = {"X-Admin-Token": "admin-token"}

    async with app_client(app) as client:
        preview = await client.post(
            "/api/actions/delete/preview",
            headers=headers,
            json=request,
        )
        unconfirmed = await client.post(
            "/api/actions/delete/jobs",
            headers=headers,
            json=request,
        )
        unconfirmed_legacy = await client.post(
            "/api/actions/delete",
            headers=headers,
            json=request,
        )
        queued = await client.post(
            "/api/actions/delete/jobs",
            headers=headers,
            json={**request, "confirmed_plan_hash": preview.json()["plan_hash"]},
        )

        for _ in range(100):
            job = await client.get(
                f"/api/actions/delete/jobs/{queued.json()['id']}",
                headers=headers,
            )
            if job.json()["status"] == "completed":
                break
            await asyncio.sleep(0.01)
        else:
            raise AssertionError("manual deletion job did not complete")

    assert preview.status_code == 200
    assert preview.json()["plan"]["item_id"] == "manual:radarr:7"
    assert preview.json()["plan"]["fingerprint"]["path"] == "/media/preflight-movie"
    assert any(action["details"].get("hash") == "HASH700" for action in preview.json()["plan"]["actions"])
    assert unconfirmed.status_code == 409
    assert unconfirmed_legacy.status_code == 409
    assert queued.status_code == 202
    assert job.json()["attempt_count"] == 1
    persisted_preflight = job.json()["preflight"]
    original_plan = preview.json()["plan"]
    assert {key: value for key, value in persisted_preflight.items() if key != "correlation_id"} == {
        key: value for key, value in original_plan.items() if key != "correlation_id"
    }
    assert persisted_preflight["correlation_id"]
    assert radarr.deleted_movie_ids == []
    assert downloader.deleted_hashes == []


@pytest.mark.asyncio
async def test_webhook_endpoint_accepts_array_payloads(tmp_path: Path) -> None:
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
    app = create_app(container=FakeContainer(service, db_path=tmp_path / "cleanarr.db"))

    async with app_client(app) as client:
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
async def test_webhook_endpoint_suppresses_completed_duplicate_delivery(tmp_path: Path) -> None:
    result = ProcessingResult(
        event=MediaDeletionEvent(
            notification_type="ItemDeleted",
            item_type=ItemType.MOVIE,
            item_id="duplicate-movie",
            name="Duplicate Movie",
            fingerprint=MediaFingerprint(tmdb_id=77),
        ),
        status=OverallStatus.SUCCESS,
        actions=(
            ActionResult(
                system="radarr",
                action="delete_movie",
                status=ActionStatus.DELETED,
                message="ok",
            ),
        ),
    )
    service = FakeService(results=[result])
    app = create_app(container=FakeContainer(service, db_path=tmp_path / "cleanarr.db"))
    payload = {
        "notification_type": "ItemDeleted",
        "item_type": "Movie",
        "item_id": "duplicate-movie",
        "name": "Duplicate Movie",
        "tmdb_id": 77,
        "occurred_at": "2026-08-12T03:00:00Z",
    }

    async with app_client(app) as client:
        first = await client.post(
            "/webhook/jellyfin",
            headers={"X-Webhook-Token": "secret-token"},
            json=payload,
        )
        second = await client.post(
            "/webhook/jellyfin",
            headers={"X-Webhook-Token": "secret-token"},
            json=payload,
        )
        dashboard = await client.get("/api/dashboard", headers={"X-Admin-Token": "admin-token"})

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json() == first.json()
    assert len(service.seen_events) == 1
    assert len(dashboard.json()["recent_activity"]) == 1
    assert "suppressed 1 completed duplicate" in dashboard.json()["webhook_status"]["message"]


@pytest.mark.asyncio
async def test_webhook_endpoint_rejects_bad_token(tmp_path: Path) -> None:
    service = FakeService(results=[])
    app = create_app(container=FakeContainer(service, db_path=tmp_path / "cleanarr.db"))

    async with app_client(app) as client:
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
        dashboard_response = await client.get("/api/dashboard", headers={"X-Admin-Token": "admin-token"})

    assert response.status_code == 401
    assert dashboard_response.status_code == 200
    assert dashboard_response.json()["webhook_status"]["outcome"] == "rejected_auth"
    assert dashboard_response.json()["webhook_status"]["http_status"] == 401


@pytest.mark.asyncio
async def test_dashboard_endpoint_exposes_recent_activity(tmp_path: Path) -> None:
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
    app = create_app(container=FakeContainer(service, db_path=tmp_path / "cleanarr.db"))

    async with app_client(app) as client:
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
        dashboard_response = await client.get("/api/dashboard", headers={"X-Admin-Token": "admin-token"})

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
async def test_webhook_endpoint_accepts_jellyfin_locale_datetime(tmp_path: Path) -> None:
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
    app = create_app(container=FakeContainer(service, db_path=tmp_path / "cleanarr.db"))

    async with app_client(app) as client:
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
async def test_dashboard_endpoint_exposes_invalid_payload_webhook_status(tmp_path: Path) -> None:
    service = FakeService(results=[])
    app = create_app(container=FakeContainer(service, db_path=tmp_path / "cleanarr.db"))

    async with app_client(app) as client:
        webhook_response = await client.post(
            "/webhook/jellyfin",
            headers={"X-Webhook-Token": "secret-token"},
            json={"notification_type": "ItemDeleted"},
        )
        dashboard_response = await client.get("/api/dashboard", headers={"X-Admin-Token": "admin-token"})

    assert webhook_response.status_code == 422
    assert dashboard_response.status_code == 200
    assert dashboard_response.json()["webhook_status"]["outcome"] == "invalid_payload"
    assert dashboard_response.json()["webhook_status"]["http_status"] == 422


@pytest.mark.asyncio
async def test_runtime_config_endpoints_persist_and_rebuild(tmp_path: Path) -> None:
    settings = Settings.model_construct(
        db_path=str(tmp_path / "cleanarr.db"),
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
        seerr_url=None,
        seerr_api_key=None,
        downloader_kind="qbittorrent",
        qbittorrent_url=None,
        qbittorrent_username=None,
        qbittorrent_password=None,
    )
    container = ServiceContainer.from_settings(settings)
    app = create_app(container=container)

    async with app_client(app) as client:
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
async def test_legacy_jellyseerr_config_route_writes_canonical_seerr_payload(tmp_path: Path) -> None:
    settings = Settings.model_construct(
        db_path=str(tmp_path / "cleanarr.db"),
        config_state_path=str(tmp_path / "runtime-config.json"),
        admin_shared_token="admin-token",
        log_level="INFO",
        dry_run=True,
        webhook_shared_token="secret-token",
        http_timeout_seconds=5.0,
    )
    container = ServiceContainer.from_settings(settings)
    app = create_app(container=container)

    async with app_client(app) as client:
        response = await client.post(
            "/api/config/jellyseerr",
            headers={"X-Admin-Token": "admin-token"},
            json={
                "name": "Migrated Seerr",
                "url": "https://seerr.example.com",
                "api_key": "key",
            },
        )

    assert response.status_code == 200
    assert "jellyseerr" not in response.json()
    assert response.json()["seerr"][0]["kind"] == "seerr"
    assert "/api/config/seerr" in app.openapi()["paths"]
    assert "/api/config/jellyseerr" not in app.openapi()["paths"]

    await container.close()


@pytest.mark.asyncio
async def test_runtime_config_crud_supports_all_tier_one_downloaders(tmp_path: Path) -> None:
    settings = Settings.model_construct(
        db_path=str(tmp_path / "cleanarr.db"),
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
        seerr_url=None,
        seerr_api_key=None,
        downloader_kind="qbittorrent",
        qbittorrent_url=None,
        qbittorrent_username=None,
        qbittorrent_password=None,
    )
    container = ServiceContainer.from_settings(settings)
    app = create_app(container=container)
    headers = {"X-Admin-Token": "admin-token"}

    async with app_client(app) as client:
        qbt = await client.post(
            "/api/config/downloaders/qbittorrent",
            headers=headers,
            json={
                "name": "qBittorrent",
                "url": "http://qbt",
                "api_key": "qbt_test_key",
                "seeding_policy": "defer",
                "min_seed_ratio": 1.5,
            },
        )
        transmission = await client.post(
            "/api/config/downloaders/transmission",
            headers=headers,
            json={"name": "Transmission", "url": "http://transmission"},
        )
        deluge = await client.post(
            "/api/config/downloaders/deluge",
            headers=headers,
            json={"name": "Deluge", "url": "http://deluge", "password": "secret"},
        )
        rtorrent = await client.post(
            "/api/config/downloaders/rtorrent",
            headers=headers,
            json={"name": "rTorrent", "url": "http://rtorrent"},
        )
        rtorrent_id = rtorrent.json()["downloaders"][-1]["id"]
        deleted = await client.delete(
            f"/api/config/downloaders/rtorrent/{rtorrent_id}",
            headers=headers,
        )
        invalid_policy = await client.post(
            "/api/config/downloaders/transmission",
            headers=headers,
            json={"name": "Invalid", "url": "http://invalid", "seeding_policy": "defer"},
        )

    assert qbt.status_code == 200
    assert qbt.json()["downloaders"][0]["seeding_policy"] == "defer"
    assert qbt.json()["downloaders"][0]["min_seed_ratio"] == 1.5
    assert transmission.status_code == 200
    assert deluge.status_code == 200
    assert rtorrent.status_code == 200
    assert [service["kind"] for service in rtorrent.json()["downloaders"]] == [
        "qbittorrent",
        "transmission",
        "deluge",
        "rtorrent",
    ]
    assert deleted.status_code == 204
    assert invalid_policy.status_code == 422
    assert [service.kind.value for service in container.config.downloaders] == [
        "qbittorrent",
        "transmission",
        "deluge",
    ]

    await container.close()


@pytest.mark.asyncio
async def test_first_run_config_does_not_seed_integrations_from_env(tmp_path: Path) -> None:
    settings = Settings.model_construct(
        db_path=str(tmp_path / "cleanarr.db"),
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
        seerr_url="http://seerr.example/api/v1",
        seerr_api_key="seerr-key",
        downloader_kind="qbittorrent",
        qbittorrent_url="http://qbt.example",
        qbittorrent_username="user",
        qbittorrent_password="pass",
    )
    container = ServiceContainer.from_settings(settings)
    app = create_app(container=container)

    async with app_client(app) as client:
        response = await client.get("/api/config", headers={"X-Admin-Token": "admin-token"})

    assert response.status_code == 200
    assert response.json()["radarr"] == []
    assert response.json()["sonarr"] == []
    assert response.json()["seerr"] == []
    assert response.json()["downloaders"] == []
    assert response.json()["general"]["webhook_shared_token"] == "secret-token"

    await container.close()


@pytest.mark.asyncio
async def test_redacted_config_export_import_endpoint_is_fail_safe(tmp_path: Path) -> None:
    settings = Settings.model_construct(
        db_path=str(tmp_path / "cleanarr.db"),
        config_state_path=str(tmp_path / "runtime-config.json"),
        admin_shared_token="admin-token",
        log_level="INFO",
        dry_run=False,
        webhook_shared_token="webhook-secret",
        http_timeout_seconds=5.0,
        downloader_kind="qbittorrent",
    )
    container = ServiceContainer.from_settings(settings)
    app = create_app(container=container)
    headers = {"X-Admin-Token": "admin-token"}

    async with app_client(app) as client:
        exported = await client.get("/api/config/export", headers=headers)
        document = exported.json()
        document["services"].append(
            {
                "id": "imported-radarr",
                "kind": "radarr",
                "name": "Imported Radarr",
                "url": "https://url-user:url-password@radarr.example/api/v3?api_key=query-secret",
                "enabled": True,
                "is_default": True,
            }
        )
        imported = await client.post("/api/config/import", headers=headers, json=document)
        saved = await client.get("/api/config", headers=headers)

    assert exported.status_code == 200
    assert "webhook-secret" not in exported.text
    assert imported.status_code == 200
    assert imported.json()["dry_run"] is True
    assert saved.json()["general"]["dry_run"] is True
    assert saved.json()["general"]["webhook_shared_token"] == "webhook-secret"
    assert saved.json()["radarr"] == [
        {
            "id": "imported-radarr",
            "kind": "radarr",
            "name": "Imported Radarr",
            "url": "https://radarr.example/api/v3",
            "enabled": False,
            "is_default": True,
            "api_key": "",
        }
    ]

    await container.close()


@pytest.mark.asyncio
@respx.mock
async def test_runtime_config_connection_test_returns_structured_failure(tmp_path: Path) -> None:
    settings = Settings.model_construct(
        db_path=str(tmp_path / "cleanarr.db"),
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
        seerr_url=None,
        seerr_api_key=None,
        downloader_kind="qbittorrent",
        qbittorrent_url=None,
        qbittorrent_username=None,
        qbittorrent_password=None,
    )
    container = ServiceContainer.from_settings(settings)
    app = create_app(container=container)
    respx.post("http://qbt/api/v2/auth/login").respond(status_code=403, text="Fails.")

    async with app_client(app) as client:
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
        db_path=str(tmp_path / "cleanarr.db"),
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
        seerr_url=None,
        seerr_api_key=None,
        downloader_kind="qbittorrent",
        qbittorrent_url=None,
        qbittorrent_username=None,
        qbittorrent_password=None,
    )
    container = ServiceContainer.from_settings(settings)
    app = create_app(container=container)
    route = respx.get("https://sonarr.example.com/api/v3/series").respond(status_code=200, json=[])

    async with app_client(app) as client:
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
async def test_seerr_test_endpoint_normalizes_plain_base_url_to_api_v1(tmp_path: Path) -> None:
    settings = Settings.model_construct(
        db_path=str(tmp_path / "cleanarr.db"),
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
        seerr_url=None,
        seerr_api_key=None,
        downloader_kind="qbittorrent",
        qbittorrent_url=None,
        qbittorrent_username=None,
        qbittorrent_password=None,
    )
    container = ServiceContainer.from_settings(settings)
    app = create_app(container=container)
    route = respx.get("https://seerr.example.com/api/v1/media").respond(
        status_code=200,
        json={"pageInfo": {"results": 0}, "results": []},
    )

    async with app_client(app) as client:
        response = await client.post(
            "/api/config/seerr/test",
            headers={"X-Admin-Token": "admin-token"},
            json={
                "name": "Seerr",
                "url": "https://seerr.example.com",
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
    container = ServiceContainer.from_settings(settings)
    app = create_app(container=container)

    async with app_client(app) as client:
        status_before = await client.get("/api/auth/status")
        register = await client.post(
            "/api/auth/register",
            headers={"Origin": "http://test"},
            json={"username": "admin", "password": "super-secret-123"},
        )
        status_after = await client.get("/api/auth/status")
        config_response = await client.get("/api/config")

    assert status_before.status_code == 200
    assert status_before.json()["requires_registration"] is True
    assert register.status_code == 200
    assert "token" not in register.json()
    assert register.json()["csrf_token"]
    assert "HttpOnly" in register.headers["set-cookie"]
    assert status_after.status_code == 200
    assert status_after.json()["authenticated"] is True
    assert status_after.json()["username"] == "admin"
    assert config_response.status_code == 200

    await container.close()


@pytest.mark.asyncio
async def test_cookie_session_requires_same_origin_csrf_for_mutations(tmp_path: Path) -> None:
    settings = Settings.model_construct(
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
    container = ServiceContainer.from_settings(settings)
    app = create_app(container=container)

    async with app_client(app) as client:
        register = await client.post(
            "/api/auth/register",
            headers={"Origin": "http://test"},
            json={"username": "admin", "password": "super-secret-123"},
        )
        csrf_token = register.json()["csrf_token"]
        missing_csrf = await client.post(
            "/api/auth/logout",
            headers={"Origin": "http://test"},
        )
        wrong_origin = await client.post(
            "/api/auth/logout",
            headers={"Origin": "https://attacker.example", "X-CSRF-Token": csrf_token},
        )
        logout = await client.post(
            "/api/auth/logout",
            headers={"Origin": "http://test", "X-CSRF-Token": csrf_token},
        )
        status_after = await client.get("/api/auth/status")

    set_cookie = register.headers["set-cookie"]
    assert "HttpOnly" in set_cookie
    assert "SameSite=strict" in set_cookie
    assert "Max-Age=604800" in set_cookie
    assert missing_csrf.status_code == 403
    assert missing_csrf.json()["detail"] == "Invalid CSRF token"
    assert wrong_origin.status_code == 403
    assert wrong_origin.json()["detail"] == "Same-origin browser request required"
    assert logout.status_code == 204
    assert "cleanarr_session=" in logout.headers["set-cookie"]
    assert "Max-Age=0" in logout.headers["set-cookie"]
    assert status_after.json()["authenticated"] is False
    assert status_after.headers["content-security-policy"].startswith("default-src 'self'")
    assert "style-src 'self' 'unsafe-inline'" in status_after.headers["content-security-policy"]
    assert "script-src 'self'" in status_after.headers["content-security-policy"]
    assert status_after.headers["x-frame-options"] == "DENY"

    await container.close()


@pytest.mark.asyncio
async def test_dashboard_requires_admin_authentication(tmp_path: Path) -> None:
    app = create_app(container=FakeContainer(FakeService(results=[]), db_path=tmp_path / "cleanarr.db"))

    async with app_client(app) as client:
        response = await client.get("/api/dashboard")

    assert response.status_code == 403
