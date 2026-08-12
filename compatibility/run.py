#!/usr/bin/env python3
"""Run the pinned CleanArr real-service compatibility stack and test suite."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
COMPOSE_FILE = ROOT / "compatibility" / "compose.yml"
COMPAT_PASSWORD = "compat-password"
ARR_API_KEY = "cleanarr-compat-arr-api-key"
SEERR_API_KEY = "cleanarr-compat-api-key"


def _run(command: list[str], *, env: dict[str, str], capture: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=ROOT,
        env=env,
        check=True,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.STDOUT if capture else None,
    )


def _compose(project: str, *arguments: str) -> list[str]:
    return [
        "docker",
        "compose",
        "--project-name",
        project,
        "--file",
        str(COMPOSE_FILE),
        *arguments,
    ]


def _write_arr_config(path: Path, *, port: int) -> None:
    path.mkdir(parents=True)
    (path / "config.xml").write_text(
        "\n".join(
            (
                "<Config>",
                "  <BindAddress>*</BindAddress>",
                f"  <Port>{port}</Port>",
                "  <EnableSsl>False</EnableSsl>",
                "  <LaunchBrowser>False</LaunchBrowser>",
                f"  <ApiKey>{ARR_API_KEY}</ApiKey>",
                "  <AuthenticationMethod>External</AuthenticationMethod>",
                "  <AuthenticationRequired>Enabled</AuthenticationRequired>",
                "  <LogLevel>info</LogLevel>",
                "</Config>",
                "",
            )
        ),
        encoding="utf-8",
    )


def _prepare_runtime(runtime: Path) -> None:
    passwd_dir = runtime / "rtorrent-passwd"
    passwd_dir.mkdir(parents=True)
    password_hash = subprocess.run(
        ["openssl", "passwd", "-apr1", COMPAT_PASSWORD],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout.strip()
    (passwd_dir / "rpc.htpasswd").write_text(f"cleanarr:{password_hash}\n", encoding="utf-8")
    _write_arr_config(runtime / "radarr", port=7878)
    _write_arr_config(runtime / "sonarr", port=8989)


def _wait_http(
    url: str,
    *,
    ready_statuses: set[int] | None = None,
    timeout_seconds: int = 180,
) -> None:
    expected = ready_statuses or {200, 204}
    deadline = time.monotonic() + timeout_seconds
    last_error = "not started"
    while time.monotonic() < deadline:
        try:
            response = httpx.get(url, timeout=3)
            if response.status_code in expected:
                return
            last_error = f"HTTP {response.status_code}"
        except httpx.HTTPError as exc:
            last_error = exc.__class__.__name__
        time.sleep(2)
    raise RuntimeError(f"Service at {url} did not become ready: {last_error}")


def _bootstrap_jellyfin() -> str:
    base_url = "http://127.0.0.1:18096"
    _wait_http(f"{base_url}/Startup/Configuration", ready_statuses={200})
    response = httpx.get(f"{base_url}/Startup/User", timeout=15)
    response.raise_for_status()
    response = httpx.post(
        f"{base_url}/Startup/User",
        json={"Name": "cleanarr", "Password": COMPAT_PASSWORD},
        timeout=15,
    )
    response.raise_for_status()
    response = httpx.post(f"{base_url}/Startup/Complete", timeout=15)
    response.raise_for_status()

    response = httpx.post(
        f"{base_url}/Users/AuthenticateByName",
        headers={
            "Authorization": (
                'MediaBrowser Client="CleanArr Compatibility", Device="CI", '
                'DeviceId="cleanarr-compatibility", Version="0.9.0"'
            )
        },
        json={"Username": "cleanarr", "Pw": COMPAT_PASSWORD},
        timeout=15,
    )
    response.raise_for_status()
    token = response.json().get("AccessToken")
    if not isinstance(token, str) or not token:
        raise RuntimeError("Jellyfin authentication response omitted AccessToken")
    return token


def _bootstrap_seerr() -> None:
    base_url = "http://127.0.0.1:15055/api/v1"
    _wait_http(f"{base_url}/status", ready_statuses={200})
    response = httpx.post(
        f"{base_url}/auth/jellyfin",
        json={
            "username": "cleanarr",
            "password": COMPAT_PASSWORD,
            "hostname": "jellyfin",
            "port": 8096,
            "useSsl": False,
            "urlBase": "",
            "email": "cleanarr@example.invalid",
            "serverType": 2,
        },
        timeout=60,
    )
    response.raise_for_status()
    response = httpx.post(
        f"{base_url}/settings/initialize",
        headers={"X-API-Key": SEERR_API_KEY},
        timeout=15,
    )
    response.raise_for_status()


def _bootstrap_deluge() -> None:
    with httpx.Client(base_url="http://127.0.0.1:18112", timeout=15) as client:
        request_id = 0

        def rpc(method: str, params: list[object]) -> object:
            nonlocal request_id
            request_id += 1
            response = client.post("/json", json={"method": method, "params": params, "id": request_id})
            response.raise_for_status()
            body = response.json()
            if body.get("error"):
                raise RuntimeError(f"Deluge bootstrap RPC failed: {method}")
            return body.get("result")

        if rpc("auth.login", ["deluge"]) is not True:
            raise RuntimeError("Deluge rejected its documented initial Web password")
        hosts = rpc("web.get_hosts", [])
        if not isinstance(hosts, list) or not hosts:
            raise RuntimeError("Deluge Web did not expose its local daemon")
        host = hosts[0]
        if not isinstance(host, list) or not host:
            raise RuntimeError("Deluge Web returned an invalid daemon entry")
        rpc("web.connect", [host[0]])
        if rpc("web.connected", []) is not True:
            raise RuntimeError("Deluge Web could not connect to its local daemon")


def _qbittorrent_password(project: str, env: dict[str, str]) -> str:
    pattern = re.compile(r"temporary password is provided for this session:\s*(\S+)", re.IGNORECASE)
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        completed = _run(
            _compose(project, "logs", "--no-color", "qbittorrent"),
            env=env,
            capture=True,
        )
        match = pattern.search(completed.stdout)
        if match:
            return match.group(1)
        time.sleep(2)
    raise RuntimeError("qBittorrent did not publish its temporary compatibility password")


def main() -> int:
    for executable in ("docker", "openssl"):
        if shutil.which(executable) is None:
            raise RuntimeError(f"Required executable is missing: {executable}")

    runtime = Path(tempfile.mkdtemp(prefix="cleanarr-compatibility-"))
    project = f"cleanarr-compat-{os.getpid()}"
    env = os.environ.copy()
    env["CLEANARR_COMPAT_RUNTIME"] = str(runtime)
    keep = env.get("CLEANARR_COMPAT_KEEP") == "1"
    _prepare_runtime(runtime)

    try:
        print("Starting the digest-pinned CleanArr compatibility stack...", flush=True)
        _run(
            _compose(project, "up", "--detach", "--wait", "--wait-timeout", "240"),
            env=env,
        )

        for url, ready_statuses in (
            ("http://127.0.0.1:18080", {200}),
            ("http://127.0.0.1:19091/transmission/rpc", {401, 409}),
            ("http://127.0.0.1:19092/transmission/rpc", {401, 409}),
            ("http://127.0.0.1:18112/json", {200, 405}),
            ("http://127.0.0.1:18000", {401}),
            ("http://127.0.0.1:17878/api/v3/system/status", {401}),
            ("http://127.0.0.1:18989/api/v3/system/status", {401}),
        ):
            _wait_http(url, ready_statuses=ready_statuses)

        jellyfin_token = _bootstrap_jellyfin()
        _bootstrap_seerr()
        _bootstrap_deluge()
        qbittorrent_password = _qbittorrent_password(project, env)

        test_env = env.copy()
        test_env.update(
            {
                "CLEANARR_REAL_COMPATIBILITY": "1",
                "CLEANARR_COMPAT_QBITTORRENT_PASSWORD": qbittorrent_password,
                "CLEANARR_COMPAT_JELLYFIN_TOKEN": jellyfin_token,
                "CLEANARR_COMPAT_ARR_API_KEY": ARR_API_KEY,
                "CLEANARR_COMPAT_SEERR_API_KEY": SEERR_API_KEY,
            }
        )
        print("Running CleanArr adapters against the live services...", flush=True)
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "tests/compatibility",
            ],
            cwd=ROOT / "backend",
            env=test_env,
            check=False,
        )
        return result.returncode
    finally:
        if keep:
            print(f"Compatibility stack kept as project {project}; runtime: {runtime}")
        else:
            _run(_compose(project, "down", "--volumes", "--remove-orphans"), env=env)
            shutil.rmtree(runtime, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
