#!/bin/sh
set -eu

if ! getent group cleanarr >/dev/null 2>&1; then
  groupadd --system cleanarr
fi

if ! id cleanarr >/dev/null 2>&1; then
  nologin_shell=$(command -v nologin || printf '%s' /bin/false)
  useradd \
    --system \
    --gid cleanarr \
    --home-dir /var/lib/cleanarr \
    --shell "$nologin_shell" \
    --comment "CleanArr service" \
    cleanarr
fi

install -d -o cleanarr -g cleanarr -m 0750 /var/lib/cleanarr
