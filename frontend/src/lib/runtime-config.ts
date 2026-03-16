export interface GeneralConfig {
  dry_run: boolean
  log_level: string
  webhook_shared_token: string | null
  http_timeout_seconds: number
  activity_retention_days: number
}

export interface BaseServiceConfig {
  id: string
  name: string
  url: string
  enabled: boolean
  is_default: boolean
}

export interface RadarrServiceConfig extends BaseServiceConfig {
  kind: "radarr"
  api_key: string
}

export interface SonarrServiceConfig extends BaseServiceConfig {
  kind: "sonarr"
  api_key: string
}

export interface JellyseerrServiceConfig extends BaseServiceConfig {
  kind: "jellyseerr"
  api_key: string
}

export interface QbittorrentServiceConfig extends BaseServiceConfig {
  kind: "qbittorrent"
  username: string
  password: string
}

export interface JellyfinServiceConfig extends BaseServiceConfig {
  kind: "jellyfin"
  api_key: string
}

export interface RuntimeConfigPayload {
  general: GeneralConfig
  radarr: RadarrServiceConfig[]
  sonarr: SonarrServiceConfig[]
  jellyseerr: JellyseerrServiceConfig[]
  downloaders: QbittorrentServiceConfig[]
  jellyfin: JellyfinServiceConfig[]
  admin_token_configured: boolean
}

export interface ConnectionTestResponse {
  ok: boolean
  message: string
}
