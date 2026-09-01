"""HTTP adapter tests."""

from __future__ import annotations

import httpx
import pytest
import respx

from cleanarr.domain import (
    AuthenticationError,
    DownloadControlAction,
    DownloadControlOutcome,
    ExternalServiceError,
    SeerrRequest,
    TorrentState,
)
from cleanarr.domain.config import TorrentRemovalPolicy
from cleanarr.infrastructure.clients import (
    JellyfinServerClient,
    NullDownloaderClient,
    QbittorrentClient,
    RadarrClient,
    SeerrClient,
    SonarrClient,
)


@pytest.mark.asyncio
@respx.mock
async def test_service_clients_report_versions_from_documented_status_contracts() -> None:
    respx.get("http://radarr/api/v3/system/status").respond(json={"version": "5.1.0"})
    respx.get("http://sonarr/api/v3/system/status").respond(json={"version": "4.2.0"})
    respx.get("http://seerr/api/v1/status").respond(json={"version": "2.7.0"})
    respx.get("http://jellyfin/System/Info").respond(json={"Version": "10.11.0"})
    clients = [
        RadarrClient(base_url="http://radarr/api/v3", api_key="key", timeout_seconds=5),
        SonarrClient(base_url="http://sonarr/api/v3", api_key="key", timeout_seconds=5),
        SeerrClient(base_url="http://seerr/api/v1", api_key="key", timeout_seconds=5),
        JellyfinServerClient(base_url="http://jellyfin", api_key="key", timeout_seconds=5),
    ]
    try:
        versions = [await client.get_version() for client in clients]
    finally:
        for client in clients:
            await client.close()

    assert versions == ["5.1.0", "4.2.0", "2.7.0", "10.11.0"]


