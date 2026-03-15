from cleanarr.domain.config import (
    JellyseerrServiceConfig,
    QbittorrentServiceConfig,
    RadarrServiceConfig,
    SonarrServiceConfig,
)


def test_radarr_url_is_normalized_to_api_v3() -> None:
    config = RadarrServiceConfig(
        name="Radarr",
        url="https://radarr.example.com",
        api_key="key",
    )

    assert config.url == "https://radarr.example.com/api/v3"


def test_sonarr_url_rewrites_wrong_api_version_to_api_v3() -> None:
    config = SonarrServiceConfig(
        name="Sonarr",
        url="https://apps.example.com/sonarr/api/v1",
        api_key="key",
    )

    assert config.url == "https://apps.example.com/sonarr/api/v3"


def test_jellyseerr_url_is_normalized_to_api_v1() -> None:
    config = JellyseerrServiceConfig(
        name="Jellyseerr",
        url="https://jellyseerr.example.com",
        api_key="key",
    )

    assert config.url == "https://jellyseerr.example.com/api/v1"


def test_qbittorrent_url_strips_api_v2_suffix() -> None:
    config = QbittorrentServiceConfig(
        name="qBittorrent",
        url="https://qbittorrent.example.com/api/v2",
        username="user",
        password="pass",
    )

    assert config.url == "https://qbittorrent.example.com"
