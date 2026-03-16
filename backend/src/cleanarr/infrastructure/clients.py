"""HTTP adapters for downstream services."""

from __future__ import annotations

import base64
from collections.abc import Sequence
from typing import Any

import httpx

from cleanarr.domain import (
    AuthenticationError,
    DownloaderRemovalResult,
    ExternalServiceError,
    JellyfinItem,
    JellyseerrIssue,
    JellyseerrMedia,
    JellyseerrRequest,
    RadarrHistoryRecord,
    RadarrMovie,
    ResourceNotFoundError,
    SonarrEpisode,
    SonarrEpisodeFile,
    SonarrHistoryRecord,
    SonarrSeries,
)


class JsonServiceClient:
    """Small wrapper around httpx with domain-specific errors."""

    def __init__(
        self,
        *,
        system: str,
        base_url: str,
        timeout_seconds: float,
        headers: dict[str, str] | None = None,
    ) -> None:
        self._system = system
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=timeout_seconds,
            headers=headers,
            transport=httpx.AsyncHTTPTransport(retries=1),
        )

    async def close(self) -> None:
        """Close the underlying client."""

        await self._client.aclose()

    async def _request(
        self,
        method: str,
        path: str,
        *,
        expected_statuses: set[int] | None = None,
        **kwargs: Any,
    ) -> Any:
        expected = expected_statuses or {200}
        try:
            response = await self._client.request(method, path, **kwargs)
        except httpx.TimeoutException as exc:
            raise ExternalServiceError(self._system, f"{self._system} request timed out") from exc
        except httpx.HTTPError as exc:
            detail = str(exc).strip() or exc.__class__.__name__
            raise ExternalServiceError(
                self._system,
                f"{self._system} request failed: {detail}",
            ) from exc

        if response.status_code in {401, 403}:
            raise AuthenticationError(
                self._system,
                f"{self._system} rejected the configured credentials.",
            )
        if response.status_code == 404:
            raise ResourceNotFoundError(
                self._system,
                f"{self._system} resource was already absent.",
            )
        if response.status_code not in expected:
            location = response.headers.get("location")
            body = response.text.strip()
            if location and not body:
                detail = f"redirected to {location}"
            elif body:
                detail = body
            else:
                detail = "empty response body"
            raise ExternalServiceError(
                self._system,
                f"{self._system} returned unexpected status {response.status_code}: {detail}",
            )
        if response.status_code == 204 or not response.content:
            return None
        return response.json()


class RadarrClient(JsonServiceClient):
    """Radarr HTTP client."""

    def __init__(self, *, base_url: str, api_key: str, timeout_seconds: float) -> None:
        super().__init__(
            system="radarr",
            base_url=base_url,
            timeout_seconds=timeout_seconds,
            headers={"X-Api-Key": api_key},
        )

    async def ping(self) -> None:
        """Verify Radarr connectivity."""
        await self._request("GET", "/system/status")

    async def list_movies(self) -> Sequence[RadarrMovie]:
        payload = await self._request("GET", "/movie")
        return [
            RadarrMovie(
                id=item["id"],
                title=item["title"],
                path=item["path"],
                tmdb_id=item.get("tmdbId"),
                imdb_id=item.get("imdbId"),
                size_on_disk=item.get("sizeOnDisk") or item.get("statistics", {}).get("sizeOnDisk"),
                has_file=bool(item.get("hasFile", False)),
            )
            for item in payload
        ]

    async def list_movie_history(self, movie_id: int) -> Sequence[RadarrHistoryRecord]:
        payload = await self._request(
            "GET",
            "/history/movie",
            params={"movieId": movie_id, "page": 1, "pageSize": 1000, "sortKey": "date", "sortDirection": "descending"},
        )
        records = payload if isinstance(payload, list) else payload.get("records", [])
        return [
            RadarrHistoryRecord(
                id=item["id"],
                movie_id=item["movieId"],
                event_type=item["eventType"],
                download_id=item.get("downloadId") or item.get("data", {}).get("torrentInfoHash"),
                imported_path=item.get("data", {}).get("importedPath"),
            )
            for item in records
        ]

    async def delete_movie(
        self,
        movie_id: int,
        *,
        delete_files: bool,
        add_import_exclusion: bool,
    ) -> None:
        await self._request(
            "DELETE",
            f"/movie/{movie_id}",
            expected_statuses={200},
            params={
                "deleteFiles": str(delete_files).lower(),
                "addImportExclusion": str(add_import_exclusion).lower(),
            },
        )


