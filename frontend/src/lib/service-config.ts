import { Download, Film, Play, Server, ShieldCheck, Star, Tv, type LucideIcon } from "lucide-react"

import type { UiTextMap } from "@/lib/i18n"
import { hasCurrentConnectionEvidence } from "@/lib/downloader-profile"
import type {
  DownloaderServiceConfig,
  JellyfinServiceConfig,
  RadarrServiceConfig,
  RuntimeConfigPayload,
  SeerrServiceConfig,
  SonarrServiceConfig,
} from "@/lib/runtime-config"

export type ServiceFamily = "radarr" | "sonarr" | "seerr" | "downloaders" | "jellyfin_server"
export type SetupStepId = "general" | ServiceFamily
export type DownloaderKind = DownloaderServiceConfig["kind"]
export type TorrentRemovalPolicy = DownloaderServiceConfig["seeding_policy"]
export type ServiceRecord =
  | RadarrServiceConfig
  | SonarrServiceConfig
  | SeerrServiceConfig
  | DownloaderServiceConfig
  | JellyfinServiceConfig

export type ServiceDraft = {
  id?: string
  name: string
  url: string
  enabled: boolean
  is_default: boolean
  api_key: string
  username: string
  password: string
  downloader_kind: DownloaderKind | null
  seeding_policy: TorrentRemovalPolicy
  min_seed_ratio: string
  min_seed_time_minutes: string
}

export type ServiceModalState = {
  family: ServiceFamily
  draft: ServiceDraft
}

export type ServiceMeta = {
  family: ServiceFamily
  title: string
  singular: string
  description: string
  endpoint: string
  accent: "blue" | "green" | "red"
  icon: LucideIcon
  fields: Array<{
    key: "api_key" | "username" | "password"
    label: string
    type: "password" | "text"
    hint: string
  }>
  steps: string[]
  help: string[]
  example: string
}

export type SetupStepMeta = {
  id: SetupStepId
  title: string
  description: string
  accent: "blue" | "green" | "red"
  icon: LucideIcon
}


// ─── Constants ───────────────────────────────────────────────────────────────

export const LOG_LEVEL_OPTIONS = ["DEBUG", "INFO", "WARNING", "ERROR"] as const
export const DOWNLOADER_KIND_OPTIONS: Array<{ value: DownloaderKind; label: string }> = [
  { value: "qbittorrent", label: "qBittorrent" },
  { value: "transmission", label: "Transmission" },
  { value: "deluge", label: "Deluge" },
  { value: "rtorrent", label: "rTorrent" },
]
export const TORRENT_REMOVAL_POLICIES: TorrentRemovalPolicy[] = ["immediate", "keep", "defer"]
export const DOWNLOADER_EXAMPLES: Record<DownloaderKind, string> = {
  qbittorrent: "https://qbittorrent.example.com",
  transmission: "https://transmission.example.com",
  deluge: "https://deluge.example.com",
  rtorrent: "https://rtorrent.example.com/RPC2",
}
export const SERVICE_FAMILIES: ServiceFamily[] = [
  "radarr",
  "sonarr",
  "seerr",
  "downloaders",
  "jellyfin_server",
]

