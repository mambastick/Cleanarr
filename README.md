# CleanArr

CleanArr listens for Jellyfin `ItemDeleted` webhooks and cascades cleanup to Radarr, Sonarr, Jellyseerr, and qBittorrent. When you delete a movie or series in Jellyfin, CleanArr automatically removes the matching entries from every connected service.

It ships with a built-in React dashboard for configuration, monitoring, and activity history. The production frontend is bundled into the same container as the backend.

## Features

- **Cascade deletion** — Movie/series/season/episode removal flows from Jellyfin → Arr apps → downloader
- **Conservative guardrails** — strict ID matching only, pack torrents and shared files are never deleted
- **Live health monitoring** — probes Radarr, Sonarr, Jellyseerr and qBittorrent every 30 seconds
- **Dry-run mode** — enabled by default, no destructive actions until you flip the switch
- **Built-in dashboard** — React SPA served by the same process, includes setup wizard and activity log
- **Multi-profile** — save multiple service definitions, pick one as the active default

## Repository layout

```
cleanarr/
├── backend/          # Python 3.12 / FastAPI
│   ├── pyproject.toml
│   ├── src/cleanarr/
│   │   ├── api/          # FastAPI routes, schemas, dashboard
│   │   ├── application/  # Cascade deletion logic, configuration service
│   │   ├── domain/       # Models, config, errors
│   │   └── infrastructure/ # HTTP clients, container, settings
│   └── tests/
├── frontend/         # React 19 + Vite + shadcn/ui
│   └── src/
├── deploy/
│   ├── Dockerfile
│   ├── docker-compose.yml
│   └── k8s/          # Kubernetes manifests
└── .env.example
```

## Quick start with Docker Compose

```bash
git clone https://github.com/mambastick/Cleanarr.git
cd Cleanarr

# Build the image
docker compose -f deploy/docker-compose.yml build

# Start (edit environment variables in the compose file first)
docker compose -f deploy/docker-compose.yml up -d
```

Open `http://localhost:8089` — the setup wizard walks you through the rest.

### Environment variables

| Variable | Default | Description |
|---|---|---|
| `DRY_RUN` | `true` | Set to `false` to enable real deletions |
| `WEBHOOK_SHARED_TOKEN` | — | Shared secret verified on every incoming webhook |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `HTTP_TIMEOUT_SECONDS` | `15` | Timeout for calls to downstream services |
| `CONFIG_STATE_PATH` | `/config/runtime-config.json` | Persistent config file path — must be on a volume |
| `ADMIN_SHARED_TOKEN` | — | Optional static admin token (bypasses session auth) |

`CONFIG_STATE_PATH` must point to a persistent volume. Without it, all service configurations are lost on restart.

## Docker (manual)

```bash
docker build -f deploy/Dockerfile -t cleanarr:latest .
docker run --rm -p 8089:8089 \
  -e DRY_RUN=true \
  -e WEBHOOK_SHARED_TOKEN=change-me \
  -v cleanarr-config:/config \
  cleanarr:latest
```

## Kubernetes

Manifests are in `deploy/k8s/`. Apply in order:

```bash
kubectl apply -f deploy/k8s/namespace.yaml
kubectl apply -f deploy/k8s/pvc.yaml
# Edit secret.example.yaml with your values first
kubectl apply -f deploy/k8s/secret.example.yaml
kubectl apply -f deploy/k8s/deployment.yaml
kubectl apply -f deploy/k8s/service.yaml
kubectl apply -f deploy/k8s/ingress.yaml
```

The deployment uses `strategy: Recreate` because the config PVC is ReadWriteOnce.

## Jellyfin webhook setup

Install the **Webhook** plugin in Jellyfin, then add a Generic destination:

- **URL:** `http://your-cleanarr-host:8089/webhook/jellyfin`
- **Method:** `POST`
- **Header:** `X-Webhook-Token: <WEBHOOK_SHARED_TOKEN>`
- **Notification type:** `Item Deleted` only
- **Payload template:**

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

The CleanArr dashboard Setup tab shows the exact template and tracks the last webhook delivery attempt so you can verify connectivity without guessing.

## Deletion behavior

### Movie

1. Resolve in Radarr by `tmdb_id → imdb_id → path` (strict, no fuzzy matching)
2. Collect torrent hashes from Radarr download history
3. Delete safe hashes in qBittorrent (`deleteFiles=true`)
4. Delete the Radarr entry
5. Delete matching Jellyseerr requests, issues, and media

### Series

1. Resolve in Sonarr by `tvdb_id → tmdb_id → imdb_id → path`
2. Delete torrent hashes that belong exclusively to the series
3. Delete the Sonarr series entry
4. Delete all Jellyseerr requests, issues, and media for the series

### Season

1. Resolve parent series in Sonarr
2. Unmonitor episodes in the target season
3. Delete only episode files and hashes fully covered by the season scope
4. Update or remove matching Jellyseerr season requests

### Episode

1. Resolve parent series in Sonarr
2. Unmonitor only the target episode range
3. Delete episode file and hash only when fully isolated
4. Jellyseerr partial-request cleanup skipped in v1

**Guardrails:** pack torrents (multiple series/seasons in one archive) and shared files are never deleted — CleanArr logs the reason and skips destructive actions.

## Health monitoring

CleanArr probes each configured downstream service every 30 seconds. The dashboard System Status card shows `healthy`, `unreachable`, or `unconfigured` per service in real time. No webhook is needed to surface connectivity issues.

## Development setup

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
cp ../.env.example ../.env
```

Build the frontend first (the backend serves the static bundle):

```bash
cd ../frontend
pnpm install
pnpm build
```

Then run the backend:

```bash
cd ../backend
uvicorn cleanarr.main:app --host 0.0.0.0 --port 8089 --reload
```

### Full local dev (hot reload on both sides)

Terminal 1 — backend:
```bash
cd backend
source .venv/bin/activate
uvicorn cleanarr.main:app --host 0.0.0.0 --port 8089 --reload
```

Terminal 2 — frontend (Vite proxies `/api`, `/health`, `/webhook` to port 8089):
```bash
cd frontend
pnpm install
pnpm dev
```

### Tests

```bash
cd backend
pytest
```

```bash
cd frontend
pnpm lint
pnpm build
```

Test coverage includes strict resolvers, TV safety analyzer, service-level cascade scenarios, FastAPI webhook auth/payload handling, and HTTP adapters via `respx`.

## API

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/webhook/jellyfin` | `X-Webhook-Token` | Main ingestion endpoint |
| `GET` | `/api/dashboard` | none | Dashboard snapshot for the SPA |
| `GET` | `/health/live` | none | Liveness probe |
| `GET` | `/health/ready` | none | Readiness probe |
| `GET` | `/api/config` | session | Runtime configuration |
| `POST` | `/api/auth/login` | — | Admin login |

## Stack

- **Backend:** Python 3.12, FastAPI, httpx, Pydantic, uvicorn
- **Frontend:** React 19, Vite, TypeScript, shadcn/ui (base-nova style), Tailwind CSS
- **Container:** multi-stage Docker build (node:24 → python:3.12-slim)
