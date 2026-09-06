# Safety model

[English](SAFETY.md) · [Русский](SAFETY_RU.md)

CleanArr is a deletion orchestrator, not a filesystem cleaner. It removes only
entities for which the configured services provide an unambiguous ownership
chain. Missing or contradictory evidence is a successful safety skip, never a
reason to guess.

## Default state

A new installation starts with `DRY_RUN=true`. Dry-run performs discovery,
ownership checks, seeding-policy evaluation, and the complete preflight, but it
does not invoke a downstream mutation. Keep it enabled until every service is
healthy and representative movie, series, season, and episode previews match
the intended ownership.

Changing an environment variable does not overwrite an already persisted
runtime setting. Confirm the current value in the authenticated Settings page
or configuration API after every restore or migration.

## Required ownership evidence

CleanArr uses exact provider identifiers and normalized paths to locate the
media entity in the owning Radarr or Sonarr instance. A torrent is eligible
only when Arr history provides its download identifier and a configured client
reports that exact normalized info hash. Numeric Arr IDs are scoped to their
instance and are never treated as globally unique.

The operation fails closed and records a structured skip when, for example:

- provider identifiers or paths conflict;
- multiple Arr instances can own the same event without a unique resolution;
- Arr history does not prove the download hash;
- a torrent/file spans material outside the requested movie, series, season,
  or episode range;
- paths are shared, a torrent is a pack, or cross-seeded content cannot be
  isolated safely;
- the client-supplied data path is empty, relative, traverses a parent, or is a
  root-level path;
- a downstream dependency or authentication check fails.

## Preflight and mutation order

Manual deletion first returns an exact plan containing the media fingerprint,
Arr instance, torrent client/hash/path, downstream mutations, and every safety
decision. Confirmation is bound to the SHA-256 hash of that canonical plan.
CleanArr rejects a missing, changed, or stale hash and recomputes the plan
before the first mutation.

The single-item confirmation shows the selected scope, concrete torrent names (or hashes
when names are unavailable), service instances, target IDs, and the effect of
each step. Torrent entry removal is distinguished from removal with downloaded
files; Seerr request/issue/availability cleanup and Sonarr monitoring changes
are described separately. Retained or blocked targets include an explanation.
An exact content path and a download directory are labelled differently;
missing metadata remains unknown. The plan does not promise a reclaimed byte
count, because shared files and hardlinks can change the physical result.

Optional inspection links open a configured service or a known media page in
a new tab. They do not execute the plan. Internal service addresses may only
work from the administrator's network; RPC-only addresses and URLs containing
credentials or query parameters are not offered as browser links. Extra
identifiers and paths can be expanded without exposing raw backend messages or
confirmation tokens. Changed reviewed torrent metadata or file-removal mode
requires a refreshed confirmation, including previews created before an upgrade.

Stable service identifiers, hashes, and paths remain the only ownership inputs.
`display_name` is presentation data only. A batch previews every child without
mutation, binds its ordered child plans to one batch hash, and rechecks them at
submit/execution time. A client idempotency key returns only the resource for
the same canonical confirmed request; reuse for a different request is rejected.
Blocked children remain visible and a batch can finish partial—there is no
cross-service all-or-nothing transaction.

Torrent removal is attempted before dependent Arr, Seerr, or Jellyfin removal.
A torrent failure blocks those dependent mutations so that ownership evidence
remains available for a safe retry. Successful earlier actions and the
remaining retry state are persisted in SQLite.

## Repetition and concurrency

Completed webhook events are idempotently suppressed for seven days. An
already absent torrent or downstream entity is treated as an idempotent result.
Partial failures and safety skips are not marked complete because dependency
state may change and a later confirmed retry may become safe.

If a restart occurs before a manual job enters a potentially mutating phase,
CleanArr rechecks its persisted preflight. If it occurs after that point, the
job is terminal `interrupted_unknown` and is not replayed automatically. A
webhook exception or cancellation likewise leaves a durable
`interrupted_unknown` tombstone; automatic reconciliation/replay is blocked
because the reached downstream stage cannot be proved.

Downloads pause/resume is reversible and distinct from removing a torrent entry
or data. It requires fresh, managed ownership evidence. Playback/watch and
download observations that are missing, stale, partial, or conflicting are
unknown: they can sort or explain a recommendation, never authorize deletion.

A process-wide safety lock serializes destructive webhook and manual work.
CleanArr 1.0 supports one application replica with one SQLite state volume;
horizontal scaling and PostgreSQL/HA are outside the 1.0 contract.

## Operator checklist

Before enabling mutations:

1. Create and verify a backup outside the application state volume.
2. Keep dry-run enabled and test every media type and download-client route in
   use, including packs and shared/cross-seeded paths.
3. Resolve every unexpected match or skip; do not weaken identifiers to force a
   deletion.
4. Enable mutations during a supervised window and retain the previous image or
   package plus its matching backup for rollback.
5. Use correlation IDs, the activity log, metrics, and the redacted support
   bundle when investigating a result.

See [Torrent clients](TORRENT_CLIENTS.md), [Operations](OPERATIONS.md),
[Troubleshooting](TROUBLESHOOTING.md), and the
[compatibility matrix](COMPATIBILITY.md) for the concrete service contracts.
