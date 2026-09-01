from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from cleanarr.api.app import create_app
from cleanarr.domain.downloads import (
    DownloadActionStatus,
    DownloadControlAction,
    ListingFreshness,
    TorrentSnapshot,
    TorrentState,
)
from tests.integration.test_api import FakeContainer, FakeService


def _item(index: int) -> TorrentSnapshot:
    return TorrentSnapshot(
        client_id="client",
        client_name="Client",
        client_kind="qbittorrent",
        info_hash=f"{index:040x}",
        display_name=f"Item {index}",
        state=TorrentState.SEEDING,
        observed_at=datetime.now(UTC),
        freshness=ListingFreshness.FRESH,
    )


@pytest.mark.asyncio
async def test_downloads_api_auth_cursor_bounds_and_refresh(tmp_path: Path) -> None:
    app = create_app(container=FakeContainer(FakeService(results=[]), db_path=tmp_path / "db.sqlite"))
    app.state.downloads_service.repository.save_listing(tuple(_item(index) for index in range(51)), {"client"})
    repository = app.state.downloads_service.repository
    target = _item(0)
    repository.record_policy_evaluation(
        revision="revision",
        snapshot=target,
        facts={"ratio": 2.0, "freshness": "fresh", "ownership": "managed"},
        reason_code="thresholds_not_met",
        decision="blocked",
    )
    claim = repository.claim_action(
        idempotency_key=str(uuid4()),
        canonical_request="{}",
        client_id=target.client_id,
        info_hash=target.info_hash,
        action=DownloadControlAction.PAUSE,
        max_attempts=1,
        source="policy",
    )
    repository.update_action(
        claim.action_id,
        DownloadActionStatus.FAILED,
        code="target_not_fresh",
        result={"outcome": "blocked", "code": "target_not_fresh"},
    )
    headers = {"X-Admin-Token": "admin-token"}
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            assert (await client.get("/api/downloads")).status_code == 403
            assert (
                await client.get("/api/downloads", cookies={"cleanarr_session": "session-token"})
            ).status_code == 200
            assert (
                await client.post(
                    "/api/downloads/refresh",
                    cookies={"cleanarr_session": "session-token"},
                    headers={"Origin": "http://test"},
                )
            ).status_code == 403
            response = await client.get("/api/downloads?limit=50", headers=headers)
            assert response.status_code == 200
            assert len(response.json()["items"]) == 50
            projected = response.json()["items"][0]
            assert datetime.fromisoformat(projected["observed_at"]).tzinfo is not None
            assert projected["policy_reason_code"] == "thresholds_not_met"
            assert projected["policy_facts"]["ratio"] == 2.0
            assert projected["latest_action"]["source"] == "policy"
            assert projected["latest_action"]["code"] == "target_not_fresh"
            assert "idempotency_key" not in projected["latest_action"]
            cursor = response.json()["next_cursor"]
            assert cursor
            assert (await client.get("/api/downloads?limit=50&cursor=not-a-cursor", headers=headers)).status_code == 422
            assert (
                await client.get("/api/downloads?limit=50&cursor=" + cursor + "&state=stopped", headers=headers)
            ).status_code == 422
            assert (await client.get("/api/downloads?limit=51", headers=headers)).status_code == 422
            assert (await client.post("/api/downloads/refresh", headers=headers)).status_code == 200
            assert (
                await client.post(
                    "/api/downloads/actions",
                    headers=headers,
                    json={
                        "client_id": "client",
                        "info_hash": "bad",
                        "action": "pause",
                        "idempotency_key": str(uuid4()),
                    },
                )
            ).status_code == 422