class NullRadarrClient:
    """No-op fallback when no active Radarr service is configured."""

    async def close(self) -> None:
        return None

    async def ping(self) -> None:
        return None

    async def list_movies(self) -> Sequence[RadarrMovie]:
        return []

    async def list_movie_history(self, movie_id: int) -> Sequence[RadarrHistoryRecord]:
        return []

    async def delete_movie(
        self,
        movie_id: int,
        *,
        delete_files: bool,
        add_import_exclusion: bool,
    ) -> None:
        return None


class SonarrClient(JsonServiceClient):
    """Sonarr HTTP client."""

    def __init__(self, *, base_url: str, api_key: str, timeout_seconds: float) -> None:
        super().__init__(
            system="sonarr",
            base_url=base_url,
            timeout_seconds=timeout_seconds,
            headers={"X-Api-Key": api_key},
        )

    async def ping(self) -> None:
        """Verify Sonarr connectivity."""
        await self._request("GET", "/system/status")

    async def list_series(self) -> Sequence[SonarrSeries]:
        payload = await self._request("GET", "/series")
        return [
            SonarrSeries(
                id=item["id"],
                title=item["title"],
                path=item["path"],
                tvdb_id=item.get("tvdbId"),
                tmdb_id=item.get("tmdbId"),
                imdb_id=item.get("imdbId"),
            )
            for item in payload
        ]

    async def list_series_history(self, series_id: int) -> Sequence[SonarrHistoryRecord]:
        payload = await self._request(
            "GET",
            "/history/series",
            params={
                "seriesId": series_id,
                "page": 1,
                "pageSize": 1000,
                "sortKey": "date",
                "sortDirection": "descending",
            },
        )
        records = payload if isinstance(payload, list) else payload.get("records", [])
        return [
            SonarrHistoryRecord(
                id=item["id"],
                series_id=item["seriesId"],
                episode_id=item.get("episodeId"),
                event_type=item["eventType"],
                download_id=item.get("downloadId") or item.get("data", {}).get("torrentInfoHash"),
                imported_path=item.get("data", {}).get("importedPath"),
                release_type=item.get("data", {}).get("releaseType"),
            )
            for item in records
        ]

    async def list_episodes(self, series_id: int) -> Sequence[SonarrEpisode]:
        payload = await self._request("GET", "/episode", params={"seriesId": series_id})
        return [
            SonarrEpisode(
                id=item["id"],
                series_id=item["seriesId"],
                season_number=item["seasonNumber"],
                episode_number=item["episodeNumber"],
                episode_file_id=item.get("episodeFileId") or None,
                has_file=item["hasFile"],
                monitored=item["monitored"],
            )
            for item in payload
        ]

    async def list_episode_files(self, series_id: int) -> Sequence[SonarrEpisodeFile]:
        payload = await self._request("GET", "/episodeFile", params={"seriesId": series_id})
        return [
            SonarrEpisodeFile(
                id=item["id"],
                path=item["path"],
                relative_path=item.get("relativePath"),
                season_number=item.get("seasonNumber"),
                size=item.get("size"),
            )
            for item in payload
        ]

    async def unmonitor_episodes(self, episode_ids: Sequence[int]) -> None:
        await self._request(
            "PUT",
            "/episode/monitor",
            expected_statuses={200, 202},
            json={"episodeIds": list(episode_ids), "monitored": False},
        )

    async def unmonitor_season(self, series_id: int, season_number: int) -> None:
        series_data = await self._request("GET", f"/series/{series_id}")
        seasons = series_data.get("seasons", [])
        for season in seasons:
            if season.get("seasonNumber") == season_number:
                season["monitored"] = False
                break
        await self._request("PUT", f"/series/{series_id}", expected_statuses={200, 202}, json=series_data)

    async def delete_episode_file(self, episode_file_id: int) -> None:
        await self._request("DELETE", f"/episodeFile/{episode_file_id}", expected_statuses={200})

    async def delete_series(
        self,
        series_id: int,
        *,
        delete_files: bool,
        add_import_list_exclusion: bool,
    ) -> None:
        await self._request(
            "DELETE",
            f"/series/{series_id}",
            expected_statuses={200},
            params={
                "deleteFiles": str(delete_files).lower(),
                "addImportListExclusion": str(add_import_list_exclusion).lower(),
            },
        )


