# CleanArr repository context

## Source of truth

Before planning or implementing release work, read:

- `docs/ROADMAP.md` — canonical CleanArr 1.0 roadmap;
- `docs/ROADMAP_RU.md` — synchronized Russian version.

When a product decision changes the 1.0 scope, acceptance criteria, release order,
or non-goals, update both roadmap files in the same change.

## Product boundary for 1.0

CleanArr 1.0 is a stable, safety-first deletion orchestrator for:

`Jellyfin -> Radarr/Sonarr -> Seerr -> major torrent clients`

"All torrent clients" means the explicitly tested Tier 1 set: qBittorrent,
Transmission, Deluge, and rTorrent through XML-RPC. ruTorrent and Flood are
frontends, not separate download engines.

Plex, Emby, additional Arr applications, Usenet clients, PostgreSQL/HA, mobile
apps, and additional UI languages are not 1.0 blockers unless the roadmap is
explicitly revised.

## Safety and compatibility rules

1. Ambiguous ownership must fail closed: report and skip destructive work.
2. Dry-run must remain the default for a new installation.
3. Shared files, packs, cross-seeded content, and multi-client routing must be
   covered by explicit tests before enabling deletion.
4. A supported integration requires a documented version matrix and contract
   tests; successful connection alone is not sufficient.
5. Database/config changes require versioned migrations, an upgrade test from
   the latest stable release, a backup path, and a rollback procedure.
6. Do not publish a release while required backend, frontend, package, or image
   checks are red.
7. Keep public documentation and release notes synchronized in English and
   Russian.

## Delivery discipline

- Treat the current-state section in the roadmap as a dated snapshot and verify
  it before relying on counts or versions.
- Do not mark a roadmap item complete without reproducible test or runtime
  evidence.
- Keep unrelated working-tree changes untouched and stage explicit files.
- Do not put credentials, tokens, real service URLs, or private environment
  values in committed files or command output.
