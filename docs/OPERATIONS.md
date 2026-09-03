# Operations and support data

[English](OPERATIONS.md) · [Русский](OPERATIONS_RU.md)

Product endpoints require an authenticated session or an explicitly configured
`ADMIN_SHARED_TOKEN`; health probes remain public. Viewer sessions are limited
to bounded read projections for dashboard, storage, Library, Downloads, and
deletion-job status. Configuration, support/metrics exports, the user directory,
manual refreshes, controls, and every mutation require an administrator. The
static token always has administrator authority. Do not expose it to Prometheus,
backup jobs, or support tooling that you do not control.

## UI-v2 library and storage operations

The authenticated Library workspace uses these read-only endpoints:

- `GET /api/library/items?media_type=movie|series&q=&sort=added|title|size&direction=asc|desc&limit=1..50&cursor=` returns a bounded, revision-bound page. `refresh=true` bypasses the in-process read cache but does not mutate Arr or Jellyfin.
- `GET /api/library/items/{resource_id}` returns one opaque-resource detail projection. Series episode/file detail is bounded and raw paths are omitted.
- `GET /api/library/artwork/{resource_id}` resolves the item first and proxies validated Jellyfin artwork. It is authenticated and private; the response permits client caching for up to one hour.
- `GET /api/storage/volumes` returns Radarr/Sonarr volume observations without raw paths. `POST /api/storage/refresh` requests one coalesced refresh and returns `429` with code `refresh_throttled` when called again inside the 10-second manual throttle.

Library collection results are cached for 30 seconds per runtime configuration,
Jellyfin language, and media type; search and sorting reuse the cached catalog.
Storage collection results are cached for 60 seconds and are considered fresh for
120 seconds. Concurrent reads coalesce. A missing, invalid, partial, stale, or
conflicting observation is `unknown`; it is never converted to healthy storage or
deletion permission. Storage status is summarized critical, unknown/partial,
warning, then healthy. Storage status is informational and does not prove torrent
ownership.

The shell is responsive (240px desktop sidebar, 80px tablet rail, mobile top bar
and bottom navigation) and reserves mobile safe-area space. These presentation
details do not change authentication, preflight, or fail-closed deletion rules.

## User roles and database schema 6

CleanArr records an account after a successful local or admitted OIDC login. The
projection contains a case-insensitive username key, display username, auth
source, role, creation time, and last-seen time; provider claims and credentials
are not copied into it. An existing local administrator is backfilled during
startup. In an SSO-only bootstrap, the first admitted identity becomes an
administrator; once an administrator exists, new SSO identities default to
viewer. A later login preserves the role already assigned to that identity.

Only administrators can call `GET /api/users` or
`PATCH /api/users/{username}/role`. The final administrator cannot be demoted.
Viewer sessions can read the bounded workspace listed above but cannot retrieve
runtime configuration or trigger refresh, pause/resume, preflight, deletion, or
history-dismiss mutations.

Database migration 6 adds `user_accounts` transactionally. Before upgrade,
create and verify the SQLite backup required by the installation guide. Rollback
requires stopping CleanArr and restoring that pre-upgrade database; never start
an older binary against schema 6.

## Upgrade and rollback

Runtime configuration schema 4 adds the storage warning and critical free-space
thresholds. The defaults are 15% and 5%; values must be finite,
non-negative percentages with warning strictly greater than critical. Invalid
configuration fails closed. Keep the automatically created v3-compatible
pre-upgrade backup until the new binary and its configuration have been verified.

For the default SQLite deployment, the sidecar is
`cleanarr.config-v3.backup.db` in the same directory as `cleanarr.db`. A legacy
file-backed configuration creates `runtime-config.config-v3.backup.json` beside
`runtime-config.json`. Existing sidecars are never overwritten. Before rollback,
stop CleanArr, preserve the failed v4 state separately, copy the matching sidecar
back to its original filename, verify SQLite with `PRAGMA integrity_check` when
applicable, then start the older binary.

