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

### v0.5.0 — release candidate

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

The v0.5 implementation gates are complete. Publication and verification of the
tagged multi-architecture artifacts, SBOMs, checksums, and attestations remain
before this milestone can be marked completed.

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
| 1.0.0 | Stable contract after all exit criteria below are satisfied |

Version boundaries may move, but the 1.0 exit criteria may not be silently
weakened.

## 1.0 exit criteria

- All required CI checks pass from a clean checkout.
- Every Tier 1 client and documented dependency version passes its contract and
  end-to-end scenarios.
- Upgrade from v0.2.11/latest 0.x and rollback from a 1.0 release candidate are
  demonstrated with a real backup and restored data.
- No unresolved data-loss defect, security-critical defect, or P0/P1 release
  blocker remains.
- At least one release candidate is exercised by independent installations
  covering all Tier 1 clients and common multi-instance layouts.
- Documentation, compatibility matrix, checksums, SBOM, and signed release
  artifacts are published together.