class NullSonarrClient:
    """No-op fallback when no active Sonarr service is configured."""

    async def close(self) -> None:
        return None

    async def ping(self) -> None:
        return None

    async def list_series(self) -> Sequence[SonarrSeries]:
        return []

    async def list_series_history(self, series_id: int) -> Sequence[SonarrHistoryRecord]:
        return []

    async def list_episodes(self, series_id: int) -> Sequence[SonarrEpisode]:
        return []

    async def list_episode_files(self, series_id: int) -> Sequence[SonarrEpisodeFile]:
        return []

    async def unmonitor_episodes(self, episode_ids: Sequence[int]) -> None:
        return None

    async def unmonitor_season(self, series_id: int, season_number: int) -> None:
        return None

    async def delete_episode_file(self, episode_file_id: int) -> None:
        return None

    async def delete_series(
        self,
        series_id: int,
        *,
        delete_files: bool,
        add_import_list_exclusion: bool,
    ) -> None:
        return None


class JellyseerrClient(JsonServiceClient):
    """Jellyseerr HTTP client."""

    def __init__(self, *, base_url: str, api_key: str, timeout_seconds: float) -> None:
        super().__init__(
            system="jellyseerr",
            base_url=base_url,
            timeout_seconds=timeout_seconds,
            headers={"X-Api-Key": api_key},
        )

    async def ping(self) -> None:
        """Verify Jellyseerr connectivity."""
        await self._request("GET", "/settings/public")

    async def _prepare_xsrf_headers(self, path: str) -> dict[str, str]:
        """Fetch a fresh XSRF token for Jellyseerr mutation endpoints."""

        try:
            response = await self._client.request("HEAD", path)
        except httpx.TimeoutException as exc:
            raise ExternalServiceError(self._system, f"{self._system} request timed out") from exc
        except httpx.HTTPError as exc:
            detail = str(exc).strip() or exc.__class__.__name__
            raise ExternalServiceError(
                self._system,
                f"{self._system} request failed: {detail}",
            ) from exc

        if response.status_code in {401, 403}:
            raise AuthenticationError(
                self._system,
                f"{self._system} rejected the configured credentials.",
            )
        if response.status_code not in {200, 204, 405}:
            raise ExternalServiceError(
                self._system,
                f"{self._system} returned unexpected status {response.status_code} while preparing XSRF headers.",
            )

        xsrf_token = response.cookies.get("XSRF-TOKEN") or self._client.cookies.get("XSRF-TOKEN")
        if not xsrf_token:
            raise ExternalServiceError(
                self._system,
                f"{self._system} did not return an XSRF token for mutation requests.",
            )
        return {"X-XSRF-TOKEN": xsrf_token}

    async def _request_with_xsrf(
        self,
        method: str,
        path: str,
        *,
        expected_statuses: set[int] | None = None,
        **kwargs: Any,
    ) -> Any:
        headers = dict(kwargs.pop("headers", {}))
        headers.update(await self._prepare_xsrf_headers(path))
        return await self._request(
            method,
            path,
            expected_statuses=expected_statuses,
            headers=headers,
            **kwargs,
        )

    async def list_media(self) -> Sequence[JellyseerrMedia]:
        skip = 0
        take = 100
        results: list[JellyseerrMedia] = []
        total_results = 0
        while True:
            payload = await self._request(
                "GET",
                "/media",
                params={"take": take, "skip": skip, "filter": "all", "sort": "added"},
            )
            page_info = payload.get("pageInfo", {})
            total_results = page_info.get("results", 0)
            for item in payload.get("results", []):
                results.append(
                    JellyseerrMedia(
                        id=item["id"],
                        media_type=item["mediaType"],
                        tmdb_id=item.get("tmdbId"),
                        tvdb_id=item.get("tvdbId"),
                        imdb_id=item.get("imdbId"),
                        jellyfin_media_id=item.get("jellyfinMediaId"),
                    )
                )
            skip += take
            if skip >= total_results:
                break
        return results

    async def list_requests(self) -> Sequence[JellyseerrRequest]:
        skip = 0
        results: list[JellyseerrRequest] = []
        total_results = 0
        while True:
            payload = await self._request(
                "GET",
                "/request",
                params={"take": 100, "skip": skip, "filter": "all", "sort": "added", "sortDirection": "desc"},
            )
            page_info = payload.get("pageInfo", {})
            total_results = page_info.get("results", 0)
            for item in payload.get("results", []):
                seasons = tuple(season["seasonNumber"] for season in item.get("seasons", []))
                requested_by = item.get("requestedBy") or {}
                results.append(
                    JellyseerrRequest(
                        id=item["id"],
                        media_id=item["media"]["id"],
                        media_type=item["type"],
                        season_numbers=seasons,
                        is_4k=item["is4k"],
                        server_id=item.get("serverId"),
                        profile_id=item.get("profileId"),
                        root_folder=item.get("rootFolder"),
                        language_profile_id=item.get("languageProfileId"),
                        requested_by_id=requested_by.get("id"),
                        tags=tuple(item.get("tags", [])),
                    )
                )
            skip += 100
            if skip >= total_results:
                break
        return results

    async def list_issues(self) -> Sequence[JellyseerrIssue]:
        skip = 0
        results: list[JellyseerrIssue] = []
        total_results = 0
        while True:
            payload = await self._request(
                "GET",
                "/issue",
                params={"take": 100, "skip": skip, "filter": "all", "sort": "added"},
            )
            page_info = payload.get("pageInfo", {})
            total_results = page_info.get("results", 0)
            for item in payload.get("results", []):
                media = item.get("media") or {}
                results.append(
                    JellyseerrIssue(
                        id=item["id"],
                        media_id=media["id"],
                        problem_season=item.get("problemSeason"),
                        problem_episode=item.get("problemEpisode"),
                    )
                )
            skip += 100
            if skip >= total_results:
                break
        return results

    async def delete_request(self, request_id: int) -> None:
        await self._request_with_xsrf("DELETE", f"/request/{request_id}", expected_statuses={204})

    async def update_request_seasons(
        self,
        request: JellyseerrRequest,
        *,
        season_numbers: Sequence[int],
    ) -> None:
        payload: dict[str, Any] = {
            "mediaType": request.media_type,
            "seasons": list(season_numbers),
            "is4k": request.is_4k,
        }
        if request.server_id is not None:
            payload["serverId"] = request.server_id
        if request.profile_id is not None:
            payload["profileId"] = request.profile_id
        if request.root_folder is not None:
            payload["rootFolder"] = request.root_folder
        if request.language_profile_id is not None:
            payload["languageProfileId"] = request.language_profile_id
        if request.requested_by_id is not None:
            payload["userId"] = request.requested_by_id
        await self._request_with_xsrf("PUT", f"/request/{request.id}", json=payload)

    async def delete_issue(self, issue_id: int) -> None:
        await self._request_with_xsrf("DELETE", f"/issue/{issue_id}", expected_statuses={204})

    async def delete_media(self, media_id: int) -> None:
        await self._request_with_xsrf("DELETE", f"/media/{media_id}", expected_statuses={204})


