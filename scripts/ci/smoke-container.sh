#!/bin/sh
set -eu

if [ "$#" -ne 1 ]; then
  echo "Usage: $0 IMAGE" >&2
  exit 2
fi

image=$1
container_name="cleanarr-container-smoke-$$"

cleanup() {
  docker rm -f "$container_name" >/dev/null 2>&1 || true
}
trap cleanup EXIT HUP INT TERM

configured_user=$(docker image inspect "$image" --format '{{.Config.User}}')
if [ "$configured_user" != "cleanarr" ]; then
  echo "Container image must run as cleanarr, got: $configured_user" >&2
  exit 1
fi

docker run --detach --name "$container_name" "$image" >/dev/null

attempt=0
until docker exec "$container_name" python -c \
  "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8089/health/ready', timeout=2).read()" \
  >/dev/null 2>&1; do
  attempt=$((attempt + 1))
  if [ "$attempt" -ge 30 ]; then
    echo "Container did not become ready." >&2
    docker logs "$container_name" >&2
    exit 1
  fi
  if [ "$(docker inspect "$container_name" --format '{{.State.Running}}')" != "true" ]; then
    echo "Container exited before becoming ready." >&2
    docker logs "$container_name" >&2
    exit 1
  fi
  sleep 1
done

docker exec --interactive "$container_name" python - <<'PY'
import json
import urllib.request
from importlib.metadata import version

from cleanarr.main import app

for endpoint, expected in (
    ("/health/live", {"status": "ok"}),
    ("/health/ready", {"status": "ready"}),
):
    with urllib.request.urlopen(f"http://127.0.0.1:8089{endpoint}", timeout=3) as response:
        assert response.status == 200
        assert json.load(response) == expected

with urllib.request.urlopen("http://127.0.0.1:8089/", timeout=3) as response:
    assert response.status == 200
    assert b"CleanArr" in response.read()

assert version("cleanarr") == app.version
PY

docker exec "$container_name" sh -c 'test "$(id -u)" -ne 0 && test -w /config'

echo "Container smoke test passed for $image"