export const SERVICE_META: Record<ServiceFamily, ServiceMeta> = {
  radarr: {
    family: "radarr",
    title: "Radarr",
    singular: "movie resolver",
    description: "Movie cleanup target used to resolve and delete movies.",
    endpoint: "/api/config/radarr",
    accent: "blue",
    icon: Film,
    fields: [
      {
        key: "api_key",
        label: "API key",
        type: "password",
        hint: "Radarr → Settings → General → Security → API Key.",
      },
    ],
    steps: [
      "Paste the Radarr base URL only. CleanArr appends /api/v3 automatically.",
      "Open Radarr → Settings → General → Security and copy the API key.",
      "Use the internal cluster URL when CleanArr runs next to Radarr.",
      "Keep exactly one enabled runtime target per family.",
    ],
    help: [
      "Example URL: https://radarr.example.com",
      "Reverse-proxy paths also work: https://apps.example.com/radarr",
    ],
    example: "https://radarr.example.com",
  },
  sonarr: {
    family: "sonarr",
    title: "Sonarr",
    singular: "series resolver",
    description: "Series, season, and episode cleanup target.",
    endpoint: "/api/config/sonarr",
    accent: "blue",
    icon: Tv,
    fields: [
      {
        key: "api_key",
        label: "API key",
        type: "password",
        hint: "Sonarr → Settings → General → Security → API Key.",
      },
    ],
    steps: [
      "Paste the Sonarr base URL only. CleanArr appends /api/v3 automatically.",
      "Open Sonarr → Settings → General → Security and copy the API key.",
      "CleanArr uses Sonarr for strict series, season, and episode resolution.",
      "Keep one enabled runtime target so partial TV cleanup has a single source of truth.",
    ],
    help: [
      "Example URL: https://sonarr.example.com",
      "Reverse-proxy paths also work: https://apps.example.com/sonarr",
    ],
    example: "https://sonarr.example.com",
  },
  seerr: {
    family: "seerr",
    title: "Seerr",
    singular: "request manager",
    description: "Request and issue cleanup target.",
    endpoint: "/api/config/seerr",
    accent: "green",
    icon: ShieldCheck,
    fields: [
      {
        key: "api_key",
        label: "API key",
        type: "password",
        hint: "Seerr → Settings → General → API Key.",
      },
    ],
    steps: [
      "Paste the Seerr base URL only. CleanArr appends /api/v1 automatically.",
      "Open Seerr → Settings → General and copy the API key.",
      "CleanArr removes matching requests, issues, and media records after successful cleanup.",
      "Keep Seerr pointed at the same Radarr/Sonarr stack you configure here.",
    ],
    help: [
      "Example URL: https://seerr.example.com",
      "Reverse-proxy paths also work: https://apps.example.com/seerr",
    ],
    example: "https://seerr.example.com",
  },
  downloaders: {
    family: "downloaders",
    title: "Torrent client",
    singular: "downloader",
    description: "qBittorrent, Transmission, Deluge, or rTorrent used for safe hash deletion.",
    endpoint: "/api/config/downloaders/qbittorrent",
    accent: "green",
    icon: Download,
    fields: [
      {
        key: "api_key",
        label: "API key",
        type: "password",
        hint: "qBittorrent 5.2+ supports stateless API-key authentication.",
      },
      {
        key: "username",
        label: "Username",
        type: "text",
        hint: "Use the same username you use to sign in to the qBittorrent Web UI.",
      },
      {
        key: "password",
        label: "Password",
        type: "password",
        hint: "Use the same password you use to sign in to the qBittorrent Web UI.",
      },
    ],
    steps: [
      "Use the Web UI base URL without /api/v2 in the path.",
      "Provide the same Web UI username and password you use in the browser.",
      "CleanArr only deletes hashes when Sonarr or Radarr history proves ownership.",
      "Pack torrents shared with unrelated content are skipped for safety.",
    ],
    help: [
      "Example URL: https://qbittorrent.example.com",
      "Reverse-proxy paths also work: https://apps.example.com/qbittorrent",
    ],
    example: "https://qbittorrent.example.com",
  },
  jellyfin_server: {
    family: "jellyfin_server",
    title: "Jellyfin",
    singular: "media server",
    description: "Jellyfin media server used for library browsing and immediate item removal.",
    endpoint: "/api/config/jellyfin",
    accent: "blue",
    icon: Server,
    fields: [
      {
        key: "api_key",
        label: "API key",
        type: "password",
        hint: "Jellyfin → Dashboard → API Keys → + → create a key for CleanArr.",
      },
    ],
    steps: [
      "Paste the Jellyfin base URL including scheme and port, e.g. http://jellyfin:8096.",
      "Open Jellyfin → Dashboard → API Keys and create a new key for CleanArr.",
      "Connecting Jellyfin enables the Library tab: browse movies and series, delete seasons immediately.",
      "Deletion cascades through Sonarr/Radarr → qBittorrent → Seerr, then removes the item from Jellyfin instantly.",
    ],
    help: [
      "Example URL: http://jellyfin:8096",
      "External URL also works: https://jellyfin.example.com",
    ],
    example: "http://jellyfin:8096",
  },
}

