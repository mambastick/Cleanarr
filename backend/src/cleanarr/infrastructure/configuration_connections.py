"""Concrete runtime-config client construction and connection testing."""

from __future__ import annotations

from cleanarr.application.configuration import AnyServiceConfig, ConnectionTestResult
from cleanarr.domain.config import (
    DelugeServiceConfig,
    DownloaderServiceConfig,
    JellyfinServiceConfig,
    QbittorrentServiceConfig,
    RadarrServiceConfig,
    SeerrServiceConfig,
    SonarrServiceConfig,
    TransmissionServiceConfig,
)
from cleanarr.domain.errors import ExternalServiceError
from cleanarr.infrastructure.clients import (
    JellyfinServerClient,
    QbittorrentClient,
    RadarrClient,
    SeerrClient,
    SonarrClient,
)
from cleanarr.infrastructure.downloaders import DelugeClient, RTorrentClient, TransmissionClient


class ServiceConnectionTester:
    """Infrastructure adapter for minimal configuration-time connectivity checks."""

    async def test(self, payload: AnyServiceConfig, *, timeout_seconds: float) -> ConnectionTestResult:
        try:
            if isinstance(payload, RadarrServiceConfig):
                radarr_client = RadarrClient(
                    base_url=payload.url,
                    api_key=payload.api_key,
                    timeout_seconds=timeout_seconds,
                )
                try:
                    await radarr_client.list_movies()
                finally:
                    await radarr_client.close()
                return ConnectionTestResult(ok=True, message="Radarr responded successfully.")
            if isinstance(payload, SonarrServiceConfig):
                sonarr_client = SonarrClient(
                    base_url=payload.url,
                    api_key=payload.api_key,
                    timeout_seconds=timeout_seconds,
                )
                try:
                    await sonarr_client.list_series()
                finally:
                    await sonarr_client.close()
                return ConnectionTestResult(ok=True, message="Sonarr responded successfully.")
            if isinstance(payload, SeerrServiceConfig):
                seerr_client = SeerrClient(
                    base_url=payload.url,
                    api_key=payload.api_key,
                    timeout_seconds=timeout_seconds,
                )
                try:
                    await seerr_client.list_media()
                finally:
                    await seerr_client.close()
                return ConnectionTestResult(ok=True, message="Seerr responded successfully.")
            if isinstance(payload, JellyfinServiceConfig):
                jellyfin_client = JellyfinServerClient(
                    base_url=payload.url,
                    api_key=payload.api_key,
                    timeout_seconds=timeout_seconds,
                )
                try:
                    await jellyfin_client.ping()
                finally:
                    await jellyfin_client.close()
                return ConnectionTestResult(ok=True, message="Jellyfin responded successfully.")
            downloader_client = build_downloader_client(payload, timeout_seconds=timeout_seconds)
            try:
                version = await downloader_client.get_version()
            finally:
                await downloader_client.close()
            return ConnectionTestResult(ok=True, message=f"{payload.name} responded successfully (version {version}).")
        except ExternalServiceError as exc:
            return ConnectionTestResult(ok=False, message=exc.message)
        except Exception as exc:  # pragma: no cover - defensive adapter boundary
            return ConnectionTestResult(ok=False, message=f"Unexpected connection test error: {exc}")


def build_downloader_client(
    payload: DownloaderServiceConfig,
    *,
    timeout_seconds: float,
) -> QbittorrentClient | TransmissionClient | DelugeClient | RTorrentClient:
    if isinstance(payload, QbittorrentServiceConfig):
        return QbittorrentClient(
            base_url=payload.url,
            timeout_seconds=timeout_seconds,
            service_id=payload.id,
            service_name=payload.name,
            username=payload.username,
            password=payload.password,
            api_key=payload.api_key,
            seeding_policy=payload.seeding_policy,
            min_seed_ratio=payload.min_seed_ratio,
            min_seed_time_minutes=payload.min_seed_time_minutes,
        )
    if isinstance(payload, TransmissionServiceConfig):
        return TransmissionClient(
            base_url=payload.url,
            timeout_seconds=timeout_seconds,
            service_id=payload.id,
            service_name=payload.name,
            username=payload.username,
            password=payload.password,
            seeding_policy=payload.seeding_policy,
            min_seed_ratio=payload.min_seed_ratio,
            min_seed_time_minutes=payload.min_seed_time_minutes,
        )
    if isinstance(payload, DelugeServiceConfig):
        return DelugeClient(
            base_url=payload.url,
            timeout_seconds=timeout_seconds,
            service_id=payload.id,
            service_name=payload.name,
            password=payload.password,
            seeding_policy=payload.seeding_policy,
            min_seed_ratio=payload.min_seed_ratio,
            min_seed_time_minutes=payload.min_seed_time_minutes,
        )
    return RTorrentClient(
        base_url=payload.url,
        timeout_seconds=timeout_seconds,
        service_id=payload.id,
        service_name=payload.name,
        username=payload.username,
        password=payload.password,
        seeding_policy=payload.seeding_policy,
        min_seed_ratio=payload.min_seed_ratio,
        min_seed_time_minutes=payload.min_seed_time_minutes,
    )