An older CleanArr binary must reject a configuration written with a newer schema
without rewriting it. If rollback is required, stop the newer binary, restore the
matching automatic v3 backup (and the matching SQLite backup when database
migrations were applied), install or pin the old binary, and start it with the
restored files. Never start an older binary against a migrated database or v4
configuration. Keep the failed state separately for diagnosis and verify the
restored database with `PRAGMA integrity_check` before bringing the service back.

## Prometheus metrics

`GET /metrics` returns Prometheus text format. Labels are intentionally bounded
to integration kind, health state, item type, operation status, webhook outcome,
job status, bounded download-action status, and bounded policy decision. Media
names and IDs, paths, profile names, URLs, hashes, and credentials are not
metrics labels.

The operation values are retained-store gauges, not lifetime counters: they can
decrease when activity retention or manual-job history removes old records.

Example scrape configuration using the optional static administrator token:

```yaml
scrape_configs:
  - job_name: cleanarr
    metrics_path: /metrics
    authorization:
      type: Bearer
      credentials_file: /run/secrets/cleanarr-admin-token
    static_configs:
      - targets: [cleanarr:8089]
```

## Support bundle

`GET /api/support/bundle` returns JSON containing the CleanArr, configuration,
and database schema versions; per-integration configured/enabled counts, health,
and downstream versions; recent structured error/action codes with correlation
IDs; and aggregate webhook/manual-job, download-action, and policy-decision
states.

The response excludes media names and IDs, paths, profile names, URLs,
credentials, free-form messages, and action details. Review every attachment
before sharing it: versions, aggregate counts, and timing can still describe
parts of an installation.

```bash
curl --fail --silent --show-error \
  -H "X-Admin-Token: ${CLEANARR_ADMIN_TOKEN}" \
  http://127.0.0.1:8089/api/support/bundle \
  --output cleanarr-support.json
```

Every new deletion cascade receives a `correlation_id`. Use that identifier to
match an API result or activity record to the redacted support error record.

## Downloads operational evidence

Download action and policy aggregates are retained-store gauges, not proof that
an individual pause/resume completed. The action projection deliberately omits
idempotency keys and canonical request bodies. Preserve the action ID, bounded
status/code, source status, and observation freshness when investigating an
action; do not infer success from an HTTP response alone.

## Redacted configuration transfer

`GET /api/config/export` returns a versioned transfer document. It includes
profile IDs, names, sanitized URLs, integration kinds, and non-secret policy
settings. It excludes the local administrator, webhook token, OIDC authentication
settings, API keys, usernames, and passwords. The document is credential-free,
but its topology and profile names can still be private.

```bash
curl --fail --silent --show-error \
  -H "X-Admin-Token: ${CLEANARR_ADMIN_TOKEN}" \
  http://127.0.0.1:8089/api/config/export \
  --output cleanarr-config-redacted.json
```

`POST /api/config/import` is merge-only and fail-safe:

- existing profiles omitted from the document are not deleted;
- credentials for a matching profile ID and kind are retained locally;
- new profiles receive empty credentials;
- every imported or updated profile is disabled;
- global dry-run is forced;
- the administrator, webhook token, and OIDC boundary are preserved.

Unknown future export schema versions are rejected. After import, enter missing
credentials, test each profile, verify a dry-run plan, and enable profiles one at
a time.

```bash
curl --fail --silent --show-error \
  -H "X-Admin-Token: ${CLEANARR_ADMIN_TOKEN}" \
  -H 'Content-Type: application/json' \
  --data-binary @cleanarr-config-redacted.json \
  http://127.0.0.1:8089/api/config/import
```

## Log redaction boundary

Structured logs redact common authorization, token, API-key, password, URL
userinfo, and sensitive query forms. Downstream error response bodies are not
copied into action messages. This is defense in depth, not permission to log or
paste credentials deliberately; protect log storage and review logs before
sharing them.
