# CleanArr 1.0 Roadmap

[English](ROADMAP.md) · [Русский](ROADMAP_RU.md)

This document is the source of truth for the scope and release gates of
CleanArr 1.0. It records product decisions, not a promise that every listed item
is already implemented.

## Product definition

CleanArr 1.0 is a stable, safety-first deletion orchestrator for:

`Jellyfin -> Radarr/Sonarr -> Seerr -> major torrent clients`

Version 1.0 means a documented compatibility contract, safe upgrades, durable
processing, and enforceable quality gates. It does not mean support for every
media server, Arr application, or download protocol.

## Baseline snapshot

Last verified: **2026-08-11**, tag **v0.2.11**, commit **ff51e29**.

Already available:

- movie, series, season, and episode deletion strategies;
- strict TMDB/TVDB/IMDB/path matching and conservative pack/shared-file checks;
- dry-run by default, activity history, manual background jobs, and service
  health monitoring;
- runtime service profiles with one active target per service family;
- qBittorrent, Radarr, Sonarr, Jellyfin, and Jellyseerr integrations;
- local authentication, OpenID Connect modes, English/Russian UI;
- multi-architecture containers plus DEB/RPM packages.

Known release blockers at this snapshot:

- the full backend suite is red: 39 passed and 12 failed, primarily because of
  `/config` test isolation plus one incomplete Sonarr fake;
- Ruff reports 8 errors, mypy reports 27 errors, and ESLint reports 1 error and
  2 warnings; the frontend production build passes;
- the tag release workflow builds and publishes artifacts without running the
  complete quality gates;
- manual deletion jobs are in memory and cannot resume after a restart;
- runtime configuration has no explicit schema version or migration chain;
- partial Seerr request cleanup for episode deletion is incomplete;
- OIDC token claims are decoded but not fully validated through JWKS/signature,
  issuer, audience, expiry, and nonce checks;
- multiple profiles can be stored, but runtime processing selects only one
  active Radarr, Sonarr, Seerr, Jellyfin, and downloader target.

This is a dated snapshot. Re-run the checks before using these counts in a new
issue, pull request, or release decision.

## Milestone progress

### v0.2.12 — completed 2026-08-11

- Restored a green baseline: 51 backend tests, Ruff format/lint, strict mypy,
  ESLint, and the frontend production build pass.
- Added required pull-request and `main` checks for backend, frontend, the
  container startup smoke test, and installed DEB/RPM smoke tests.
- Made the tag release workflow wait for the complete quality gate before it
  can publish packages, checksums, and the multi-architecture container.
