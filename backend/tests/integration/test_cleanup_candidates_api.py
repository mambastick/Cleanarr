from __future__ import annotations

from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient

from cleanarr.api.app import create_app
from cleanarr.api.cleanup_candidates import DeletionLinkResponse
from cleanarr.api.library_schemas import ManualDeleteRequest
from cleanarr.application.cleanup_candidates import CleanupCandidatesResult
from cleanarr.domain import (
    CleanupCandidate,
    CleanupMediaType,
    JellyfinCleanupItem,
    PlaybackAggregate,
    PlaybackStatus,
    SeedingSummary,
)
from cleanarr.domain.config import GeneralConfig, JellyfinServiceConfig, RuntimeConfig
from tests.integration.test_api import FakeContainer, FakeService


class CandidateService:
    def with_sources(self, **_: object) -> CandidateService:
        return self

    async def list_candidates(self, **_: object) -> CleanupCandidatesResult:
        now = datetime(2026, 1, 1, tzinfo=UTC)
        candidates = tuple(
            CleanupCandidate(
                JellyfinCleanupItem(str(index), f"Movie {index}", CleanupMediaType.MOVIE, now, now, index),
                PlaybackAggregate(PlaybackStatus.NEVER_WATCHED, 0, 0, None),
                SeedingSummary("unknown", "unknown", "arr_mapping_unknown", unavailable_reason="arr_mapping_unknown"),
                None,
                None,
                "jellyfin_standard",
                now,
            )
            for index in range(2)
        )
        return CleanupCandidatesResult(candidates, "complete", (), False)


class DynamicPlayback:
    def __init__(self) -> None:
        self.languages: list[str | None] = []

    async def list_cleanup_items(self, *, accept_language: str | None, **_: object):  # type: ignore[no-untyped-def]
        self.languages.append(accept_language)
        item = JellyfinCleanupItem("intentional-item-id", "Dynamic", CleanupMediaType.MOVIE, None, None, None)
        return (item,), False

    async def list_playback_users(self, **_: object):  # type: ignore[no-untyped-def]
        return ("private-user-id",), False

    async def list_user_playback(self, **_: object):  # type: ignore[no-untyped-def]
        from cleanarr.domain import PlaybackObservation

        return (PlaybackObservation("private-user-id", "intentional-item-id", False, 0, None),)


@pytest.mark.asyncio
async def test_cleanup_candidates_requires_auth_and_binds_cursor_filters(tmp_path) -> None:  # type: ignore[no-untyped-def]
    container = FakeContainer(FakeService(results=[]), db_path=tmp_path / "cleanup.db")
    container.config = RuntimeConfig(
        jellyfin=[JellyfinServiceConfig(name="Jellyfin", url="http://jellyfin", api_key="key")]
    )
    app = create_app(container=container)
    app.state.cleanup_candidates_service = CandidateService()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        assert (await client.get("/api/downloads/cleanup-candidates")).status_code == 403
        first = await client.get(
            "/api/downloads/cleanup-candidates?limit=1&media_type=movie&sort=size",
            headers={"X-Admin-Token": "admin-token"},
        )
        assert first.status_code == 200
        payload = first.json()
        assert payload["items"][0]["jellyfin_item_id"] == "1"
        assert "jellyfin_standard" == payload["items"][0]["data_source"]
        assert "user_id" not in str(payload).casefold()
        assert "username" not in str(payload).casefold()
        mismatched = await client.get(
            f"/api/downloads/cleanup-candidates?limit=1&media_type=series&sort=size&cursor={payload['next_cursor']}",
            headers={"X-Admin-Token": "admin-token"},
        )
        assert mismatched.status_code == 422
        assert mismatched.json()["detail"]["code"] == "invalid_cursor"
        # A valid base64 JSON array is still not a valid cursor object.
        malformed = "W10"
        assert (
            await client.get(
                f"/api/downloads/cleanup-candidates?cursor={malformed}", headers={"X-Admin-Token": "admin-token"}
            )
        ).status_code == 422
        assert (
            await client.get(
                "/api/downloads/cleanup-candidates?seed_readiness=nope",
                headers={"X-Admin-Token": "admin-token"},
            )
        ).status_code == 422
        assert (
            await client.get(
                "/api/downloads/cleanup-candidates?limit=51",
                headers={"X-Admin-Token": "admin-token"},
            )
        ).status_code == 422


@pytest.mark.asyncio
async def test_cleanup_candidates_refreshes_sources_after_runtime_configuration_swap(tmp_path) -> None:  # type: ignore[no-untyped-def]
    container = FakeContainer(FakeService(results=[]), db_path=tmp_path / "dynamic.db")
    app = create_app(container=container)
    container.config = RuntimeConfig(
        general=GeneralConfig(jellyfin_language="en"),
        jellyfin=[JellyfinServiceConfig(name="Jellyfin", url="http://jellyfin", api_key="key")],
    )
    dynamic = DynamicPlayback()
    container.jellyfin_server = dynamic
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/downloads/cleanup-candidates", headers={"X-Admin-Token": "admin-token"})
        overridden = await client.get(
            "/api/downloads/cleanup-candidates", headers={"X-Admin-Token": "admin-token", "Accept-Language": "ru"}
        )
    assert response.status_code == 200
    assert overridden.status_code == 200
    assert response.json()["items"][0]["jellyfin_item_id"] == "intentional-item-id"
    assert dynamic.languages == ["en", "ru"]


def test_deletion_prefill_matches_existing_manual_request_contract() -> None:
    prefill = DeletionLinkResponse(
        item_type="Movie",
        radarr_movie_id=12,
        sonarr_series_id=None,
        jellyfin_item_id="intentional-item-id",
        display_name="Safe display name",
    ).model_dump()
    request = ManualDeleteRequest.model_validate(prefill)
    assert request.radarr_movie_id == 12
    assert request.sonarr_series_id is None
    assert request.confirmed_plan_hash is None and request.idempotency_key is None