export const SETUP_STEPS: SetupStepMeta[] = [
  {
    id: "jellyfin_server",
    title: "Jellyfin",
    description: "Connect Jellyfin server and configure the webhook plugin.",
    accent: "blue",
    icon: Play,
  },
  {
    id: "radarr",
    title: "Radarr",
    description: "Movie lookup and delete source.",
    accent: "blue",
    icon: Film,
  },
  {
    id: "sonarr",
    title: "Sonarr",
    description: "Series, season, and episode lookup source.",
    accent: "blue",
    icon: Tv,
  },
  {
    id: "seerr",
    title: "Seerr",
    description: "Request and issue cleanup source.",
    accent: "green",
    icon: Star,
  },
  {
    id: "downloaders",
    title: "Torrent client",
    description: "Connect qBittorrent, Transmission, Deluge, or rTorrent.",
    accent: "green",
    icon: Download,
  },
]

export const EMPTY_DRAFTS: Record<ServiceFamily, ServiceDraft> = {
  radarr: { name: "Radarr", url: "", api_key: "", username: "", password: "", downloader_kind: null, enabled: true, is_default: true, seeding_policy: "immediate", min_seed_ratio: "", min_seed_time_minutes: "" },
  sonarr: { name: "Sonarr", url: "", api_key: "", username: "", password: "", downloader_kind: null, enabled: true, is_default: true, seeding_policy: "immediate", min_seed_ratio: "", min_seed_time_minutes: "" },
  seerr: { name: "Seerr", url: "", api_key: "", username: "", password: "", downloader_kind: null, enabled: true, is_default: true, seeding_policy: "immediate", min_seed_ratio: "", min_seed_time_minutes: "" },
  downloaders: { name: "qBittorrent", url: "", api_key: "", username: "", password: "", downloader_kind: "qbittorrent", enabled: true, is_default: true, seeding_policy: "immediate", min_seed_ratio: "", min_seed_time_minutes: "" },
  jellyfin_server: { name: "Jellyfin", url: "", api_key: "", username: "", password: "", downloader_kind: null, enabled: true, is_default: true, seeding_policy: "immediate", min_seed_ratio: "", min_seed_time_minutes: "" },
}

export const DASHBOARD_NAME_TO_FAMILY: Partial<Record<string, ServiceFamily>> = {
  Radarr: "radarr",
  Sonarr: "sonarr",
  Jellyfin: "jellyfin_server",
  Seerr: "seerr",
  Downloader: "downloaders",
}

export const JELLYFIN_LANGUAGE_OPTIONS = [
  { value: "en", label: "English" },
  { value: "ru", label: "Русский" },
  { value: "de", label: "Deutsch" },
  { value: "fr", label: "Français" },
  { value: "it", label: "Italiano" },
  { value: "es", label: "Español" },
  { value: "pl", label: "Polski" },
  { value: "uk", label: "Українська" },
  { value: "cs", label: "Čeština" },
  { value: "zh", label: "中文" },
  { value: "ja", label: "日本語" },
]

export const UI_LANGUAGE_OPTIONS = [
  { value: "en", label: "English" },
  { value: "ru", label: "Русский" },
  { value: "de", label: "Deutsch" },
  { value: "fr", label: "Français" },
  { value: "es", label: "Español" },
  { value: "it", label: "Italiano" },
  { value: "pt", label: "Português" },
  { value: "tr", label: "Türkçe" },
  { value: "pl", label: "Polski" },
  { value: "uk", label: "Українська" },
  { value: "cs", label: "Čeština" },
  { value: "zh", label: "中文" },
  { value: "ja", label: "日本語" },
]

export function getServiceDescription(family: ServiceFamily, text: UiTextMap): string {
  switch (family) {
    case "radarr": return text.serviceRadarrDescription
    case "sonarr": return text.serviceSonarrDescription
    case "seerr": return text.serviceSeerrDescription
    case "downloaders": return text.serviceDownloaderDescription
    case "jellyfin_server": return text.serviceJellyfinDescription
  }
}