- Published the verified [v0.2.12 release](https://github.com/mambastick/Cleanarr/releases/tag/v0.2.12)
  from commit `9782504`; its [release workflow](https://github.com/mambastick/Cleanarr/actions/runs/31510458986)
  completed successfully for `linux/amd64` and `linux/arm64`.

### v0.3.0 — completed 2026-08-12

- Added qBittorrent, Transmission legacy/JSON-RPC 2.0, Deluge Web JSON-RPC, and
  rTorrent XML-RPC adapters behind one removal contract.
- Enabled simultaneous Radarr, Sonarr, and mixed torrent-client routing while
  preserving instance ownership when integer Arr IDs collide.
- Added per-client keep/immediate/deferred seeding-policy evaluation and
  qBittorrent v1/v2 hybrid identifier mapping. Durable automatic retries remain
  assigned to v0.4.0.
- Added full service inventory/configuration UI and protocol-level automated
  contract coverage. Real-service compatibility certification remains a v0.9
  release-candidate gate.
- Verified commit `b2b5ae2` with 73 backend tests, Ruff format/lint, strict
  mypy, ESLint, frontend production build, package/container smoke tests, and a
  browser walkthrough of mixed downloader configuration.
- Published the verified [v0.3.0 release](https://github.com/mambastick/Cleanarr/releases/tag/v0.3.0)
  from commit `894b393`; its [release workflow](https://github.com/mambastick/Cleanarr/actions/runs/31550224512)
  completed successfully with DEB/RPM assets and a GHCR image for
  `linux/amd64` and `linux/arm64`.

### v0.4.0 — completed 2026-08-12

- Episode deletion now removes only matching Seerr issues. Because Seerr
  requests are season-scoped, CleanArr retains the request with the structured
  `partial_request_retained` reason unless the event and Sonarr inventory prove
  that the complete season is covered; only then is the season removed from the
  request or the empty request deleted.
- Seerr is now the canonical name in the domain, API, UI, logs, and persisted
  configuration. Existing `jellyseerr` SQLite/JSON profiles are rewritten
  without data loss; legacy environment variables and hidden configuration API
  routes remain accepted as compatibility aliases.
- Commit `ff1bb1a` is verified by 78 backend tests, Ruff format/lint, strict
  mypy, ESLint, the frontend production build, container/package smoke tests,
  and a browser walkthrough of canonical Seerr profile creation. Its
  [quality run](https://github.com/mambastick/Cleanarr/actions/runs/31556760557)
  completed all required jobs successfully.
- Manual deletion now requires an exact dry-run preflight showing stable media
  identifiers/path, Arr instance, download client/hash, Seerr/Jellyfin changes,
  and every structured safety skip. The server binds confirmation to a SHA-256
  hash of the canonical plan, rejects failed or changed plans, and rechecks it
  before the first mutation.
- Manual jobs, the resolved event, confirmed preflight, partial result, attempt
  count, and retry deadline are persisted in SQLite. Partial downstream
  failures are replanned and retried; an interrupted process resumes from the
  persisted event rather than depending on an Arr record that may already be
  absent. Failed torrent cleanup blocks dependent Arr, Seerr, and Jellyfin
  removal so ownership evidence remains available for the next safe attempt.
- SQLite schema version 1 is an ordered additive migration from the unversioned
  v0.3 database. Automated upgrade, idempotent re-run, newer-schema rejection,
  verified backup, and restore tests protect existing config/activity data;
  container and native rollback commands are documented in both languages.
- Commit `c1ed854` is verified by 87 backend tests, Ruff format/lint, strict
  mypy, ESLint, the frontend production build, container and installed DEB/RPM
  smoke tests, plus a browser walkthrough of plan review and hash-bound
  submission. Its [quality run](https://github.com/mambastick/Cleanarr/actions/runs/31559076267)
  completed all required jobs successfully.
- SQLite schema version 2 adds a persistent webhook event ledger. A successful
  delivery is suppressed for seven days in memory and across restarts; partial
  failures and ignored outcomes are deliberately not completed because their
  source/downstream state may change. A new source timestamp produces a new
  event key.
- One process-wide safety lock now serializes webhook, queued manual, and legacy
  synchronous mutations. This conservative single-instance design prevents
  overlap for the same media entity, torrent hash, or path; PostgreSQL/HA is
  outside the 1.0 product boundary.
- Final implementation commit `76e5b71` is verified by 96 backend tests, Ruff
  format/lint, strict mypy, ESLint, the frontend production build, and
  container/installed-package smoke tests. Its
  [quality run](https://github.com/mambastick/Cleanarr/actions/runs/31559810076)
  completed all required jobs successfully.
- Published the verified [v0.4.0 release](https://github.com/mambastick/Cleanarr/releases/tag/v0.4.0)
  from commit `8f032f4`; its [release workflow](https://github.com/mambastick/Cleanarr/actions/runs/31560298020)
  completed successfully with checksums, amd64/arm64 DEB and RPM assets, and a
  public GHCR manifest for `linux/amd64` and `linux/arm64`.

### v0.5.0 — completed 2026-08-12

- Persisted runtime configuration now has an ordered schema chain from the
  unversioned v0.4 format through versions 1 and 2. Upgrade tests preserve the
  local administrator and OIDC client settings, prove fail-closed policy
  defaults, verify a pre-upgrade SQLite backup/restore, and reject future
  config versions without rewriting them.
- OIDC authorization-code login now validates exact discovery issuer and HTTPS
  endpoints, bounded metadata/JWKS responses, asymmetric ID-token signature and
  algorithm, issuer, audience, expiry, issued-at, nonce, and multi-audience
  `azp`. PKCE S256 and a browser-bound, one-time state are mandatory; an access
  token is never treated as an ID token.
- Administration through OIDC requires an explicit user, group, or required
  claim policy. Local login has source/account throttling. Browser sessions use
  a seven-day `HttpOnly`, `SameSite=Strict` cookie, per-session CSRF tokens,
  same-origin mutation checks, and documented reverse-proxy `Secure` behavior;
  the dashboard is no longer public and baseline security headers are enabled.
- Implementation commit `e493502` is verified by 109 backend tests, Ruff
  format/lint, strict mypy, ESLint, the frontend production build, a browser
  registration/settings/logout walkthrough, container smoke, and installed
  DEB/RPM smoke tests. Its [quality run](https://github.com/mambastick/Cleanarr/actions/runs/31563074725)
  completed all required jobs successfully.
- Added a versioned, credential-free configuration export and fail-safe merge
  import. Import preserves local authentication and existing credentials,
  disables every imported profile, keeps omitted profiles, strips URL-carried
  credentials, and forces global dry-run.
- Added authenticated Prometheus metrics with bounded non-identifying labels,
  a redacted support bundle with validated dependency versions, and correlation
  IDs shared by processing results and structured logs. Central redaction now
  covers logs, serialized activity actions, nested diagnostic details, and
  persisted manual-job errors.
- Required CI now audits resolved Python runtime dependencies, scans source,
  lockfiles, deployment configuration, committed secrets, and the installed
  container, and blocks fixable high/critical findings. The release workflow
  generates SPDX JSON SBOMs and signed GitHub build, SBOM, and artifact
  attestations bound to image and file digests.
- Implementation commit `1db8a46` is verified by 117 backend tests, Ruff
  format/lint, strict mypy, frontend lint/build and dependency audit, Trivy
  source/container scans, actionlint, container smoke, and installed DEB/RPM
  smoke tests. Its [quality run](https://github.com/mambastick/Cleanarr/actions/runs/31565040954)
  completed all required jobs successfully.
- Published the verified [v0.5.0 release](https://github.com/mambastick/Cleanarr/releases/tag/v0.5.0)
  from commit `04d4db8`; its [release workflow](https://github.com/mambastick/Cleanarr/actions/runs/31565556759)
  completed all required quality, native-package, multi-architecture image,
  SBOM, provenance, and publication jobs successfully.
- Post-publication verification downloaded all four DEB/RPM packages and three
  SPDX 2.3 SBOMs, validated every checksum, and verified each GitHub artifact
  attestation against the tag, source commit, signer workflow, and hosted-runner
  policy. The GHCR image build and SBOM attestations also verify; its
  `linux/amd64` and `linux/arm64` manifest digest is
  `sha256:5425c1f73ecc4abd6434e9db750a6cc5ddc8f4426d1df028118e97a8fa9e13ca`.

### v0.9.0 — completed 2026-08-12

- Published a bilingual compatibility matrix and 1.x
  compatibility/deprecation policy with exact digest-pinned versions for
  qBittorrent 5.2.3, Transmission 4.0.6 and 4.1.3, Deluge 2.2.0, rTorrent
  0.16.17, Radarr 6.3.0.10514, Sonarr 4.0.19.2979, Seerr 3.4.1, and Jellyfin
  10.11.11. ruTorrent and Flood remain correctly classified as frontends.
- The real-service suite creates a deterministic torrent through every Tier 1
  native API and proves version/authentication, invalid-credential rejection,
  dry-run, entry-only deletion, with-data deletion, and idempotent absence. It
  exposed and fixed Deluge hash-case preservation, the rTorrent
  `execute.throw` target argument, and Jellyfin's formerly public-only health
  probe.
- The release candidate was upgraded from real published v0.2.11 and v0.5.0
  containers with seeded config/activity state, then rolled back through a
  byte-verified backup and successfully restarted on each source version. The
  clean hosted [compatibility run](https://github.com/mambastick/Cleanarr/actions/runs/31588845484)
  independently repeated the full pinned stack and both rehearsals.
- Implementation commit `1c5547d` and hosted-runner portability fix `d215261`
  are verified by 118 backend tests, Ruff format/lint, strict mypy, frontend
  lint/build, dependency and source/container scans, actionlint, container
  smoke, installed DEB/RPM smoke tests, and the seven real-service contracts.
- Published the verified [v0.9.0 release](https://github.com/mambastick/Cleanarr/releases/tag/v0.9.0)
  from commit `d215261`; its [release workflow](https://github.com/mambastick/Cleanarr/actions/runs/31589090793)
  repeated all required quality and compatibility gates before publishing
  native packages, the multi-architecture image, SPDX SBOMs, provenance, and
  signed artifact attestations.
- Post-publication verification downloaded all release files, validated every
  checksum and file attestation, and verified the GHCR attestation. The
  `linux/amd64` and `linux/arm64` image manifest digest is
  `sha256:c77bffd72ca49279b95a5c1b82e3b20938d702d7016ab759ce11fc39be29de67`.

### v1.0.0 — completed 2026-08-12

- The package and API version were finalized at 1.0.0 in release commit
  `d8a63c2`, establishing the documented safety-first contract for Jellyfin,
  Seerr, simultaneous Radarr/Sonarr instances, and all four Tier 1 torrent
  engines. Ambiguous ownership and incomplete destructive evidence remain
  fail-closed, and a new installation remains in dry-run mode by default.
- The final commit's [quality run](https://github.com/mambastick/Cleanarr/actions/runs/31590801294)
  passed the backend suite (118 passed, 7 live-service tests skipped in the
  ordinary suite), Ruff format/lint, strict mypy, frontend lint/build, runtime
  dependency audit, source/secret/configuration and installed-image scans,
  container smoke, and installed DEB/RPM smoke tests. The corresponding local
  Trivy scans reported zero fixable high/critical findings.
- Three isolated candidate installations — a local temporary stack, the clean
  hosted [release-candidate run](https://github.com/mambastick/Cleanarr/actions/runs/31591012707),
  and the tag release's clean hosted stack — each created the full pinned
  service matrix. They passed all seven real-service contracts across
  qBittorrent, both Transmission generations, Deluge, rTorrent, Radarr,
  Sonarr, Seerr, and Jellyfin; the normal scenario suite additionally covers
  simultaneous multi-Arr and multi-client routing.
- The same local and hosted gates upgraded seeded installations from published
  v0.2.11 and v0.9.0 images to the final candidate, preserved configuration,
  schema and activity data, restored a byte-identical verified backup, and
  successfully restarted each original release after rollback.
- The final blocker audit found no open GitHub issues, no red required checks,
  and no security scan findings at the release threshold. There are no known
  unresolved data-loss, security-critical, or P0/P1 defects at publication.
- The verified [v1.0.0 stable release](https://github.com/mambastick/Cleanarr/releases/tag/v1.0.0)
  was published from `d8a63c2`. Its [release workflow](https://github.com/mambastick/Cleanarr/actions/runs/31591298566)
  repeated every required quality and compatibility gate before publishing
  amd64/arm64 DEB and RPM packages, three SPDX SBOMs, checksums, signed file
  attestations, and the multi-architecture GHCR image.
- Independent post-publication verification downloaded all eight release
  assets, validated every recorded checksum and GitHub file attestation, and
  verified the OCI provenance. The `linux/amd64` and `linux/arm64` image index
  digest is
  `sha256:fd039528eed3326ad0c16d8f36630a4dc5b67962e3c93d3687a768e206979dc5`.

## Accepted post-1.0 workstream

Accepted on **2026-09-01**. This section records the next product direction; it
does not claim that the work is implemented or released. The 1.0 fail-closed,
dry-run, compatibility, migration, and quality contracts remain mandatory.

### 1. Deletion interaction correctness and first-run setup

- Make a single confirmed click start exactly one deletion job. Expose explicit
  plan-loading, ready, submitting, success, failure, and retry states; prevent
  duplicate submission and never require repeated clicking to advance.
- Keep the user-facing library title stable through preview, background job,
  activity, retry, and batch results. A localized display title is presentation
  data and must not replace stable media identifiers or ownership evidence.
- Redesign the first-run downloader step around qBittorrent, Transmission,
  Deluge, and rTorrent-specific URL/authentication fields, validation, help, and
  connection evidence. It must support configuring more than one client instead
  of implying that the first client is the complete runtime topology.

### 2. Unified design system and accessible destructive UX

- Audit every frontend surface and consolidate color, status, surface, focus,
  radius, spacing, motion, and scrollbar behavior into semantic tokens with
  verified light, dark, and system-theme parity.
- Use shadcn/ui as the accessible component foundation, Animate UI for the
  compatible animated tabs and Lucide icon interactions, and a curated subset
  of React Bits for presentation-only polish. Do not add an independent fourth
  component system or use decorative components for critical form semantics.
- Replace inconsistent native selects, checkboxes, ad-hoc dialogs, buttons, and
  scroll containers with reviewed local primitives. Respect keyboard access,
  focus restoration, reduced motion, responsive reflow, and WCAG 2.2 AA
  contrast/semantics.
- Replace the technical deletion dump with a progressive plan: a plain-language
  summary of what will be deleted, retained, skipped, or blocked, followed by
  optional technical identifiers and diagnostics.

### 3. Bounded batch deletion

- Add explicit card selection, visible selected counts, select-visible/clear
  actions, and a persistent batch action bar without making the whole card an
  ambiguous destructive control.
- Generate a mutation-free item-level plan for every selection, then bind the
  exact ordered batch to one confirmation hash. A changed, failed, ambiguous,
  or stale child plan blocks that child and requires a refreshed confirmation.
- Require a separate accessible confirmation dialog summarizing item types,
  item count, estimated size, affected systems, retained torrents, and safety
  blocks. Batch submission is bounded server-side, idempotent, and reports
  per-item progress and partial outcomes instead of pretending to be atomic
  across external services.

### 4. Downloads and cleanup insights

- Add a top-level **Downloads** section with two distinct views: live download/
  seeding state and library cleanup candidates. Do not mix torrent state with
  watch-derived deletion eligibility in one opaque score.
- Normalize read-only state across all four Tier 1 clients: client, state,
  progress, size, ratio, seeding time, activity, category/tags when available,
  and data freshness. Add idempotent pause/stop and resume actions only after
  each adapter has documented semantics and contract tests.
- Add an explicit policy for stopping seeding after configured ratio/time
  conditions. Policy evaluation, state changes, failures, and retries must be
  persisted and auditable; stopping is not torrent/data deletion.
- Build explainable Jellyfin cleanup signals: watched/never-watched/unknown,
  aggregate play count, last played time, library age, size, and seeding
  readiness. Missing or stale history remains unknown. Initial delivery is for
  filtering, sorting, recommendations, and manual/batch deletion only.
- Treat automatic media deletion, "leaving soon" workflows, optional historical
  providers, and scheduled rule execution as a later opt-in stage requiring a
  separate preview, exclusions, cooling period, migration, recovery, and
  end-to-end safety gate.

### Post-1.0 acceptance gates

- Establish required frontend interaction tests (component plus browser level)
  for single-click submission, duplicate prevention, batch confirmation,
  keyboard/focus behavior, loading/error/retry, themes, reduced motion,
  responsive overflow, and English/Russian copy.
- Keep the complete backend, frontend, package, container, supply-chain, upgrade,
  and Tier 1 compatibility gates green. New adapter commands require fake,
  protocol, and pinned real-service evidence before a compatibility claim.
- Version and test every new persisted job, policy, playback, or batch schema;
  provide backup and rollback/restore instructions.
- Do not mark a workstream item complete from screenshots or a successful build
  alone. Record reproducible tests and a real browser walkthrough of the exact
  destructive and recovery flows.

## v1.1.0 completion snapshot — 2026-09-01

- [Issue #4](https://github.com/mambastick/Cleanarr/issues/4) and
  [PR #5](https://github.com/mambastick/Cleanarr/pull/5) delivered the bounded
  post-1.0 slice in release commit `ac66ae0`: single-click idempotent manual
  deletion, hash-bound batch plans, reversible download pause/resume, bounded
  playback insights, multi-downloader first-run setup, and the accessible
  tokenized component system. Automatic deletion and the other later opt-in
  items remain outside this release.
- SQLite schema v5 and the prior v1.1 configuration were exercised through
  ordered upgrade, idempotency, future-version rejection, verified backup, and
  rollback paths. The UI-v2 workstream advances runtime configuration to schema
  v4 with storage thresholds; this snapshot does not claim that work is released.
  The final local candidate passed 214 backend tests with 7 pinned live-service
  tests skipped in the ordinary suite, Ruff format/lint, strict mypy, 66
  Vitest/Testing Library tests, 12 Playwright/Axe browser tests, frontend lint
  and production build, dependency/source/container scans, container smoke,
  and installed DEB/RPM smoke tests.
- The tag's required
  [release workflow](https://github.com/mambastick/Cleanarr/actions/runs/33552452113)
  repeated the backend, frontend, supply-chain, container, and package gates.
  Its clean compatibility stack passed all seven pinned real-service contracts
  and upgraded seeded v0.2.11, v0.9.0, and v1.0.0 installations before
  restoring verified backups and restarting each original release.
- The verified [v1.1.0 release](https://github.com/mambastick/Cleanarr/releases/tag/v1.1.0)
  published four amd64/arm64 DEB/RPM packages, three SPDX SBOMs, `SHA256SUMS`,
  and a public multi-architecture GHCR image. Independent post-publication
  verification downloaded all eight files, validated every checksum and file
  provenance attestation, and verified the OCI provenance. The `linux/amd64`
  and `linux/arm64` image index digest is
  `sha256:67cadfe8caa795ec5c6a5d9daaf61df25260ffce1f54bf72199aec47f5e37336`.

## Tracked Epic #8 — UI-v2 library workspace

Tracked in [GitHub Issue #8](https://github.com/mambastick/Cleanarr/issues/8) and
accepted as post-1.1 work. This epic is a planned delivery sequence, not a
release claim. It preserves the 1.0 fail-closed, dry-run, ownership, freshness,
authentication, migration, and quality contracts.

Delivery order:

1. **Frontend harness and extraction** — expand the existing Vitest/Testing
   Library and Playwright coverage, then extract the current controllers and feature
   boundaries without changing production visuals or behavior.
2. **Backend contracts** — deliver configuration schema v4, ordered migration,
   storage monitoring, resource-based Library/detail/artwork APIs, compatibility,
   automatic v3 backup, rollback/restore, and backend tests.
3. **Shell foundation** — add semantic light/dark tokens, the responsive
   sidebar/rail/mobile navigation, and account/storage blocks without switching
   the production entry point yet.
4. **Dashboard and Library** — deliver the storage dashboard, poster grid,
   selected-item inspector, persistent bounded selection, and single/batch
   preflight integration.
5. **Production cutover** — migrate Downloads, Cleanup Candidates, Activity,
   Settings, Setup/Auth/Jobs, remove the obsolete UI, synchronize EN/RU docs,
   and record browser/accessibility/visual evidence and all required gates.

The five changes remain stacked, linked to Epic #8, and independently
revertible. Backend and foundation work may land separately, but the new shell
becomes the production default only in the final cutover; merge, release, and
publication require separate authorization.

Until all five steps and their gates are complete, UI-v2 must not be described as
released or as weakening existing deletion safety. Missing, stale, partial, or
conflicting watch/download/storage data remains unknown and cannot authorize a
destructive action.

### Accepted UI-v2 administration follow-up — 2026-09-03

The annotated UI review extends Epic #8 with an administrator-only user
directory and persisted `admin`/`viewer` roles. The first admitted identity can
bootstrap administration; later new SSO identities default to viewer, role
changes preserve at least one administrator, and viewer sessions expose only
bounded read projections—never configuration, credentials, user inventory, or
mutations. Database schema 6 adds the user-account projection and remains
subject to the normal backup, upgrade, future-version rejection, and restore
gates.

The same follow-up accepts the collapsible shell and animated active marker,
expanded Settings information architecture, dense Activity stream, flat
service list, bounded scrolling dialogs, Library cursor pagination and card
density controls, explicit selection reset, mobile safe-area navigation, and
tooltips for icon-only actions. These are implementation targets, not release
claims, and they do not relax preflight, ownership, freshness, or dry-run
contracts.

## v2.0.0 release-candidate preparation — 2026-09-03

- The five UI-v2 delivery changes were merged in order through PRs
  [#9](https://github.com/mambastick/Cleanarr/pull/9),
  [#10](https://github.com/mambastick/Cleanarr/pull/10),
  [#11](https://github.com/mambastick/Cleanarr/pull/11),
  [#12](https://github.com/mambastick/Cleanarr/pull/12), and
  [#13](https://github.com/mambastick/Cleanarr/pull/13), completing the
  production cutover tracked by
  [Epic #8](https://github.com/mambastick/Cleanarr/issues/8).
- Version 2.0.0 is selected because this delivery replaces the production UI
  and introduces a persisted administrator/viewer authorization boundary. It
  does not remove a Tier 1 adapter, weaken fail-closed deletion behavior, or use
  the major boundary to bypass the published deprecation policy.
- The release candidate advances SQLite from schema v5 to v6 and runtime
  configuration from schema v3 to v4. Publication remains gated on the complete
  quality, package, container, security, pinned real-service compatibility, and
  latest-stable v1.1.0 upgrade/automatic-backup/rollback evidence from the
  release commit. Until those gates pass and a release tag is explicitly
  authorized, v2.0.0 remains an unpublished candidate.

## Required 1.0 scope

### 1. Download clients and routing

Tier 1 clients:

| Client | 1.0 requirement |
| --- | --- |
| qBittorrent | Keep existing support, add explicit API/version coverage and modern authentication where available |
| Transmission | Support the tested legacy RPC generation and the JSON-RPC 2.0 generation |
| Deluge | Support its authenticated remote API and both removal modes |
| rTorrent | Support the XML-RPC interface; ruTorrent is treated as a frontend, not a separate engine |

Every Tier 1 adapter must cover:

- health/authentication and version discovery;
- lookup and removal by BitTorrent v1, v2, and hybrid identifiers where exposed
  by Arr and the client;
- remove torrent only versus remove torrent and local data;
- idempotent handling of a missing/already removed torrent;
- timeouts, authentication failures, partial failures, and retry behavior;
- shared paths, packs, cross-seeded data, and multiple clients;
- an optional seeding policy: immediate removal, keep the torrent, or defer
  removal until a configured ratio/time condition is satisfied.

Multiple Radarr/Sonarr/download-client instances must be active simultaneously.
CleanArr must route each deletion to the instance and client that own the item,
instead of relying on one default target.

### 2. Complete deletion behavior and Seerr

- Complete movie, series, season, and episode flows. For episode ranges, remove
  matching Seerr issues and update a season-scoped request only when the event
  provably covers the complete season; otherwise retain it with an explicit
  safety reason because Seerr has no episode-scoped request model.
- Use **Seerr** as the current product name while accepting and migrating legacy
  Jellyseerr configuration.
- Keep destructive matching strict and expose the reason for every skip.
- Provide an exact preflight/preview plan: media entity, Arr instance, download
  client, hash/path, downstream mutations, and safety decision.
- Make webhook and manual deletion processing idempotent.
- Persist partial progress and support a safe retry/resume after downstream or
  process failure.
- Serialize concurrent work for the same media entity, torrent, or path.

### 3. Data lifecycle and upgrades

- Introduce explicit database and configuration schema versions.
- Maintain ordered, tested, forward migrations.
- Test upgrade from the latest stable 0.x release to every 1.0 release
  candidate.
- Create or require a verified backup before a destructive migration.
- Document and test rollback and restore procedures for containers and native
  packages.
- Provide redacted configuration export/import suitable for support and
  migration.
- Persist manual jobs and the data required to resume or safely reconcile them
  after restart.

### 4. Security baseline

- Validate OIDC ID tokens using provider metadata and JWKS: signature,
  algorithm, issuer, audience, expiry, state, and nonce; use PKCE where the
  provider supports it.
- Allow access only for explicitly configured users/groups/claims instead of
  granting administration to every identity accepted by the provider.
- Add login throttling and CSRF/Origin protection for cookie-authenticated
  mutations.
- Preserve secure cookie behavior behind documented reverse-proxy deployments.
- Redact credentials and tokens from logs, activity data, exports, and support
  bundles.
- Add dependency and container scanning, an SBOM, and signed/provenanced release
  artifacts.

### 5. Quality and compatibility gates

Required pull-request checks:

- complete backend pytest suite;
- Ruff formatting/lint and strict mypy;
- frontend type-check, ESLint, and production build;
- Docker image build and startup smoke test;
- DEB/RPM package build and installation smoke tests;
- adapter contract tests for every Tier 1 download client;
- scenario tests for every item type, pack/shared/cross-seed safety, duplicate
  events, partial failures, restart recovery, and multi-instance routing.

Before 1.0, run end-to-end release-candidate tests against real supported
versions of Jellyfin, Radarr, Sonarr, Seerr, and every Tier 1 client. Record the
result in a public compatibility matrix.

### 6. Operations and supportability

- Structured error/action codes and correlation IDs across a deletion cascade.
- Prometheus-compatible health/operation metrics without media names or
  credentials in labels.
- A redacted support bundle containing CleanArr version, dependency service
  versions, health summaries, configuration shape, and recent error codes.
- Complete English and Russian documentation for installation, upgrades,
  backup/restore, reverse proxy and SSO, each download client, the safety model,
  troubleshooting, and release rollback.
- A published compatibility/deprecation policy for the 1.x series.

## Explicit non-goals for 1.0

These may be implemented later, but they do not block 1.0:

- Plex and Emby as deletion-event sources;
- Lidarr, Readarr, Whisparr, and other Arr applications;
- SABnzbd, NZBGet, and other Usenet clients;
- PostgreSQL, horizontal scaling, and high availability;
- mobile applications, plugin marketplaces, and additional UI languages.

Changing a non-goal into a 1.0 requirement is a product scope decision and must
update this roadmap explicitly.

## Release train

| Version | Exit outcome |
| --- | --- |
| 0.2.12 | Green backend/frontend checks and CI that blocks an invalid release |
| 0.3.0 | Tier 1 torrent adapters plus simultaneous multi-instance routing |
| 0.4.0 | Complete deletion/Seerr behavior, idempotency, durable retries, and safety scenarios |
| 0.5.0 | Versioned migrations, backup/restore, security baseline, metrics, and support tooling |
| 0.9.0 | Feature freeze, compatibility matrix, migration rehearsal, and public release candidates |
| 1.0.0 | Published stable contract with all exit criteria below satisfied |

Version boundaries may move, but the 1.0 exit criteria may not be silently
weakened.

## 1.0 exit criteria

- [x] All required CI checks pass from a clean checkout.
- [x] Every Tier 1 client and documented dependency version passes its contract and
  end-to-end scenarios.
- [x] Upgrade from v0.2.11/latest 0.x and rollback from a 1.0 release candidate are
  demonstrated with a real backup and restored data.
- [x] No unresolved data-loss defect, security-critical defect, or P0/P1 release
  blocker remains.
- [x] At least one release candidate is exercised by independent installations
  covering all Tier 1 clients and common multi-instance layouts.
- [x] Documentation, compatibility matrix, checksums, SBOM, and signed release
  artifacts are published together.
