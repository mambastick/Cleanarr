#!/bin/sh
set -eu

case "${1:-}" in
  remove|purge|0)
    if command -v systemctl >/dev/null 2>&1 && [ -d /run/systemd/system ]; then
      systemctl stop cleanarr.service >/dev/null 2>&1 || true
      systemctl disable cleanarr.service >/dev/null 2>&1 || true
    fi
    ;;
esac
