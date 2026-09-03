#!/usr/bin/env python3
"""Rehearse state upgrade and backup-based rollback with released containers."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

V0211_IMAGE = "ghcr.io/mambastick/cleanarr:0.2.11@sha256:a7c8c64f102e134c30a385ed42d3951766cf1a97891d9af2de133d93f7f95aa6"
V090_IMAGE = "ghcr.io/mambastick/cleanarr:0.9.0@sha256:c77bffd72ca49279b95a5c1b82e3b20938d702d7016ab759ce11fc39be29de67"
V100_IMAGE = "ghcr.io/mambastick/cleanarr:1.0.0@sha256:fd039528eed3326ad0c16d8f36630a4dc5b67962e3c93d3687a768e206979dc5"
V110_IMAGE = "ghcr.io/mambastick/cleanarr:1.1.0@sha256:67cadfe8caa795ec5c6a5d9daaf61df25260ffce1f54bf72199aec47f5e37336"
CANDIDATE_DATABASE_SCHEMA_VERSION = 6
CANDIDATE_CONFIG_SCHEMA_VERSION = 4
AUTOMATIC_V3_BACKUP_NAME = "cleanarr.config-v3.backup.db"


@dataclass(frozen=True)
class SourceRelease:
    version: str
    image: str
    schema_version: int
    config: dict[str, object]


SOURCES = (
    SourceRelease(
        version="0.2.11",
        image=V0211_IMAGE,
        schema_version=0,
        config={
            "admin": {
                "username": "upgrade-admin",
                "password_salt": "upgrade-salt",
                "password_hash": "upgrade-hash",
            },
            "general": {
                "dry_run": False,
                "log_level": "WARNING",
                "webhook_shared_token": "upgrade-marker-0.2.11",
                "ui_language": "ru",
                "sso_enabled": False,
            },
            "radarr": [],
            "sonarr": [],
            "jellyseerr": [
                {
                    "id": "legacy-seerr",
                    "name": "Legacy Seerr",
                    "kind": "jellyseerr",
                    "url": "http://seerr.invalid/api/v1",
                    "api_key": "upgrade-fixture-key",
                    "enabled": False,
                    "is_default": False,
                }
            ],
            "downloaders": [],
            "jellyfin": [],
        },
    ),
    SourceRelease(
        version="0.9.0",
        image=V090_IMAGE,
        schema_version=2,
        config={
            "config_schema_version": 2,
            "admin": {
                "username": "upgrade-admin",
                "password_salt": "upgrade-salt",
                "password_hash": "upgrade-hash",
            },
            "general": {
                "dry_run": False,
                "log_level": "WARNING",
                "webhook_shared_token": "upgrade-marker-0.9.0",
                "ui_language": "ru",
                "sso_mode": "password_only",
                "sso_allowed_users": [],
                "sso_allowed_groups": [],
                "sso_group_claim": "groups",
            },
            "radarr": [],
            "sonarr": [],
            "seerr": [],
            "downloaders": [],
            "jellyfin": [],
        },
    ),
    SourceRelease(
        version="1.0.0",
        image=V100_IMAGE,
        schema_version=2,
        config={
            "config_schema_version": 2,
            "admin": {
                "username": "upgrade-admin",
                "password_salt": "upgrade-salt",
                "password_hash": "upgrade-hash",
            },
            "general": {
                "dry_run": False,
                "log_level": "WARNING",
                "webhook_shared_token": "upgrade-marker-1.0.0",
                "ui_language": "ru",
                "sso_mode": "password_only",
                "sso_allowed_users": [],
                "sso_allowed_groups": [],
                "sso_group_claim": "groups",
            },
            "radarr": [],
            "sonarr": [],
            "seerr": [],
            "downloaders": [],
            "jellyfin": [],
        },
    ),
    SourceRelease(
        version="1.1.0",
        image=V110_IMAGE,
        schema_version=5,
        config={
            "config_schema_version": 3,
            "admin": {
                "username": "upgrade-admin",
                "password_salt": "upgrade-salt",
                "password_hash": "upgrade-hash",
            },
            "general": {
                "dry_run": False,
                "log_level": "WARNING",
                "webhook_shared_token": "upgrade-marker-1.1.0",
                "ui_language": "ru",
                "sso_mode": "password_only",
                "sso_allowed_users": [],
                "sso_allowed_groups": [],
                "sso_group_claim": "groups",
                "seeding_stop_policy": {},
            },
            "radarr": [],
            "sonarr": [],
            "seerr": [],
            "downloaders": [],
            "jellyfin": [],
        },
    ),
)


def _docker(*arguments: str, capture: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", *arguments],
        check=True,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.STDOUT if capture else None,
    )


def _start_container(name: str, image: str, state_dir: Path) -> None:
    _docker(
        "run",
        "--detach",
        "--name",
        name,
        "--network",
        "none",
        "--volume",
        f"{state_dir}:/config",
        "--env",
        "DRY_RUN=true",
        image,
    )
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        probe = subprocess.run(
            [
                "docker",
                "exec",
                name,
                "python",
                "-c",
                (
                    "import urllib.request; "
                    "urllib.request.urlopen('http://127.0.0.1:8089/health/ready', timeout=2).read()"
                ),
            ],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if probe.returncode == 0:
            return
        running = _docker(
            "inspect", name, "--format", "{{.State.Running}}", capture=True
        ).stdout.strip()
        if running != "true":
            logs = _docker("logs", name, capture=True).stdout
            raise RuntimeError(f"{image} exited during upgrade rehearsal:\n{logs}")
        time.sleep(2)
    logs = _docker("logs", name, capture=True).stdout
    raise RuntimeError(
        f"{image} did not become ready during upgrade rehearsal:\n{logs}"
    )


def _remove_container(name: str) -> None:
    subprocess.run(
        ["docker", "rm", "--force", name],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _seed_source_data(container_name: str, source: SourceRelease) -> None:
    activity = {
        "correlation_id": f"upgrade-activity-{source.version}",
        "item_type": "Movie",
        "item_name": f"Upgrade fixture {source.version}",
        "matched": False,
        "ignored_reason": "upgrade rehearsal fixture",
        "actions": [],
    }
    script = (
        "import os,sqlite3,sys;"
        "database='/config/cleanarr.db';"
        "connection=sqlite3.connect(database);"
        "connection.execute("
        '"INSERT INTO config (id, config_json) VALUES (1, ?) "'
        '"ON CONFLICT(id) DO UPDATE SET config_json = excluded.config_json",'
        "(sys.argv[1],));"
        "connection.execute("
        '"INSERT INTO activity (processed_at, result_json) VALUES (?, ?)",'
        "('2026-08-12T00:00:00+00:00',sys.argv[2]));"
        "connection.commit();"
        "connection.close();"
        "os.chmod(database,0o666)"
    )
    _docker(
        "exec",
        container_name,
        "python",
        "-c",
        script,
        json.dumps(source.config, separators=(",", ":")),
        json.dumps(activity, separators=(",", ":")),
    )


def _database_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _assert_source_state(source: SourceRelease, database: Path) -> None:
    with sqlite3.connect(database) as connection:
        schema_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        payload = json.loads(
            connection.execute(
                "SELECT config_json FROM config WHERE id = 1"
            ).fetchone()[0]
        )
        activity_count = int(
            connection.execute(
                "SELECT COUNT(*) FROM activity WHERE result_json LIKE ?",
                (f"%upgrade-activity-{source.version}%",),
            ).fetchone()[0]
        )
    assert schema_version == source.schema_version
    assert payload["admin"]["username"] == "upgrade-admin"
    assert (
        payload["general"]["webhook_shared_token"] == f"upgrade-marker-{source.version}"
    )
    assert activity_count == 1


def _assert_candidate_state(
    container_name: str, source: SourceRelease, database: Path
) -> None:
    validation = (
        "from cleanarr.infrastructure.config_store import SqliteConfigStore;"
        "c=SqliteConfigStore('/config/cleanarr.db').load();"
        "assert c is not None;"
        f"assert c.config_schema_version == {CANDIDATE_CONFIG_SCHEMA_VERSION};"
        "assert c.admin.username == 'upgrade-admin';"
        f"assert c.general.webhook_shared_token == 'upgrade-marker-{source.version}';"
        "assert c.general.dry_run is False;"
        "assert c.general.seeding_stop_policy.enabled is False;"
        + (
            "assert c.seerr[0].name == 'Legacy Seerr';"
            if source.version == "0.2.11"
            else ""
        )
    )
    _docker("exec", container_name, "python", "-c", validation)
    with sqlite3.connect(database) as connection:
        assert (
            int(connection.execute("PRAGMA user_version").fetchone()[0])
            == CANDIDATE_DATABASE_SCHEMA_VERSION
        )
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        assert {
            "destructive_idempotency_ledger",
            "manual_delete_batches",
            "manual_delete_batch_children",
            "download_observations",
            "download_actions",
            "policy_evaluations",
            "user_accounts",
        } <= tables
        config = json.loads(
            connection.execute(
                "SELECT config_json FROM config WHERE id = 1"
            ).fetchone()[0]
        )
        assert config["config_schema_version"] == CANDIDATE_CONFIG_SCHEMA_VERSION
        assert config["general"]["seeding_stop_policy"]["enabled"] is False
        assert config["general"]["storage_warning_free_percent"] == 15.0
        assert config["general"]["storage_critical_free_percent"] == 5.0
        account = connection.execute(
            "SELECT username, role, auth_source FROM user_accounts WHERE username_key = ?",
            ("upgrade-admin",),
        ).fetchone()
        activity_count = int(
            connection.execute(
                "SELECT COUNT(*) FROM activity WHERE result_json LIKE ?",
                (f"%upgrade-activity-{source.version}%",),
            ).fetchone()[0]
        )
    assert account == ("upgrade-admin", "admin", "local")
    assert activity_count == 1


def _rehearse(source: SourceRelease, candidate_image: str, work_dir: Path) -> None:
    state_dir = work_dir / f"state-{source.version}"
    backup_dir = work_dir / f"backup-{source.version}"
    state_dir.mkdir(mode=0o777)
    os.chmod(state_dir, 0o777)
    source_name = (
        f"cleanarr-upgrade-source-{source.version.replace('.', '-')}-{os.getpid()}"
    )
    candidate_name = (
        f"cleanarr-upgrade-candidate-{source.version.replace('.', '-')}-{os.getpid()}"
    )
    rollback_name = (
        f"cleanarr-upgrade-rollback-{source.version.replace('.', '-')}-{os.getpid()}"
    )

    try:
        _start_container(source_name, source.image, state_dir)
        _seed_source_data(source_name, source)
        _remove_container(source_name)
        database = state_dir / "cleanarr.db"
        _assert_source_state(source, database)

        shutil.copytree(state_dir, backup_dir)
        backup_digest = _database_digest(backup_dir / "cleanarr.db")

        _start_container(candidate_name, candidate_image, state_dir)
        _assert_candidate_state(candidate_name, source, database)
        _remove_container(candidate_name)

        automatic_rollback: Path | None = None
        if source.version == "1.1.0":
            generated_backup = state_dir / AUTOMATIC_V3_BACKUP_NAME
            if not generated_backup.is_file():
                raise AssertionError(
                    "The v1.1.0 upgrade did not create its automatic v3 rollback backup."
                )
            _assert_source_state(source, generated_backup)
            automatic_rollback = work_dir / f"automatic-rollback-{source.version}.db"
            shutil.copy2(generated_backup, automatic_rollback)

        shutil.rmtree(state_dir)
        if automatic_rollback is None:
            shutil.copytree(backup_dir, state_dir)
            assert _database_digest(state_dir / "cleanarr.db") == backup_digest
        else:
            state_dir.mkdir(mode=0o777)
            shutil.copy2(automatic_rollback, state_dir / "cleanarr.db")
            os.chmod(state_dir / "cleanarr.db", 0o666)
        _start_container(rollback_name, source.image, state_dir)
        _assert_source_state(source, state_dir / "cleanarr.db")
        _remove_container(rollback_name)
        print(
            f"Upgrade and backup rollback passed: v{source.version} -> candidate -> v{source.version}"
        )
    finally:
        for name in (source_name, candidate_name, rollback_name):
            _remove_container(name)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("candidate_image", help="Locally built release-candidate image")
    arguments = parser.parse_args()
    if shutil.which("docker") is None:
        raise RuntimeError("docker is required")

    with tempfile.TemporaryDirectory(prefix="cleanarr-upgrade-rehearsal-") as temporary:
        work_dir = Path(temporary)
        for source in SOURCES:
            _rehearse(source, arguments.candidate_image, work_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
