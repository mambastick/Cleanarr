# Operations and support data

[English](OPERATIONS.md) · [Русский](OPERATIONS_RU.md)

All operational endpoints require an administrator session or an explicitly
configured `ADMIN_SHARED_TOKEN`. Health probes remain public. Do not expose the
administrator token to Prometheus, backup jobs, or support tooling that you do
not control.

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
