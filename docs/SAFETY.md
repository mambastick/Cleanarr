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

- provider identifiers conflict, or trusted Arr-derived paths conflict;
- multiple Arr instances can own the same event without a unique resolution;
- Arr history does not prove the download hash;
- a torrent/file spans material outside the requested movie, series, season,
  or episode range;
- paths are shared, a torrent is a pack, or cross-seeded content cannot be
  isolated safely;
- the client-supplied data path is empty, relative, traverses a parent, or is a
  filesystem root;
- a downstream dependency or authentication check fails.

## Source and physical-scope verification

Webhook cascades require a configured, enabled Jellyfin connection. Exact item
ID lookup is attempted first. Jellyfin 10.11.11 has no supported provider-equality
filter on this endpoint, so fingerprint fallback uses complete pagination with
the existing 20,000-item library bound. There is no 1,000-item rejection.
A changed total discards the entire pass and restarts once; a second changed
pass fails closed. Missing/invalid totals, partial data, a catalogue above the
bound or a failed lookup returns `source_unverifiable`
and blocks the cascade. Manual confirmed flows remain available independently.

Every data-removal preview and execution reads complete private content scopes
from all configured downloaders. Equal, ancestor or descendant scopes belonging
to another torrent, including the same hash on another client, return
`shared_path` when both scopes are known. Incomplete file metadata with a
validated root produces `sibling_scope_unknown` for overlapping targets. The
preview identifies the unverified sibling by name, client and hash without
claiming its files are shared. Unrelated paths remain available. A metadata-less torrent is ignored for overlap
only when its
protocol counters prove zero local payload bytes; an empty file list alone is
not proof. qBittorrent requires `metaDL`, `total_size` of -1 or 0, strict zero
completed/downloaded counters and finite numeric zero progress.
Unbounded/invalid/failed inventory returns `ownership_unverifiable`.
Blocked targets retain all dependent Arr/Seerr/Jellyfin data. Each call reuses one
fleet assessment, binds fresh target metadata to its recorded scope and keeps
standalone adapter guards active. Unknown existence is never reported as present
on every client or used to authorize dependent cleanup. Radarr hashes must also be
absent from every other movie's complete download-ID-filtered history across
configured instances. These checks do not fan out once per movie or impose a
1,000-movie catalogue cap; a shared hash is a pack block, and an unreadable or
incomplete filtered history fails closed.

Provider identifiers are compared independently from Jellyfin's file/mount
namespace. A webhook file path cannot veto a matching provider ID because an
Arr path names a folder in a different namespace. Only trusted manual selections
derived from Arr carry an internal Arr-path marker for conflict checks; inbound
webhooks cannot set that marker. Exact-path fallback remains a weak last resort.

These checks compare reported POSIX paths and exact file lists. They do not
inspect remote inodes or resolve different bind-mount/symlink aliases. Configure
clients with a consistent path namespace; unresolved physical aliases must be
kept outside mutation-enabled operation. Hardlinks can retain physical bytes,
so no reclaimed-space guarantee is made. Windows/UNC and malformed paths are
unknown. rTorrent reads `d.multicall2` and `download_list` with explicit target
`""` and view `main`, plus `directory.default`, within the existing 20,000-scope
bound. Both normalized hash sets must agree, including every sibling; invalid
IDs, duplicate IDs or mismatches fail closed. A base path equal to the default
root is retained as a conservative uncertain envelope. Membership is checked again
before removal. A change triggers at most one inventory refresh, preserving
other clients' scopes and rechecking both inventory views and final membership.
In the fleet flow this refresh is a barrier before any adapter mutates; every
client receives the merged evidence. The rTorrent adapter cannot refresh it
locally after that barrier and silently leave other clients on an older snapshot.
Stable unrelated additions or removals may proceed; new overlapping or unknown
scopes still block affected targets. The target must exist in both snapshots,
and its fresh deletion path must match both original and refreshed evidence.
Further membership changes fail closed. A valid absolute base path outside the
default root remains an
exact inventory scope: it blocks overlapping targets across the fleet, while
unrelated paths remain eligible. A malformed row with a readable hash and
bounded path is retained as uncertain evidence. A row with no recoverable
identity/path, or an unreadable/oversized response, makes inventory unverifiable.
Closed rTorrent inventory may derive a conservative scope from its directory,
name and multi-file flag. A closed target reports `torrent_closed`: open or
resume it in rTorrent, then refresh the preview. Actual data removal still
requires a
nonempty base path strictly below its live
`directory.default` root; root/no-subdirectory and paths outside that root are
blocked for that rTorrent target rather than recursively removed by a directory
fallback. They do not invalidate an otherwise complete outside-root inventory.

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

A preflight containing an already `DELETED` action is invalid. A real execution
result is classified separately: successful applied deletions complete their
batch child; unsafe evidence remains failed, and partial applied outcomes are
recorded without replay.

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

A failed manual preflight retries only transient downstream/authentication
failures in read actions, within the existing attempt bound. Ownership, shared
paths, incomplete scopes, closed torrents and other safety blockers are terminal
`unsafe_plan`; an automatic retry cannot make their evidence valid. Failed
durable retention recording is also terminal and blocks dependent cleanup.

Every live result is classified, including `ignored` or nominally successful
results containing safety skips: blocked jobs fail rather than report completion.
A transient downstream/authentication failure on `delete_hash` or `delete_hashes`
before any recorded `DELETED` action retains bounded `execution_failed` retries,
with a fresh preflight on each attempt. Dependent `SKIPPED/downstream_error`
placeholders do not turn that failure into a safety block. Actual safety blockers,
failed retention recording, other failed mutations, and partial results with
applied deletions remain terminal; automatic replay is blocked.

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
