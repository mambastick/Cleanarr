"""Authenticated Downloads transport routes."""

from __future__ import annotations

from typing import cast

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Query, Request, status

from cleanarr.api.download_schemas import (
    DownloadActionRequest,
    DownloadActionResponse,
    DownloadItemResponse,
    DownloadRefreshResponse,
    DownloadsResponse,
)
from cleanarr.application.downloads import (
    DownloadRequestError,
    DownloadsService,
    NullDownloaderFleet,
    collect_arr_history_evidence,
    decode_cursor,
    encode_cursor,
)
from cleanarr.application.ports import DownloaderFleetPort
from cleanarr.domain.downloads import TorrentSnapshot, TorrentState


async def _require_admin_token(
    request: Request,
    authorization: str | None = Header(default=None),
    x_admin_token: str | None = Header(default=None),
    x_csrf_token: str | None = Header(default=None),
    cleanarr_session: str | None = Cookie(default=None, alias="cleanarr_session"),
) -> None:
    # Delayed import avoids an app/router import cycle while sharing the exact
    # authentication and CSRF dependency used by existing admin mutations.
    from cleanarr.api.app import require_admin_token

    await require_admin_token(request, authorization, x_admin_token, x_csrf_token, cleanarr_session)


def _service(request: Request) -> DownloadsService:
    return cast(DownloadsService, request.app.state.downloads_service)


def _filtered(request: Request, service: DownloadsService) -> tuple[list[TorrentSnapshot], dict[str, str | None]]:
    filters = {
        "client": request.query_params.get("client"),
        "kind": request.query_params.get("kind"),
        "state": request.query_params.get("state"),
        "ownership": request.query_params.get("ownership"),
        "category": request.query_params.get("category"),
        "tag": request.query_params.get("tag"),
    }
    allowed = {
        "state": {item.value for item in TorrentState},
        "ownership": {"managed", "unmanaged", "conflict", "unknown"},
    }
    for key, value in filters.items():
        if value is not None and (not value or len(value) > 128):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"invalid_{key}_filter")
    for key in ("state", "ownership"):
        if filters[key] is not None and filters[key] not in allowed[key]:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"invalid_{key}_filter")
    items = service.snapshots()
    result = []
    for item in items:
        if filters["client"] and item.client_id != filters["client"]:
            continue
        if filters["kind"] and item.client_kind != filters["kind"]:
            continue
        if filters["state"] and item.state.value != filters["state"]:
            continue
        if filters["ownership"] and item.ownership.value != filters["ownership"]:
            continue
        if filters["category"] and (item.category or "").casefold() != filters["category"].casefold():
            continue
        if filters["tag"] and (
            item.tags is None or filters["tag"].casefold() not in {tag.casefold() for tag in item.tags}
        ):
            continue
        result.append(item)
    result.sort(key=lambda item: (item.client_id, item.info_hash))
    return result, filters


