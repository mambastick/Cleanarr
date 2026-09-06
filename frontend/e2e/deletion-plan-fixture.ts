import type { DashboardProcessingResult } from "../src/lib/dashboard"

export const detailedPlan: DashboardProcessingResult = {
  item_type: "Series", item_id: "fixture-series", name: "Example Series", display_name: "Пример сериала", status: "success",
  fingerprint: { tmdb_id: 42, tvdb_id: 123, imdb_id: "tt12345", path: "/media/series/Example Series" },
  season_number: null, episode_number: null, episode_end_number: null,
  actions: [
    ...[1, 2, 3].map((season) => ({ system: "qbittorrent", action: "delete_hash", status: "dry_run" as const, message: "PRIVATE BACKEND MESSAGE", reason: null, details: { hash: String(season).repeat(40), torrent_name: `Example.Series.S0${season}.1080p.WEB-DL`, content_path: `/downloads/Example.Series/Season 0${season}`, downloader_id: "fixture-client", downloader_name: "qBittorrent · Media", delete_files: true } })),
    { system: "sonarr", action: "delete_series", status: "dry_run", message: "PRIVATE", reason: null, details: { series_id: 201, title: "Example Series", path: "/media/series/Example Series", sonarr_instance_id: "fixture-sonarr", sonarr_instance_name: "Sonarr · Series" } },
    ...[71, 72].map((id) => ({ system: "seerr", action: "delete_request", status: "dry_run" as const, message: "PRIVATE", reason: null, details: { request_id: id } })),
    { system: "seerr", action: "delete_media", status: "dry_run", message: "PRIVATE", reason: null, details: { media_id: 90 } },
    { system: "jellyfin", action: "delete_item", status: "dry_run", message: "PRIVATE", reason: null, details: { jellyfin_item_id: "fixture-series" } },
  ],
}

export const inspectionProfiles = {
  sonarr: [{ id: "fixture-sonarr", name: "Sonarr · Series", kind: "sonarr", enabled: true, is_default: true, url: "https://sonarr.example/series-ui", api_key: "fixture-only" }],
  downloaders: [{ id: "fixture-client", name: "qBittorrent · Media", kind: "qbittorrent", enabled: true, is_default: true, url: "https://torrent.example/", username: "fixture", password: "fixture-only", api_key: null, seeding_policy: "immediate", min_seed_ratio: null, min_seed_time_minutes: null }],
  seerr: [{ id: "fixture-seerr", name: "Seerr", kind: "seerr", enabled: true, is_default: true, url: "https://seerr.example/", api_key: "fixture-only" }],
  jellyfin: [{ id: "fixture-jellyfin", name: "Jellyfin", kind: "jellyfin", enabled: true, is_default: true, url: "https://jellyfin.example/", api_key: "fixture-only" }],
}
