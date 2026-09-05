#!/bin/sh
set -eu

repo_root=$(CDPATH='' cd -- "$(dirname -- "$0")/../.." && pwd)
test_root=$(mktemp -d)
docker_log="$test_root/docker.log"
output_log="$test_root/output.log"
artifact_dir="$test_root/artifacts"
fake_bin="$test_root/bin"

cleanup() {
  rm -rf -- "$test_root"
}
trap cleanup EXIT HUP INT TERM

mkdir -p "$artifact_dir" "$fake_bin"
touch "$artifact_dir/cleanarr_2.0.1_amd64.deb" "$artifact_dir/cleanarr_2.0.1_amd64.rpm"

sed 's/^+//' >"$fake_bin/docker" <<'SCRIPT'
+#!/bin/sh
+set -eu
+printf '%s\n' "$*" >>"$FAKE_DOCKER_LOG"
+if [ "${FAKE_DOCKER_MODE:-success}" = "hang" ] && [ "${1:-}" = "run" ]; then
+  trap 'exit 143' HUP INT TERM
+  while :; do sleep 1; done
+fi
+exit 0
SCRIPT
chmod +x "$fake_bin/docker"

PATH="$fake_bin:$PATH" \
FAKE_DOCKER_LOG="$docker_log" \
CLEANARR_PACKAGE_SMOKE_TIMEOUT_SECONDS=5 \
CLEANARR_PACKAGE_SMOKE_KILL_AFTER_SECONDS=1 \
sh "$repo_root/scripts/ci/smoke-packages.sh" 2.0.1 amd64 "$artifact_dir" >"$output_log" 2>&1

test "$(grep -c '^run --name cleanarr-package-smoke-' "$docker_log")" -eq 2
grep -q 'ubuntu:24.04' "$docker_log"
grep -q 'rockylinux:9' "$docker_log"
grep -q '^rm --force cleanarr-package-smoke-deb-' "$docker_log"
grep -q 'DEB and RPM installation smoke tests passed' "$output_log"

: >"$docker_log"
: >"$output_log"
set +e
PATH="$fake_bin:$PATH" \
FAKE_DOCKER_LOG="$docker_log" \
FAKE_DOCKER_MODE=hang \
CLEANARR_PACKAGE_SMOKE_TIMEOUT_SECONDS=1 \
CLEANARR_PACKAGE_SMOKE_KILL_AFTER_SECONDS=1 \
sh "$repo_root/scripts/ci/smoke-packages.sh" 2.0.1 amd64 "$artifact_dir" >"$output_log" 2>&1
status=$?
set -e

test "$status" -eq 124
grep -q 'DEB package smoke timed out after 1s.' "$output_log"
grep -q '^rm --force cleanarr-package-smoke-deb-' "$docker_log"
if grep -q 'rockylinux:9' "$docker_log"; then
  echo "RPM smoke must not start after the DEB smoke times out." >&2
  exit 1
fi

echo "Package smoke guardrail tests passed"
