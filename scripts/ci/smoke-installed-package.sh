#!/bin/sh
set -eu

python_bin=${1:-python3.12}
state_dir=/var/lib/cleanarr
log_path=/tmp/cleanarr-package-smoke.log
server_pid=

cleanup() {
  if [ -n "$server_pid" ]; then
    kill "$server_pid" >/dev/null 2>&1 || true
    wait "$server_pid" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT HUP INT TERM

test -x /usr/bin/cleanarr
test -f /usr/lib/systemd/system/cleanarr.service
test -f /etc/cleanarr/cleanarr.env
test "$(id -u cleanarr)" -ne 0
test "$(stat -c '%U:%G' "$state_dir")" = "cleanarr:cleanarr"

runuser -u cleanarr -- env \
  DB_PATH="$state_dir/smoke.db" \
  CONFIG_STATE_PATH="$state_dir/smoke-runtime-config.json" \
  DRY_RUN=true \
  /usr/bin/cleanarr --host 127.0.0.1 --port 18089 >"$log_path" 2>&1 &
server_pid=$!

attempt=0
until "$python_bin" -c \
  "import urllib.request; urllib.request.urlopen('http://127.0.0.1:18089/health/ready', timeout=2).read()" \
  >/dev/null 2>&1; do
  attempt=$((attempt + 1))
  if [ "$attempt" -ge 30 ] || ! kill -0 "$server_pid" >/dev/null 2>&1; then
    echo "Installed package did not become ready." >&2
    cat "$log_path" >&2
    exit 1
  fi
  sleep 1
done

PYTHONPATH=/opt/cleanarr/lib "$python_bin" - <<'PY'
import json
import urllib.request
from importlib.metadata import version

from cleanarr.main import app

for endpoint, expected in (
    ("/health/live", {"status": "ok"}),
    ("/health/ready", {"status": "ready"}),
):
    with urllib.request.urlopen(f"http://127.0.0.1:18089{endpoint}", timeout=3) as response:
        assert response.status == 200
        assert json.load(response) == expected

with urllib.request.urlopen("http://127.0.0.1:18089/", timeout=3) as response:
    assert response.status == 200
    assert b"CleanArr" in response.read()

assert version("cleanarr") == app.version
PY

echo "Installed package smoke test passed"
