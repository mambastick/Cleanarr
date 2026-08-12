"""FastAPI application factory."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import secrets
from collections.abc import Sequence
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, cast
from urllib.parse import quote, urlencode, urlsplit
from uuid import UUID

from fastapi import Cookie, Depends, FastAPI, Header, HTTPException, Query, Request, Response, status
from fastapi.responses import FileResponse, PlainTextResponse, RedirectResponse
from pydantic import BaseModel, ValidationError
from starlette.middleware.base import RequestResponseEndpoint

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
    DeletionPreflightError,
    DeletionProgressReporter,
    ManualDeletionJobStore,
    validate_plan_confirmation,
)
from cleanarr.api.event_processing import DeletionExecutionCoordinator
from cleanarr.api.library_schemas import (
    LibraryMoviesResponse,
    LibrarySeriesResponse,
    ManualDeleteJobListResponse,
    ManualDeleteJobPhase,
    ManualDeleteJobResponse,
    ManualDeletePreviewResponse,
    ManualDeleteRequest,
    MovieSummary,
    SeasonSummary,
    SeriesSummary,
)
from cleanarr.api.operations import (
    ConfigImportResponse,
    RedactedConfigExport,
    SupportBundle,
    build_support_bundle,
    export_redacted_config,
    import_redacted_config,
    render_metrics,
)
from cleanarr.api.schemas import JellyfinWebhookPayload, ProcessingResultResponse, WebhookBatchResponse
from cleanarr.application.authentication import LoginThrottledError
from cleanarr.application.results import observe_actions
from cleanarr.application.service import CascadeDeletionService
from cleanarr.domain import (
    ActionResult,
    ActionStatus,
    FailureReason,
    ItemType,
    MediaDeletionEvent,
    MediaFingerprint,
    OverallStatus,
    ProcessingResult,
    SonarrSeries,
)
from cleanarr.domain.config import BaseServiceConfig, GeneralConfig, ServiceKind
from cleanarr.infrastructure.container import ServiceContainer
from cleanarr.infrastructure.oidc import (
    OIDCError,
    create_pkce_challenge,
    discover_oidc_provider,
    exchange_authorization_code,
    fetch_jwks,
    validate_id_token,
)
from cleanarr.infrastructure.settings import Settings

_logger = logging.getLogger("cleanarr")
_COOKIE_NAME = "cleanarr_session"
_SSO_STATE_COOKIE_NAME = "cleanarr_sso_state"
_COOKIE_MAX_AGE_SECONDS = 60 * 60 * 24 * 7
_SSO_STATE_MAX_AGE_SECONDS = 60 * 5
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
            version = "unknown"
            get_version = getattr(client, "get_version", None)
            if get_version is not None:
                try:
                    version = str(await asyncio.wait_for(get_version(), timeout=10.0))
                except Exception:  # noqa: BLE001
                    version = "unknown"
            health_store.update(name, "healthy", version=version)
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


def _cookie_secure(request: Request) -> bool:
    secure_override = getattr(request.app.state.container.settings, "session_cookie_secure", None)
    return request.url.scheme == "https" if secure_override is None else bool(secure_override)


def _set_session_cookie(response: Response, request: Request, token: str | None) -> None:
    secure = _cookie_secure(request)
    if token:
        response.set_cookie(
            key=_COOKIE_NAME,
            value=token,
            httponly=True,
            max_age=_COOKIE_MAX_AGE_SECONDS,
            samesite="strict",
            secure=secure,
            path="/",
        )
    else:
        response.delete_cookie(
            _COOKIE_NAME,
            path="/",
            httponly=True,
            samesite="strict",
            secure=secure,
        )


def _set_sso_state_cookie(response: Response, request: Request, state: str | None) -> None:
    secure = _cookie_secure(request)
    if state:
        response.set_cookie(
            key=_SSO_STATE_COOKIE_NAME,
            value=state,
            httponly=True,
            max_age=_SSO_STATE_MAX_AGE_SECONDS,
            samesite="lax",
            secure=secure,
            path="/api/auth/sso/callback",
        )
    else:
        response.delete_cookie(
            _SSO_STATE_COOKIE_NAME,
            path="/api/auth/sso/callback",
            httponly=True,
            samesite="lax",
            secure=secure,
        )


def _sso_redirect_uri(request: Request, general: GeneralConfig) -> str:
    if general.sso_redirect_uri:
        return general.sso_redirect_uri
    return str(request.url_for("sso_callback"))


def _sso_error_target(message: str) -> str:
    return f"{_SSO_ERROR_PREFIX}{quote(message)}"


def _sso_redirect_response(request: Request, target: str) -> RedirectResponse:
    response = RedirectResponse(target, status_code=status.HTTP_303_SEE_OTHER)
    _set_sso_state_cookie(response, request, None)
    response.headers["Cache-Control"] = "no-store"
    return response


def _constant_time_equal(expected: str, provided: str) -> bool:
    return secrets.compare_digest(expected.encode("utf-8"), provided.encode("utf-8"))


def _is_same_origin_browser_request(request: Request) -> bool:
    source = request.headers.get("origin") or request.headers.get("referer")
    if not source:
        return False
    parsed = urlsplit(source)
    expected_host = request.headers.get("host", "").casefold()
    return (
        parsed.scheme in {"http", "https"}
        and bool(parsed.netloc)
        and parsed.netloc.casefold() == expected_host
        and not parsed.username
        and not parsed.password
    )


def _require_same_origin_browser_request(request: Request) -> None:
    if not _is_same_origin_browser_request(request):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Same-origin browser request required",
        )


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
    if provided is None or not _constant_time_equal(expected, provided):
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
    x_csrf_token: str | None = Header(default=None),
    cleanarr_session: str | None = Cookie(default=None, alias=_COOKIE_NAME),
) -> None:
    """Validate admin access via session token or fallback static token."""

    container = request.app.state.container
    header_token = _extract_token(authorization, x_admin_token)
    if header_token:
        if container.auth_service.resolve_session(header_token):
            return
        expected = container.admin_shared_token
        if expected and _constant_time_equal(expected, header_token):
            return
    elif cleanarr_session and container.auth_service.resolve_session(cleanarr_session):
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            _require_same_origin_browser_request(request)
            if not container.auth_service.verify_csrf_token(cleanarr_session, x_csrf_token):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Invalid CSRF token",
                )
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
    execution_coordinator = DeletionExecutionCoordinator(Path(settings.db_path))
    static_dir = Path(__file__).resolve().parents[1] / "ui" / "static"

    async def resolve_manual_delete(payload: ManualDeleteRequest) -> MediaDeletionEvent:
        """Resolve a manual library selection to a stable deletion event."""

        container = resolved_container

        if payload.item_type is ItemType.MOVIE:
            if payload.radarr_movie_id is None:
                raise HTTPException(
                    status_code=_HTTP_UNPROCESSABLE_CONTENT,
                    detail="radarr_movie_id is required for movie deletion.",
                )
            movies_list = list(await container.radarr.list_movies())
            movie = next((movie for movie in movies_list if movie.id == payload.radarr_movie_id), None)
            if movie is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Radarr movie {payload.radarr_movie_id} not found.",
                )
            return MediaDeletionEvent(
                notification_type="ItemDeleted",
                item_type=ItemType.MOVIE,
                item_id=f"manual:radarr:{movie.id}",
                name=movie.title,
                fingerprint=MediaFingerprint(
                    tmdb_id=movie.tmdb_id,
                    imdb_id=movie.imdb_id,
                    path=movie.path,
                ),
            )

        if payload.item_type not in {ItemType.SERIES, ItemType.SEASON}:
            raise HTTPException(
                status_code=_HTTP_UNPROCESSABLE_CONTENT,
                detail="Manual deletion supports movies, series, and seasons.",
            )
        if payload.sonarr_series_id is None:
            raise HTTPException(
                status_code=_HTTP_UNPROCESSABLE_CONTENT,
                detail="sonarr_series_id is required for series/season deletion.",
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
        scope = "series" if payload.item_type is ItemType.SERIES else f"season:{payload.season_number}"
        return MediaDeletionEvent(
            notification_type="ItemDeleted",
            item_type=payload.item_type,
            item_id=f"manual:sonarr:{series.id}:{scope}",
            name=series.title,
            fingerprint=MediaFingerprint(
                tvdb_id=series.tvdb_id,
                tmdb_id=series.tmdb_id,
                imdb_id=series.imdb_id,
                path=series.path,
            ),
            series_name=series.title,
            season_number=payload.season_number,
        )

    def with_jellyfin_action(result: ProcessingResult, action: ActionResult) -> ProcessingResult:
        actions = (*result.actions, action)
        overall = OverallStatus.PARTIAL_FAILURE if action.status is ActionStatus.FAILED else result.status
        return ProcessingResult(
            event=result.event,
            status=overall,
            actions=actions,
            correlation_id=result.correlation_id,
        )

    async def preview_manual_delete(
        payload: ManualDeleteRequest,
        event: MediaDeletionEvent,
    ) -> ProcessingResultResponse:
        """Build a mutation-free plan containing every intended target."""

        strategy = resolved_container.strategy_factory.for_item_type(event.item_type, dry_run=True)
        result = await strategy.handle(event)
        if payload.jellyfin_item_id:
            result = with_jellyfin_action(
                result,
                ActionResult(
                    system="jellyfin",
                    action="delete_item",
                    status=ActionStatus.DRY_RUN,
                    message="Would remove the selected item from Jellyfin after downstream cleanup succeeds.",
                    details={"jellyfin_item_id": payload.jellyfin_item_id},
                ),
            )
        return ProcessingResultResponse.from_domain(result)

    async def execute_manual_delete(
        payload: ManualDeleteRequest,
        event: MediaDeletionEvent,
        report_progress: DeletionProgressReporter | None = None,
    ) -> ProcessingResultResponse:
        """Execute a previously resolved manual deletion and record its outcome."""

        report = report_progress or _ignore_deletion_progress
        container = resolved_container
        item_name = event.name

        report(
            ManualDeleteJobPhase.CLEANING,
            30,
            "Cleaning up Arr services, torrent clients, and Seerr.",
            item_name,
        )
        strategy = container.strategy_factory.for_item_type(event.item_type)
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

        if payload.jellyfin_item_id and container.config.general.dry_run:
            result = with_jellyfin_action(
                result,
                ActionResult(
                    system="jellyfin",
                    action="delete_item",
                    status=ActionStatus.DRY_RUN,
                    message="Would remove the selected item from Jellyfin after downstream cleanup succeeds.",
                    details={"jellyfin_item_id": payload.jellyfin_item_id},
                ),
            )
        elif payload.jellyfin_item_id and result.status is OverallStatus.PARTIAL_FAILURE:
            result = with_jellyfin_action(
                result,
                ActionResult(
                    system="jellyfin",
                    action="delete_item",
                    status=ActionStatus.SKIPPED,
                    message="Kept the Jellyfin item because downstream cleanup did not finish safely.",
                    reason=FailureReason.DOWNSTREAM_ERROR,
                    details={"jellyfin_item_id": payload.jellyfin_item_id},
                ),
            )
        elif payload.jellyfin_item_id:
            report(
                ManualDeleteJobPhase.JELLYFIN,
                92,
                "Removing the item from Jellyfin.",
                item_name,
            )
            try:
                await container.jellyfin_server.delete_item(payload.jellyfin_item_id)
            except Exception as exc:  # noqa: BLE001
                _logger.warning(
                    "Failed to delete Jellyfin item %s after cascade deletion",
                    payload.jellyfin_item_id,
                )
                result = with_jellyfin_action(
                    result,
                    ActionResult(
                        system="jellyfin",
                        action="delete_item",
                        status=ActionStatus.FAILED,
                        message="Could not remove the selected item from Jellyfin.",
                        reason=FailureReason.DOWNSTREAM_ERROR,
                        details={"jellyfin_item_id": payload.jellyfin_item_id, "error": str(exc)},
                    ),
                )
            else:
                result = with_jellyfin_action(
                    result,
                    ActionResult(
                        system="jellyfin",
                        action="delete_item",
                        status=ActionStatus.DELETED,
                        message="Removed the selected item from Jellyfin.",
                        details={"jellyfin_item_id": payload.jellyfin_item_id},
                    ),
                )
        else:
            report(
                ManualDeleteJobPhase.RECORDING,
                95,
                "Finalizing the background task.",
                item_name,
            )

        report(
            ManualDeleteJobPhase.RECORDING,
            97,
            "Saving the cleanup result to activity history.",
            item_name,
        )
        await activity_store.record(result)
        return ProcessingResultResponse.from_domain(result)

    deletion_jobs = ManualDeletionJobStore(
        resolve_manual_delete,
        preview_manual_delete,
        execute_manual_delete,
        db_path=Path(settings.db_path),
        execution_lock=execution_coordinator.lock,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> Any:
        await execution_coordinator.initialize()
        await activity_store.initialize()
        app.state.container = resolved_container
        app.state.activity_store = activity_store
        app.state.webhook_attempt_store = webhook_attempt_store
        app.state.health_probe_store = health_probe_store
        app.state.deletion_jobs = deletion_jobs
        app.state.execution_coordinator = execution_coordinator
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

    app = FastAPI(title="CleanArr", version="1.0.0", lifespan=lifespan)
    app.state.container = resolved_container
    app.state.activity_store = activity_store
    app.state.webhook_attempt_store = webhook_attempt_store
    app.state.health_probe_store = health_probe_store
    app.state.deletion_jobs = deletion_jobs
    app.state.execution_coordinator = execution_coordinator

    @app.middleware("http")
    async def security_headers(request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'; "
            "object-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; font-src 'self'; "
            "img-src 'self' data:; connect-src 'self'",
        )
        if request.url.path.startswith("/api/auth/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/health/live")
    async def health_live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready")
    async def health_ready() -> dict[str, str]:
        return {"status": "ready"}

    @app.get(
        "/api/dashboard",
        response_model=DashboardResponse,
        dependencies=[Depends(require_admin_token)],
    )
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
    async def sso_start(request: Request, response: Response) -> SSOLoginResponse:
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
            metadata = await discover_oidc_provider(general.sso_issuer_url)
        except OIDCError as exc:
            _logger.exception("Failed to fetch OIDC discovery for %s", general.sso_issuer_url)
            raise HTTPException(
                status_code=_HTTP_UNPROCESSABLE_CONTENT,
                detail="Could not fetch OpenID discovery data.",
            ) from exc

        state, authorization = container.auth_service.create_sso_state()
        params = {
            "response_type": "code",
            "client_id": general.sso_client_id,
            "redirect_uri": _sso_redirect_uri(request, general),
            "scope": general.sso_scopes,
            "state": state,
            "nonce": authorization.nonce,
            "code_challenge": create_pkce_challenge(authorization.code_verifier),
            "code_challenge_method": "S256",
        }
        authorize_url = f"{metadata.authorization_endpoint}?{urlencode(params)}"
        _set_sso_state_cookie(response, request, state)
        response.headers["Cache-Control"] = "no-store"
        return SSOLoginResponse(authorize_url=authorize_url)

    @app.get("/api/auth/sso/callback", name="sso_callback")
    async def sso_callback(
        request: Request,
        code: str | None = Query(default=None),
        state: str | None = Query(default=None),
        error: str | None = Query(default=None),
        cleanarr_sso_state: str | None = Cookie(default=None, alias=_SSO_STATE_COOKIE_NAME),
    ) -> Response:
        if not state or not cleanarr_sso_state or not _constant_time_equal(state, cleanarr_sso_state):
            return _sso_redirect_response(request, _sso_error_target("Invalid or expired SSO browser state."))

        authorization = request.app.state.container.auth_service.consume_sso_state(state)
        if authorization is None:
            return _sso_redirect_response(request, _sso_error_target("Invalid or expired SSO state."))

        if error:
            return _sso_redirect_response(request, _sso_error_target("Identity provider denied authentication."))

        container = request.app.state.container
        general = container.config.general
        if not container.auth_service.is_sso_auth_enabled(
            general,
        ) or not container.auth_service.is_sso_configured(general):
            return _sso_redirect_response(request, _sso_error_target("SSO is not configured."))

        if not code:
            return _sso_redirect_response(request, _sso_error_target("Missing authorization code from provider."))

        try:
            metadata = await discover_oidc_provider(general.sso_issuer_url)
            token_payload = await exchange_authorization_code(
                metadata,
                code=code,
                client_id=general.sso_client_id,
                client_secret=general.sso_client_secret,
                redirect_uri=_sso_redirect_uri(request, general),
                code_verifier=authorization.code_verifier,
            )
            jwks = await fetch_jwks(metadata)
            id_payload = validate_id_token(
                token_payload.get("id_token"),
                jwks=jwks,
                metadata=metadata,
                client_id=general.sso_client_id,
                expected_nonce=authorization.nonce,
            )
            username = container.auth_service.authorize_sso_identity(general, id_payload)
        except (OIDCError, PermissionError) as exc:
            _logger.warning("SSO callback rejected: %s", exc)
            return _sso_redirect_response(
                request,
                _sso_error_target("SSO token validation or access policy failed."),
            )

        session = container.auth_service.create_session_for_user(username)
        redirect_response = RedirectResponse(
            url="/",
            status_code=status.HTTP_303_SEE_OTHER,
        )
        _set_session_cookie(redirect_response, request, session.token)
        _set_sso_state_cookie(redirect_response, request, None)
        redirect_response.headers["Cache-Control"] = "no-store"
        return redirect_response

    @app.post("/api/auth/register", response_model=AuthSessionResponse)
    async def register_admin(
        request: Request,
        response: Response,
        payload: AdminCredentialsRequest,
    ) -> AuthSessionResponse:
        _require_same_origin_browser_request(request)
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
        response.headers["Cache-Control"] = "no-store"
        return AuthSessionResponse.from_domain(session)

    @app.post("/api/auth/login", response_model=AuthSessionResponse)
    async def login_admin(
        request: Request,
        response: Response,
        payload: AdminCredentialsRequest,
    ) -> AuthSessionResponse:
        _require_same_origin_browser_request(request)
        try:
            session = request.app.state.container.auth_service.login(
                username=payload.username,
                password=payload.password,
                source=request.client.host if request.client else "unknown",
            )
        except LoginThrottledError as exc:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=str(exc),
                headers={"Retry-After": str(exc.retry_after_seconds)},
            ) from exc
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
        response.headers["Cache-Control"] = "no-store"
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
        cleanarr_session: str | None = Cookie(default=None, alias=_COOKIE_NAME),
    ) -> Response:
        token = _extract_token(authorization, x_admin_token) or cleanarr_session
        request.app.state.container.auth_service.logout(token)
        logout_response = Response(status_code=status.HTTP_204_NO_CONTENT)
        _set_session_cookie(logout_response, request, None)
        return logout_response

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

    @app.get(
        "/api/config/export",
        response_model=RedactedConfigExport,
        dependencies=[Depends(require_admin_token)],
    )
    async def export_runtime_config(request: Request) -> RedactedConfigExport:
        return export_redacted_config(request.app.state.container.config)

    @app.post(
        "/api/config/import",
        response_model=ConfigImportResponse,
        dependencies=[Depends(require_admin_token)],
    )
    async def import_runtime_config(
        request: Request,
        payload: RedactedConfigExport,
    ) -> ConfigImportResponse:
        container = request.app.state.container
        config, result = import_redacted_config(container.config, payload)
        container.config_service.replace_config(config)
        request.app.state.activity_store.set_retention_days(config.general.activity_retention_days)
        await container.refresh_runtime()
        return result

    @app.get(
        "/metrics",
        response_class=PlainTextResponse,
        dependencies=[Depends(require_admin_token)],
    )
    async def metrics(request: Request) -> PlainTextResponse:
        payload = await render_metrics(
            version=app.version,
            config=request.app.state.container.config,
            activity_store=request.app.state.activity_store,
            webhook_attempt_store=request.app.state.webhook_attempt_store,
            health_probe_store=request.app.state.health_probe_store,
            deletion_jobs=request.app.state.deletion_jobs,
        )
        return PlainTextResponse(
            payload,
            media_type="text/plain; version=0.0.4; charset=utf-8",
        )

    @app.get(
        "/api/support/bundle",
        response_model=SupportBundle,
        dependencies=[Depends(require_admin_token)],
    )
    async def support_bundle(request: Request) -> SupportBundle:
        return await build_support_bundle(
            version=app.version,
            config=request.app.state.container.config,
            activity_store=request.app.state.activity_store,
            webhook_attempt_store=request.app.state.webhook_attempt_store,
            health_probe_store=request.app.state.health_probe_store,
            deletion_jobs=request.app.state.deletion_jobs,
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

        service = cast(CascadeDeletionService, request.app.state.container.service)

        async def process_and_record(event: MediaDeletionEvent) -> ProcessingResult:
            result = await service.process(event)
            await request.app.state.activity_store.record(result)
            return result

        results: list[ProcessingResult] = []
        duplicate_count = 0
        for item in webhook_payloads:
            result, duplicate = await execution_coordinator.process_webhook(
                item.to_domain(),
                process_and_record,
            )
            results.append(result)
            if duplicate:
                duplicate_count += 1
        batch_response = WebhookBatchResponse.from_results(results)
        first_payload = webhook_payloads[0]
        request.app.state.webhook_attempt_store.record(
            outcome="processed",
            http_status=status.HTTP_200_OK,
            message=(
                f"Processed {len(results)} Jellyfin event(s); suppressed {duplicate_count} completed duplicate(s). "
                f"Overall status: {batch_response.status}."
            ),
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
        "/api/actions/delete/preview",
        response_model=ManualDeletePreviewResponse,
        dependencies=[Depends(require_admin_token)],
    )
    async def preview_manual_deletion(
        payload: ManualDeleteRequest,
    ) -> ManualDeletePreviewResponse:
        return await deletion_jobs.preview(payload)

    @app.post(
        "/api/actions/delete/jobs",
        response_model=ManualDeleteJobResponse,
        status_code=status.HTTP_202_ACCEPTED,
        dependencies=[Depends(require_admin_token)],
    )
    async def queue_manual_delete(
        payload: ManualDeleteRequest,
    ) -> ManualDeleteJobResponse:
        try:
            return await deletion_jobs.submit(payload)
        except DeletionPreflightError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(exc),
            ) from exc

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
                detail="An active deletion job cannot be dismissed.",
            ) from exc
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.post(
        "/api/actions/delete",
        response_model=ProcessingResultResponse,
        dependencies=[Depends(require_admin_token)],
        include_in_schema=False,
    )
    async def manual_delete(payload: ManualDeleteRequest) -> ProcessingResultResponse:
        async with execution_coordinator.lock:
            event = await resolve_manual_delete(payload)
            plan = await preview_manual_delete(payload, event)
            try:
                validate_plan_confirmation(payload, plan)
            except DeletionPreflightError as exc:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=str(exc),
                ) from exc
            return await execute_manual_delete(payload, event)

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
