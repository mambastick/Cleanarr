"""FastAPI application factory."""

from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import logging
from collections.abc import Sequence
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode
from uuid import UUID

import httpx
from fastapi import Cookie, Depends, FastAPI, Header, HTTPException, Query, Request, Response, status
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel, ValidationError

from cleanarr.api.auth_schemas import (
    AdminCredentialsRequest,
    AuthSessionResponse,
    AuthStatusResponse,
    SSOLoginResponse,
)
from cleanarr.api.config_schemas import (
    ConnectionTestResponse,
    DelugeServiceRequest,
    GeneralConfigRequest,
    JellyfinServiceRequest,
    QbittorrentServiceRequest,
    RadarrServiceRequest,
    RTorrentServiceRequest,
    RuntimeConfigResponse,
    SeerrServiceRequest,
    SonarrServiceRequest,
    TransmissionServiceRequest,
)
from cleanarr.api.dashboard import (
    JELLYFIN_GENERIC_TEMPLATE,
    ActivityStore,
    DashboardResponse,
    HealthProbeStore,
    WebhookAttemptStore,
    build_dashboard_response,
)
from cleanarr.api.deletion_jobs import (
    DeletionJobActiveError,
    DeletionJobNotFoundError,
    DeletionProgressReporter,
    ManualDeletionJobStore,
)
from cleanarr.api.library_schemas import (
    LibraryMoviesResponse,
    LibrarySeriesResponse,
    ManualDeleteJobListResponse,
    ManualDeleteJobPhase,
    ManualDeleteJobResponse,
    ManualDeleteRequest,
    MovieSummary,
    SeasonSummary,
    SeriesSummary,
)
from cleanarr.api.schemas import JellyfinWebhookPayload, ProcessingResultResponse, WebhookBatchResponse
from cleanarr.application.results import observe_actions
from cleanarr.domain import ActionResult, ItemType, MediaDeletionEvent, MediaFingerprint, SonarrSeries
from cleanarr.domain.config import BaseServiceConfig, GeneralConfig, ServiceKind
from cleanarr.infrastructure.container import ServiceContainer
from cleanarr.infrastructure.settings import Settings

_logger = logging.getLogger("cleanarr")
_COOKIE_NAME = "cleanarr_session"
_COOKIE_MAX_AGE_SECONDS = 60 * 60 * 24 * 30
_SSO_ERROR_PREFIX = "/?sso_error="
_HTTP_UNPROCESSABLE_CONTENT = 422


def _ignore_deletion_progress(
    phase: ManualDeleteJobPhase,
    progress_percent: int,
    message: str,
    item_name: str | None,
) -> None:
    """No-op reporter used by the backwards-compatible synchronous endpoint."""


def _has_active_service(services: Sequence[BaseServiceConfig]) -> bool:
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
                _probe("Seerr", _has_active_service(config.seerr), container.seerr),
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


def _set_session_cookie(response: Response, request: Request, token: str | None) -> None:
    if token:
        response.set_cookie(
            key=_COOKIE_NAME,
            value=token,
            httponly=True,
            max_age=_COOKIE_MAX_AGE_SECONDS,
            samesite="strict",
            secure=request.url.scheme == "https",
            path="/",
        )
    else:
        response.delete_cookie(_COOKIE_NAME, path="/")


def _sso_redirect_uri(request: Request, general: GeneralConfig) -> str:
    if general.sso_redirect_uri:
        return general.sso_redirect_uri
    return str(request.url_for("sso_callback"))


def _sso_error_target(message: str) -> str:
    return f"{_SSO_ERROR_PREFIX}{quote(message)}"


