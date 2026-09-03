<p align="center">
  <img src="media/logo.svg" alt="CleanArr" width="480"/>
</p>

<p align="center">
  <strong>English</strong> · <a href="README_RU.md">Русский</a>
</p>

<p align="center">
  <strong>Automatic cascade cleanup for your self-hosted media stack.</strong><br/>
  CleanArr listens for Jellyfin <code>ItemDeleted</code> webhooks and cascades deletion to Radarr, Sonarr, Seerr, and supported torrent clients — automatically, safely, and without touching files it doesn't own.
</p>

<p align="center">
  <a href="#quick-start"><strong>Quick start</strong></a> ·
  <a href="#native-linux-packages"><strong>Linux packages</strong></a> ·
  <a href="#screenshots"><strong>Screenshots</strong></a> ·
  <a href="#how-it-works"><strong>How it works</strong></a> ·
  <a href="#configuration"><strong>Configuration</strong></a> ·
  <a href="docs/TORRENT_CLIENTS.md"><strong>Torrent clients</strong></a> ·
  <a href="docs/COMPATIBILITY.md"><strong>Compatibility</strong></a> ·
  <a href="docs/SAFETY.md"><strong>Safety</strong></a> ·
  <a href="docs/TROUBLESHOOTING.md"><strong>Troubleshooting</strong></a> ·
  <a href="docs/OPERATIONS.md"><strong>Operations</strong></a> ·
  <a href="docs/ROADMAP.md"><strong>Roadmap</strong></a> ·
  <a href="CONTRIBUTING.md"><strong>Contributing</strong></a>
</p>

<p align="center">
  <img alt="Python 3.12" src="https://img.shields.io/badge/python-3.12-blue?logo=python&logoColor=white"/>
  <img alt="React 19" src="https://img.shields.io/badge/react-19-61DAFB?logo=react&logoColor=white"/>
  <img alt="License MIT" src="https://img.shields.io/github/license/mambastick/Cleanarr"/>
  <img alt="Docker" src="https://img.shields.io/badge/docker-ready-2496ED?logo=docker&logoColor=white"/>
  <img alt="Linux packages" src="https://img.shields.io/badge/Linux-DEB%20%7C%20RPM-FCC624?logo=linux&logoColor=black"/>
</p>

---

## What is CleanArr?

When you delete something in Jellyfin, you usually have to manually clean up the same item in Radarr, Sonarr, Seerr, and your torrent clients. CleanArr automates this entire chain:

1. Jellyfin fires an `ItemDeleted` webhook
2. CleanArr resolves the item in Radarr/Sonarr using strict ID matching (TMDB → IMDB → path)
3. Torrent hashes are routed to qBittorrent, Transmission, Deluge, and rTorrent — only when Arr history proves ownership
4. The entry is removed from Radarr/Sonarr
5. Matching requests, issues, and media records are cleaned up in Seerr

Pack torrents, shared files, and anything that can't be safely attributed are always skipped.

---

## Screenshots

<table>
  <tr>
    <td width="50%">
      <img src="docs/screenshots/login.png" alt="Sign in" width="100%"/>
      <p align="center"><sub>Sign in screen</sub></p>
    </td>
    <td width="50%">
      <img src="docs/screenshots/register.png" alt="Create admin account" width="100%"/>
      <p align="center"><sub>First-run — create admin account</sub></p>
    </td>
  </tr>
  <tr>
    <td width="50%">
      <img src="docs/screenshots/setup_wizard_step1.png" alt="Setup wizard" width="100%"/>
      <p align="center"><sub>Guided setup wizard — Jellyfin step</sub></p>
    </td>
    <td width="50%">
      <img src="docs/screenshots/dashboard.png" alt="Dashboard" width="100%"/>
      <p align="center"><sub>Dashboard — all services healthy, Live mode</sub></p>
    </td>
  </tr>
  <tr>
    <td width="50%">
      <img src="docs/screenshots/dashboard_activity.png" alt="Activity log" width="100%"/>
      <p align="center"><sub>Activity log with deletion history</sub></p>
    </td>
    <td width="50%">
      <img src="docs/screenshots/jellyfin_modal.png" alt="Jellyfin service modal" width="100%"/>
      <p align="center"><sub>Jellyfin service editor — webhook auto-configure</sub></p>
    </td>
  </tr>
  <tr>
    <td colspan="2">
      <img src="docs/screenshots/settings.png" alt="Settings" width="100%"/>
      <p align="center"><sub>Settings — General configuration</sub></p>
    </td>
  </tr>
</table>

---

## Features

