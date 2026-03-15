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
from pydantic import ValidationError

from cleanarr.api.auth_schemas import (
    AdminCredentialsRequest,
    AuthSessionResponse,
    AuthStatusResponse,
)
from cleanarr.api.config_schemas import (
    ConnectionTestResponse,
    GeneralConfigRequest,
    JellyseerrServiceRequest,
    QbittorrentServiceRequest,
    RadarrServiceRequest,
    RuntimeConfigResponse,
    SonarrServiceRequest,
)
from cleanarr.api.dashboard import (
    DashboardResponse,
    HealthProbeStore,
    RecentActivityStore,
    WebhookAttemptStore,
    build_dashboard_response,
)
from cleanarr.api.schemas import JellyfinWebhookPayload, WebhookBatchResponse
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


def create_app(*, container: ServiceContainer | None = None) -> FastAPI:
    """Create the FastAPI application."""

    own_container = container is None
    resolved_container = container or ServiceContainer.from_settings(Settings())
    activity_store = RecentActivityStore()
    webhook_attempt_store = WebhookAttemptStore()
    health_probe_store = HealthProbeStore()
    static_dir = Path(__file__).resolve().parents[1] / "ui" / "static"

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> Any:
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
        return build_dashboard_response(
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
            request.app.state.activity_store.record(result)
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

        return FileResponse(index_path)

    return app
