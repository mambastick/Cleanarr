#!/bin/sh
set -eu

if command -v systemctl >/dev/null 2>&1 && [ -d /run/systemd/system ]; then
  systemctl daemon-reload || true
  systemctl enable cleanarr.service >/dev/null 2>&1 || true
  if systemctl is-active --quiet cleanarr.service; then
    systemctl restart cleanarr.service
  fi
fi

printf '%s\n' \
  'CleanArr installed. Review /etc/cleanarr/cleanarr.env and run:' \
  'CleanArr установлен. Проверьте /etc/cleanarr/cleanarr.env и выполните:' \
  '  systemctl enable --now cleanarr'