- **Cascade deletion** — one webhook triggers a full cleanup chain: Jellyfin → Radarr/Sonarr → torrent clients → Seerr
- **Multi-instance routing** — every enabled Radarr, Sonarr, and torrent-client profile participates without numeric ID collisions
- **Strict ID matching** — resolves items by TMDB/TVDB/IMDB ID and path; no fuzzy guessing
- **Conservative guardrails** — pack torrents and files shared between items are never deleted; CleanArr logs the reason and skips
- **Confirmed preflight** — enabled before every manual deletion; shows exact media IDs, Arr instance, torrent client/hash/path, downstream mutations, and safety skips
- **Durable background cleanup** — manual jobs, partial results, and retry state survive process restarts and report live step-by-step progress
- **Idempotent execution** — completed Jellyfin deliveries are suppressed for seven days, partial failures remain retryable, and one safety lock serializes all destructive work in a CleanArr instance
- **Live health monitoring** — probes all connected services every 30 s; status visible on the dashboard
- **Webhook auto-configure** — one-click setup of the Jellyfin Webhook plugin directly from the UI
- **Activity log** — every processed event is stored with full action breakdown; searchable by title, system, action, or status
- **Guided setup wizard** — first-run wizard walks you through connecting each service step by step
- **Multi-profile downloaders** — save qBittorrent, Transmission, Deluge, and rTorrent profiles together; enabled profiles participate while one preferred profile is retained for setup and display
- **Downloads and cleanup recommendations** — inspect bounded, normalized torrent observations and Jellyfin-based cleanup candidates without turning unknown data into deletion permission
- **Responsive authenticated workspace** — UI-v2 adapts from a full sidebar to an accessible rail and mobile bottom navigation; Library combines poster browsing, a selected-item inspector, and a storage-health headline
- **Local and SSO authentication** — local password login plus strict OpenID Connect validation, PKCE, nonce, and explicit user/group/claim access policies
- **Persisted user roles** — administrators can search known local/SSO identities and assign administrator or bounded read-only viewer access without exposing configuration or destructive controls
- **Dark / light mode** — follows system preference

---

## Quick start

### Docker Compose

```bash
git clone https://github.com/mambastick/Cleanarr.git
cd Cleanarr

# Start (review environment variables in the compose file first)
docker compose -f deploy/docker-compose.yml up -d
```

Open **http://localhost:8089** — the setup wizard walks you through the rest.

Before an image upgrade, create and export a verified SQLite backup:

```bash
docker compose -f deploy/docker-compose.yml exec -T cleanarr python3 -c 'import sqlite3; source=sqlite3.connect("/config/cleanarr.db"); backup=sqlite3.connect("/config/cleanarr.pre-upgrade.db"); source.backup(backup); print(backup.execute("PRAGMA integrity_check").fetchone()[0]); backup.close(); source.close()'
docker compose -f deploy/docker-compose.yml cp \
  cleanarr:/config/cleanarr.pre-upgrade.db ./cleanarr.pre-upgrade.db
```

The check must print `ok`. To roll back, pin the previous image, stop the
service, copy the verified backup back to `/config/cleanarr.db`, and start it
again. Keep the failed database under a different name until the restore is
verified.

### Docker (manual)

```bash
docker run -d \
  --name cleanarr \
  -p 8089:8089 \
  -e DRY_RUN=true \
  -v cleanarr-config:/config \
  ghcr.io/mambastick/cleanarr:latest
```

### Native Linux packages

Every release provides `.deb` and `.rpm` packages for `amd64` and `arm64`. They install CleanArr under `/opt/cleanarr`, create a dedicated system user, and provide a hardened systemd service.

```bash
# Debian / Ubuntu
sudo apt install ./cleanarr_<version>_amd64.deb

# Fedora / RHEL-compatible distributions
sudo dnf install ./cleanarr-<version>-1.x86_64.rpm

sudo systemctl enable --now cleanarr
```

The default configuration is stored in `/etc/cleanarr/cleanarr.env`; application data is stored in `/var/lib/cleanarr`. Packages require systemd and Python 3.12. See the complete [native package guide](docs/LINUX_PACKAGES.md), including upgrade, removal, backup, and checksum instructions.

### Kubernetes

```bash
kubectl apply -f deploy/k8s/namespace.yaml
kubectl apply -f deploy/k8s/pvc.yaml
# Edit secret.example.yaml with your values first
kubectl apply -f deploy/k8s/secret.example.yaml
kubectl apply -f deploy/k8s/deployment.yaml
kubectl apply -f deploy/k8s/service.yaml
kubectl apply -f deploy/k8s/ingress.yaml
```

