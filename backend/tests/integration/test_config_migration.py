"""Persisted runtime configuration migration tests."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from cleanarr.application.configuration import RuntimeConfigurationService
from cleanarr.infrastructure.config_store import SqliteConfigStore
from cleanarr.infrastructure.settings import Settings


def test_v030_sqlite_config_migrates_jellyseerr_to_canonical_seerr(tmp_path: Path) -> None:
    db_path = tmp_path / "cleanarr.db"
    store = SqliteConfigStore(str(db_path))
    legacy_payload = {
        "jellyseerr": [
            {
                "id": "legacy-seerr",
                "kind": "jellyseerr",
                "name": "Existing Seerr profile",
                "url": "https://seerr.example.com/api/v1",
                "api_key": "existing-key",
                "enabled": True,
                "is_default": True,
            }
        ]
    }
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "INSERT INTO config (id, config_json) VALUES (1, ?)",
            (json.dumps(legacy_payload),),
        )
        connection.commit()

    service = RuntimeConfigurationService(store=store, settings=Settings.model_construct())

    config = service.get_config()
    assert len(config.seerr) == 1
    assert config.seerr[0].id == "legacy-seerr"
    assert config.seerr[0].kind.value == "seerr"

    with sqlite3.connect(db_path) as connection:
        row = connection.execute("SELECT config_json FROM config WHERE id = 1").fetchone()
    assert row is not None
    persisted = json.loads(row[0])
    assert "jellyseerr" not in persisted
    assert persisted["seerr"][0]["id"] == "legacy-seerr"
    assert persisted["seerr"][0]["kind"] == "seerr"


def test_mixed_upgrade_payload_merges_unique_legacy_and_canonical_profiles(tmp_path: Path) -> None:
    db_path = tmp_path / "cleanarr.db"
    store = SqliteConfigStore(str(db_path))
    mixed_payload = {
        "seerr": [
            {
                "id": "canonical",
                "kind": "seerr",
                "name": "Canonical profile",
                "url": "https://canonical.example.com/api/v1",
                "api_key": "canonical-key",
            }
        ],
        "jellyseerr": [
            {
                "id": "canonical",
                "kind": "jellyseerr",
                "name": "Stale duplicate",
                "url": "https://stale.example.com/api/v1",
                "api_key": "stale-key",
            },
            {
                "id": "legacy-only",
                "kind": "jellyseerr",
                "name": "Legacy-only profile",
                "url": "https://legacy.example.com/api/v1",
                "api_key": "legacy-key",
            },
        ],
    }
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "INSERT INTO config (id, config_json) VALUES (1, ?)",
            (json.dumps(mixed_payload),),
        )
        connection.commit()

    service = RuntimeConfigurationService(store=store, settings=Settings.model_construct())

    profiles = service.get_config().seerr
    assert [profile.id for profile in profiles] == ["canonical", "legacy-only"]
    assert profiles[0].name == "Canonical profile"