def create_downloads_router() -> APIRouter:
    router = APIRouter(prefix="/api/downloads", tags=["downloads"])

    @router.get("", response_model=DownloadsResponse, dependencies=[Depends(_require_admin_token)])
    async def list_downloads(
        request: Request,
        limit: int = Query(default=50, ge=1, le=50),
        cursor: str | None = Query(default=None, max_length=4096),
    ) -> DownloadsResponse:
        service = _service(request)
        items, filters = _filtered(request, service)
        if cursor:
            try:
                after = decode_cursor(cursor, filters)
            except DownloadRequestError as exc:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail={"code": "invalid_cursor", "message": "Cursor is invalid or does not match filters."},
                ) from exc
            items = [item for item in items if (item.client_id, item.info_hash) > after]
        page = items[:limit]
        policy = service.repository.latest_policy_evaluations()
        page_keys = {(item.client_id, item.info_hash) for item in page}
        actions = service.repository.latest_action_projections(page_keys)
        next_cursor = encode_cursor(filters, (page[-1].client_id, page[-1].info_hash)) if len(items) > limit else None
        active = sum(
            item.state not in {TorrentState.STOPPED, TorrentState.ERROR, TorrentState.UNKNOWN}
            for item in service.snapshots()
        )
        return DownloadsResponse(
            items=[
                DownloadItemResponse.from_domain(
                    item,
                    policy.get((item.client_id, item.info_hash)),
                    actions.get((item.client_id, item.info_hash)),
                )
                for item in page
            ],
            next_cursor=next_cursor,
            source_status="complete" if service.last_refresh.complete else "partial",
            failures=list(service.last_refresh.failures),
            failure_details=[
                {"client_id": client_id, "code": code} for client_id, code in service.last_refresh.failure_details
            ],
            active_count=active,
        )

    @router.get(
        "/{client_id}/{info_hash}",
        response_model=DownloadItemResponse,
        dependencies=[Depends(_require_admin_token)],
    )
    async def download_detail(request: Request, client_id: str, info_hash: str) -> DownloadItemResponse:
        if not client_id or len(client_id) > 128:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invalid_client_id")
        if len(info_hash) not in {40, 64} or any(character not in "0123456789abcdefABCDEF" for character in info_hash):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invalid_info_hash")
        item = _service(request).repository.get_snapshot(client_id, info_hash.upper())
        if item is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="download_not_found")
        return DownloadItemResponse.from_domain(
            item,
            _service(request).repository.latest_policy_evaluations().get((client_id, info_hash.upper())),
            _service(request)
            .repository.latest_action_projections({(client_id, info_hash.upper())})
            .get((client_id, info_hash.upper())),
        )

    @router.post("/refresh", response_model=DownloadRefreshResponse, dependencies=[Depends(_require_admin_token)])
    async def refresh_downloads(request: Request) -> DownloadRefreshResponse:
        service = _service(request)
        service.set_downloader(
            cast(
                DownloaderFleetPort,
                getattr(request.app.state.container, "downloader", NullDownloaderFleet()),
            )
        )
        config = request.app.state.container.config
        history_hashes, history_failed = await collect_arr_history_evidence(
            radarr=getattr(request.app.state.container, "radarr", None),
            radarr_configured=any(profile.enabled for profile in config.radarr),
            sonarr=getattr(request.app.state.container, "sonarr", None),
            sonarr_configured=any(profile.enabled for profile in config.sonarr),
        )
        result = await service.refresh(
            config=request.app.state.container.config.general,
            arr_history_hashes=history_hashes,
            arr_source_failed=history_failed,
        )
        await service.evaluate_and_apply_policy(config=request.app.state.container.config.general)
        items = service.snapshots()
        policy = service.repository.latest_policy_evaluations()
        response_items = items[:50]
        actions = service.repository.latest_action_projections(
            {(item.client_id, item.info_hash) for item in response_items}
        )
        active = sum(
            item.state not in {TorrentState.STOPPED, TorrentState.ERROR, TorrentState.UNKNOWN} for item in items
        )
        return DownloadRefreshResponse(
            items=[
                DownloadItemResponse.from_domain(
                    item,
                    policy.get((item.client_id, item.info_hash)),
                    actions.get((item.client_id, item.info_hash)),
                )
                for item in response_items
            ],
            next_cursor=None,
            source_status="complete" if result.complete else "partial",
            failures=list(result.failures),
            failure_details=[{"client_id": client_id, "code": code} for client_id, code in result.failure_details],
            active_count=active,
            refreshed=result.complete,
        )

    @router.post("/actions", response_model=DownloadActionResponse, dependencies=[Depends(_require_admin_token)])
    async def control_download(request: Request, payload: DownloadActionRequest) -> DownloadActionResponse:
        service = _service(request)
        service.set_downloader(
            cast(
                DownloaderFleetPort,
                getattr(request.app.state.container, "downloader", NullDownloaderFleet()),
            )
        )
        try:
            action_id, action_status, code = await service.control(
                client_id=payload.client_id,
                info_hash=payload.info_hash,
                action=payload.action,
                idempotency_key=payload.idempotency_key,
                dry_run=request.app.state.container.config.general.dry_run,
            )
        except DownloadRequestError as exc:
            if str(exc) == "idempotency_conflict":
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    detail={"code": "idempotency_conflict", "message": "Idempotency key is already bound."},
                ) from exc
            code = str(exc)
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"code": code, "message": "Download action request is invalid."},
            ) from exc
        return DownloadActionResponse(action_id=action_id, status=action_status, code=code)

    return router
