import type { SsoAuthMode } from "@/lib/auth"

export interface GeneralConfig {
  dry_run: boolean
  log_level: string
  webhook_shared_token: string | null
  http_timeout_seconds: number
  activity_retention_days: number
  jellyfin_language: string
  ui_language: string
  sso_enabled: boolean
  sso_mode: SsoAuthMode
  sso_issuer_url: string | null
  sso_client_id: string | null
  sso_client_secret: string | null
  sso_redirect_uri: string | null
  sso_scopes: string
  sso_allowed_users: string[]
  sso_allowed_groups: string[]
  sso_group_claim: string
  sso_required_claim: string | null
  sso_required_value: string | null
  seeding_stop_policy: SeedingStopPolicyConfig
}

export interface SeedingStopPolicyConfig {
  enabled: boolean
  mode: "all" | "any"
  min_ratio: number | null
  min_seeding_minutes: number | null
  include_categories: string[]
  exclude_categories: string[]
  include_tags: string[]
  exclude_tags: string[]
  interval_seconds: number
  max_attempts: number
}

export interface BaseServiceConfig {
  id: string
  name: string
  url: string
  enabled: boolean
  is_default: boolean
}

export type TorrentRemovalPolicy = "immediate" | "keep" | "defer"

export interface BaseDownloaderServiceConfig extends BaseServiceConfig {
  seeding_policy: TorrentRemovalPolicy
  min_seed_ratio: number | null
  min_seed_time_minutes: number | null
}

export interface RadarrServiceConfig extends BaseServiceConfig {
  kind: "radarr"
  api_key: string
}

export interface SonarrServiceConfig extends BaseServiceConfig {
  kind: "sonarr"
  api_key: string
}

export interface SeerrServiceConfig extends BaseServiceConfig {
  kind: "seerr"
  api_key: string
}

export interface QbittorrentServiceConfig extends BaseDownloaderServiceConfig {
  kind: "qbittorrent"
  username: string
  password: string
  api_key: string | null
}

export interface TransmissionServiceConfig extends BaseDownloaderServiceConfig {
  kind: "transmission"
  username: string
  password: string
}

export interface DelugeServiceConfig extends BaseDownloaderServiceConfig {
  kind: "deluge"
  password: string
}

export interface RTorrentServiceConfig extends BaseDownloaderServiceConfig {
  kind: "rtorrent"
  username: string
  password: string
}

export type DownloaderServiceConfig =
  | QbittorrentServiceConfig
  | TransmissionServiceConfig
  | DelugeServiceConfig
  | RTorrentServiceConfig

export interface JellyfinServiceConfig extends BaseServiceConfig {
  kind: "jellyfin"
  api_key: string
}

export interface RuntimeConfigPayload {
  general: GeneralConfig
  radarr: RadarrServiceConfig[]
  sonarr: SonarrServiceConfig[]
  seerr: SeerrServiceConfig[]
  downloaders: DownloaderServiceConfig[]
  jellyfin: JellyfinServiceConfig[]
  admin_token_configured: boolean
}

export interface ConnectionTestResponse {
  ok: boolean
  message: string
}
