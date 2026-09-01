from __future__ import annotations

import httpx
import pytest
import respx

from cleanarr.infrastructure.clients import JellyfinServerClient


@pytest.mark.asyncio
@respx.mock
async def test_standard_jellyfin_cleanup_reads_use_bounded_canonical_queries() -> None:
    calls: list[httpx.Request] = []

    def items(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        params = request.url.params
        if "UserId" in params:
            return httpx.Response(
                200,
                json={"Items": [{"Id": "movie", "UserData": {"Played": False, "PlayCount": 0}}]},
            )
        return httpx.Response(
            200,
            json={
                "TotalRecordCount": 1,
                "Items": [
                    {
                        "Id": "movie",
                        "Name": "A Movie",
                        "Type": "Movie",
                        "DateCreated": "2026-01-01T00:00:00Z",
                        "DateLastMediaAdded": "2026-01-02T00:00:00Z",
                        "ProviderIds": {"Tmdb": "1"},
                        "MediaSources": [{"Size": 42}],
                    }
                ],
            },
        )

    items_route = respx.get("http://jellyfin/Items").mock(side_effect=items)
    users_route = respx.get("http://jellyfin/Users").respond(json=[{"Id": "user"}])
    client = JellyfinServerClient(base_url="http://jellyfin", api_key="key", timeout_seconds=5)
    try:
        catalogue, truncated = await client.list_cleanup_items(accept_language="ru", max_items=200)
        users, users_truncated = await client.list_playback_users(max_users=20)
        observations = await client.list_user_playback(user_id=users[0], item_ids=("movie",), accept_language="ru")
    finally:
        await client.close()

    assert not truncated and not users_truncated
    assert catalogue[0].size_bytes == 42
    assert observations[0].play_count == 0
    assert users_route.called and items_route.call_count == 2
    catalogue_call, playback_call = calls
    assert catalogue_call.headers["Accept-Language"] == "ru"
    assert catalogue_call.url.params["Recursive"] == "true"
    assert catalogue_call.url.params["EnableUserData"] == "false"
    assert catalogue_call.url.params["Fields"] == "DateCreated,DateLastMediaAdded,MediaSources,ParentId,ProviderIds"
    assert playback_call.url.params["UserId"] == "user"
    assert playback_call.url.params["Ids"] == "movie"
    assert playback_call.url.params["EnableUserData"] == "true"