The deployment uses `strategy: Recreate` because the config PVC is `ReadWriteOnce`.

---

## Configuration

All settings can be changed at runtime from the **Settings** tab. Environment variables provide defaults on first start.

| Variable | Default | Description |
|---|---|---|
| `DRY_RUN` | `true` | Set to `false` to enable real deletions |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `HTTP_TIMEOUT_SECONDS` | `15` | Timeout for calls to downstream services |
| `DB_PATH` | `/config/cleanarr.db` | SQLite database path — must be on a persistent volume |
| `CONFIG_STATE_PATH` | `/config/runtime-config.json` | Legacy runtime-config migration path |
| `ADMIN_SHARED_TOKEN` | — | Optional static token that bypasses session auth (useful for automation) |
| `WEBHOOK_SHARED_TOKEN` | auto-generated | Shared secret verified on every inbound webhook. Auto-generated on first start; rotate from Settings → General |
| `UI_LANGUAGE` | `en` | Initial UI language: `en` or `ru` |
| `JELLYFIN_LANGUAGE` | `en` | Preferred metadata language for Jellyfin integration |
| `SSO_MODE` | `password_only` | Authentication mode: `password_only`, `both`, or `sso_only` |
| `SSO_ENABLED` | `false` | Enables the OpenID Connect integration |
| `SSO_ISSUER_URL` | — | OpenID Connect issuer URL |
| `SSO_CLIENT_ID` | — | OpenID Connect client ID |
| `SSO_CLIENT_SECRET` | — | OpenID Connect client secret |
| `SSO_REDIRECT_URI` | — | Callback URL, usually `https://cleanarr.example/api/auth/sso/callback` |
| `SSO_SCOPES` | `openid profile email` | OpenID Connect scopes |
| `SSO_ALLOWED_USERS` | — | Comma-separated usernames/emails/subjects allowed to sign in |
| `SSO_ALLOWED_GROUPS` | — | Comma-separated group values allowed to sign in |
| `SSO_GROUP_CLAIM` | `groups` | ID-token claim containing group values |
| `SSO_REQUIRED_CLAIM` | — | Optional additional ID-token claim required for access |
| `SSO_REQUIRED_VALUE` | — | Required value; configure together with `SSO_REQUIRED_CLAIM` |
| `SESSION_COOKIE_SECURE` | auto | Force `Secure` on/off; set `true` when TLS terminates at a reverse proxy not trusted for forwarded headers |

> **Important:** `DB_PATH` must point to a persistent volume. Without it, all service configurations and activity history are lost on restart.

The current persisted runtime configuration is schema **4**. Its ordered
migration adds conservative storage thresholds (15% warning and 5% critical by
default). Thresholds accept only finite, non-negative percentages with warning
strictly above critical; invalid values fail closed rather than being silently
coerced. New installations remain in dry-run by default.

The corresponding Settings fields are `storage_warning_free_percent` and
`storage_critical_free_percent`; they are runtime configuration fields rather
than environment-variable defaults.

