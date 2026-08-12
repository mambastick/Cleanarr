import pytest
from pydantic import ValidationError

from cleanarr.domain.config import (
    DelugeServiceConfig,
    JellyseerrServiceConfig,
    QbittorrentServiceConfig,
    RadarrServiceConfig,
    RTorrentServiceConfig,
    RuntimeConfig,
    SonarrServiceConfig,
    TorrentRemovalPolicy,
    TransmissionServiceConfig,
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


def test_torrent_client_urls_add_protocol_default_paths() -> None:
    transmission = TransmissionServiceConfig(name="Transmission", url="https://transmission.example.com")
    deluge = DelugeServiceConfig(name="Deluge", url="https://deluge.example.com", password="secret")
    rtorrent = RTorrentServiceConfig(name="rTorrent", url="https://rtorrent.example.com")

    assert transmission.url == "https://transmission.example.com/transmission/rpc"
    assert deluge.url == "https://deluge.example.com/json"
    assert rtorrent.url == "https://rtorrent.example.com/RPC2"


def test_runtime_config_deserializes_mixed_downloader_kinds() -> None:
    config = RuntimeConfig.model_validate(
        {
            "downloaders": [
                {"kind": "qbittorrent", "name": "qBittorrent", "url": "http://qbt"},
                {"kind": "transmission", "name": "Transmission", "url": "http://transmission"},
                {"kind": "deluge", "name": "Deluge", "url": "http://deluge", "password": "secret"},
                {"kind": "rtorrent", "name": "rTorrent", "url": "http://rtorrent"},
            ]
        }
    )

    assert [service.kind.value for service in config.downloaders] == [
        "qbittorrent",
        "transmission",
        "deluge",
        "rtorrent",
    ]


def test_deferred_seeding_policy_requires_at_least_one_threshold() -> None:
    with pytest.raises(ValidationError, match="minimum seed ratio or time"):
        TransmissionServiceConfig(
            name="Transmission",
            url="http://transmission",
            seeding_policy=TorrentRemovalPolicy.DEFER,
        )
