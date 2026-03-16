"""FastAPI application factory."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, ValidationError

from cleanarr.api.auth_schemas import (
    AdminCredentialsRequest,
    AuthSessionResponse,
    AuthStatusResponse,
)
from cleanarr.api.config_schemas import (
    ConnectionTestResponse,
    GeneralConfigRequest,
    JellyfinServiceRequest,
    JellyseerrServiceRequest,
    QbittorrentServiceRequest,
    RadarrServiceRequest,
    RuntimeConfigResponse,
    SonarrServiceRequest,
)
from cleanarr.api.dashboard import (
    JELLYFIN_GENERIC_TEMPLATE,
    ActivityStore,
    DashboardResponse,
    HealthProbeStore,
    WebhookAttemptStore,
    build_dashboard_response,
)
from cleanarr.api.library_schemas import (
    LibraryMoviesResponse,
    LibrarySeriesResponse,
    ManualDeleteRequest,
    MovieSummary,
    SeasonSummary,
    SeriesSummary,
)
from cleanarr.api.schemas import JellyfinWebhookPayload, ProcessingResultResponse, WebhookBatchResponse
from cleanarr.domain import ItemType, MediaDeletionEvent, MediaFingerprint
from cleanarr.domain.config import ServiceKind
from cleanarr.infrastructure.container import ServiceContainer
from cleanarr.infrastructure.settings import Settings

_logger = logging.getLogger("cleanarr")


def _has_active_service(services: list) -> bool:
    return any(getattr(s, "enabled", False) for s in services)


async def _health_probe_loop(container: ServiceContainer, health_store: HealthProbeStore) -> None:
    """Background task: probe all configured downstream services periodically."""

    async def _probe(name: str, configured: bool, client: Any) -> None:
        if not configured:
            health_store.update(name, "unconfigured")
            return
        try:
            await asyncio.wait_for(client.ping(), timeout=10.0)
            health_store.update(name, "healthy")
        except Exception as exc:
            _logger.warning("Health probe [%s] failed: %s: %s", name, type(exc).__name__, exc)
            health_store.update(name, "unreachable")

    await asyncio.sleep(5)
    while True:
        config = container.config
        try:
            await asyncio.gather(
                _probe("Radarr", _has_active_service(config.radarr), container.radarr),
                _probe("Sonarr", _has_active_service(config.sonarr), container.sonarr),
                _probe("Jellyseerr", _has_active_service(config.jellyseerr), container.jellyseerr),
                _probe("Downloader", _has_active_service(config.downloaders), container.downloader),
                _probe("Jellyfin", _has_active_service(config.jellyfin), container.jellyfin_server),
            )
        except Exception:
            _logger.exception("Health probe loop encountered an unexpected error")
        await asyncio.sleep(30)


def _extract_token(authorization: str | None, header_token: str | None) -> str | None:
    if header_token:
        return header_token
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:]
    return None


async def require_webhook_token(
    request: Request,
    authorization: str | None = Header(default=None),
    x_webhook_token: str | None = Header(default=None),
) -> None:
    """Validate the shared webhook token when configured."""

    expected = request.app.state.container.webhook_shared_token
    if not expected:
        return
    provided = _extract_token(authorization, x_webhook_token)
    if provided != expected:
        request.app.state.webhook_attempt_store.record(
            outcome="rejected_auth",
            http_status=status.HTTP_401_UNAUTHORIZED,
            message="Webhook token did not match the token saved in CleanArr runtime settings.",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook token",
        )


async def require_admin_token(
    request: Request,
    authorization: str | None = Header(default=None),
    x_admin_token: str | None = Header(default=None),
) -> None:
    """Validate admin access via session token or fallback static token."""

    provided = _extract_token(authorization, x_admin_token)
    container = request.app.state.container
    if container.auth_service.resolve_session(provided):
        return

    expected = container.admin_shared_token
    if expected and provided == expected:
        return

    if not container.config.admin.configured:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin registration required",
        )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid admin session",
    )


class SetupWebhookRequest(BaseModel):
    webhook_url: str


class SetupWebhookResponse(BaseModel):
    found: bool
    configured: bool
    message: str


def create_app(*, container: ServiceContainer | None = None) -> FastAPI:
    """Create the FastAPI application."""

    own_container = container is None
    resolved_container = container or ServiceContainer.from_settings(Settings())
    settings = resolved_container.settings
    activity_store = ActivityStore(
        Path(settings.db_path),
        retention_days=resolved_container.config.general.activity_retention_days,
    )
    webhook_attempt_store = WebhookAttemptStore()
    health_probe_store = HealthProbeStore()
    static_dir = Path(__file__).resolve().parents[1] / "ui" / "static"

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> Any:
        await activity_store.initialize()
        app.state.container = resolved_container
        app.state.activity_store = activity_store
        app.state.webhook_attempt_store = webhook_attempt_store
        app.state.health_probe_store = health_probe_store
        probe_task = asyncio.create_task(_health_probe_loop(resolved_container, health_probe_store))
        try:
            yield
        finally:
            probe_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await probe_task
            if own_container:
                await resolved_container.close()

    app = FastAPI(title="CleanArr", version="0.1.0", lifespan=lifespan)
    app.state.container = resolved_container
    app.state.activity_store = activity_store
    app.state.webhook_attempt_store = webhook_attempt_store
    app.state.health_probe_store = health_probe_store

    @app.get("/health/live")
    async def health_live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready")
    async def health_ready() -> dict[str, str]:
        return {"status": "ready"}

    @app.get("/api/dashboard", response_model=DashboardResponse)
    async def dashboard(request: Request) -> DashboardResponse:
        return await build_dashboard_response(
            config=request.app.state.container.config,
            downloader_kind=request.app.state.container.settings.downloader_kind,
            version=app.version,
            activity_store=request.app.state.activity_store,
            webhook_attempt_store=request.app.state.webhook_attempt_store,
            health_probe_store=request.app.state.health_probe_store,
        )

    @app.get("/api/auth/status", response_model=AuthStatusResponse)
    async def auth_status(
        request: Request,
        authorization: str | None = Header(default=None),
        x_admin_token: str | None = Header(default=None),
    ) -> AuthStatusResponse:
        token = _extract_token(authorization, x_admin_token)
        status_payload = request.app.state.container.auth_service.get_status(token)
        return AuthStatusResponse.from_domain(status_payload)

    @app.post("/api/auth/register", response_model=AuthSessionResponse)
    async def register_admin(
        request: Request,
        payload: AdminCredentialsRequest,
    ) -> AuthSessionResponse:
        try:
            session = request.app.state.container.auth_service.register_admin(
                username=payload.username,
                password=payload.password,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(exc),
            ) from exc
        return AuthSessionResponse.from_domain(session)

    @app.post("/api/auth/login", response_model=AuthSessionResponse)
    async def login_admin(
        request: Request,
        payload: AdminCredentialsRequest,
    ) -> AuthSessionResponse:
        try:
            session = request.app.state.container.auth_service.login(
                username=payload.username,
                password=payload.password,
            )
        except LookupError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(exc),
            ) from exc
        except PermissionError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=str(exc),
            ) from exc
        return AuthSessionResponse.from_domain(session)

    @app.post(
        "/api/auth/logout",
        status_code=status.HTTP_204_NO_CONTENT,
        dependencies=[Depends(require_admin_token)],
    )
    async def logout_admin(
        request: Request,
        authorization: str | None = Header(default=None),
        x_admin_token: str | None = Header(default=None),
    ) -> Response:
        token = _extract_token(authorization, x_admin_token)
        request.app.state.container.auth_service.logout(token)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.get(
        "/api/config",
        response_model=RuntimeConfigResponse,
        dependencies=[Depends(require_admin_token)],
    )
    async def get_runtime_config(request: Request) -> RuntimeConfigResponse:
        container = request.app.state.container
        return RuntimeConfigResponse.from_config(
            container.config,
            admin_token_configured=bool(container.admin_shared_token),
        )

    @app.put(
        "/api/config/general",
        response_model=RuntimeConfigResponse,
        dependencies=[Depends(require_admin_token)],
    )
    async def put_general_config(
        request: Request,
        payload: GeneralConfigRequest,
    ) -> RuntimeConfigResponse:
        container = request.app.state.container
        config = container.config_service.update_general(payload.to_domain())
        request.app.state.activity_store.set_retention_days(payload.activity_retention_days)
        await container.refresh_runtime()
        return RuntimeConfigResponse.from_config(
            config,
            admin_token_configured=bool(container.admin_shared_token),
        )

    @app.post(
        "/api/config/radarr",
        response_model=RuntimeConfigResponse,
        dependencies=[Depends(require_admin_token)],
    )
    async def create_radarr(request: Request, payload: RadarrServiceRequest) -> RuntimeConfigResponse:
        container = request.app.state.container
        config = container.config_service.add_service(payload.to_domain().kind, payload.to_domain())
        await container.refresh_runtime()
        return RuntimeConfigResponse.from_config(config, admin_token_configured=bool(container.admin_shared_token))

    @app.put(
        "/api/config/radarr/{service_id}",
        response_model=RuntimeConfigResponse,
        dependencies=[Depends(require_admin_token)],
    )
    async def update_radarr(
        request: Request,
        service_id: str,
        payload: RadarrServiceRequest,
    ) -> RuntimeConfigResponse:
        container = request.app.state.container
        config = container.config_service.update_service(
            payload.to_domain(service_id=service_id).kind,
            service_id,
            payload.to_domain(service_id=service_id),
        )
        await container.refresh_runtime()
        return RuntimeConfigResponse.from_config(config, admin_token_configured=bool(container.admin_shared_token))

    @app.delete(
        "/api/config/radarr/{service_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        dependencies=[Depends(require_admin_token)],
    )
    async def delete_radarr(request: Request, service_id: str) -> Response:
        container = request.app.state.container
        container.config_service.delete_service(ServiceKind.RADARR, service_id)
        await container.refresh_runtime()
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.post(
        "/api/config/radarr/test",
        response_model=ConnectionTestResponse,
        dependencies=[Depends(require_admin_token)],
    )
    async def test_radarr(payload: RadarrServiceRequest, request: Request) -> ConnectionTestResponse:
        result = await request.app.state.container.config_service.test_service(payload.to_domain())
        return ConnectionTestResponse.from_domain(result)

    @app.post(
        "/api/config/sonarr",
        response_model=RuntimeConfigResponse,
        dependencies=[Depends(require_admin_token)],
    )
    async def create_sonarr(request: Request, payload: SonarrServiceRequest) -> RuntimeConfigResponse:
        container = request.app.state.container
        config = container.config_service.add_service(payload.to_domain().kind, payload.to_domain())
        await container.refresh_runtime()
        return RuntimeConfigResponse.from_config(config, admin_token_configured=bool(container.admin_shared_token))

    @app.put(
        "/api/config/sonarr/{service_id}",
        response_model=RuntimeConfigResponse,
        dependencies=[Depends(require_admin_token)],
    )
    async def update_sonarr(
        request: Request,
        service_id: str,
        payload: SonarrServiceRequest,
    ) -> RuntimeConfigResponse:
        container = request.app.state.container
        config = container.config_service.update_service(
            payload.to_domain(service_id=service_id).kind,
            service_id,
            payload.to_domain(service_id=service_id),
        )
        await container.refresh_runtime()
        return RuntimeConfigResponse.from_config(config, admin_token_configured=bool(container.admin_shared_token))

    @app.delete(
        "/api/config/sonarr/{service_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        dependencies=[Depends(require_admin_token)],
    )
    async def delete_sonarr(request: Request, service_id: str) -> Response:
        container = request.app.state.container
        container.config_service.delete_service(ServiceKind.SONARR, service_id)
        await container.refresh_runtime()
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.post(
        "/api/config/sonarr/test",
        response_model=ConnectionTestResponse,
        dependencies=[Depends(require_admin_token)],
    )
    async def test_sonarr(payload: SonarrServiceRequest, request: Request) -> ConnectionTestResponse:
        result = await request.app.state.container.config_service.test_service(payload.to_domain())
        return ConnectionTestResponse.from_domain(result)

    @app.post(
        "/api/config/jellyseerr",
        response_model=RuntimeConfigResponse,
        dependencies=[Depends(require_admin_token)],
    )
    async def create_jellyseerr(
        request: Request,
        payload: JellyseerrServiceRequest,
    ) -> RuntimeConfigResponse:
        container = request.app.state.container
        config = container.config_service.add_service(payload.to_domain().kind, payload.to_domain())
        await container.refresh_runtime()
        return RuntimeConfigResponse.from_config(config, admin_token_configured=bool(container.admin_shared_token))

    @app.put(
        "/api/config/jellyseerr/{service_id}",
        response_model=RuntimeConfigResponse,
        dependencies=[Depends(require_admin_token)],
    )
    async def update_jellyseerr(
        request: Request,
        service_id: str,
        payload: JellyseerrServiceRequest,
    ) -> RuntimeConfigResponse:
        container = request.app.state.container
        config = container.config_service.update_service(
            payload.to_domain(service_id=service_id).kind,
            service_id,
            payload.to_domain(service_id=service_id),
        )
        await container.refresh_runtime()
        return RuntimeConfigResponse.from_config(config, admin_token_configured=bool(container.admin_shared_token))

    @app.delete(
        "/api/config/jellyseerr/{service_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        dependencies=[Depends(require_admin_token)],
    )
    async def delete_jellyseerr(request: Request, service_id: str) -> Response:
        container = request.app.state.container
        container.config_service.delete_service(ServiceKind.JELLYSEERR, service_id)
        await container.refresh_runtime()
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.post(
        "/api/config/jellyseerr/test",
        response_model=ConnectionTestResponse,
        dependencies=[Depends(require_admin_token)],
    )
    async def test_jellyseerr(
        payload: JellyseerrServiceRequest,
        request: Request,
    ) -> ConnectionTestResponse:
        result = await request.app.state.container.config_service.test_service(payload.to_domain())
        return ConnectionTestResponse.from_domain(result)

    @app.post(
        "/api/config/downloaders/qbittorrent",
        response_model=RuntimeConfigResponse,
        dependencies=[Depends(require_admin_token)],
    )
    async def create_qbittorrent(
        request: Request,
        payload: QbittorrentServiceRequest,
    ) -> RuntimeConfigResponse:
        container = request.app.state.container
        config = container.config_service.add_service(payload.to_domain().kind, payload.to_domain())
        await container.refresh_runtime()
        return RuntimeConfigResponse.from_config(config, admin_token_configured=bool(container.admin_shared_token))

    @app.put(
        "/api/config/downloaders/qbittorrent/{service_id}",
        response_model=RuntimeConfigResponse,
        dependencies=[Depends(require_admin_token)],
    )
    async def update_qbittorrent(
        request: Request,
        service_id: str,
        payload: QbittorrentServiceRequest,
    ) -> RuntimeConfigResponse:
        container = request.app.state.container
        config = container.config_service.update_service(
            payload.to_domain(service_id=service_id).kind,
            service_id,
            payload.to_domain(service_id=service_id),
        )
        await container.refresh_runtime()
        return RuntimeConfigResponse.from_config(config, admin_token_configured=bool(container.admin_shared_token))

    @app.delete(
        "/api/config/downloaders/qbittorrent/{service_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        dependencies=[Depends(require_admin_token)],
    )
    async def delete_qbittorrent(request: Request, service_id: str) -> Response:
        container = request.app.state.container
        container.config_service.delete_service(ServiceKind.QBITTORRENT, service_id)
        await container.refresh_runtime()
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.post(
        "/api/config/downloaders/qbittorrent/test",
        response_model=ConnectionTestResponse,
        dependencies=[Depends(require_admin_token)],
    )
    async def test_qbittorrent(
        payload: QbittorrentServiceRequest,
        request: Request,
    ) -> ConnectionTestResponse:
        result = await request.app.state.container.config_service.test_service(payload.to_domain())
        return ConnectionTestResponse.from_domain(result)

    @app.post(
        "/api/config/jellyfin",
        response_model=RuntimeConfigResponse,
        dependencies=[Depends(require_admin_token)],
    )
    async def create_jellyfin(
        request: Request,
        payload: JellyfinServiceRequest,
    ) -> RuntimeConfigResponse:
        container = request.app.state.container
        config = container.config_service.add_service(payload.to_domain().kind, payload.to_domain())
        await container.refresh_runtime()
        return RuntimeConfigResponse.from_config(config, admin_token_configured=bool(container.admin_shared_token))

    @app.put(
        "/api/config/jellyfin/{service_id}",
        response_model=RuntimeConfigResponse,
        dependencies=[Depends(require_admin_token)],
    )
    async def update_jellyfin(
        request: Request,
        service_id: str,
        payload: JellyfinServiceRequest,
    ) -> RuntimeConfigResponse:
        container = request.app.state.container
        config = container.config_service.update_service(
            payload.to_domain(service_id=service_id).kind,
            service_id,
            payload.to_domain(service_id=service_id),
        )
        await container.refresh_runtime()
        return RuntimeConfigResponse.from_config(config, admin_token_configured=bool(container.admin_shared_token))

    @app.delete(
        "/api/config/jellyfin/{service_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        dependencies=[Depends(require_admin_token)],
    )
    async def delete_jellyfin(request: Request, service_id: str) -> Response:
        container = request.app.state.container
        container.config_service.delete_service(ServiceKind.JELLYFIN, service_id)
        await container.refresh_runtime()
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.post(
        "/api/config/jellyfin/test",
        response_model=ConnectionTestResponse,
        dependencies=[Depends(require_admin_token)],
    )
    async def test_jellyfin(
        payload: JellyfinServiceRequest,
        request: Request,
    ) -> ConnectionTestResponse:
        result = await request.app.state.container.config_service.test_service(payload.to_domain())
        return ConnectionTestResponse.from_domain(result)

    @app.post(
        "/api/config/jellyfin/setup-webhook",
        response_model=SetupWebhookResponse,
        dependencies=[Depends(require_admin_token)],
    )
    async def setup_jellyfin_webhook(
        request: Request,
        payload: SetupWebhookRequest,
    ) -> SetupWebhookResponse:
        container = request.app.state.container
        result = await container.jellyfin_server.setup_webhook(
            webhook_url=payload.webhook_url,
            webhook_token=container.config.general.webhook_shared_token,
            template=JELLYFIN_GENERIC_TEMPLATE,
        )
        return SetupWebhookResponse(**result)

    @app.post(
        "/webhook/jellyfin",
        response_model=WebhookBatchResponse,
        dependencies=[Depends(require_webhook_token)],
    )
    async def webhook_jellyfin(request: Request) -> WebhookBatchResponse:
        try:
            payload = await request.json()
        except ValueError as exc:
            request.app.state.webhook_attempt_store.record(
                outcome="invalid_payload",
                http_status=status.HTTP_422_UNPROCESSABLE_ENTITY,
                message="Request body is not valid JSON.",
            )
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Invalid JSON payload",
            ) from exc

        payload_list = payload if isinstance(payload, list) else [payload]
        if not payload_list:
            request.app.state.webhook_attempt_store.record(
                outcome="invalid_payload",
                http_status=status.HTTP_422_UNPROCESSABLE_ENTITY,
                message="Payload array is empty. Jellyfin must send at least one event.",
            )
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Empty Jellyfin webhook payload",
            )

        try:
            webhook_payloads = [JellyfinWebhookPayload.model_validate(item) for item in payload_list]
        except ValidationError as exc:
            first_error = exc.errors()[0] if exc.errors() else None
            error_location = (
                " -> ".join(str(part) for part in first_error["loc"])
                if first_error is not None
                else ""
            )
            error_message = (
                first_error["msg"]
                if first_error is not None
                else "Payload validation failed."
            )
            request.app.state.webhook_attempt_store.record(
                outcome="invalid_payload",
                http_status=status.HTTP_422_UNPROCESSABLE_ENTITY,
                message=f"{error_location}: {error_message}" if error_location else error_message,
            )
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Invalid Jellyfin webhook payload",
            ) from exc

        service = request.app.state.container.service
        results = [await service.process(item.to_domain()) for item in webhook_payloads]
        for result in results:
            await request.app.state.activity_store.record(result)
        batch_response = WebhookBatchResponse.from_results(results)
        first_payload = webhook_payloads[0]
        request.app.state.webhook_attempt_store.record(
            outcome="processed",
            http_status=status.HTTP_200_OK,
            message=f"Processed {len(results)} Jellyfin event(s). Overall status: {batch_response.status}.",
            notification_type=first_payload.notification_type,
            item_type=first_payload.item_type,
            item_name=first_payload.name if len(results) == 1 else f"{len(results)} events",
            result_status=batch_response.status,
        )
        return batch_response

    @app.get(
        "/api/library/series",
        response_model=LibrarySeriesResponse,
        dependencies=[Depends(require_admin_token)],
    )
    async def library_series(request: Request) -> LibrarySeriesResponse:
        container = request.app.state.container
        sonarr = container.sonarr
        jellyfin = container.jellyfin_server

        series_list = list(await sonarr.list_series())

        # Fetch Jellyfin series + seasons in a single call for cross-referencing
        jf_series_items = list(await jellyfin.list_items(include_types=["Series", "Season"]))
        jf_series_by_tvdb: dict[int, str] = {}
        jf_series_by_tmdb: dict[int, str] = {}
        jf_series_by_imdb: dict[str, str] = {}
        jf_seasons_by_parent: dict[str, dict[int, str]] = {}  # parent_id -> {season_number -> jellyfin_id}

        for item in jf_series_items:
            if item.type == "Series":
                if item.tvdb_id:
                    jf_series_by_tvdb[item.tvdb_id] = item.id
                if item.tmdb_id:
                    jf_series_by_tmdb[item.tmdb_id] = item.id
                if item.imdb_id:
                    jf_series_by_imdb[item.imdb_id] = item.id
            elif item.type == "Season" and item.parent_id and item.season_number is not None:
                jf_seasons_by_parent.setdefault(item.parent_id, {})[item.season_number] = item.id

        def find_jf_series_id(series: object) -> str | None:
            if getattr(series, "tvdb_id", None) and series.tvdb_id in jf_series_by_tvdb:  # type: ignore[union-attr]
                return jf_series_by_tvdb[series.tvdb_id]  # type: ignore[union-attr]
            if getattr(series, "tmdb_id", None) and series.tmdb_id in jf_series_by_tmdb:  # type: ignore[union-attr]
                return jf_series_by_tmdb[series.tmdb_id]  # type: ignore[union-attr]
            if getattr(series, "imdb_id", None) and series.imdb_id in jf_series_by_imdb:  # type: ignore[union-attr]
                return jf_series_by_imdb[series.imdb_id]  # type: ignore[union-attr]
            return None

        result: list[SeriesSummary] = []
        for series in sorted(series_list, key=lambda s: s.title.lower()):
            episodes = list(await sonarr.list_episodes(series.id))
            episode_files = list(await sonarr.list_episode_files(series.id))

            size_by_season: dict[int, int] = {}
            file_count_by_season: dict[int, int] = {}
            for ef in episode_files:
                sn = ef.season_number or 0
                size_by_season[sn] = size_by_season.get(sn, 0) + (ef.size or 0)
                file_count_by_season[sn] = file_count_by_season.get(sn, 0) + 1

            episode_count_by_season: dict[int, int] = {}
            for ep in episodes:
                sn = ep.season_number
                episode_count_by_season[sn] = episode_count_by_season.get(sn, 0) + 1

            season_numbers = sorted(
                {ep.season_number for ep in episodes if ep.season_number > 0}
            )

            jf_series_id = find_jf_series_id(series)
            jf_season_map = jf_seasons_by_parent.get(jf_series_id, {}) if jf_series_id else {}

            seasons = [
                SeasonSummary(
                    season_number=sn,
                    episode_count=episode_count_by_season.get(sn, 0),
                    episode_file_count=file_count_by_season.get(sn, 0),
                    size_bytes=size_by_season.get(sn, 0),
                    jellyfin_season_id=jf_season_map.get(sn),
                )
                for sn in season_numbers
            ]
            result.append(
                SeriesSummary(
                    sonarr_id=series.id,
                    title=series.title,
                    seasons=seasons,
                    jellyfin_series_id=jf_series_id,
                )
            )
        return LibrarySeriesResponse(series=result)

    @app.get(
        "/api/library/movies",
        response_model=LibraryMoviesResponse,
        dependencies=[Depends(require_admin_token)],
    )
    async def library_movies(request: Request) -> LibraryMoviesResponse:
        container = request.app.state.container
        radarr = container.radarr
        jellyfin = container.jellyfin_server

        movies_list = list(await radarr.list_movies())

        # Fetch Jellyfin movies for cross-referencing
        jf_movie_items = list(await jellyfin.list_items(include_types=["Movie"]))
        jf_movies_by_tmdb: dict[int, str] = {}
        jf_movies_by_imdb: dict[str, str] = {}
        for item in jf_movie_items:
            if item.tmdb_id:
                jf_movies_by_tmdb[item.tmdb_id] = item.id
            if item.imdb_id:
                jf_movies_by_imdb[item.imdb_id] = item.id

        result: list[MovieSummary] = []
        for movie in sorted(movies_list, key=lambda m: m.title.lower()):
            jf_movie_id: str | None = None
            if movie.tmdb_id and movie.tmdb_id in jf_movies_by_tmdb:
                jf_movie_id = jf_movies_by_tmdb[movie.tmdb_id]
            elif movie.imdb_id and movie.imdb_id in jf_movies_by_imdb:
                jf_movie_id = jf_movies_by_imdb[movie.imdb_id]
            result.append(
                MovieSummary(
                    radarr_id=movie.id,
                    title=movie.title,
                    size_bytes=movie.size_on_disk or 0,
                    has_file=movie.has_file,
                    jellyfin_movie_id=jf_movie_id,
                )
            )
        return LibraryMoviesResponse(movies=result)

    @app.post(
        "/api/actions/delete",
        response_model=ProcessingResultResponse,
        dependencies=[Depends(require_admin_token)],
    )
    async def manual_delete(request: Request, payload: ManualDeleteRequest) -> ProcessingResultResponse:
        container = request.app.state.container

        if payload.item_type is ItemType.MOVIE:
            if payload.radarr_movie_id is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="radarr_movie_id is required for movie deletion.",
                )
            radarr = container.radarr
            movies_list = list(await radarr.list_movies())
            movie = next((m for m in movies_list if m.id == payload.radarr_movie_id), None)
            if movie is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Radarr movie {payload.radarr_movie_id} not found.",
                )
            fingerprint = MediaFingerprint(
                tmdb_id=movie.tmdb_id,
                imdb_id=movie.imdb_id,
                path=movie.path,
            )
            event = MediaDeletionEvent(
                notification_type="ItemDeleted",
                item_type=ItemType.MOVIE,
                item_id="manual",
                name=movie.title,
                fingerprint=fingerprint,
            )
        else:
            if payload.sonarr_series_id is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="sonarr_series_id is required for series/season deletion.",
                )
            sonarr = container.sonarr
            series_list = list(await sonarr.list_series())
            series = next((s for s in series_list if s.id == payload.sonarr_series_id), None)
            if series is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Sonarr series {payload.sonarr_series_id} not found.",
                )
            if payload.item_type is ItemType.SEASON and payload.season_number is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="season_number is required for season deletion.",
                )
            fingerprint = MediaFingerprint(
                tvdb_id=series.tvdb_id,
                tmdb_id=series.tmdb_id,
                imdb_id=series.imdb_id,
                path=series.path,
            )
            event = MediaDeletionEvent(
                notification_type="ItemDeleted",
                item_type=payload.item_type,
                item_id="manual",
                name=series.title,
                fingerprint=fingerprint,
                series_name=series.title,
                season_number=payload.season_number,
            )

        strategy = container.strategy_factory.for_item_type(payload.item_type)
        result = await strategy.handle(event)
        await request.app.state.activity_store.record(result)

        # After cascade deletion, also remove from Jellyfin if ID provided and not dry_run
        if payload.jellyfin_item_id and not container.config.general.dry_run:
            try:
                await container.jellyfin_server.delete_item(payload.jellyfin_item_id)
            except Exception:
                _logger.warning("Failed to delete Jellyfin item %s after cascade deletion", payload.jellyfin_item_id)

        return ProcessingResultResponse.from_domain(result)

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str) -> FileResponse:
        if full_path.startswith(("api/", "health/", "webhook/")):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")

        index_path = static_dir / "index.html"
        if not index_path.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Frontend build not found",
            )

        if full_path:
            requested_path = (static_dir / full_path).resolve()
            if requested_path.is_relative_to(static_dir.resolve()) and requested_path.is_file():
                return FileResponse(requested_path)

        return FileResponse(index_path, headers={"Cache-Control": "no-cache, no-store, must-revalidate"})

    return app
