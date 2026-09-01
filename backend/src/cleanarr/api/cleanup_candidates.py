"""Authenticated, read-only cleanup-candidate transport."""

from __future__ import annotations

import base64
import json
from datetime import datetime
from typing import Literal, cast

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Query, Request, status
from pydantic import BaseModel

from cleanarr.application.cleanup_candidates import CleanupCandidatesResult, CleanupCandidatesService
from cleanarr.domain import CleanupCandidate, PlaybackStatus

_SORTS = {"play_count", "last_played", "library_added", "size", "seed_ratio", "seed_time", "seed_readiness"}


async def _require_admin_token(
    request: Request,
    authorization: str | None = Header(default=None),
    x_admin_token: str | None = Header(default=None),
    x_csrf_token: str | None = Header(default=None),
    cleanarr_session: str | None = Cookie(default=None, alias="cleanarr_session"),
) -> None:
    from cleanarr.api.app import require_admin_token

    await require_admin_token(request, authorization, x_admin_token, x_csrf_token, cleanarr_session)


class DeletionLinkResponse(BaseModel):
    item_type: Literal["Movie", "Series"]
    radarr_movie_id: int | None
    sonarr_series_id: int | None
    jellyfin_item_id: str
    display_name: str


class SeedingResponse(BaseModel):
    torrent_state: str
    readiness: str
    readiness_reason: str | None
    torrent_count: int | None
    ratio: float | None
    seeding_time_seconds: int | None
    unavailable_reason: str | None


class CleanupCandidateResponse(BaseModel):
    jellyfin_item_id: str
    display_name: str
    media_type: str
    created_at: datetime | None
    added_at: datetime | None
    size_bytes: int | None
    playback_status: PlaybackStatus
    play_count: int | None
    watched_user_count: int | None
    last_played_at: datetime | None
    playback_unavailable_reason: str | None
    data_source: Literal["jellyfin_standard"]
    fetched_at: datetime
    unavailable_reason: str | None
    seeding: SeedingResponse
    deletion_link: DeletionLinkResponse | None

    @classmethod
    def from_domain(cls, candidate: CleanupCandidate) -> CleanupCandidateResponse:
        return cls(
            jellyfin_item_id=candidate.item.item_id,
            display_name=candidate.item.display_name,
            media_type=candidate.item.media_type.value,
            created_at=candidate.item.created_at,
            added_at=candidate.item.added_at,
            size_bytes=candidate.item.size_bytes,
            playback_status=candidate.playback.status,
            play_count=candidate.playback.play_count,
            watched_user_count=candidate.playback.watched_user_count,
            last_played_at=candidate.playback.last_played_at,
            playback_unavailable_reason=candidate.playback.unavailable_reason,
            data_source="jellyfin_standard",
            fetched_at=candidate.fetched_at,
            unavailable_reason=candidate.unavailable_reason,
            seeding=SeedingResponse(**candidate.seeding.__dict__),
            deletion_link=(
                DeletionLinkResponse(**candidate.deletion_link.__dict__) if candidate.deletion_link else None
            ),
        )


class CleanupCandidatesResponse(BaseModel):
    items: list[CleanupCandidateResponse]
    next_cursor: str | None
    source_status: str
    failure_codes: list[str]
    truncated: bool


def _encode_cursor(binding: dict[str, str], offset: int) -> str:
    encoded = json.dumps({"v": 1, "q": binding, "o": offset}, sort_keys=True, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(encoded).decode().rstrip("=")


def _decode_cursor(value: str, binding: dict[str, str]) -> int:
    try:
        decoded = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
        payload = json.loads(decoded)
        if not isinstance(payload, dict):
            raise ValueError
        raw_offset: object = payload.get("o")
        if payload.get("v") != 1 or payload.get("q") != binding or not isinstance(raw_offset, int):
            raise ValueError
        offset = raw_offset
        if offset < 0 or offset > 10_000:
            raise ValueError
        return offset
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "invalid_cursor", "message": "Cursor is invalid or does not match the requested filters."},
        ) from exc