@pytest.mark.asyncio
@respx.mock
async def test_jellyfin_ping_validates_the_configured_token() -> None:
    respx.get("http://jellyfin/System/Info").respond(status_code=401)
    client = JellyfinServerClient(base_url="http://jellyfin", api_key="wrong", timeout_seconds=5)
    try:
        with pytest.raises(AuthenticationError):
            await client.ping()
    finally:
        await client.close()


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
async def test_seerr_client_parses_media_requests_and_issues() -> None:
    media_route = respx.get("http://seerr/api/v1/media").respond(
        json={
            "pageInfo": {"pages": 1, "page": 1},
            "results": [
                {"id": 1, "mediaType": "tv", "tmdbId": 5, "tvdbId": 6, "imdbId": "tt5", "jellyfinMediaId": "jf"}
            ],
        }
    )
    respx.get("http://seerr/api/v1/request").respond(
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
    respx.get("http://seerr/api/v1/issue").respond(
        json={
            "pageInfo": {"results": 1},
            "results": [{"id": 3, "problemSeason": 1, "problemEpisode": 2, "media": {"id": 1}}],
        }
    )

    client = SeerrClient(base_url="http://seerr/api/v1", api_key="key", timeout_seconds=5)
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
async def test_seerr_client_tolerates_null_tags() -> None:
    respx.get("http://seerr/api/v1/request").respond(
        json={
            "pageInfo": {"results": 1},
            "results": [
                {
                    "id": 2,
                    "type": "movie",
                    "is4k": False,
                    "serverId": 0,
                    "profileId": 1,
                    "rootFolder": "/data",
                    "languageProfileId": None,
                    "requestedBy": {"id": 1},
                    "tags": None,
                    "media": {"id": 1},
                    "seasons": None,
                }
            ],
        }
    )

    client = SeerrClient(base_url="http://seerr/api/v1", api_key="key", timeout_seconds=5)
    try:
        requests = await client.list_requests()
    finally:
        await client.close()

    assert requests == [
        SeerrRequest(
            id=2,
            media_id=1,
            media_type="movie",
            season_numbers=(),
            is_4k=False,
            server_id=0,
            profile_id=1,
            root_folder="/data",
            language_profile_id=None,
            requested_by_id=1,
            tags=(),
        )
    ]


@pytest.mark.asyncio
@respx.mock
@pytest.mark.parametrize("scheme", ["http", "https"])
async def test_seerr_client_adds_xsrf_cookie_and_header_for_mutations(scheme: str) -> None:
    base_url = f"{scheme}://seerr/api/v1"
    head_route = respx.head(f"{base_url}/request/2").respond(
        status_code=405,
        headers=[
            ("set-cookie", "XSRF-TOKEN=test-xsrf-token; Path=/; Secure; SameSite=Strict"),
            ("set-cookie", "_csrf=test-cookie; Path=/; HttpOnly; Secure; SameSite=Strict"),
        ],
    )
    delete_route = respx.delete(f"{base_url}/request/2").respond(status_code=204)

    client = SeerrClient(base_url=base_url, api_key="key", timeout_seconds=5)
    try:
        await client.delete_request(2)
    finally:
        await client.close()

    assert head_route.called
    assert delete_route.called
    assert delete_route.calls[0].request.headers["X-XSRF-TOKEN"] == "test-xsrf-token"
    assert delete_route.calls[0].request.headers["X-Api-Key"] == "key"
    cookie_header = delete_route.calls[0].request.headers["Cookie"]
    assert "_csrf=test-cookie" in cookie_header
    assert "XSRF-TOKEN=test-xsrf-token" in cookie_header


@pytest.mark.asyncio
@respx.mock
async def test_seerr_client_preserves_existing_cookies_for_mutations() -> None:
    respx.head("http://seerr/api/v1/request/2").respond(
        status_code=405,
        headers=[
            ("set-cookie", "XSRF-TOKEN=test-xsrf-token; Path=/; Secure; SameSite=Strict"),
            ("set-cookie", "_csrf=test-cookie; Path=/; HttpOnly; Secure; SameSite=Strict"),
        ],
    )
    delete_route = respx.delete("http://seerr/api/v1/request/2").respond(status_code=204)

    client = SeerrClient(base_url="http://seerr/api/v1", api_key="key", timeout_seconds=5)
    try:
        await client._request_with_xsrf(
            "DELETE",
            "/request/2",
            expected_statuses={204},
            headers={"Cookie": "existing=value; _csrf=stale-secret; XSRF-TOKEN=stale-token"},
        )
    finally:
        await client.close()

    cookie_header = delete_route.calls[0].request.headers["Cookie"]
    assert "existing=value" in cookie_header
    assert "_csrf=test-cookie" in cookie_header
    assert "XSRF-TOKEN=test-xsrf-token" in cookie_header
    assert "stale-secret" not in cookie_header
    assert "stale-token" not in cookie_header


@pytest.mark.asyncio
@respx.mock
async def test_seerr_client_mutates_without_xsrf_headers_when_csrf_is_disabled() -> None:
    respx.head("http://seerr/api/v1/request/2").respond(status_code=405)
    delete_route = respx.delete("http://seerr/api/v1/request/2").respond(status_code=204)

    client = SeerrClient(base_url="http://seerr/api/v1", api_key="key", timeout_seconds=5)
    try:
        await client.delete_request(2)
    finally:
        await client.close()

    assert delete_route.called
    assert "X-XSRF-TOKEN" not in delete_route.calls[0].request.headers
    assert "Cookie" not in delete_route.calls[0].request.headers


@pytest.mark.asyncio
@respx.mock
async def test_seerr_client_requires_complete_csrf_cookie_pair() -> None:
    respx.head("http://seerr/api/v1/request/2").respond(
        status_code=405,
        headers={"set-cookie": "XSRF-TOKEN=test-xsrf-token; Path=/; Secure; SameSite=Strict"},
    )

    client = SeerrClient(base_url="http://seerr/api/v1", api_key="key", timeout_seconds=5)
    try:
        with pytest.raises(ExternalServiceError, match="_csrf missing"):
            await client.delete_request(2)
    finally:
        await client.close()


@pytest.mark.asyncio
@respx.mock
async def test_seerr_client_reports_mutation_forbidden_as_downstream_error() -> None:
    respx.head("http://seerr/api/v1/request/2").respond(
        status_code=405,
        headers=[
            ("set-cookie", "XSRF-TOKEN=test-xsrf-token; Path=/; Secure; SameSite=Strict"),
            ("set-cookie", "_csrf=test-cookie; Path=/; HttpOnly; Secure; SameSite=Strict"),
        ],
    )
    respx.delete("http://seerr/api/v1/request/2").respond(
        status_code=403,
        json={"status": 403, "error": "invalid csrf token"},
    )

    client = SeerrClient(base_url="http://seerr/api/v1", api_key="key", timeout_seconds=5)
    try:
        with pytest.raises(ExternalServiceError, match="unexpected status 403") as exc_info:
            await client.delete_request(2)
    finally:
        await client.close()

    assert not isinstance(exc_info.value, AuthenticationError)


@pytest.mark.asyncio
@respx.mock
async def test_seerr_ping_uses_authenticated_endpoint_and_checks_csrf_cookies() -> None:
    ping_route = respx.get("http://seerr/api/v1/auth/me").respond(
        json={"id": 1},
        headers=[
            ("set-cookie", "XSRF-TOKEN=test-xsrf-token; Path=/; Secure; SameSite=Strict"),
            ("set-cookie", "_csrf=test-cookie; Path=/; HttpOnly; Secure; SameSite=Strict"),
        ],
    )

    client = SeerrClient(base_url="http://seerr/api/v1", api_key="key", timeout_seconds=5)
    try:
        await client.ping()
    finally:
        await client.close()

    assert ping_route.called
    assert ping_route.calls[0].request.headers["X-Api-Key"] == "key"


@pytest.mark.asyncio
@respx.mock
async def test_seerr_ping_rejects_incomplete_csrf_cookie_pair() -> None:
    respx.get("http://seerr/api/v1/auth/me").respond(
        json={"id": 1},
        headers={"set-cookie": "XSRF-TOKEN=test-xsrf-token; Path=/; Secure; SameSite=Strict"},
    )

    client = SeerrClient(base_url="http://seerr/api/v1", api_key="key", timeout_seconds=5)
    try:
        with pytest.raises(ExternalServiceError, match="_csrf missing"):
            await client.ping()
    finally:
        await client.close()


@pytest.mark.asyncio
@respx.mock
async def test_qbittorrent_client_accepts_no_content_login_response() -> None:
    respx.post("http://qbt/api/v2/auth/login").respond(status_code=204)
    respx.get("http://qbt/api/v2/app/version").respond(text="v5.2.1")

    client = QbittorrentClient(base_url="http://qbt", username="user", password="pass", timeout_seconds=5)
    try:
        await client.ping()
    finally:
        await client.close()


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


@pytest.mark.asyncio
@respx.mock
async def test_qbittorrent_client_supports_stateless_api_key_authentication() -> None:
    version_route = respx.get(
        "http://qbt/api/v2/app/version",
        headers={"Authorization": "Bearer qbt_test_key"},
    ).respond(text="v5.2.1")
    login_route = respx.post("http://qbt/api/v2/auth/login").respond(text="should not be called")

    client = QbittorrentClient(base_url="http://qbt", api_key="qbt_test_key", timeout_seconds=5)
    try:
        version = await client.get_version()
    finally:
        await client.close()

    assert version == "v5.2.1"
    assert version_route.called
    assert login_route.called is False


@pytest.mark.asyncio
@respx.mock
async def test_qbittorrent_client_maps_hybrid_hashes_to_one_policy_checked_removal() -> None:
    respx.post("http://qbt/api/v2/auth/login").respond(text="Ok.")
    respx.get("http://qbt/api/v2/torrents/info").respond(
        json=[
            {
                "hash": "V1HASH",
                "infohash_v1": "V1HASH",
                "infohash_v2": "V2HASH",
                "ratio": 2.0,
                "seeding_time": 7_200,
            }
        ]
    )
    delete_route = respx.post("http://qbt/api/v2/torrents/delete").respond(status_code=200)

    client = QbittorrentClient(
        base_url="http://qbt",
        username="user",
        password="pass",
        timeout_seconds=5,
        seeding_policy=TorrentRemovalPolicy.DEFER,
        min_seed_ratio=1.5,
        min_seed_time_minutes=60,
    )
    try:
        results = await client.delete_hashes(["v1hash", "v2hash"], delete_files=True)
    finally:
        await client.close()

    assert delete_route.calls[0].request.content == b"hashes=V1HASH&deleteFiles=true"
    assert [(result.hash_value, result.existed, result.skip_reason) for result in results] == [
        ("V1HASH", True, None),
        ("V2HASH", True, None),
    ]


@pytest.mark.asyncio
@respx.mock
@pytest.mark.parametrize(
    ("version", "action", "initial_stopped", "endpoint"),
    [
        ("v5.2.3", DownloadControlAction.PAUSE, False, "stop"),
        ("v5.2.3", DownloadControlAction.RESUME, True, "start"),
        ("v4.6.7", DownloadControlAction.PAUSE, False, "pause"),
        ("v4.6.7", DownloadControlAction.RESUME, True, "resume"),
    ],
)
async def test_qbittorrent_control_protocol_matrix(
    version: str, action: DownloadControlAction, initial_stopped: bool, endpoint: str
) -> None:
    info_hash = "C" * 40
    stopped = initial_stopped
    stale_reads = 0

    respx.post("http://qbt/api/v2/auth/login").respond(text="Ok.")
    respx.get("http://qbt/api/v2/app/version").respond(text=version)

    def info_handler(_: httpx.Request) -> httpx.Response:
        nonlocal stale_reads
        visible_stopped = not stopped if stale_reads else stopped
        stale_reads = max(0, stale_reads - 1)
        return httpx.Response(
            200,
            json=[
                {
                    "hash": info_hash,
                    "name": "/private/path",
                    "state": "pausedDL" if visible_stopped else "downloading",
                    "progress": 0.5,
                    "tracker": "https://tracker.example/announce",
                    "eta": 8640001,
                }
            ],
        )

    route = respx.get("http://qbt/api/v2/torrents/info").mock(side_effect=info_handler)

    def control_handler(request: httpx.Request) -> httpx.Response:
        nonlocal stale_reads, stopped
        assert request.content == f"hashes={info_hash}".encode()
        stopped = action is DownloadControlAction.PAUSE
        stale_reads = 1
        return httpx.Response(200)

    controls = {
        name: respx.post(f"http://qbt/api/v2/torrents/{name}").mock(side_effect=control_handler)
        for name in ("stop", "start", "pause", "resume")
    }
    delete = respx.post("http://qbt/api/v2/torrents/delete").respond(status_code=200)
    client = QbittorrentClient(base_url="http://qbt", username="user", password="pass", timeout_seconds=5)
    try:
        listing = await client.list_torrents()
        result = await client.control_torrent(info_hash, action=action)
    finally:
        await client.close()

    assert listing.torrents[0].display_name is None
    assert listing.torrents[0].tracker_summary == "tracker.example"
    assert listing.torrents[0].eta_seconds is None
    assert result.outcome is DownloadControlOutcome.APPLIED
    assert result.after is not None and result.after.state is (
        TorrentState.STOPPED if action is DownloadControlAction.PAUSE else TorrentState.DOWNLOADING
    )
    assert controls[endpoint].call_count == 1
    assert sum(route.call_count for route in controls.values()) == 1
    assert delete.call_count == 0
    assert route.call_count >= 3


@pytest.mark.asyncio
@respx.mock
@pytest.mark.parametrize("version", ["unknown", "v3.3.0"])
async def test_qbittorrent_unknown_version_fails_closed_without_control_mutation(version: str) -> None:
    info_hash = "F" * 40
    respx.post("http://qbt/api/v2/auth/login").respond(text="Ok.")
    respx.get("http://qbt/api/v2/torrents/info").respond(json=[{"hash": info_hash, "state": "downloading"}])
    respx.get("http://qbt/api/v2/app/version").respond(text=version)
    stop = respx.post("http://qbt/api/v2/torrents/stop").respond(status_code=200)
    legacy = respx.post("http://qbt/api/v2/torrents/pause").respond(status_code=200)
    client = QbittorrentClient(base_url="http://qbt", username="user", password="pass", timeout_seconds=5)
    try:
        result = await client.control_torrent(info_hash, action=DownloadControlAction.PAUSE)
    finally:
        await client.close()

    assert result.outcome is DownloadControlOutcome.UNKNOWN
    assert result.code == "unsupported_client_version"
    assert not stop.called and not legacy.called


@pytest.mark.asyncio
async def test_null_downloader_read_and_control_are_safe_without_configuration() -> None:
    client = NullDownloaderClient()

    listing = await client.list_torrents()
    result = await client.control_torrent("not-a-hash", action=DownloadControlAction.PAUSE)

    assert listing.torrents == () and listing.failures == ()
    assert result.outcome is DownloadControlOutcome.UNKNOWN
    assert result.info_hash == ""
    assert result.code == "not_configured"


@pytest.mark.asyncio
@respx.mock
@pytest.mark.parametrize(
    ("action", "state"),
    [(DownloadControlAction.PAUSE, "pausedDL"), (DownloadControlAction.RESUME, "downloading")],
)
async def test_qbittorrent_already_in_desired_state_issues_no_control(
    action: DownloadControlAction, state: str
) -> None:
    info_hash = "A" * 40
    respx.post("http://qbt/api/v2/auth/login").respond(text="Ok.")
    respx.get("http://qbt/api/v2/torrents/info").respond(json=[{"hash": info_hash, "state": state}])
    controls = [
        respx.post(f"http://qbt/api/v2/torrents/{name}").respond(status_code=200)
        for name in ("stop", "start", "pause", "resume", "delete")
    ]
    client = QbittorrentClient(base_url="http://qbt", username="user", password="pass", timeout_seconds=5)
    try:
        result = await client.control_torrent(info_hash, action=action)
    finally:
        await client.close()

    assert result.outcome is DownloadControlOutcome.ALREADY_IN_DESIRED_STATE
    assert all(route.call_count == 0 for route in controls)


@pytest.mark.asyncio
@respx.mock
async def test_qbittorrent_queued_states_are_not_misclassified_as_seeding_or_downloading() -> None:
    respx.post("http://qbt/api/v2/auth/login").respond(text="Ok.")
    respx.get("http://qbt/api/v2/torrents/info").respond(
        json=[
            {"hash": "B" * 40, "state": "queuedUP"},
            {"hash": "C" * 40, "state": "queuedDL"},
        ]
    )
    client = QbittorrentClient(base_url="http://qbt", username="user", password="pass", timeout_seconds=5)
    try:
        listing = await client.list_torrents()
    finally:
        await client.close()

    assert [torrent.state for torrent in listing.torrents] == [TorrentState.QUEUED, TorrentState.QUEUED]
