# Troubleshooting

[English](TROUBLESHOOTING.md) · [Русский](TROUBLESHOOTING_RU.md)

Start by enabling dry-run in the authenticated Settings page. Preserve the
database, logs, failed job, and correlation ID before restarting or rolling
back; a restart may change downstream evidence even though durable CleanArr
state is retained.

## Process is not ready

Check `/health/live` first, then `/health/ready`. For containers, inspect
`docker compose ps` and `docker compose logs cleanarr`; for a native package use
`systemctl status cleanarr` and `journalctl -u cleanarr`.

Common causes are an unwritable or ephemeral `DB_PATH`, an unsupported future
database/config schema, and a damaged SQLite file. Do not delete the database to
make readiness green. Stop CleanArr, copy the failed state aside, run SQLite
`PRAGMA integrity_check`, and follow the documented backup/restore procedure.

## Service is unhealthy or rejects credentials

Use Test connection for the exact profile and compare its reported version with
the [compatibility matrix](COMPATIBILITY.md). A public ping endpoint does not
prove that the configured credential works; CleanArr health checks use
authenticated contracts.

- qBittorrent needs the base Web UI URL, not an appended `/api/v2`. Verify the
  Web UI host/port policy and use either username/password or a supported Bearer
  API key.
- Transmission normally uses `/transmission/rpc`. Confirm Basic credentials and
  do not force a protocol generation; CleanArr negotiates it from the server.
- Deluge Web must be connected to its daemon. The configured secret is the Web
  password, not a daemon-only credential.
- rTorrent requires an authenticated HTTP XML-RPC endpoint. Remove-with-data
  additionally requires `execute.throw` and filesystem permission for the
  rTorrent process.
- Radarr and Sonarr URLs must include the configured API base, normally
  `/api/v3`. Jellyfin and Seerr tokens must be accepted by authenticated status
  endpoints.

## Webhook is rejected or ignored

Confirm the Jellyfin destination URL, `Item Deleted` event selection,
`X-Webhook-Token`, and template from the README. An authentication failure is
different from a safety skip. For a skip, find the correlation ID in Activity
and inspect its reason: missing exact identifier/path, ambiguous Arr owner,
missing history hash, pack/shared data, and duplicate completed events are all
intentional fail-closed outcomes.

Do not add fuzzy matching to work around a skip. Correct the source metadata,
profile URL, instance ownership, or download history and generate a new dry-run
preview.

## A manual job is partial or retrying

Open the persisted job and compare completed actions with the newly computed
preflight. A torrent failure intentionally blocks dependent Arr/Seerr/Jellyfin
deletions. Restore the dependency, keep dry-run enabled for investigation, and
retry using the newly confirmed plan hash. Do not edit the SQLite job row.

If the process restarted, wait for readiness and reload the job. The resolved
event, confirmed preflight, completed actions, attempt count, and next retry
time are persisted.

## Login or SSO fails

Use the dedicated [OIDC and reverse-proxy troubleshooting](SSO.md#troubleshooting).
In particular, verify the exact HTTPS issuer/redirect URI, proxy scheme/host,
allowlist or required claim, clock synchronization, and `Secure` cookie
contract. Keep a tested local administrator path while introducing SSO.

## Upgrade or rollback fails

Stop mutations and preserve both pre-upgrade and failed-upgrade databases. Do
not start an older release on a migrated database. Restore the verified backup
that belongs to the older image/package, then start that exact version. Docker
commands are in the README; native-package commands are in
[Linux packages](LINUX_PACKAGES.md#upgrade-and-rollback).

## Collecting support evidence

Download the authenticated redacted support bundle and include the CleanArr and
dependency versions, health summary, structured error code, correlation ID,
deployment type, and exact reproduction steps. Review the bundle and logs
before sharing: redaction covers known credential fields but cannot recognize a
secret pasted into a free-form name or external error.

Never attach the live database, environment file, tokens, cookies, private
service URLs, or an unreviewed debug log to a public issue.

