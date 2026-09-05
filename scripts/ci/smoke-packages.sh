#!/bin/sh
set -eu

if [ "$#" -ne 3 ]; then
  echo "Usage: $0 VERSION ARCH ARTIFACT_DIR" >&2
  exit 2
fi

version=${1#v}
arch=$2
artifact_dir=$3

case "$arch" in
  amd64) ;;
  *)
    echo "Containerized package installation smoke currently supports amd64 only." >&2
    exit 2
    ;;
esac

repo_root=$(CDPATH='' cd -- "$(dirname -- "$0")/../.." && pwd)
artifact_dir=$(CDPATH='' cd -- "$artifact_dir" && pwd)
smoke_script="$repo_root/scripts/ci/smoke-installed-package.sh"
deb_name="cleanarr_${version}_${arch}.deb"
rpm_name="cleanarr_${version}_${arch}.rpm"
container_timeout_seconds=${CLEANARR_PACKAGE_SMOKE_TIMEOUT_SECONDS:-600}
container_kill_after_seconds=${CLEANARR_PACKAGE_SMOKE_KILL_AFTER_SECONDS:-30}
deb_container="cleanarr-package-smoke-deb-$$"
rpm_container="cleanarr-package-smoke-rpm-$$"

test -f "$artifact_dir/$deb_name"
test -f "$artifact_dir/$rpm_name"

case "$container_timeout_seconds" in
  ''|*[!0-9]*|0) echo "CLEANARR_PACKAGE_SMOKE_TIMEOUT_SECONDS must be a positive integer." >&2; exit 2 ;;
esac
case "$container_kill_after_seconds" in
  ''|*[!0-9]*|0) echo "CLEANARR_PACKAGE_SMOKE_KILL_AFTER_SECONDS must be a positive integer." >&2; exit 2 ;;
esac
command -v timeout >/dev/null 2>&1 || {
  echo "Package smoke requires the GNU timeout command." >&2
  exit 2
}

cleanup_containers() {
  docker rm --force "$deb_container" "$rpm_container" >/dev/null 2>&1 || true
}
trap cleanup_containers EXIT
trap 'exit 130' HUP INT TERM

run_container() {
  phase=$1
  container_name=$2
  shift 2
  if timeout --foreground --signal=TERM --kill-after="${container_kill_after_seconds}s" "${container_timeout_seconds}s" \
    docker run --name "$container_name" --rm "$@"; then
    return 0
  else
    status=$?
  fi
  docker rm --force "$container_name" >/dev/null 2>&1 || true
  if [ "$status" -eq 124 ] || [ "$status" -eq 137 ]; then
    echo "$phase package smoke timed out after ${container_timeout_seconds}s." >&2
  else
    echo "$phase package smoke failed with status $status." >&2
  fi
  return "$status"
}

run_container DEB "$deb_container" \
  --volume "$artifact_dir:/packages:ro" \
  --volume "$smoke_script:/smoke-installed-package.sh:ro" \
  --env "PACKAGE_NAME=$deb_name" \
  ubuntu:24.04 \
  sh -ceu '
    export DEBIAN_FRONTEND=noninteractive
    apt-get --quiet=2 \
      -o Acquire::Retries=3 \
      -o Acquire::http::Timeout=30 \
      -o Acquire::https::Timeout=30 \
      update
    apt-get --quiet=2 --yes \
      -o Acquire::Retries=3 \
      -o Acquire::http::Timeout=30 \
      -o Acquire::https::Timeout=30 \
      -o Dpkg::Use-Pty=0 \
      install "/packages/$PACKAGE_NAME"
    sh /smoke-installed-package.sh python3.12
  '

run_container RPM "$rpm_container" \
  --volume "$artifact_dir:/packages:ro" \
  --volume "$smoke_script:/smoke-installed-package.sh:ro" \
  --env "PACKAGE_NAME=$rpm_name" \
  rockylinux:9 \
  sh -ceu '
    dnf install --assumeyes \
      --setopt=install_weak_deps=False \
      --setopt=retries=3 \
      --setopt=timeout=30 \
      "/packages/$PACKAGE_NAME"
    sh /smoke-installed-package.sh python3.12
  '

echo "DEB and RPM installation smoke tests passed for CleanArr $version ($arch)"