export function getDownloaderLabel(kind: DownloaderKind | null): string {
  return DOWNLOADER_KIND_OPTIONS.find((option) => option.value === kind)?.label ?? "Torrent client"
}

export function getServiceTitle(family: ServiceFamily, draft?: ServiceDraft | null): string {
  return family === "downloaders" ? getDownloaderLabel(draft?.downloader_kind ?? null) : SERVICE_META[family].title
}

export function getServiceEndpoint(family: ServiceFamily, kind: DownloaderKind | null): string {
  return family === "downloaders"
    ? `/api/config/downloaders/${kind ?? "qbittorrent"}`
    : SERVICE_META[family].endpoint
}

export function getServiceFields(meta: ServiceMeta, draft: ServiceDraft): ServiceMeta["fields"] {
  if (meta.family !== "downloaders") return meta.fields
  if (draft.downloader_kind === "deluge") return meta.fields.filter((field) => field.key === "password")
  if (draft.downloader_kind === "qbittorrent") return meta.fields
  return meta.fields.filter((field) => field.key === "username" || field.key === "password")
}

export function getServiceExample(meta: ServiceMeta, draft: ServiceDraft): string {
  return meta.family === "downloaders"
    ? DOWNLOADER_EXAMPLES[draft.downloader_kind ?? "qbittorrent"]
    : meta.example
}

export function getServiceHelp(meta: ServiceMeta, text: UiTextMap, draft: ServiceDraft): string[] {
  return [`${text.exampleUrl}: ${getServiceExample(meta, draft)}`, text.reverseProxyHint]
}

export function getServiceFieldLabel(
  key: ServiceMeta["fields"][number]["key"],
  text: UiTextMap,
): string {
  if (key === "username") return text.username
  if (key === "password") return text.password
  return text.apiKey
}

export function getServiceFieldHint(
  family: ServiceFamily,
  key: ServiceMeta["fields"][number]["key"],
  text: UiTextMap,
  downloaderKind: DownloaderKind | null = null,
): string {
  if (family === "downloaders") {
    if (downloaderKind === "qbittorrent" && key === "api_key") {
      return text.qbittorrentApiHint
    }
    if (downloaderKind === "deluge") return text.delugePasswordHint
    if (key === "username") return text.downloaderUsernameHint
    if (key === "password") return text.downloaderPasswordHint
  }
  switch (family) {
    case "radarr": return text.radarrApiHint
    case "sonarr": return text.sonarrApiHint
    case "seerr": return text.seerrApiHint
    case "jellyfin_server": return text.jellyfinApiHint
    case "downloaders": return text.apiKey
  }
}

export function getStatusLabel(status: string, text: UiTextMap): string {
  switch (status.toLowerCase()) {
    case "partial_failure": return text.partialFailure
    case "success": return text.success
    case "failed": return text.failed
    case "deleted": return text.deleted
    case "queued": return text.queued
    case "running": return text.running
    case "planning": return text.planning
    case "retry_wait":
    case "retrying": return text.retrying
    case "completed": return text.completed
    case "skipped": return text.skipped
    case "healthy": return text.healthy
    case "unreachable": return text.unreachable
    case "unconfigured": return text.notConfigured
    default: return status || text.unknown
  }
}

export function getItemTypeLabel(itemType: string, text: UiTextMap): string {
  switch (itemType.toLowerCase()) {
    case "movie": return text.movie
    case "series": return text.series
    case "season": return text.season
    default: return itemType || text.item
  }
}

export function getServices(config: RuntimeConfigPayload | null, family: ServiceFamily): ServiceRecord[] {
  if (!config) return []
  switch (family) {
    case "radarr": return config.radarr
    case "sonarr": return config.sonarr
    case "seerr": return config.seerr
    case "downloaders": return config.downloaders
    case "jellyfin_server": return config.jellyfin
  }
}