def _pick_username_from_token_payload(payload: dict[str, Any]) -> str | None:
    for key in ("preferred_username", "name", "email", "upn", "sub"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _decode_jwt_payload(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    segments = raw.split(".")
    if len(segments) < 2:
        return {}
    payload = segments[1]
    pad = "=" * (-len(payload) % 4)
    try:
        decoded = json.loads(base64.urlsafe_b64decode(payload + pad).decode("utf-8"))
    except Exception:
        return {}
    if not isinstance(decoded, dict) or not all(isinstance(key, str) for key in decoded):
        return {}
    return decoded


async def _fetch_oidc_metadata(issuer_url: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(f"{issuer_url.rstrip('/')}/.well-known/openid-configuration")
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("Invalid OpenID discovery payload.")
        return payload


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
    cleanarr_session: str | None = Cookie(default=None, alias=_COOKIE_NAME),
) -> None:
    """Validate admin access via session token or fallback static token."""

    provided = _extract_token(authorization, x_admin_token) or cleanarr_session
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

    async def execute_manual_delete(
        payload: ManualDeleteRequest,
        report_progress: DeletionProgressReporter | None = None,
    ) -> ProcessingResultResponse:
        """Resolve and execute one manual deletion, optionally reporting progress."""

        report = report_progress or _ignore_deletion_progress
        container = resolved_container
        item_name: str

        if payload.item_type is ItemType.MOVIE:
            if payload.radarr_movie_id is None:
                raise HTTPException(
                    status_code=_HTTP_UNPROCESSABLE_CONTENT,
                    detail="radarr_movie_id is required for movie deletion.",
                )
            report(
                ManualDeleteJobPhase.LOCATING,
                10,
                "Looking up the movie in Radarr.",
                None,
            )
            movies_list = list(await container.radarr.list_movies())
            movie = next((movie for movie in movies_list if movie.id == payload.radarr_movie_id), None)
            if movie is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Radarr movie {payload.radarr_movie_id} not found.",
                )
            item_name = movie.title
            fingerprint = MediaFingerprint(
                tmdb_id=movie.tmdb_id,
                imdb_id=movie.imdb_id,
                path=movie.path,
            )
            event = MediaDeletionEvent(
                notification_type="ItemDeleted",
                item_type=ItemType.MOVIE,
                item_id="manual",
                name=item_name,
                fingerprint=fingerprint,
            )
        else:
            if payload.sonarr_series_id is None:
                raise HTTPException(
                    status_code=_HTTP_UNPROCESSABLE_CONTENT,
                    detail="sonarr_series_id is required for series/season deletion.",
                )
            report(
                ManualDeleteJobPhase.LOCATING,
                10,
                "Looking up the series in Sonarr.",
                None,
            )
            series_list = list(await container.sonarr.list_series())
            series = next((series for series in series_list if series.id == payload.sonarr_series_id), None)
            if series is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Sonarr series {payload.sonarr_series_id} not found.",
                )
            if payload.item_type is ItemType.SEASON and payload.season_number is None:
                raise HTTPException(
                    status_code=_HTTP_UNPROCESSABLE_CONTENT,
                    detail="season_number is required for season deletion.",
                )
            item_name = series.title
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
                name=item_name,
                fingerprint=fingerprint,
                series_name=item_name,
                season_number=payload.season_number,
            )

        report(
            ManualDeleteJobPhase.CLEANING,
            30,
            "Cleaning up Arr services, torrent clients, and Seerr.",
            item_name,
        )
        strategy = container.strategy_factory.for_item_type(payload.item_type)
        completed_actions = 0

        def report_action(action: ActionResult) -> None:
            nonlocal completed_actions
            completed_actions += 1
            report(
                ManualDeleteJobPhase.CLEANING,
                min(78, 30 + completed_actions * 6),
                f"{action.system}: {action.message}",
                item_name,
            )

        with observe_actions(report_action):
            result = await strategy.handle(event)

        report(
            ManualDeleteJobPhase.RECORDING,
            82,
            "Saving the cleanup result to activity history.",
            item_name,
        )
        await activity_store.record(result)

        if payload.jellyfin_item_id and not container.config.general.dry_run:
            report(
                ManualDeleteJobPhase.JELLYFIN,
                92,
                "Removing the item from Jellyfin.",
                item_name,
            )
            try:
                await container.jellyfin_server.delete_item(payload.jellyfin_item_id)
            except Exception:
                _logger.warning(
                    "Failed to delete Jellyfin item %s after cascade deletion",
                    payload.jellyfin_item_id,
                )
        else:
            report(
                ManualDeleteJobPhase.RECORDING,
                95,
                "Finalizing the background task.",
                item_name,
            )

        return ProcessingResultResponse.from_domain(result)

    deletion_jobs = ManualDeletionJobStore(execute_manual_delete)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> Any:
        await activity_store.initialize()
        app.state.container = resolved_container
        app.state.activity_store = activity_store
        app.state.webhook_attempt_store = webhook_attempt_store
        app.state.health_probe_store = health_probe_store
        app.state.deletion_jobs = deletion_jobs
        await deletion_jobs.start()
        probe_task = asyncio.create_task(_health_probe_loop(resolved_container, health_probe_store))
        try:
            yield
        finally:
            probe_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await probe_task
            await deletion_jobs.stop()
            if own_container:
                await resolved_container.close()

    app = FastAPI(title="CleanArr", version="0.3.0", lifespan=lifespan)
    app.state.container = resolved_container
    app.state.activity_store = activity_store
    app.state.webhook_attempt_store = webhook_attempt_store
    app.state.health_probe_store = health_probe_store
    app.state.deletion_jobs = deletion_jobs

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
        cleanarr_session: str | None = Cookie(default=None, alias=_COOKIE_NAME),
    ) -> AuthStatusResponse:
        token = _extract_token(authorization, x_admin_token) or cleanarr_session
        container = request.app.state.container
        status_payload = container.auth_service.get_status(token)
        return AuthStatusResponse.from_domain(
            status_payload,
            ui_language=container.config.general.ui_language,
        )

    @app.get("/api/auth/sso/start", response_model=SSOLoginResponse)
    async def sso_start(request: Request) -> SSOLoginResponse:
        container = request.app.state.container
        general = container.config.general
        if not container.auth_service.is_sso_auth_enabled(
            general,
        ) or not container.auth_service.is_sso_configured(general):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="SSO is not configured yet.",
            )

        try:
            metadata = await _fetch_oidc_metadata(general.sso_issuer_url)
        except Exception as exc:
            _logger.exception("Failed to fetch OIDC discovery for %s", general.sso_issuer_url)
            raise HTTPException(
                status_code=_HTTP_UNPROCESSABLE_CONTENT,
                detail="Could not fetch OpenID discovery data.",
            ) from exc

        authorization_endpoint = metadata.get("authorization_endpoint")
        if not isinstance(authorization_endpoint, str) or not authorization_endpoint:
            raise HTTPException(
                status_code=_HTTP_UNPROCESSABLE_CONTENT,
                detail="OpenID provider does not expose authorization_endpoint.",
            )

        state = container.auth_service.create_sso_state()
        params = {
            "response_type": "code",
            "client_id": general.sso_client_id,
            "redirect_uri": _sso_redirect_uri(request, general),
            "scope": general.sso_scopes,
            "state": state,
        }
        authorize_url = f"{authorization_endpoint}?{urlencode(params)}"
        return SSOLoginResponse(authorize_url=authorize_url, state=state)

    @app.get("/api/auth/sso/callback", name="sso_callback")
    async def sso_callback(
        request: Request,
        code: str | None = Query(default=None),
        state: str | None = Query(default=None),
        error: str | None = Query(default=None),
        error_description: str | None = Query(default=None),
    ) -> Response:
        if error:
            message = error_description or error
            return RedirectResponse(_sso_error_target(message))

        container = request.app.state.container
        general = container.config.general
        if not container.auth_service.is_sso_auth_enabled(
            general,
        ) or not container.auth_service.is_sso_configured(general):
            return RedirectResponse(_sso_error_target("SSO is not configured."))

        if not container.auth_service.consume_sso_state(state):
            return RedirectResponse(_sso_error_target("Invalid or expired SSO state."))

        if not code:
            return RedirectResponse(_sso_error_target("Missing authorization code from provider."))

        try:
            metadata = await _fetch_oidc_metadata(general.sso_issuer_url)
            token_endpoint = metadata.get("token_endpoint")
        except Exception:
            _logger.exception("Failed to fetch token endpoint from %s", general.sso_issuer_url)
            return RedirectResponse(_sso_error_target("Could not read token endpoint from identity provider."))

        if not isinstance(token_endpoint, str) or not token_endpoint:
            return RedirectResponse(_sso_error_target("Identity provider does not expose token_endpoint."))

        token_payload_data = {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": general.sso_client_id,
            "client_secret": general.sso_client_secret,
            "redirect_uri": _sso_redirect_uri(request, general),
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            token_response = await client.post(
                token_endpoint,
                data=token_payload_data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            if token_response.status_code >= 400:
                return RedirectResponse(_sso_error_target("Token exchange failed."))
            token_payload = token_response.json()

        if not isinstance(token_payload, dict):
            return RedirectResponse(_sso_error_target("Invalid token response."))

        id_payload = _decode_jwt_payload(token_payload.get("id_token"))
        if not id_payload:
            id_payload = _decode_jwt_payload(token_payload.get("access_token"))
        username = _pick_username_from_token_payload(id_payload)
        if not username:
            return RedirectResponse(_sso_error_target("ID token does not include user identity."))

        session_token = container.auth_service.create_session_for_user(username)
        redirect_response = RedirectResponse(
            url="/",
            status_code=status.HTTP_303_SEE_OTHER,
        )
        _set_session_cookie(redirect_response, request, session_token)
        return redirect_response

    @app.post("/api/auth/register", response_model=AuthSessionResponse)
    async def register_admin(
        request: Request,
        response: Response,
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
        except PermissionError as exc:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=str(exc),
            ) from exc
        _set_session_cookie(response, request, session.token)
        return AuthSessionResponse.from_domain(session)

    @app.post("/api/auth/login", response_model=AuthSessionResponse)
    async def login_admin(
        request: Request,
        response: Response,
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
        _set_session_cookie(response, request, session.token)
        return AuthSessionResponse.from_domain(session)

    @app.post(
        "/api/auth/logout",
        status_code=status.HTTP_204_NO_CONTENT,
        dependencies=[Depends(require_admin_token)],
    )
    async def logout_admin(
        request: Request,
        response: Response,
        authorization: str | None = Header(default=None),
        x_admin_token: str | None = Header(default=None),
        cleanarr_session: str | None = Cookie(default=None, alias=_COOKIE_NAME),
    ) -> Response:
        token = _extract_token(authorization, x_admin_token) or cleanarr_session
        request.app.state.container.auth_service.logout(token)
        _set_session_cookie(response, request, None)
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
        include_in_schema=False,
    )
    @app.post(
        "/api/config/seerr",
        response_model=RuntimeConfigResponse,
        dependencies=[Depends(require_admin_token)],
    )
    async def create_seerr(
        request: Request,
        payload: SeerrServiceRequest,
    ) -> RuntimeConfigResponse:
        container = request.app.state.container
        config = container.config_service.add_service(payload.to_domain().kind, payload.to_domain())
        await container.refresh_runtime()
        return RuntimeConfigResponse.from_config(config, admin_token_configured=bool(container.admin_shared_token))

    @app.put(
        "/api/config/jellyseerr/{service_id}",
        response_model=RuntimeConfigResponse,
        dependencies=[Depends(require_admin_token)],
        include_in_schema=False,
    )
    @app.put(
        "/api/config/seerr/{service_id}",
        response_model=RuntimeConfigResponse,
        dependencies=[Depends(require_admin_token)],
    )
    async def update_seerr(
        request: Request,
        service_id: str,
        payload: SeerrServiceRequest,
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
        include_in_schema=False,
    )
    @app.delete(
        "/api/config/seerr/{service_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        dependencies=[Depends(require_admin_token)],
    )
    async def delete_seerr(request: Request, service_id: str) -> Response:
        container = request.app.state.container
        container.config_service.delete_service(ServiceKind.SEERR, service_id)
        await container.refresh_runtime()
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.post(
        "/api/config/jellyseerr/test",
        response_model=ConnectionTestResponse,
        dependencies=[Depends(require_admin_token)],
        include_in_schema=False,
    )
    @app.post(
        "/api/config/seerr/test",
        response_model=ConnectionTestResponse,
        dependencies=[Depends(require_admin_token)],
    )
    async def test_seerr(
        payload: SeerrServiceRequest,
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
        service = payload.to_domain()
        config = container.config_service.add_service(service.kind, service)
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
        service = payload.to_domain(service_id=service_id)
        config = container.config_service.update_service(service.kind, service_id, service)
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
        "/api/config/downloaders/transmission",
        response_model=RuntimeConfigResponse,
        dependencies=[Depends(require_admin_token)],
    )
    async def create_transmission(
        request: Request,
        payload: TransmissionServiceRequest,
    ) -> RuntimeConfigResponse:
        container = request.app.state.container
        service = payload.to_domain()
        config = container.config_service.add_service(service.kind, service)
        await container.refresh_runtime()
        return RuntimeConfigResponse.from_config(config, admin_token_configured=bool(container.admin_shared_token))

    @app.put(
        "/api/config/downloaders/transmission/{service_id}",
        response_model=RuntimeConfigResponse,
        dependencies=[Depends(require_admin_token)],
    )
    async def update_transmission(
        request: Request,
        service_id: str,
        payload: TransmissionServiceRequest,
    ) -> RuntimeConfigResponse:
        container = request.app.state.container
        service = payload.to_domain(service_id=service_id)
        config = container.config_service.update_service(service.kind, service_id, service)
        await container.refresh_runtime()
        return RuntimeConfigResponse.from_config(config, admin_token_configured=bool(container.admin_shared_token))

    @app.delete(
        "/api/config/downloaders/transmission/{service_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        dependencies=[Depends(require_admin_token)],
    )
    async def delete_transmission(request: Request, service_id: str) -> Response:
        container = request.app.state.container
        container.config_service.delete_service(ServiceKind.TRANSMISSION, service_id)
        await container.refresh_runtime()
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.post(
        "/api/config/downloaders/transmission/test",
        response_model=ConnectionTestResponse,
        dependencies=[Depends(require_admin_token)],
    )
    async def test_transmission(
        payload: TransmissionServiceRequest,
        request: Request,
    ) -> ConnectionTestResponse:
        result = await request.app.state.container.config_service.test_service(payload.to_domain())
        return ConnectionTestResponse.from_domain(result)

    @app.post(
        "/api/config/downloaders/deluge",
        response_model=RuntimeConfigResponse,
        dependencies=[Depends(require_admin_token)],
    )
    async def create_deluge(
        request: Request,
        payload: DelugeServiceRequest,
    ) -> RuntimeConfigResponse:
        container = request.app.state.container
        service = payload.to_domain()
        config = container.config_service.add_service(service.kind, service)
        await container.refresh_runtime()
        return RuntimeConfigResponse.from_config(config, admin_token_configured=bool(container.admin_shared_token))

    @app.put(
        "/api/config/downloaders/deluge/{service_id}",
        response_model=RuntimeConfigResponse,
        dependencies=[Depends(require_admin_token)],
    )
    async def update_deluge(
        request: Request,
        service_id: str,
        payload: DelugeServiceRequest,
    ) -> RuntimeConfigResponse:
        container = request.app.state.container
        service = payload.to_domain(service_id=service_id)
        config = container.config_service.update_service(service.kind, service_id, service)
        await container.refresh_runtime()
        return RuntimeConfigResponse.from_config(config, admin_token_configured=bool(container.admin_shared_token))

    @app.delete(
        "/api/config/downloaders/deluge/{service_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        dependencies=[Depends(require_admin_token)],
    )
    async def delete_deluge(request: Request, service_id: str) -> Response:
        container = request.app.state.container
        container.config_service.delete_service(ServiceKind.DELUGE, service_id)
        await container.refresh_runtime()
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.post(
        "/api/config/downloaders/deluge/test",
        response_model=ConnectionTestResponse,
        dependencies=[Depends(require_admin_token)],
    )
    async def test_deluge(
        payload: DelugeServiceRequest,
        request: Request,
    ) -> ConnectionTestResponse:
        result = await request.app.state.container.config_service.test_service(payload.to_domain())
        return ConnectionTestResponse.from_domain(result)

    @app.post(
        "/api/config/downloaders/rtorrent",
        response_model=RuntimeConfigResponse,
        dependencies=[Depends(require_admin_token)],
    )
    async def create_rtorrent(
        request: Request,
        payload: RTorrentServiceRequest,
    ) -> RuntimeConfigResponse:
        container = request.app.state.container
        service = payload.to_domain()
        config = container.config_service.add_service(service.kind, service)
        await container.refresh_runtime()
        return RuntimeConfigResponse.from_config(config, admin_token_configured=bool(container.admin_shared_token))

    @app.put(
        "/api/config/downloaders/rtorrent/{service_id}",
        response_model=RuntimeConfigResponse,
        dependencies=[Depends(require_admin_token)],
    )
    async def update_rtorrent(
        request: Request,
        service_id: str,
        payload: RTorrentServiceRequest,
    ) -> RuntimeConfigResponse:
        container = request.app.state.container
        service = payload.to_domain(service_id=service_id)
        config = container.config_service.update_service(service.kind, service_id, service)
        await container.refresh_runtime()
        return RuntimeConfigResponse.from_config(config, admin_token_configured=bool(container.admin_shared_token))

    @app.delete(
        "/api/config/downloaders/rtorrent/{service_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        dependencies=[Depends(require_admin_token)],
    )
    async def delete_rtorrent(request: Request, service_id: str) -> Response:
        container = request.app.state.container
        container.config_service.delete_service(ServiceKind.RTORRENT, service_id)
        await container.refresh_runtime()
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.post(
        "/api/config/downloaders/rtorrent/test",
        response_model=ConnectionTestResponse,
        dependencies=[Depends(require_admin_token)],
    )
    async def test_rtorrent(
        payload: RTorrentServiceRequest,
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
                http_status=_HTTP_UNPROCESSABLE_CONTENT,
                message="Request body is not valid JSON.",
            )
            raise HTTPException(
                status_code=_HTTP_UNPROCESSABLE_CONTENT,
                detail="Invalid JSON payload",
            ) from exc

        payload_list = payload if isinstance(payload, list) else [payload]
        if not payload_list:
            request.app.state.webhook_attempt_store.record(
                outcome="invalid_payload",
                http_status=_HTTP_UNPROCESSABLE_CONTENT,
                message="Payload array is empty. Jellyfin must send at least one event.",
            )
            raise HTTPException(
                status_code=_HTTP_UNPROCESSABLE_CONTENT,
                detail="Empty Jellyfin webhook payload",
            )

        try:
            webhook_payloads = [JellyfinWebhookPayload.model_validate(item) for item in payload_list]
        except ValidationError as exc:
            first_error = exc.errors()[0] if exc.errors() else None
            error_location = " -> ".join(str(part) for part in first_error["loc"]) if first_error is not None else ""
            error_message = first_error["msg"] if first_error is not None else "Payload validation failed."
            request.app.state.webhook_attempt_store.record(
                outcome="invalid_payload",
                http_status=_HTTP_UNPROCESSABLE_CONTENT,
                message=f"{error_location}: {error_message}" if error_location else error_message,
            )
            raise HTTPException(
                status_code=_HTTP_UNPROCESSABLE_CONTENT,
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
            payload_event_count=len(payload_list),
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
        accept_language = request.app.state.container.config.general.jellyfin_language
        jf_series_items = list(
            await jellyfin.list_items(
                include_types=["Series", "Season"],
                accept_language=accept_language,
            ),
        )
        jf_series_by_tvdb: dict[int, tuple[str, str]] = {}
        jf_series_by_tmdb: dict[int, tuple[str, str]] = {}
        jf_series_by_imdb: dict[str, tuple[str, str]] = {}
        # parent_id -> season_number -> (jellyfin_id, jellyfin_title)
        jf_seasons_by_parent: dict[str, dict[int, tuple[str, str]]] = {}

        for item in jf_series_items:
            if item.type == "Series":
                if item.tvdb_id:
                    jf_series_by_tvdb[item.tvdb_id] = (item.id, item.name)
                if item.tmdb_id:
                    jf_series_by_tmdb[item.tmdb_id] = (item.id, item.name)
                if item.imdb_id:
                    jf_series_by_imdb[item.imdb_id] = (item.id, item.name)
            elif item.type == "Season" and item.parent_id and item.season_number is not None:
                jf_seasons_by_parent.setdefault(item.parent_id, {})[item.season_number] = (
                    item.id,
                    item.name,
                )

        try:
            seerr_media_items = list(await container.seerr.list_media())
            seerr_requests = list(await container.seerr.list_requests())
        except Exception:  # noqa: BLE001
            _logger.warning(
                "Unable to load Seerr requests for the series library",
                exc_info=True,
            )
            seerr_media_items = []
            seerr_requests = []

        seerr_series_by_tvdb: dict[int, int] = {}
        seerr_series_by_tmdb: dict[int, int] = {}
        seerr_series_by_imdb: dict[str, int] = {}
        for item in seerr_media_items:
            if item.media_type.lower() not in {"tv", "series"}:
                continue
            if item.tvdb_id is not None:
                seerr_series_by_tvdb[item.tvdb_id] = item.id
            if item.tmdb_id is not None:
                seerr_series_by_tmdb[item.tmdb_id] = item.id
            if item.imdb_id is not None:
                seerr_series_by_imdb[item.imdb_id] = item.id
        requested_media_ids: set[int] = set()
        requested_seasons_by_media_id: dict[int, set[int]] = {}
        whole_series_request_ids: set[int] = set()
        for seerr_request in seerr_requests:
            requested_media_ids.add(seerr_request.media_id)
            if seerr_request.season_numbers:
                requested_seasons_by_media_id.setdefault(
                    seerr_request.media_id,
                    set(),
                ).update(seerr_request.season_numbers)
            else:
                whole_series_request_ids.add(seerr_request.media_id)

        def find_jf_series(series: SonarrSeries) -> tuple[str | None, str | None]:
            if series.tvdb_id and series.tvdb_id in jf_series_by_tvdb:
                return jf_series_by_tvdb[series.tvdb_id]
            if series.tmdb_id and series.tmdb_id in jf_series_by_tmdb:
                return jf_series_by_tmdb[series.tmdb_id]
            if series.imdb_id and series.imdb_id in jf_series_by_imdb:
                return jf_series_by_imdb[series.imdb_id]
            return None, None

        def find_seerr_series_id(series: SonarrSeries) -> int | None:
            if series.tvdb_id is not None:
                match = seerr_series_by_tvdb.get(series.tvdb_id)
                if match is not None:
                    return match
            if series.tmdb_id is not None:
                match = seerr_series_by_tmdb.get(series.tmdb_id)
                if match is not None:
                    return match
            if series.imdb_id is not None:
                match = seerr_series_by_imdb.get(series.imdb_id)
                if match is not None:
                    return match
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

            season_numbers = sorted({ep.season_number for ep in episodes if ep.season_number > 0})

            jf_series_id, jf_series_title = find_jf_series(series)
            jf_season_map = jf_seasons_by_parent.get(jf_series_id, {}) if jf_series_id else {}
            seerr_media_id = find_seerr_series_id(series)
            has_series_request = seerr_media_id is not None and seerr_media_id in requested_media_ids

            seasons = [
                SeasonSummary(
                    season_number=sn,
                    episode_count=episode_count_by_season.get(sn, 0),
                    episode_file_count=file_count_by_season.get(sn, 0),
                    size_bytes=size_by_season.get(sn, 0),
                    jellyfin_season_id=jf_season_map.get(sn, (None, None))[0],
                    jellyfin_title=jf_season_map.get(sn, (None, None))[1],
                    has_seerr_request=(
                        seerr_media_id is not None
                        and has_series_request
                        and (
                            seerr_media_id in whole_series_request_ids
                            or sn
                            in requested_seasons_by_media_id.get(
                                seerr_media_id,
                                set(),
                            )
                        )
                    ),
                )
                for sn in season_numbers
            ]
            result.append(
                SeriesSummary(
                    sonarr_id=series.id,
                    title=series.title,
                    jellyfin_series_title=jf_series_title,
                    seasons=seasons,
                    jellyfin_series_id=jf_series_id,
                    has_seerr_request=has_series_request,
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
        accept_language = request.app.state.container.config.general.jellyfin_language
        jf_movie_items = list(
            await jellyfin.list_items(include_types=["Movie"], accept_language=accept_language),
        )
        jf_movies_by_tmdb: dict[int, tuple[str, str]] = {}
        jf_movies_by_imdb: dict[str, tuple[str, str]] = {}
        for item in jf_movie_items:
            if item.tmdb_id:
                jf_movies_by_tmdb[item.tmdb_id] = (item.id, item.name)
            if item.imdb_id:
                jf_movies_by_imdb[item.imdb_id] = (item.id, item.name)

        try:
            seerr_media_items = list(await container.seerr.list_media())
            seerr_requests = list(await container.seerr.list_requests())
        except Exception:  # noqa: BLE001
            _logger.warning(
                "Unable to load Seerr requests for the movie library",
                exc_info=True,
            )
            seerr_media_items = []
            seerr_requests = []

        seerr_movies_by_tmdb = {
            item.tmdb_id: item.id for item in seerr_media_items if item.media_type.lower() == "movie" and item.tmdb_id
        }
        seerr_movies_by_imdb = {
            item.imdb_id: item.id for item in seerr_media_items if item.media_type.lower() == "movie" and item.imdb_id
        }
        requested_movie_ids = {item.media_id for item in seerr_requests}

        result: list[MovieSummary] = []
        for movie in sorted(movies_list, key=lambda m: m.title.lower()):
            jf_movie_id: str | None = None
            jellyfin_movie_title: str | None = None
            if movie.tmdb_id and movie.tmdb_id in jf_movies_by_tmdb:
                jf_movie_id, jellyfin_movie_title = jf_movies_by_tmdb[movie.tmdb_id]
            elif movie.imdb_id and movie.imdb_id in jf_movies_by_imdb:
                jf_movie_id, jellyfin_movie_title = jf_movies_by_imdb[movie.imdb_id]
            seerr_media_id: int | None = None
            if movie.tmdb_id and movie.tmdb_id in seerr_movies_by_tmdb:
                seerr_media_id = seerr_movies_by_tmdb[movie.tmdb_id]
            elif movie.imdb_id and movie.imdb_id in seerr_movies_by_imdb:
                seerr_media_id = seerr_movies_by_imdb[movie.imdb_id]
            result.append(
                MovieSummary(
                    radarr_id=movie.id,
                    title=movie.title,
                    jellyfin_movie_title=jellyfin_movie_title,
                    size_bytes=movie.size_on_disk or 0,
                    has_file=movie.has_file,
                    jellyfin_movie_id=jf_movie_id,
                    has_seerr_request=(seerr_media_id is not None and seerr_media_id in requested_movie_ids),
                )
            )
        return LibraryMoviesResponse(movies=result)

    @app.post(
        "/api/actions/delete/jobs",
        response_model=ManualDeleteJobResponse,
        status_code=status.HTTP_202_ACCEPTED,
        dependencies=[Depends(require_admin_token)],
    )
    async def queue_manual_delete(
        payload: ManualDeleteRequest,
    ) -> ManualDeleteJobResponse:
        return await deletion_jobs.submit(payload)

    @app.get(
        "/api/actions/delete/jobs",
        response_model=ManualDeleteJobListResponse,
        dependencies=[Depends(require_admin_token)],
    )
    async def list_manual_delete_jobs() -> ManualDeleteJobListResponse:
        return ManualDeleteJobListResponse(jobs=deletion_jobs.list_jobs())

    @app.get(
        "/api/actions/delete/jobs/{job_id}",
        response_model=ManualDeleteJobResponse,
        dependencies=[Depends(require_admin_token)],
    )
    async def get_manual_delete_job(job_id: UUID) -> ManualDeleteJobResponse:
        try:
            return deletion_jobs.get(job_id)
        except DeletionJobNotFoundError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Deletion job not found.",
            ) from exc

    @app.delete(
        "/api/actions/delete/jobs/{job_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        dependencies=[Depends(require_admin_token)],
    )
    async def dismiss_manual_delete_job(job_id: UUID) -> Response:
        try:
            deletion_jobs.dismiss(job_id)
        except DeletionJobNotFoundError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Deletion job not found.",
            ) from exc
        except DeletionJobActiveError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A running deletion job cannot be dismissed.",
            ) from exc
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.post(
        "/api/actions/delete",
        response_model=ProcessingResultResponse,
        dependencies=[Depends(require_admin_token)],
    )
    async def manual_delete(payload: ManualDeleteRequest) -> ProcessingResultResponse:
        return await execute_manual_delete(payload)

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
