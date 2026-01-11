# CleanArr backend

CleanArr receives Jellyfin webhook events and removes the same media from Sonarr, Radarr, Jellyseerr, and qBittorrent.

## Quick start

1. Copy `backend/.env.example` to `backend/.env` and fill in the URLs and API keys.
2. Install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

3. Run the API:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8089
```

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

## Jellyfin webhook

- Endpoint: `POST /webhook/jellyfin`
- Payload: Jellyfin webhook plugin JSON (array or single object).
- By default CleanArr only reacts to `NotificationType=ItemDeleted`.

If your webhook is sending a different event, set `JELLYFIN_EVENT_TYPES` to a comma-separated list.

## qBittorrent matching

qBittorrent deletion uses the `downloadId` (torrent hash) from Sonarr/Radarr history, so path mapping is not required.

```
LIBRARY_PATH_MAPS=/srv/media/library:/srv/media/downloads
```

Multiple maps are separated by `;` (currently optional/future use).

## Environment variables

- `LOG_LEVEL`: logging level (default: `INFO`)
- `DRY_RUN`: log actions without deleting anything (default: `false`)
- `WEBHOOK_TOKEN`: optional shared secret for webhook requests
- `JELLYFIN_URL`: Jellyfin base URL, e.g. `https://tv.example.com`
- `JELLYFIN_API_KEY`: Jellyfin API key
- `JELLYFIN_EVENT_TYPES`: allowed NotificationType values
- `SONARR_URL`: Sonarr API base URL (`.../api/v3`)
- `SONARR_API_KEY`: Sonarr API key
- `SONARR_DELETE_FILES`: delete files in Sonarr
- `SONARR_ADD_IMPORT_LIST_EXCLUSION`: keep false to avoid blacklists
- `RADARR_URL`: Radarr API base URL (`.../api/v3`)
- `RADARR_API_KEY`: Radarr API key
- `RADARR_DELETE_FILES`: delete files in Radarr
- `RADARR_ADD_IMPORT_EXCLUSION`: keep false to avoid exclusions
- `JELLYSEERR_URL`: Jellyseerr API base URL (`.../api/v1`)
- `JELLYSEERR_API_KEY`: Jellyseerr API key
- `JELLYSEERR_DELETE_REQUESTS`: delete requests
- `JELLYSEERR_DELETE_ISSUES`: delete issues
- `QBITTORRENT_URL`: qBittorrent base URL
- `QBITTORRENT_USERNAME`: qBittorrent username
- `QBITTORRENT_PASSWORD`: qBittorrent password
- `QBITTORRENT_DELETE_FILES`: remove data with torrent
- `HTTP_TIMEOUT_SECONDS`: HTTP request timeout
- `LIBRARY_PATH_MAPS`: `library:download` path pairs (optional, future use)