class NullJellyseerrClient:
    """No-op fallback when no active Jellyseerr service is configured."""

    async def close(self) -> None:
        return None

    async def ping(self) -> None:
        return None

    async def list_media(self) -> Sequence[JellyseerrMedia]:
        return []

    async def list_requests(self) -> Sequence[JellyseerrRequest]:
        return []

    async def list_issues(self) -> Sequence[JellyseerrIssue]:
        return []

    async def delete_request(self, request_id: int) -> None:
        return None

    async def update_request_seasons(
        self,
        request: JellyseerrRequest,
        *,
        season_numbers: Sequence[int],
    ) -> None:
        return None

    async def delete_issue(self, issue_id: int) -> None:
        return None

    async def delete_media(self, media_id: int) -> None:
        return None


class QbittorrentClient:
    """qBittorrent WebUI API client."""

    def __init__(
        self,
        *,
        base_url: str,
        username: str,
        password: str,
        timeout_seconds: float,
    ) -> None:
        self._system = "qbittorrent"
        self._username = username
        self._password = password
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=timeout_seconds,
            transport=httpx.AsyncHTTPTransport(retries=1),
        )

    async def close(self) -> None:
        """Close the underlying client."""

        await self._client.aclose()

    async def _login(self) -> None:
        try:
            response = await self._client.post(
                "/api/v2/auth/login",
                data={"username": self._username, "password": self._password},
            )
        except httpx.HTTPError as exc:
            raise ExternalServiceError(self._system, f"qBittorrent login failed: {exc}") from exc

        if response.status_code in {401, 403} or response.text.strip() != "Ok.":
            raise AuthenticationError(self._system, "qBittorrent rejected the configured credentials.")

    async def ping(self) -> None:
        """Validate qBittorrent credentials and session setup."""

        await self._login()
        try:
            response = await self._client.get("/api/v2/app/version")
        except httpx.HTTPError as exc:
            raise ExternalServiceError(self._system, f"qBittorrent ping failed: {exc}") from exc

        if response.status_code in {401, 403}:
            raise AuthenticationError(self._system, "qBittorrent rejected the configured credentials.")
        if response.status_code >= 400:
            raise ExternalServiceError(
                self._system,
                f"qBittorrent returned unexpected status {response.status_code}: {response.text}",
            )

    async def delete_hashes(
        self,
        hashes: Sequence[str],
        *,
        delete_files: bool,
    ) -> Sequence[DownloaderRemovalResult]:
        normalized = [hash_value.upper() for hash_value in hashes]
        if not normalized:
            return []

        await self._login()
        existing_hashes = await self._existing_hashes(normalized)
        if existing_hashes:
            await self._delete_existing_hashes(existing_hashes, delete_files=delete_files)
        return [
            DownloaderRemovalResult(hash_value=hash_value, existed=hash_value in existing_hashes)
            for hash_value in normalized
        ]

    async def _existing_hashes(self, hashes: Sequence[str]) -> set[str]:
        try:
            response = await self._client.get(
                "/api/v2/torrents/info",
                params={"hashes": "|".join(hashes)},
            )
        except httpx.HTTPError as exc:
            raise ExternalServiceError(self._system, f"qBittorrent torrent lookup failed: {exc}") from exc

        if response.status_code in {401, 403}:
            raise AuthenticationError(self._system, "qBittorrent rejected the configured credentials.")
        if response.status_code >= 400:
            raise ExternalServiceError(
                self._system,
                f"qBittorrent returned unexpected status {response.status_code}: {response.text}",
            )
        return {item["hash"].upper() for item in response.json()}

    async def _delete_existing_hashes(self, hashes: set[str], *, delete_files: bool) -> None:
        try:
            response = await self._client.post(
                "/api/v2/torrents/delete",
                data={"hashes": "|".join(sorted(hashes)), "deleteFiles": str(delete_files).lower()},
            )
        except httpx.HTTPError as exc:
            raise ExternalServiceError(self._system, f"qBittorrent delete failed: {exc}") from exc

        if response.status_code in {401, 403}:
            raise AuthenticationError(self._system, "qBittorrent rejected the configured credentials.")
        if response.status_code >= 400:
            raise ExternalServiceError(
                self._system,
                f"qBittorrent returned unexpected status {response.status_code}: {response.text}",
            )