def _sort_value(candidate: CleanupCandidate, sort: str) -> object | None:
    if sort == "play_count":
        return candidate.playback.play_count
    if sort == "last_played":
        return candidate.playback.last_played_at
    if sort == "library_added":
        return candidate.item.added_at or candidate.item.created_at
    if sort == "size":
        return candidate.item.size_bytes
    if sort == "seed_ratio":
        return candidate.seeding.ratio
    if sort == "seed_time":
        return candidate.seeding.seeding_time_seconds
    return {"disabled": 0, "excluded": 1, "blocked": 2, "eligible": 3}.get(candidate.seeding.readiness)


def _sorted(candidates: list[CleanupCandidate], *, sort: str, direction: str) -> list[CleanupCandidate]:
    # Unknown/null values always follow known values, in both directions.  The
    # explicit Jellyfin item-id tie-breaker makes cursor pages deterministic.
    known = [item for item in candidates if _sort_value(item, sort) is not None]
    unknown = [item for item in candidates if _sort_value(item, sort) is None]
    known.sort(key=lambda item: (_sort_value(item, sort), item.item.item_id), reverse=direction == "desc")
    unknown.sort(key=lambda item: item.item.item_id)
    return [*known, *unknown]


def create_cleanup_candidates_router() -> APIRouter:
    router = APIRouter(prefix="/api/downloads", tags=["downloads"])

    @router.get(
        "/cleanup-candidates",
        response_model=CleanupCandidatesResponse,
        dependencies=[Depends(_require_admin_token)],
    )
    async def list_cleanup_candidates(
        request: Request,
        limit: int = Query(default=50, ge=1, le=50),
        cursor: str | None = Query(default=None, max_length=4096),
        playback_status: PlaybackStatus | None = Query(default=None),  # noqa: B008
        media_type: Literal["movie", "series"] | None = Query(default=None),
        seed_readiness: Literal["eligible", "blocked", "excluded", "disabled", "unknown"] | None = Query(default=None),
        sort: str = Query(default="library_added", max_length=32),
        direction: Literal["asc", "desc"] = Query(default="desc"),
        accept_language: str | None = Header(default=None, max_length=64),
    ) -> CleanupCandidatesResponse:
        if sort not in _SORTS:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail={"code": "invalid_sort"})
        binding = {
            "playback_status": playback_status.value if playback_status else "",
            "media_type": media_type or "",
            "seed_readiness": seed_readiness or "",
            "sort": sort,
            "direction": direction,
        }
        offset = _decode_cursor(cursor, binding) if cursor else 0
        service = cast(CleanupCandidatesService, request.app.state.cleanup_candidates_service)
        config = request.app.state.container.config
        fallback_playback, fallback_radarr, fallback_sonarr = request.app.state.cleanup_candidate_fallbacks
        request_service = service.with_sources(
            playback=getattr(request.app.state.container, "jellyfin_server", fallback_playback),
            radarr=getattr(request.app.state.container, "radarr", fallback_radarr),
            sonarr=getattr(request.app.state.container, "sonarr", fallback_sonarr),
        )
        result: CleanupCandidatesResult = await request_service.list_candidates(
            accept_language=accept_language or config.general.jellyfin_language,
            jellyfin_configured=any(item.enabled for item in config.jellyfin),
            radarr_configured=any(item.enabled for item in config.radarr),
            sonarr_configured=any(item.enabled for item in config.sonarr),
            config=config.general,
        )
        candidates = [
            item
            for item in result.candidates
            if (playback_status is None or item.playback.status is playback_status)
            and (media_type is None or item.item.media_type.value == media_type)
            and (seed_readiness is None or item.seeding.readiness == seed_readiness)
        ]
        ordered = _sorted(candidates, sort=sort, direction=direction)
        page = ordered[offset : offset + limit]
        next_cursor = _encode_cursor(binding, offset + len(page)) if offset + len(page) < len(ordered) else None
        return CleanupCandidatesResponse(
            items=[CleanupCandidateResponse.from_domain(item) for item in page],
            next_cursor=next_cursor,
            source_status=result.source_status,
            failure_codes=list(result.failure_codes),
            truncated=result.truncated,
        )

    return router
