#!/bin/sh
set -eu

if [ "$#" -lt 1 ] || [ "$#" -gt 3 ]; then
  echo "Usage: $0 VERSION [amd64|arm64] [OUTPUT_DIR]" >&2
  exit 2
fi

version=${1#v}
arch=${2:-}
output_dir=${3:-dist}

repo_root=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
cd "$repo_root"

if [ -z "$arch" ]; then
  case "$(uname -m)" in
    x86_64) arch=amd64 ;;
    aarch64|arm64) arch=arm64 ;;
    *) echo "Unsupported architecture: $(uname -m)" >&2; exit 2 ;;
  esac
fi

case "$arch" in
  amd64|arm64) ;;
  *) echo "Unsupported architecture: $arch" >&2; exit 2 ;;
esac

python_bin=${PYTHON_BIN:-python3.12}
for command_name in "$python_bin" pnpm nfpm; do
  command -v "$command_name" >/dev/null 2>&1 || {
    echo "Required command not found: $command_name" >&2
    exit 1
  }
done

project_version=$(
  "$python_bin" -c 'import pathlib,tomllib; print(tomllib.loads(pathlib.Path("backend/pyproject.toml").read_text())["project"]["version"])'
)
if [ "$project_version" != "$version" ]; then
  echo "Requested version $version does not match backend version $project_version" >&2
  exit 1
fi

package_root=$(mktemp -d "${TMPDIR:-/tmp}/cleanarr-package.XXXXXX")
cleanup() {
  case "$package_root" in
    "${TMPDIR:-/tmp}"/cleanarr-package.*) rm -rf -- "$package_root" ;;
    *) echo "Refusing to remove unexpected temporary path: $package_root" >&2 ;;
  esac
}
trap cleanup EXIT HUP INT TERM

mkdir -p \
  "$package_root/opt/cleanarr/lib" \
  "$package_root/frontend-static" \
  "$package_root/build-source/src" \
  "$output_dir"
"$python_bin" -m venv "$package_root/build-venv"
build_python="$package_root/build-venv/bin/python"

(
  cd frontend
  pnpm install --frozen-lockfile
  pnpm exec tsc -b
  pnpm exec vite build --outDir "$package_root/frontend-static" --emptyOutDir
)

cp backend/pyproject.toml README.md "$package_root/build-source/"
cp -a backend/src/. "$package_root/build-source/src/"
rm -rf -- "$package_root/build-source/src/cleanarr/ui/static"
mkdir -p "$package_root/build-source/src/cleanarr/ui/static"
cp -a "$package_root/frontend-static/." "$package_root/build-source/src/cleanarr/ui/static/"

"$build_python" -m pip install \
  --disable-pip-version-check \
  --no-compile \
  --target "$package_root/opt/cleanarr/lib" \
  "$package_root/build-source"

mkdir -p "$package_root/payload-check"
DB_PATH="$package_root/payload-check/cleanarr.db" \
CONFIG_STATE_PATH="$package_root/payload-check/runtime-config.json" \
PYTHONPATH="$package_root/opt/cleanarr/lib" "$python_bin" -c \
  'from importlib.metadata import version; from cleanarr.main import app; assert version("cleanarr") == app.version; print(f"CleanArr {app.version} package payload OK")'

export PACKAGE_ARCH="$arch"
export PACKAGE_VERSION="$version"
export PACKAGE_ROOT="$package_root"

nfpm package \
  --config packaging/nfpm.yaml \
  --packager deb \
  --target "$output_dir/cleanarr_${version}_${arch}.deb"
nfpm package \
  --config packaging/nfpm.yaml \
  --packager rpm \
  --target "$output_dir/cleanarr_${version}_${arch}.rpm"

sha256sum "$output_dir/cleanarr_${version}_${arch}.deb" "$output_dir/cleanarr_${version}_${arch}.rpm"