class JellyfinServerClient(JsonServiceClient):
    """Jellyfin media server HTTP client."""

    def __init__(self, *, base_url: str, api_key: str, timeout_seconds: float) -> None:
        super().__init__(
            system="jellyfin",
            base_url=base_url,
            timeout_seconds=timeout_seconds,
            headers={"Authorization": f'MediaBrowser Token="{api_key}"'},
        )

    async def ping(self) -> None:
        """Verify Jellyfin connectivity."""
        await self._request("GET", "/System/Ping", expected_statuses={200, 204})

    async def list_items(self, *, include_types: list[str]) -> Sequence[JellyfinItem]:
        payload = await self._request(
            "GET",
            "/Items",
            params={
                "Recursive": "true",
                "IncludeItemTypes": ",".join(include_types),
                "Fields": "ProviderIds,ParentId,IndexNumber",
                "Limit": 5000,
            },
        )
        raw_items = payload.get("Items", []) if isinstance(payload, dict) else []
        result: list[JellyfinItem] = []
        for item in raw_items:
            provider_ids = item.get("ProviderIds") or {}
            tmdb_raw = provider_ids.get("Tmdb")
            tvdb_raw = provider_ids.get("Tvdb")
            result.append(
                JellyfinItem(
                    id=item["Id"],
                    name=item.get("Name", ""),
                    type=item.get("Type", ""),
                    tmdb_id=int(tmdb_raw) if tmdb_raw and str(tmdb_raw).isdigit() else None,
                    tvdb_id=int(tvdb_raw) if tvdb_raw and str(tvdb_raw).isdigit() else None,
                    imdb_id=provider_ids.get("Imdb"),
                    parent_id=item.get("ParentId") or item.get("SeriesId"),
                    season_number=item.get("IndexNumber"),
                )
            )
        return result

    async def delete_item(self, item_id: str) -> None:
        await self._request("DELETE", f"/Items/{item_id}", expected_statuses={200, 204, 404})

    async def list_plugins(self) -> list[dict[str, Any]]:
        """Return the list of installed Jellyfin plugins."""
        data = await self._request("GET", "/Plugins")
        return data if isinstance(data, list) else []

    async def get_plugin_config_raw(self, plugin_id: str) -> Any:
        """Fetch a plugin's configuration object."""
        return await self._request("GET", f"/Plugins/{plugin_id}/Configuration")

    async def set_plugin_config_raw(self, plugin_id: str, config: Any) -> None:
        """Write back a plugin's configuration object."""
        await self._request(
            "POST",
            f"/Plugins/{plugin_id}/Configuration",
            json=config,
            expected_statuses={200, 204},
        )

    async def setup_webhook(
        self,
        *,
        webhook_url: str,
        webhook_token: str | None,
        template: str,
    ) -> dict[str, Any]:
        """Auto-configure the Jellyfin Webhook plugin for CleanArr.

        Returns a dict with keys: ``found``, ``configured``, ``message``.
        """
        plugins = await self.list_plugins()
        webhook_plugin = next(
            (p for p in plugins if "webhook" in p.get("Name", "").lower()),
            None,
        )
        if webhook_plugin is None:
            return {
                "found": False,
                "configured": False,
                "message": (
                    "Webhook plugin not found. "
                    "Install it via Jellyfin → Dashboard → Plugins → Catalog → Webhook."
                ),
            }

        plugin_id = webhook_plugin["Id"]
        config = await self.get_plugin_config_raw(plugin_id)
        if not isinstance(config, dict):
            config = {}

        generics: list[dict[str, Any]] = list(config.get("GenericOptions", []))

        # Remove all previous CleanArr entries and leftover entries with no name
        # and no URI (artifacts of earlier incorrect configuration attempts).
        generics = [
            g for g in generics
            if g.get("WebhookName") != "CleanArr"
            and (g.get("WebhookName") or g.get("WebhookUri"))
        ]

        headers: list[dict[str, str]] = (
            [{"Key": "X-Webhook-Token", "Value": webhook_token}] if webhook_token else []
        )
        template_b64 = base64.b64encode(template.encode()).decode()
        our_entry: dict[str, Any] = {
            "WebhookName": "CleanArr",
            "WebhookUri": webhook_url,
            "NotificationTypes": ["ItemDeleted"],
            "EnableMovies": True,
            "EnableEpisodes": True,
            "EnableSeries": True,
            "EnableSeasons": True,
            "EnableAlbums": True,
            "EnableSongs": True,
            "EnableVideos": True,
            "EnableWebhook": True,
            "SendAllProperties": False,
            "TrimWhitespace": False,
            "SkipEmptyMessageBody": False,
            "Template": template_b64,
            "Headers": headers,
            "Fields": [],
            "UserFilter": [],
        }
        generics.append(our_entry)
        config["GenericOptions"] = generics

        await self.set_plugin_config_raw(plugin_id, config)
        return {
            "found": True,
            "configured": True,
            "message": "Webhook configured in Jellyfin successfully.",
        }


