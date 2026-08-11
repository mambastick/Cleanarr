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

test -f "$artifact_dir/$deb_name"
test -f "$artifact_dir/$rpm_name"

docker run --rm \
  --volume "$artifact_dir:/packages:ro" \
  --volume "$smoke_script:/smoke-installed-package.sh:ro" \
  --env "PACKAGE_NAME=$deb_name" \
  ubuntu:24.04 \
  sh -ceu '
    export DEBIAN_FRONTEND=noninteractive
    apt-get update >/dev/null
    apt-get install --yes "/packages/$PACKAGE_NAME" >/dev/null
    sh /smoke-installed-package.sh python3.12
  '

docker run --rm \
  --volume "$artifact_dir:/packages:ro" \
  --volume "$smoke_script:/smoke-installed-package.sh:ro" \
  --env "PACKAGE_NAME=$rpm_name" \
  rockylinux:9 \
  sh -ceu '
    dnf install --assumeyes --setopt=install_weak_deps=False "/packages/$PACKAGE_NAME" >/dev/null
    sh /smoke-installed-package.sh python3.12
  '

echo "DEB and RPM installation smoke tests passed for CleanArr $version ($arch)"