export function resolveActiveService(services: ServiceRecord[]): ServiceRecord | null {
  const enabled = services.filter((s) => s.enabled)
  if (enabled.length === 0) return null
  return enabled.find((s) => s.is_default) ?? enabled[0] ?? null
}

export function isServiceFamily(step: SetupStepId): step is ServiceFamily {
  return SERVICE_FAMILIES.includes(step as ServiceFamily)
}

export function generateWebhookToken(): string {
  const bytes = new Uint8Array(24)
  window.crypto.getRandomValues(bytes)
  return Array.from(bytes, (v) => v.toString(16).padStart(2, "0")).join("")
}

export function isSetupStepReady(
  step: SetupStepId,
  config: RuntimeConfigPayload | null,
  testedDownloaderFingerprints: ReadonlySet<string> = new Set(),
): boolean {
  if (!config) return false
  if (step === "general") return Boolean(config.general.webhook_shared_token)
  if (!isServiceFamily(step)) return false
  const services = getServices(config, step)
  const active = resolveActiveService(services)
  if (!active) return false
  if (step !== "downloaders") return true
  const enabledDownloaders = services.filter((service) => service.enabled)
  return enabledDownloaders.length > 0 && enabledDownloaders.every((service) =>
    hasCurrentConnectionEvidence(toDraft(service), testedDownloaderFingerprints),
  )
}

/** Persisted setup progress shown outside the wizard.
 *
 * Connection-test fingerprints intentionally live only for the current wizard
 * session. They must not make a healthy saved downloader look unfinished after
 * a page reload; the wizard still uses `hasCurrentConnectionEvidence` before
 * saving or advancing a changed draft.
 */
export function isSetupStepConfigured(step: SetupStepId, config: RuntimeConfigPayload | null): boolean {
  if (!config) return false
  if (step === "general") return Boolean(config.general.webhook_shared_token)
  if (!isServiceFamily(step)) return false
  return getServices(config, step).some((service) => service.enabled)
}


export function toDraft(service: ServiceRecord): ServiceDraft {
  return {
    id: service.id,
    name: service.name,
    url: service.url,
    enabled: service.enabled,
    is_default: service.is_default,
    api_key: "api_key" in service ? service.api_key ?? "" : "",
    username: "username" in service ? service.username : "",
    password: "password" in service ? service.password : "",
    downloader_kind: ["qbittorrent", "transmission", "deluge", "rtorrent"].includes(service.kind)
      ? service.kind as DownloaderKind
      : null,
    seeding_policy: "seeding_policy" in service ? service.seeding_policy : "immediate",
    min_seed_ratio: "min_seed_ratio" in service && service.min_seed_ratio != null
      ? String(service.min_seed_ratio)
      : "",
    min_seed_time_minutes: "min_seed_time_minutes" in service && service.min_seed_time_minutes != null
      ? String(service.min_seed_time_minutes)
      : "",
  }
}

export function buildServicePayload(family: ServiceFamily, draft: ServiceDraft) {
  const base = { name: draft.name, url: draft.url, enabled: draft.enabled, is_default: draft.is_default }
  switch (family) {
    case "radarr":
    case "sonarr":
    case "seerr":
    case "jellyfin_server":
      return { ...base, api_key: draft.api_key }
    case "downloaders": {
      const policy = {
        seeding_policy: draft.seeding_policy,
        min_seed_ratio: optionalNumber(draft.min_seed_ratio),
        min_seed_time_minutes: optionalNumber(draft.min_seed_time_minutes),
      }
      switch (draft.downloader_kind) {
        case "qbittorrent":
          return { ...base, ...policy, username: draft.username, password: draft.password, api_key: draft.api_key || null }
        case "deluge":
          return { ...base, ...policy, password: draft.password }
        case "transmission":
        case "rtorrent":
          return { ...base, ...policy, username: draft.username, password: draft.password }
        default:
          return { ...base, ...policy, username: draft.username, password: draft.password }
      }
    }
  }
}

export function optionalNumber(value: string): number | null {
  const normalized = value.trim()
  return normalized ? Number(normalized) : null
}