class NullJellyfinServerClient:
    """No-op fallback when no active Jellyfin server is configured."""

    async def close(self) -> None:
        return None

    async def ping(self) -> None:
        return None

    async def list_items(self, *, include_types: list[str]) -> Sequence[JellyfinItem]:
        return []

    async def delete_item(self, item_id: str) -> None:
        return None

    async def list_plugins(self) -> list[dict[str, Any]]:
        return []

    async def get_plugin_config_raw(self, plugin_id: str) -> Any:
        return {}

    async def set_plugin_config_raw(self, plugin_id: str, config: Any) -> None:
        return None

    async def setup_webhook(
        self,
        *,
        webhook_url: str,
        webhook_token: str | None,
        template: str,
    ) -> dict[str, Any]:
        return {"found": False, "configured": False, "message": "Jellyfin not configured."}


class NullDownloaderClient:
    """No-op fallback when no active download client is configured."""

    async def close(self) -> None:
        return None

    async def ping(self) -> None:
        return None

    async def delete_hashes(
        self,
        hashes: Sequence[str],
        *,
        delete_files: bool,
    ) -> Sequence[DownloaderRemovalResult]:
        return [
            DownloaderRemovalResult(hash_value=hash_value.upper(), existed=False)
            for hash_value in hashes
        ]
