"""HTTP adapter tests."""

from __future__ import annotations

import pytest
import respx

from cleanarr.infrastructure.clients import JellyseerrClient, QbittorrentClient, RadarrClient, SonarrClient


@pytest.mark.asyncio
@respx.mock
async def test_radarr_client_parses_movies_and_history() -> None:
    respx.get("http://radarr/api/v3/movie").respond(
        json=[{"id": 1, "title": "Movie", "path": "/data/movie", "tmdbId": 10, "imdbId": "tt10"}]
    )
    respx.get("http://radarr/api/v3/history/movie").respond(
        json=[
            {
                "id": 100,
                "movieId": 1,
                "eventType": "grabbed",
                "downloadId": "HASH10",
                "data": {"torrentInfoHash": "HASH10"},
            }
        ]
    )

    client = RadarrClient(base_url="http://radarr/api/v3", api_key="key", timeout_seconds=5)
    try:
        movies = await client.list_movies()
        history = await client.list_movie_history(1)
    finally:
        await client.close()

    assert movies[0].tmdb_id == 10
    assert history[0].download_id == "HASH10"


@pytest.mark.asyncio
@respx.mock
async def test_sonarr_client_parses_series_and_episode_data() -> None:
    respx.get("http://sonarr/api/v3/series").respond(
        json=[{"id": 5, "title": "Show", "path": "/data/show", "tvdbId": 20, "tmdbId": 21, "imdbId": "tt21"}]
    )
    respx.get("http://sonarr/api/v3/history/series").respond(
        json=[
            {
                "id": 200,
                "seriesId": 5,
                "episodeId": 77,
                "eventType": "grabbed",
                "downloadId": "HASH20",
                "data": {"releaseType": "MultiEpisode"},
            }
        ]
    )
    respx.get("http://sonarr/api/v3/episode").respond(
        json=[
            {
                "id": 77,
                "seriesId": 5,
                "seasonNumber": 1,
                "episodeNumber": 1,
                "episodeFileId": 700,
                "hasFile": True,
                "monitored": True,
            }
        ]
    )
    respx.get("http://sonarr/api/v3/episodeFile").respond(
        json=[{"id": 700, "path": "/data/show/S01E01.mkv", "relativePath": "S01E01.mkv", "seasonNumber": 1}]
    )

    client = SonarrClient(base_url="http://sonarr/api/v3", api_key="key", timeout_seconds=5)
    try:
        series = await client.list_series()
        history = await client.list_series_history(5)
        episodes = await client.list_episodes(5)
        episode_files = await client.list_episode_files(5)
    finally:
        await client.close()

    assert series[0].tvdb_id == 20
    assert history[0].download_id == "HASH20"
    assert episodes[0].episode_file_id == 700
    assert episode_files[0].path.endswith("S01E01.mkv")


@pytest.mark.asyncio
@respx.mock
async def test_jellyseerr_client_parses_media_requests_and_issues() -> None:
    media_route = respx.get("http://jellyseerr/api/v1/media").respond(
        json={
            "pageInfo": {"pages": 1, "page": 1},
            "results": [
                {"id": 1, "mediaType": "tv", "tmdbId": 5, "tvdbId": 6, "imdbId": "tt5", "jellyfinMediaId": "jf"}
            ],
        }
    )
    respx.get("http://jellyseerr/api/v1/request").respond(
        json={
            "pageInfo": {"results": 1},
            "results": [
                {
                    "id": 2,
                    "type": "tv",
                    "is4k": False,
                    "serverId": 0,
                    "profileId": 1,
                    "rootFolder": "/data",
                    "languageProfileId": None,
                    "requestedBy": {"id": 1},
                    "tags": [2],
                    "media": {"id": 1},
                    "seasons": [{"seasonNumber": 1}],
                }
            ],
        }
    )
    respx.get("http://jellyseerr/api/v1/issue").respond(
        json={
            "pageInfo": {"results": 1},
            "results": [{"id": 3, "problemSeason": 1, "problemEpisode": 2, "media": {"id": 1}}],
        }
    )

    client = JellyseerrClient(base_url="http://jellyseerr/api/v1", api_key="key", timeout_seconds=5)
    try:
        media = await client.list_media()
        requests = await client.list_requests()
        issues = await client.list_issues()
    finally:
        await client.close()

    assert media[0].jellyfin_media_id == "jf"
    assert requests[0].season_numbers == (1,)
    assert issues[0].problem_episode == 2
    assert media_route.calls[0].request.url.params["skip"] == "0"
    assert "page" not in media_route.calls[0].request.url.params


@pytest.mark.asyncio
@respx.mock
async def test_jellyseerr_client_adds_xsrf_header_for_mutations() -> None:
    head_route = respx.head("http://jellyseerr/api/v1/request/2").respond(
        status_code=405,
        headers=[
            ("set-cookie", "XSRF-TOKEN=test-xsrf-token; Path=/; Secure; SameSite=Strict"),
            ("set-cookie", "_csrf=test-cookie; Path=/; HttpOnly; Secure; SameSite=Strict"),
        ],
    )
    delete_route = respx.delete("http://jellyseerr/api/v1/request/2").respond(status_code=204)

    client = JellyseerrClient(base_url="http://jellyseerr/api/v1", api_key="key", timeout_seconds=5)
    try:
        await client.delete_request(2)
    finally:
        await client.close()

    assert head_route.called
    assert delete_route.called
    assert delete_route.calls[0].request.headers["X-XSRF-TOKEN"] == "test-xsrf-token"
    assert delete_route.calls[0].request.headers["X-Api-Key"] == "key"


@pytest.mark.asyncio
@respx.mock
async def test_qbittorrent_client_marks_absent_hashes() -> None:
    respx.post("http://qbt/api/v2/auth/login").respond(text="Ok.")
    respx.get("http://qbt/api/v2/torrents/info").respond(json=[{"hash": "AA"}])
    delete_route = respx.post("http://qbt/api/v2/torrents/delete").respond(status_code=200)

    client = QbittorrentClient(base_url="http://qbt", username="user", password="pass", timeout_seconds=5)
    try:
        results = await client.delete_hashes(["AA", "BB"], delete_files=True)
    finally:
        await client.close()

    assert delete_route.called
    assert [(result.hash_value, result.existed) for result in results] == [("AA", True), ("BB", False)]