When schema 3 is first read, CleanArr creates an immutable sidecar before schema
4 can be persisted: `cleanarr.config-v3.backup.db` beside the SQLite database,
or `runtime-config.config-v3.backup.json` beside a legacy JSON configuration.
Keep that file with the matching application version; the exact rollback steps
are documented in [Operations](docs/OPERATIONS.md#upgrade-and-rollback).

Existing `jellyseerr` profiles are migrated in place to the canonical `seerr`
configuration on startup. The legacy `JELLYSEERR_URL` /
`JELLYSEERR_API_KEY` variables and `/api/config/jellyseerr` routes remain
backward-compatible aliases.

SSO remains disabled until at least one explicit user/group allowlist or a
required claim/value pair is configured. See the complete [OIDC and reverse
proxy guide](docs/SSO.md) before enabling `both` or `sso_only` mode.

The downloader step can save several qBittorrent, Transmission, Deluge, and
rTorrent profiles. A profile may be saved disabled for later setup; **enabled**
and **preferred/default** are separate states. Test the exact current draft
before treating it as ready: changing its client kind, URL, or credentials
invalidates the frontend's saved connection-test fingerprint.

---

## Jellyfin webhook setup

The easiest way is to use **Auto-configure** in the Jellyfin service editor (click the pencil icon on the Jellyfin card in the Dashboard). It installs the correct config into the Jellyfin Webhook plugin automatically.

**Manual setup:** install the Webhook plugin in Jellyfin → Dashboard → Plugins → Catalog, then add a Generic destination:

- **URL:** `http://your-cleanarr-host:8089/webhook/jellyfin`
- **Method:** `POST`
- **Header:** `X-Webhook-Token: <your-token>`
- **Notification type:** `Item Deleted` only
- **Template:**

```handlebars
{
  "notification_type": "{{json_encode NotificationType}}",
  "item_type": "{{json_encode ItemType}}",
  "item_id": "{{json_encode ItemId}}",
  "name": "{{json_encode Name}}",
  "path": null,
  "tmdb_id": {{#if_exist Provider_tmdb}}{{Provider_tmdb}}{{else}}null{{/if_exist}},
  "tvdb_id": {{#if_exist Provider_tvdb}}{{Provider_tvdb}}{{else}}null{{/if_exist}},
  "imdb_id": {{#if_exist Provider_imdb}}"{{json_encode Provider_imdb}}"{{else}}null{{/if_exist}},
  "series_name": {{#if_exist SeriesName}}"{{json_encode SeriesName}}"{{else}}null{{/if_exist}},
  "series_id": {{#if_exist SeriesId}}"{{json_encode SeriesId}}"{{else}}null{{/if_exist}},
  "season_number": {{#if_exist SeasonNumber}}{{SeasonNumber}}{{else}}null{{/if_exist}},
  "episode_number": {{#if_exist EpisodeNumber}}{{EpisodeNumber}}{{else}}null{{/if_exist}},
  "episode_end_number": {{#if_exist EpisodeNumberEnd}}{{EpisodeNumberEnd}}{{else}}null{{/if_exist}},
  "occurred_at": "{{json_encode UtcTimestamp}}"
}
```

---

## How it works

### Movie deletion

1. Resolve in Radarr by `tmdb_id → imdb_id → path` (strict, no fuzzy matching)
2. Collect torrent hashes from Radarr download history
3. Delete safe hashes in every owning torrent client, optionally together with local data
4. Delete the Radarr entry
5. Delete matching Seerr requests, issues, and media records

### Series deletion

1. Resolve in Sonarr by `tvdb_id → tmdb_id → imdb_id → path`
2. Delete torrent hashes exclusively owned by the series
3. Delete the Sonarr series entry
4. Delete all Seerr requests, issues, and media for the series

### Season deletion

1. Resolve parent series in Sonarr
2. Unmonitor all episodes in the target season
3. Delete only episode files and hashes fully covered by the season scope
4. Update or remove matching Seerr season requests

### Episode deletion

1. Resolve parent series in Sonarr
2. Unmonitor the target episode range
3. Delete episode file and hash only when fully isolated
4. Delete matching Seerr episode issues; retain a season-scoped request unless
   the event provably covers the complete season, then update or remove it

**Guardrails:** pack torrents (multiple series/seasons in one archive) and shared files are never deleted — CleanArr logs the reason and skips destructive actions.

---

## API reference

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/webhook/jellyfin` | `X-Webhook-Token` header | Main ingestion endpoint |
| `GET` | `/api/dashboard` | session | Dashboard snapshot for the SPA |
| `GET` | `/api/config` | session | Runtime configuration |
| `PUT` | `/api/config/general` | session | Update general settings |
| `GET` | `/api/config/export` | session | Export a credential-free configuration document |
| `POST` | `/api/config/import` | session | Merge a redacted configuration in fail-safe mode |
| `GET` | `/api/support/bundle` | session | Redacted operational support snapshot |
| `GET` | `/metrics` | session or admin token | Privacy-safe Prometheus metrics |
| `POST` | `/api/config/jellyfin/setup-webhook` | session | Auto-configure the Jellyfin Webhook plugin |
| `POST` | `/api/actions/delete/preview` | session | Mutation-free single-item deletion preview |
| `POST` / `GET` | `/api/actions/delete/jobs` | session | Queue or list hash-bound single deletion jobs |
| `GET` / `DELETE` | `/api/actions/delete/jobs/{job_id}` | session | Inspect or dismiss a terminal deletion job |
| `POST` | `/api/actions/delete/batches/preview` | session | Mutation-free item-level batch preview |
| `POST` / `GET` | `/api/actions/delete/batches` | session | Submit or list bounded hash-bound batches |
| `GET` | `/api/actions/delete/batches/{batch_id}` | session | Inspect batch and child outcomes |
| `GET` / `POST` | `/api/downloads`, `/api/downloads/refresh` | session | Bounded cursor read model and refresh |
| `GET` | `/api/downloads/{client_id}/{info_hash}` | session | One normalized torrent observation |
| `POST` | `/api/downloads/actions` | session | Reversible pause/resume only; idempotency required |
| `GET` | `/api/downloads/cleanup-candidates` | session | Bounded Jellyfin-based cleanup recommendations |
| `GET` | `/api/storage/volumes` | session | Privacy-safe Radarr/Sonarr volume health read model |
| `POST` | `/api/storage/refresh` | session | Coalesced storage refresh; manually throttled |
| `GET` | `/api/library/items` | session | Cursor-based movie/series library page with bounded search and sort |
| `GET` | `/api/library/items/{resource_id}` | session | Selected library item and bounded series detail |
| `GET` | `/api/library/artwork/{resource_id}` | session | Authenticated Jellyfin artwork proxy |
| `POST` | `/api/auth/login` | — | Admin login |
| `GET` | `/api/auth/status` | — | Current authentication capabilities and session state |
| `GET` | `/api/auth/sso/login` | — | Start the OpenID Connect login flow |
| `GET` | `/health/live` | none | Liveness probe |
| `GET` | `/health/ready` | none | Readiness probe |

### UI-v2 library and storage contract

The authenticated workspace is responsive: desktop uses a 240px sidebar, tablet
uses an 80px accessible rail, and mobile uses a compact top bar plus fixed bottom
navigation. The mobile layout reserves safe-area space so content is not hidden
behind navigation. Library is read-only until an explicit, hash-bound deletion
preflight and confirmation; poster cards, the selected-item inspector, and the
storage headline never replace ownership evidence.

Library reads use opaque resource IDs and a bounded cursor (`limit` 1–50), with
search and `added`/`title`/`size` sorting. The server may serve an in-process
cache for up to 30 seconds per runtime configuration, Jellyfin language, and
media type; search and sorting reuse that catalog snapshot. `refresh=true`
requests a new read but does not mutate downstream services. Artwork is proxied only after the
resource is resolved, is private, and is cached by clients for at most one hour.
Raw paths, credentials, downstream URLs, and unvalidated artwork metadata are
never returned.

Storage reads collect Radarr/Sonarr root and disk-space observations. Collection
results are cached for 60 seconds and are fresh for 120 seconds; concurrent
requests are coalesced, while manual refresh is throttled to one request per 10
seconds. A partial, stale, missing, invalid, or conflicting observation is
`unknown`, never healthy or deletion permission. Headlines are ordered
critical → unknown/partial → warning → healthy. Storage monitoring remains
read-only. Downloader stop/pause controls remain separate from torrent-entry or
media deletion.

---

## Repository layout

```
cleanarr/
├── backend/                    # Python 3.12 / FastAPI
│   └── src/cleanarr/
│       ├── api/                # Routes, schemas, dashboard, auth
│       ├── application/        # Cascade deletion logic, configuration service
│       ├── domain/             # Models, config, errors
│       └── infrastructure/     # HTTP clients, SQLite stores, settings
├── frontend/                   # React 19 + Vite + TypeScript + shadcn/ui
│   └── src/
├── deploy/
│   ├── Dockerfile              # Multi-stage build (node:24 → python:3.12-slim)
│   ├── docker-compose.yml
│   └── k8s/                    # Kubernetes manifests
├── packaging/                  # DEB/RPM metadata, systemd unit, build scripts
└── docs/
    ├── LINUX_PACKAGES.md       # Native Linux package guide
    ├── OPERATIONS.md           # Metrics, support bundle, config transfer
    ├── RELEASING.md            # Bilingual release policy
    └── screenshots/
```

---

## Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12, FastAPI, httpx, Pydantic v2, uvicorn |
| Frontend | React 19, Vite, TypeScript, shadcn/ui, Tailwind CSS v4, Sonner, Motion |
| Storage | SQLite (config + activity log) |
| Container | Multi-stage Docker build — node:24-bookworm-slim → python:3.12-slim |

---

## Development

```bash
# Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Frontend (build static assets served by the backend)
cd frontend
pnpm install && pnpm build

# Run backend with hot reload
cd backend
uvicorn cleanarr.api.app:app --host 0.0.0.0 --port 8089 --reload
```

For full hot-reload on both sides, run the frontend dev server in parallel — it proxies `/api`, `/health`, and `/webhook` to port 8089:

```bash
# Terminal 2
cd frontend
pnpm dev
```

### Tests

```bash
cd backend
ruff format --check src tests
ruff check src tests
mypy src
pytest -q

cd ../frontend
pnpm lint
pnpm test -- --run
pnpm build
pnpm exec playwright test --project=chromium
```

Release notes are maintained in both Russian and English. See [Release process](docs/RELEASING.md).

---

## License

[MIT](LICENSE)
