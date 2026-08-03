import {
  Activity,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  CircleAlert,
  CircleHelp,
  Copy,
  Download,
  Eye,
  EyeOff,
  Film,
  Info,
  KeyRound,
  LayoutDashboard,
  Library,
  LoaderCircle,
  LogOut,
  PenSquare,
  Play,

  RefreshCw,
  Server,
  Settings2,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  Star,
  TestTubeDiagonal,
  Trash2,
  Tv,
  type LucideIcon,
  UserRound,
  UserRoundPlus,
  Webhook,
  X,
  Zap,
} from "lucide-react"
import { useCallback, useDeferredValue, useEffect, useMemo, useRef, useState } from "react"
import { toast } from "sonner"

import { ThemeToggle } from "@/components/theme-toggle"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Modal } from "@/components/ui/modal"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Skeleton } from "@/components/ui/skeleton"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Textarea } from "@/components/ui/textarea"
import Stepper, { Step } from "@/components/ui/stepper"
import type { AuthSessionPayload, AuthStatusPayload, SSOLoginPayload } from "@/lib/auth"
import type { SsoAuthMode } from "@/lib/auth"
import type {
  DashboardAction,
  DashboardActivity,
  DashboardPayload,
  DashboardUnifiedActivityItem,
  DashboardWebhookAttempt,
  HealthStatus,
} from "@/lib/dashboard"
import type {
  ConnectionTestResponse,
  GeneralConfig,
  JellyfinServiceConfig,
  JellyseerrServiceConfig,
  QbittorrentServiceConfig,
  RadarrServiceConfig,
  RuntimeConfigPayload,
  SonarrServiceConfig,
} from "@/lib/runtime-config"
import { cn } from "@/lib/utils"
import type {
  LibraryMoviesResponse,
  LibrarySeriesResponse,
  ManualDeleteJob,
  ManualDeleteJobListResponse,
} from "@/lib/library"

// ─── Brand ───────────────────────────────────────────────────────────────────

function CleanArrBrand({ size = "sm" }: { size?: "sm" | "lg" }) {
  const iconSize = size === "sm" ? 18 : 36
  const textClass = size === "sm" ? "text-base" : "text-3xl"
  return (
    <div className="flex items-center gap-2">
      <svg width={iconSize} height={iconSize} viewBox="0 0 48 48" fill="none">
        <path d="M28,6 L8,28 L24,28 L22,42 L40,20 L24,20 Z" fill="#a855f7" />
      </svg>
      <span className={textClass}>
        <span className="font-light text-foreground">Clean</span>
        <span className="font-bold text-purple-500">Arr</span>
      </span>
    </div>
  )
}

// ─── Types ───────────────────────────────────────────────────────────────────

type MainTab = "dashboard" | "settings" | "activity" | "library"
type ServiceFamily = "radarr" | "sonarr" | "jellyseerr" | "downloaders" | "jellyfin_server"
type SetupStepId = "general" | ServiceFamily
type AuthMode = "register" | "login"
type ServiceRecord =
  | RadarrServiceConfig
  | SonarrServiceConfig
  | JellyseerrServiceConfig
  | QbittorrentServiceConfig
  | JellyfinServiceConfig

type LibraryDeleteTarget =
  | {
      kind: "series"
      sonarr_series_id: number
      series_title: string
      item_type: "Season" | "Series"
      season_number?: number
      jellyfin_item_id?: string | null
    }
  | {
      kind: "movie"
      radarr_movie_id: number
      movie_title: string
      jellyfin_movie_id?: string | null
    }

type ServiceDraft = {
  id?: string
  name: string
  url: string
  enabled: boolean
  is_default: boolean
  api_key: string
  username: string
  password: string
}

type ServiceModalState = {
  family: ServiceFamily
  draft: ServiceDraft
}

type ServiceMeta = {
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

type SetupStepMeta = {
  id: SetupStepId
  title: string
  description: string
  accent: "blue" | "green" | "red"
  icon: LucideIcon
}


// ─── Cookie auth ─────────────────────────────────────────────────────────────

const COOKIE_NAME = "cleanarr_session"

function readSessionCookie(): string {
  if (typeof document === "undefined") return ""
  const entry = document.cookie
    .split("; ")
    .find((row) => row.startsWith(`${COOKIE_NAME}=`))
  return entry ? entry.split("=").slice(1).join("=") : ""
}

function writeSessionCookie(token: string): void {
  if (typeof document === "undefined") return
  if (token) {
    const maxAge = 60 * 60 * 24 * 30 // 30 days
    document.cookie = `${COOKIE_NAME}=${token}; path=/; SameSite=Strict; max-age=${maxAge}`
  } else {
    document.cookie = `${COOKIE_NAME}=; path=/; max-age=0`
  }
}

// ─── Constants ───────────────────────────────────────────────────────────────

const LOG_LEVEL_OPTIONS = ["DEBUG", "INFO", "WARNING", "ERROR"] as const
const SERVICE_FAMILIES: ServiceFamily[] = [
  "radarr",
  "sonarr",
  "jellyseerr",
  "downloaders",
  "jellyfin_server",
]

const SERVICE_META: Record<ServiceFamily, ServiceMeta> = {
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
  jellyseerr: {
    family: "jellyseerr",
    title: "Jellyseerr",
    singular: "request manager",
    description: "Request and issue cleanup target.",
    endpoint: "/api/config/jellyseerr",
    accent: "green",
    icon: ShieldCheck,
    fields: [
      {
        key: "api_key",
        label: "API key",
        type: "password",
        hint: "Jellyseerr → Settings → General → API Key.",
      },
    ],
    steps: [
      "Paste the Jellyseerr base URL only. CleanArr appends /api/v1 automatically.",
      "Open Jellyseerr → Settings → General and copy the API key.",
      "CleanArr removes matching requests, issues, and media records after successful cleanup.",
      "Keep Jellyseerr pointed at the same Radarr/Sonarr stack you configure here.",
    ],
    help: [
      "Example URL: https://jellyseerr.example.com",
      "Reverse-proxy paths also work: https://apps.example.com/jellyseerr",
    ],
    example: "https://jellyseerr.example.com",
  },
  downloaders: {
    family: "downloaders",
    title: "qBittorrent",
    singular: "downloader",
    description: "Downloader used for torrent hash deletion with files.",
    endpoint: "/api/config/downloaders/qbittorrent",
    accent: "green",
    icon: Download,
    fields: [
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
      "Deletion cascades through Sonarr/Radarr → qBittorrent → Jellyseerr, then removes the item from Jellyfin instantly.",
    ],
    help: [
      "Example URL: http://jellyfin:8096",
      "External URL also works: https://jellyfin.example.com",
    ],
    example: "http://jellyfin:8096",
  },
}

const SETUP_STEPS: SetupStepMeta[] = [
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
    id: "jellyseerr",
    title: "Jellyseerr",
    description: "Request and issue cleanup source.",
    accent: "green",
    icon: Star,
  },
  {
    id: "downloaders",
    title: "qBittorrent",
    description: "Downloader used for safe hash deletion.",
    accent: "green",
    icon: Download,
  },
]

const EMPTY_DRAFTS: Record<ServiceFamily, ServiceDraft> = {
  radarr: { name: "Radarr", url: "", api_key: "", username: "", password: "", enabled: true, is_default: true },
  sonarr: { name: "Sonarr", url: "", api_key: "", username: "", password: "", enabled: true, is_default: true },
  jellyseerr: { name: "Jellyseerr", url: "", api_key: "", username: "", password: "", enabled: true, is_default: true },
  downloaders: { name: "qBittorrent", url: "", api_key: "", username: "", password: "", enabled: true, is_default: true },
  jellyfin_server: { name: "Jellyfin", url: "", api_key: "", username: "", password: "", enabled: true, is_default: true },
}

const DASHBOARD_NAME_TO_FAMILY: Partial<Record<string, ServiceFamily>> = {
  Radarr: "radarr",
  Sonarr: "sonarr",
  Jellyfin: "jellyfin_server",
  Jellyseerr: "jellyseerr",
  Downloader: "downloaders",
}

const JELLYFIN_LANGUAGE_OPTIONS = [
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

const UI_LANGUAGE_OPTIONS = [
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

type UiLanguage = string

type UiTextKey =
  | "dashboard"
  | "settings"
  | "activity"
  | "library"
  | "live"
  | "dryRun"
  | "liveMode"
  | "liveModeDescription"
  | "dryRunDescription"
  | "logOut"
  | "status"
  | "setup"
  | "setupWizard"
  | "connectedServices"
  | "webhookStatus"
  | "latestEvent"
  | "webhookStatusDescription"
  | "latestEventDescription"
  | "noWebhookReceived"
  | "runtimeSettingsSaved"
  | "save"
  | "saveChanges"
  | "saveSettings"
  | "cancel"
  | "delete"
  | "deleteSeries"
  | "deleteItem"
  | "refresh"
  | "filter"
  | "clear"
  | "activityTimeline"
  | "activityTimelineDescription"
  | "eventCount"
  | "noActivityFiltered"
  | "noActivity"
  | "noActivityDescription"
  | "noActivityWebhook"
  | "sendWebhookToSeeActivity"
  | "sendWebhookForStatus"
  | "noWebhookAttempts"
  | "webhookAttempts"
  | "setupCount"
  | "deletionsLogged"
  | "noWebhookActivity"
  | "library"
  | "backgroundTasks"
  | "searchMovies"
  | "noMoviesFound"
  | "noMoviesMatch"
  | "searchSeries"
  | "noSeriesFound"
  | "noSeriesMatch"
  | "noSeasonsFound"
  | "season"
  | "libraryDescription"
  | "dryRunModeInfo"
  | "noLiveChanges"
  | "series"
  | "movies"
  | "searchPlaceholderSeries"
  | "searchPlaceholderMovies"
  | "confirmDelete"
  | "simulate"
  | "deleteButton"
  | "confirmDeleteDescription"
  | "titleDeleteConfirmation"
  | "dryRunModeNotice"
  | "titleNotConfigured"
  | "general"
  | "settingsUnavailable"
  | "tryAgain"
  | "runtimeSettings"
  | "noItemsYet"
  | "appBehaviour"
  | "logLevel"
  | "httpTimeoutSeconds"
  | "activityRetention"
  | "jellyfinMetadataLanguage"
  | "uiLanguage"
  | "webhookToken"
  | "hideToken"
  | "showToken"
  | "regenerateToken"
  | "copyToken"
  | "tokenHint"
  | "allSettingsSaved"
  | "unsavedChanges"
  | "firstLaunchCreateAdmin"
  | "signInWithLocalOrSso"
  | "signInWithLocalOnly"
  | "signInWithSso"
  | "authTitleSignIn"
  | "authTitleCreateAdmin"
  | "username"
  | "password"
  | "confirmPassword"
  | "signInWithCredentials"
  | "orDivider"
  | "ssoSignInError"
  | "continueWithSso"
  | "ssoNotConfigured"
  | "connecting"
  | "configureSsoBefore"
  | "noAuthConfigured"
  | "requestFailed"
  | "ssoAuthMode"
  | "ssoIssuer"
  | "ssoClientId"
  | "ssoClientSecret"
  | "ssoRedirectUri"
  | "ssoScopes"
  | "ssoModePasswordOnly"
  | "ssoModeSsoOnly"
  | "ssoModeBoth"
  | "ssoModePasswordOnlyHint"
  | "ssoModeSsoOnlyHint"
  | "ssoModeBothHint"
  | "ssoIssuerHint"
  | "ssoClientIdHint"
  | "ssoClientSecretHint"
  | "ssoRedirectHint"
  | "ssoScopesHint"
  | "ssoFieldDisabledHint"
  | "webhookMessageLabel"
  | "webhookPayloadEventsLabel"
  | "webhookNotificationLabel"
  | "webhookResultStatusLabel"
  | "reasonLabel"
  | "add"
  | "edit"
  | "test"
  | "next"
  | "back"
  | "skipForNow"
  | "done"
  | "enabled"
  | "runtimeTarget"
  | "displayName"
  | "baseUrl"
  | "alreadyConfigured"
  | "beforeYouSave"
  | "beforeSaveDescription"
  | "webhook"
  | "notConfigured"
  | "healthy"
  | "unreachable"
  | "noStatus"
  | "none"
  | "active"
  | "recent"
  | "dismiss"
  | "progress"
  | "actions"
  | "deletion"
  | "unexpectedRequestError"
  | "unknownError"
  | "passwordsDoNotMatch"
  | "adminCreated"
  | "signedIn"
  | "deletionStarted"
  | "backgroundRefreshFailed"
  | "serviceUpdated"
  | "serviceAdded"
  | "serviceRemoved"
  | "runtimeSettingsSummary"
  | "jellyfinLanguageHint"
  | "uiLanguageHint"
  | "runtimeSettingsDescription"
  | "recommendedFirstRun"
  | "recommendedDryRun"
  | "httpTimeoutHint"
  | "retentionHint"
  | "closeAndRefresh"
  | "keepDryRun"
  | "oneDay"
  | "sevenDays"
  | "thirtyDays"
  | "ninetyDays"
  | "oneYear"
  | "serviceRadarrDescription"
  | "serviceSonarrDescription"
  | "serviceJellyseerrDescription"
  | "serviceDownloaderDescription"
  | "serviceJellyfinDescription"
  | "apiKey"
  | "exampleUrl"
  | "reverseProxyHint"
  | "serviceUrlHint"
  | "downloaderUrlHint"
  | "radarrApiHint"
  | "sonarrApiHint"
  | "jellyseerrApiHint"
  | "downloaderUsernameHint"
  | "downloaderPasswordHint"
  | "jellyfinApiHint"
  | "firstTimeSetup"
  | "autoConfigureWebhook"
  | "autoConfigureWebhookDescription"
  | "connectJellyfinFirst"
  | "setWebhookTokenFirst"
  | "configuring"
  | "configured"
  | "installJellyfinWebhook"
  | "installJellyfinWebhookDescription"
  | "jellyfinInstallStep1"
  | "jellyfinInstallStep2"
  | "jellyfinInstallStep3"
  | "jellyfinInstallStep4"
  | "verifyDelivery"
  | "verifyDeliveryDescription"
  | "deliveryStatus"
  | "lastAttempt"
  | "httpStatus"
  | "lastItem"
  | "notReceivedYet"
  | "noItemReceived"
  | "processing"
  | "latestWebhookAttempt"
  | "noJellyfinWebhook"
  | "smokeTestCurl"
  | "tokenPrefilled"
  | "configureTokenFirst"
  | "smokeTestDescription"
  | "copyCurl"
  | "generalSetupStep1"
  | "generalSetupStep2"
  | "generalSetupStep3"
  | "tryDifferentSearch"
  | "noSeriesSetup"
  | "noMoviesSetup"
  | "onDisk"
  | "noFile"
  | "episodes"
  | "seasons"
  | "dryRunNoChanges"
  | "seasonOfSeries"
  | "movie"
  | "item"
  | "webhookReceived"
  | "tokenMismatch"
  | "payloadRejected"
  | "noDeliveryYet"
  | "partialFailure"
  | "success"
  | "failed"
  | "deleted"
  | "queued"
  | "running"
  | "completed"
  | "skipped"
  | "unknown"

type UiTextMap = Record<UiTextKey, string>

const UI_TEXTS: Record<UiLanguage, Partial<UiTextMap>> = {
  en: {
    dashboard: "Dashboard",
    settings: "Settings",
    activity: "Activity",
    library: "Library",
    live: "Live",
    dryRun: "Dry run",
    liveMode: "Live mode",
    liveModeDescription: "Real deletions are active",
    dryRunDescription: "No deletions will be made",
    status: "Status",
    setup: "Setup",
    setupWizard: "Setup wizard",
    connectedServices: "Connected services",
    webhookStatus: "Webhook status",
    latestEvent: "Latest event",
    webhookStatusDescription: "Last Jellyfin delivery attempt.",
    latestEventDescription: "Most recent processed item.",
    noWebhookReceived: "No webhook received",
    logOut: "Log out",
    runtimeSettingsSaved: "Runtime settings saved.",
    save: "Save",
    saveChanges: "Save changes",
    saveSettings: "Save settings",
    cancel: "Cancel",
    delete: "Delete",
    deleteSeries: "Delete series",
    deleteItem: "Delete movie",
    series: "Series",
    movies: "Movies",
    refresh: "Refresh",
    filter: "Filter",
    clear: "Clear",
    activityTimeline: "Runtime activity timeline",
    activityTimelineDescription: "Incoming Jellyfin webhooks and processed deletion events in one stream.",
    eventCount: "event",
    noActivityFiltered: "No items match the current filter.",
    noActivity: "No activity yet",
    noActivityDescription: "No items found.",
    noActivityWebhook: "No activity yet",
    sendWebhookToSeeActivity: "Send a Jellyfin webhook or process a cleanup event to populate the timeline.",
    sendWebhookForStatus: "Send a Jellyfin webhook to see current status.",
    noWebhookAttempts: "No webhook attempts yet.",
    webhookAttempts: "No webhook attempts yet.",
    setupCount: "Setup progress",
    deletionsLogged: "deletions logged",
    noWebhookActivity: "No webhook activity yet.",
    noItemsYet: "No items found.",
    noSeriesFound: "No series found",
    noSeriesMatch: "No series match your search",
    noSeasonsFound: "No seasons with episodes found.",
    season: "Season",
    searchPlaceholderSeries: "Search series…",
    searchPlaceholderMovies: "Search movies…",
    libraryDescription:
      "Browse your media library and delete items — cascades to Sonarr/Radarr, qBittorrent, Jellyseerr, and Jellyfin.",
    dryRunModeInfo: "Dry run mode",
    noLiveChanges: "No actual changes will be made. Enable Live mode in Runtime settings to execute real deletions.",
    deleteButton: "Delete",
    confirmDelete: "Delete",
    simulate: "Simulate (dry run)",
    confirmDeleteDescription:
      "This will remove files from Sonarr, delete matching torrents from qBittorrent, and clean up requests in Jellyseerr. The task will continue in the background, so you can keep using CleanArr.",
    titleDeleteConfirmation: "Delete \"{{title}}\"?",
    dryRunModeNotice: "Dry run mode",
    titleNotConfigured: "No authentication method is currently configured.",
    backgroundTasks: "Background tasks",
    searchMovies: "Search movies…",
    noMoviesFound: "No movies found",
    noMoviesMatch: "No movies match your search",
    general: "General",
    settingsUnavailable: "Settings unavailable",
    tryAgain: "Refresh the configuration and try again.",
    runtimeSettings: "Runtime settings",
    appBehaviour: "Application behaviour and operational parameters.",
    logLevel: "Log level",
    httpTimeoutSeconds: "HTTP timeout (s)",
    activityRetention: "Activity retention",
    jellyfinMetadataLanguage: "Jellyfin metadata language",
    uiLanguage: "UI language",
    webhookToken: "Webhook token",
    hideToken: "Hide token",
    showToken: "Show token",
    regenerateToken: "Regenerate token",
    copyToken: "Copy token",
    tokenHint:
      "Auto-generated. Regenerate only if you need to rotate it — then re-run auto-configure in the Jellyfin step.",
    allSettingsSaved: "All settings saved.",
    unsavedChanges: "You have unsaved changes.",
    firstLaunchCreateAdmin: "First launch — create the admin account.",
    signInWithLocalOrSso: "Sign in with local credentials or SSO.",
    signInWithLocalOnly: "Sign in with local credentials.",
    signInWithSso: "Sign in with SSO",
    authTitleSignIn: "Sign in",
    authTitleCreateAdmin: "Create administrator",
    username: "Username",
    password: "Password",
    confirmPassword: "Confirm password",
    signInWithCredentials: "Sign in with credentials",
    orDivider: "or",
    ssoSignInError: "SSO sign-in error",
    continueWithSso: "Continue with SSO",
    ssoNotConfigured: "SSO is not configured yet",
    connecting: "Connecting...",
    configureSsoBefore: "Enable and configure SSO in Runtime settings, then reload this screen.",
    noAuthConfigured: "No authentication method is currently configured.",
    requestFailed: "Request failed",
    ssoAuthMode: "SSO auth mode",
    ssoIssuer: "Issuer URL",
    ssoClientId: "Client ID",
    ssoClientSecret: "Client Secret",
    ssoRedirectUri: "Redirect URI",
    ssoScopes: "Scopes",
    ssoModePasswordOnly: "Local credentials only",
    ssoModeSsoOnly: "SSO only",
    ssoModeBoth: "Local + SSO",
    ssoIssuerHint: "Full OIDC issuer URL from your provider.",
    ssoClientIdHint: "Public client ID for your OIDC application.",
    ssoClientSecretHint: "Secret sent to your provider's token endpoint.",
    ssoRedirectHint: "Usually your CleanArr public URL + /api/auth/sso/callback.",
    ssoScopesHint: "Optional override for OIDC scope list.",
    ssoFieldDisabledHint: "SSO fields are disabled while auth mode is Password-only.",
    webhookMessageLabel: "Message:",
    webhookPayloadEventsLabel: "Payload events:",
    webhookNotificationLabel: "Notification:",
    webhookResultStatusLabel: "Processing result:",
    reasonLabel: "reason:",
    ssoModePasswordOnlyHint: "Use only local credentials. SSO fields are disabled.",
    ssoModeSsoOnlyHint: "Use only external identity provider authentication.",
    ssoModeBothHint: "Allow both local credentials and external identity provider authentication.",
    add: "Add",
    edit: "Edit",
    test: "Test",
    next: "Next",
    back: "Back",
    skipForNow: "Skip for now",
    done: "Done",
    enabled: "Enabled",
    runtimeTarget: "Use as runtime target",
    displayName: "Display name",
    baseUrl: "Base URL",
    alreadyConfigured: "Already configured",
    beforeYouSave: "Before you save",
    beforeSaveDescription: "Paste the service URL and credentials, then run Test. The result must turn green before switching live.",
    webhook: "Webhook",
    notConfigured: "Not configured",
    healthy: "Healthy",
    unreachable: "Unreachable",
    noStatus: "No status",
    none: "None",
    active: "active",
    recent: "recent",
    dismiss: "Dismiss",
    progress: "progress",
    actions: "actions",
    deletion: "deletion",
    unexpectedRequestError: "Unexpected request error",
    unknownError: "Unknown error",
    passwordsDoNotMatch: "Passwords do not match.",
    adminCreated: "Administrator created. Use the setup wizard to configure your services.",
    signedIn: "Signed in successfully.",
    deletionStarted: "Deletion started in the background.",
    backgroundRefreshFailed: "Could not refresh background tasks",
    serviceUpdated: "updated",
    serviceAdded: "added",
    serviceRemoved: "removed",
    runtimeSettingsSummary: "Runtime settings: log level, HTTP timeout, activity retention, metadata language, SSO, and webhook token.",
    jellyfinLanguageHint: "Used when requesting series and movie titles from Jellyfin metadata.",
    uiLanguageHint: "Changes the language of the CleanArr interface.",
    runtimeSettingsDescription: "Changes are persisted and immediately rebuild the live runtime.",
    recommendedFirstRun: "Recommended first-run settings",
    recommendedDryRun: "Leave Dry Run enabled while you validate every downstream integration.",
    httpTimeoutHint: "Increase only if your Arr services are slow to respond.",
    retentionHint: "Events older than this are deleted from the SQLite database.",
    closeAndRefresh: "Close this window and refresh the configuration.",
    keepDryRun: "Keep CleanArr in Dry Run",
    oneDay: "1 day",
    sevenDays: "7 days",
    thirtyDays: "30 days",
    ninetyDays: "90 days",
    oneYear: "1 year",
    serviceRadarrDescription: "Movie cleanup target used to resolve and delete movies.",
    serviceSonarrDescription: "Series, season, and episode cleanup target.",
    serviceJellyseerrDescription: "Request and issue cleanup target.",
    serviceDownloaderDescription: "Downloader used for torrent hash deletion with files.",
    serviceJellyfinDescription: "Jellyfin media server used for library browsing and immediate item removal.",
    apiKey: "API key",
    exampleUrl: "Example URL",
    reverseProxyHint: "Reverse-proxy paths are supported.",
    serviceUrlHint: "Paste the service URL only. CleanArr appends the correct API path automatically.",
    downloaderUrlHint: "Paste the qBittorrent Web UI URL only. CleanArr strips /api/v2 automatically.",
    radarrApiHint: "Radarr → Settings → General → Security → API Key.",
    sonarrApiHint: "Sonarr → Settings → General → Security → API Key.",
    jellyseerrApiHint: "Jellyseerr → Settings → General → API Key.",
    downloaderUsernameHint: "Use the same username you use to sign in to the qBittorrent Web UI.",
    downloaderPasswordHint: "Use the same password you use to sign in to the qBittorrent Web UI.",
    jellyfinApiHint: "Jellyfin → Dashboard → API Keys → + → create a key for CleanArr.",
    firstTimeSetup: "First-time setup — configure each service to get started.",
    autoConfigureWebhook: "Auto-configure webhook",
    autoConfigureWebhookDescription: "CleanArr configures the Jellyfin Webhook plugin automatically. The plugin must already be installed in Jellyfin.",
    connectJellyfinFirst: "Connect the Jellyfin server before auto-configuring the webhook.",
    setWebhookTokenFirst: "Set a webhook token in Runtime settings first — it will be included in the plugin config.",
    configuring: "Configuring…",
    configured: "Configured",
    installJellyfinWebhook: "Install the Jellyfin Webhook plugin",
    installJellyfinWebhookDescription: "Jellyfin → Dashboard → Plugins → Catalog → search Webhook → install → restart if prompted.",
    jellyfinInstallStep1: "Open Jellyfin → Dashboard → Catalog.",
    jellyfinInstallStep2: "Find the plugin named Webhook and install it.",
    jellyfinInstallStep3: "Restart Jellyfin if the plugin manager asks for it.",
    jellyfinInstallStep4: "After restart, open Jellyfin → Dashboard → Plugins → Webhook.",
    verifyDelivery: "Verify delivery",
    verifyDeliveryDescription: "CleanArr records every inbound webhook attempt so you can confirm delivery without a real deletion event.",
    deliveryStatus: "Delivery status",
    lastAttempt: "Last attempt",
    httpStatus: "HTTP status",
    lastItem: "Last item",
    notReceivedYet: "Not received yet",
    noItemReceived: "No item received yet",
    processing: "Processing",
    latestWebhookAttempt: "Latest webhook attempt",
    noJellyfinWebhook: "No Jellyfin webhook has reached CleanArr yet.",
    smokeTestCurl: "Smoke test (cURL)",
    tokenPrefilled: "token pre-filled",
    configureTokenFirst: "configure token first",
    smokeTestDescription: "Sends a synthetic ItemDeleted event to CleanArr. Use it to confirm network connectivity and token authentication before a real deletion.",
    copyCurl: "Copy cURL",
    generalSetupStep1: "Keep CleanArr in Dry Run until all services test green.",
    generalSetupStep2: "Set a webhook token. Jellyfin must send the same X-Webhook-Token header.",
    generalSetupStep3: "Only switch to Live mode after all downstream services are configured.",
    tryDifferentSearch: "Try a different search term.",
    noSeriesSetup: "Sonarr returned no series. Configure Sonarr in Setup first.",
    noMoviesSetup: "Radarr returned no movies. Configure Radarr in Setup first.",
    onDisk: "On disk",
    noFile: "No file",
    episodes: "episodes",
    seasons: "seasons",
    dryRunNoChanges: "No actual changes will be made.",
    seasonOfSeries: "Season {{season}} of {{series}}",
    movie: "Movie",
    item: "Item",
    webhookReceived: "Webhook received",
    tokenMismatch: "Token mismatch",
    payloadRejected: "Payload rejected",
    noDeliveryYet: "No delivery yet",
    partialFailure: "Partial failure",
    success: "Success",
    failed: "Failed",
    deleted: "Deleted",
    queued: "Queued",
    running: "Running",
    completed: "Completed",
    skipped: "Skipped",
    unknown: "Unknown",
  },
  ru: {
    dashboard: "Панель",
    settings: "Настройки",
    activity: "Активность",
    library: "Библиотека",
    live: "Включен",
    dryRun: "Тестовый режим",
    liveMode: "Рабочий режим",
    liveModeDescription: "Выполняются реальные удаления",
    dryRunDescription: "Реальные удаления отключены",
    status: "Статус",
    setup: "Настройка",
    setupWizard: "Мастер настройки",
    connectedServices: "Подключённые сервисы",
    webhookStatus: "Состояние webhook",
    latestEvent: "Последнее событие",
    webhookStatusDescription: "Последняя попытка доставки webhook от Jellyfin.",
    latestEventDescription: "Последний обработанный элемент.",
    noWebhookReceived: "Webhook пока не получен",
    logOut: "Выйти",
    runtimeSettingsSaved: "Настройки сохранены.",
    save: "Сохранить",
    saveChanges: "Сохранить изменения",
    saveSettings: "Сохранить настройки",
    cancel: "Отмена",
    delete: "Удалить",
    deleteSeries: "Удалить сериал",
    deleteItem: "Удалить фильм",
    series: "Сериалы",
    movies: "Фильмы",
    refresh: "Обновить",
    filter: "Фильтр",
    clear: "Очистить",
    activityTimeline: "Журнал активности",
    activityTimelineDescription: "Входящие webhooks от Jellyfin и события удаления в едином потоке.",
    eventCount: "событие",
    noActivityFiltered: "По текущему фильтру ничего не найдено.",
    noActivity: "Пока активности нет",
    noActivityDescription: "События отсутствуют.",
    noActivityWebhook: "Событий пока нет",
    sendWebhookToSeeActivity: "Отправьте webhook из Jellyfin или обработайте событие очистки, чтобы видеть историю.",
    sendWebhookForStatus: "Отправьте webhook из Jellyfin для получения статуса доставки.",
    noWebhookAttempts: "Попыток webhook пока нет.",
    webhookAttempts: "Попыток webhook пока нет.",
    setupCount: "Прогресс настройки",
    deletionsLogged: "удалений в журнале",
    noWebhookActivity: "Пока событий от webhook не было.",
    noItemsYet: "Записей пока нет.",
    noSeriesFound: "Сериалы не найдены",
    noSeriesMatch: "Нет совпадений по вашему запросу",
    noSeasonsFound: "Сезоны с эпизодами не найдены.",
    season: "Сезон",
    searchPlaceholderSeries: "Поиск сериалов…",
    searchPlaceholderMovies: "Поиск фильмов…",
    libraryDescription:
      "Просматривайте медиатеку и удаляйте элементы — очистка затем выполняется в Sonarr/Radarr, qBittorrent, Jellyseerr и Jellyfin.",
    dryRunModeInfo: "Тестовый режим",
    noLiveChanges: "Реальные изменения не выполняются. Включите рабочий режим в настройках приложения, чтобы разрешить удаление.",
    deleteButton: "Удалить",
    confirmDelete: "Удалить",
    simulate: "Симулировать (тест)",
    confirmDeleteDescription:
      "Будут удалены файлы в Sonarr, сопутствующие торренты в qBittorrent и запросы в Jellyseerr. Задача продолжится в фоне.",
    titleDeleteConfirmation: "Удалить {{title}}?",
    dryRunModeNotice: "Тестовый режим",
    titleNotConfigured: "Метод авторизации сейчас не настроен.",
    backgroundTasks: "Фоновые задачи",
    searchMovies: "Поиск фильмов…",
    noMoviesFound: "Фильмы не найдены",
    noMoviesMatch: "Нет совпадений по вашему поиску",
    general: "Общее",
    settingsUnavailable: "Настройки недоступны",
    tryAgain: "Обновите конфигурацию и повторите.",
    runtimeSettings: "Настройки приложения",
    appBehaviour: "Параметры работы и поведения приложения.",
    logLevel: "Уровень логирования",
    httpTimeoutSeconds: "Тайм-аут HTTP (с)",
    activityRetention: "Хранение активности",
    jellyfinMetadataLanguage: "Язык метаданных Jellyfin",
    uiLanguage: "Язык интерфейса",
    webhookToken: "Токен webhook",
    hideToken: "Скрыть токен",
    showToken: "Показать токен",
    regenerateToken: "Пересоздать токен",
    copyToken: "Копировать токен",
    tokenHint:
      "Генерируется автоматически. Пересоздайте только если нужно обновить ключ; затем повторите автонастройку в шаге Jellyfin.",
    allSettingsSaved: "Все настройки сохранены.",
    unsavedChanges: "Есть несохранённые изменения.",
    firstLaunchCreateAdmin: "Первый запуск — создайте учётную запись администратора.",
    signInWithLocalOrSso: "Войти с локальными учётными данными или через SSO.",
    signInWithLocalOnly: "Войти с локальными учётными данными.",
    signInWithSso: "Войти через SSO",
    authTitleSignIn: "Вход",
    authTitleCreateAdmin: "Создать администратора",
    username: "Имя пользователя",
    password: "Пароль",
    confirmPassword: "Подтвердите пароль",
    signInWithCredentials: "Войти через учётные данные",
    orDivider: "или",
    ssoSignInError: "Ошибка входа по SSO",
    continueWithSso: "Продолжить через SSO",
    ssoNotConfigured: "SSO ещё не настроен",
    connecting: "Подключение...",
    configureSsoBefore: "Настройте SSO в настройках приложения, затем перезагрузите экран.",
    noAuthConfigured: "Метод авторизации не настроен.",
    requestFailed: "Ошибка запроса",
    ssoAuthMode: "Режим SSO",
    ssoIssuer: "URL issuer",
    ssoClientId: "Client ID",
    ssoClientSecret: "Client Secret",
    ssoRedirectUri: "Redirect URI",
    ssoScopes: "Scopes",
    ssoModePasswordOnly: "Только локальные учётные данные",
    ssoModeSsoOnly: "Только SSO",
    ssoModeBoth: "Локально + SSO",
    ssoIssuerHint: "Полный URL OIDC issuer вашего провайдера.",
    ssoClientIdHint: "Public client ID вашей OIDC интеграции.",
    ssoClientSecretHint: "Секрет для токен endpoint провайдера.",
    ssoRedirectHint: "Обычно это CleanArr public URL + /api/auth/sso/callback.",
    ssoScopesHint: "Дополнительный список scope (необязательно).",
    ssoFieldDisabledHint: "SSO поля отключены в режиме только локальной авторизации.",
    webhookMessageLabel: "Сообщение:",
    webhookPayloadEventsLabel: "Событий в payload:",
    webhookNotificationLabel: "Уведомление:",
    webhookResultStatusLabel: "Результат обработки:",
    reasonLabel: "причина:",
    ssoModePasswordOnlyHint: "Только локальные учётные данные. Поля SSO отключены.",
    ssoModeSsoOnlyHint: "Только внешняя аутентификация через OIDC.",
    ssoModeBothHint: "Локальная и SSO авторизация включены.",
    add: "Добавить",
    edit: "Изменить",
    test: "Проверить",
    next: "Далее",
    back: "Назад",
    skipForNow: "Пропустить пока",
    done: "Готово",
    enabled: "Включено",
    runtimeTarget: "Использовать как основной сервис",
    displayName: "Отображаемое имя",
    baseUrl: "Базовый URL",
    alreadyConfigured: "Уже настроено",
    beforeYouSave: "Перед сохранением",
    beforeSaveDescription: "Укажите URL и учётные данные сервиса, затем запустите проверку. До включения рабочего режима результат должен быть успешным.",
    webhook: "Webhook",
    notConfigured: "Не настроено",
    healthy: "Доступен",
    unreachable: "Недоступен",
    noStatus: "Нет статуса",
    none: "Нет",
    active: "активных",
    recent: "недавних",
    dismiss: "Скрыть",
    progress: "прогресс",
    actions: "действий",
    deletion: "удаление",
    unexpectedRequestError: "Неожиданная ошибка запроса",
    unknownError: "Неизвестная ошибка",
    passwordsDoNotMatch: "Пароли не совпадают.",
    adminCreated: "Администратор создан. Настройте сервисы в мастере настройки.",
    signedIn: "Вход выполнен.",
    deletionStarted: "Удаление запущено в фоне.",
    backgroundRefreshFailed: "Не удалось обновить фоновые задачи",
    serviceUpdated: "обновлён",
    serviceAdded: "добавлен",
    serviceRemoved: "удалён",
    runtimeSettingsSummary: "Параметры приложения: журналирование, HTTP-таймаут, срок хранения событий, язык метаданных, SSO и токен webhook.",
    jellyfinLanguageHint: "Используется при запросе названий сериалов и фильмов из метаданных Jellyfin.",
    uiLanguageHint: "Изменяет язык интерфейса CleanArr.",
    runtimeSettingsDescription: "Изменения сохраняются и сразу применяются к работающему приложению.",
    recommendedFirstRun: "Рекомендуемые настройки первого запуска",
    recommendedDryRun: "Оставьте тестовый режим включённым, пока не проверите все интеграции.",
    httpTimeoutHint: "Увеличивайте только если сервисы Arr отвечают слишком медленно.",
    retentionHint: "Более старые события удаляются из базы данных SQLite.",
    closeAndRefresh: "Закройте это окно и обновите конфигурацию.",
    keepDryRun: "Оставить CleanArr в тестовом режиме",
    oneDay: "1 день",
    sevenDays: "7 дней",
    thirtyDays: "30 дней",
    ninetyDays: "90 дней",
    oneYear: "1 год",
    serviceRadarrDescription: "Сервис поиска и удаления фильмов.",
    serviceSonarrDescription: "Сервис поиска и удаления сериалов, сезонов и эпизодов.",
    serviceJellyseerrDescription: "Сервис очистки запросов и обращений.",
    serviceDownloaderDescription: "Загрузчик для удаления торрентов вместе с файлами.",
    serviceJellyfinDescription: "Медиасервер для просмотра библиотеки и немедленного удаления элементов.",
    apiKey: "API-ключ",
    exampleUrl: "Пример URL",
    reverseProxyHint: "Поддерживаются пути через обратный прокси.",
    serviceUrlHint: "Укажите только URL сервиса. CleanArr автоматически добавит правильный путь API.",
    downloaderUrlHint: "Укажите только URL веб-интерфейса qBittorrent. CleanArr автоматически уберёт /api/v2.",
    radarrApiHint: "Radarr → Настройки → Общие → Безопасность → API Key.",
    sonarrApiHint: "Sonarr → Настройки → Общие → Безопасность → API Key.",
    jellyseerrApiHint: "Jellyseerr → Настройки → Общие → API Key.",
    downloaderUsernameHint: "Используйте имя пользователя от веб-интерфейса qBittorrent.",
    downloaderPasswordHint: "Используйте пароль от веб-интерфейса qBittorrent.",
    jellyfinApiHint: "Jellyfin → Панель управления → API Keys → + → создайте ключ для CleanArr.",
    firstTimeSetup: "Первичная настройка — подключите необходимые сервисы.",
    autoConfigureWebhook: "Настроить webhook автоматически",
    autoConfigureWebhookDescription: "CleanArr автоматически настроит плагин Webhook в Jellyfin. Плагин должен быть заранее установлен.",
    connectJellyfinFirst: "Сначала подключите сервер Jellyfin, затем настройте webhook.",
    setWebhookTokenFirst: "Сначала задайте токен webhook в настройках приложения — он будет добавлен в конфигурацию плагина.",
    configuring: "Настройка…",
    configured: "Настроено",
    installJellyfinWebhook: "Установите плагин Webhook для Jellyfin",
    installJellyfinWebhookDescription: "Jellyfin → Панель управления → Плагины → Каталог → найдите Webhook → установите → при необходимости перезапустите Jellyfin.",
    jellyfinInstallStep1: "Откройте Jellyfin → Панель управления → Каталог.",
    jellyfinInstallStep2: "Найдите плагин Webhook и установите его.",
    jellyfinInstallStep3: "Перезапустите Jellyfin, если этого потребует менеджер плагинов.",
    jellyfinInstallStep4: "После перезапуска откройте Jellyfin → Панель управления → Плагины → Webhook.",
    verifyDelivery: "Проверка доставки",
    verifyDeliveryDescription: "CleanArr сохраняет каждую попытку webhook, поэтому доставку можно проверить без реального удаления.",
    deliveryStatus: "Статус доставки",
    lastAttempt: "Последняя попытка",
    httpStatus: "Статус HTTP",
    lastItem: "Последний элемент",
    notReceivedYet: "Пока не получено",
    noItemReceived: "Элементы пока не получены",
    processing: "Обработка",
    latestWebhookAttempt: "Последняя попытка webhook",
    noJellyfinWebhook: "Webhook из Jellyfin ещё не поступал в CleanArr.",
    smokeTestCurl: "Проверочный запрос (cURL)",
    tokenPrefilled: "токен уже подставлен",
    configureTokenFirst: "сначала настройте токен",
    smokeTestDescription: "Отправляет синтетическое событие ItemDeleted в CleanArr. Используйте его для проверки сети и токена до реального удаления.",
    copyCurl: "Копировать cURL",
    generalSetupStep1: "Оставьте CleanArr в тестовом режиме, пока все проверки сервисов не будут успешными.",
    generalSetupStep2: "Задайте токен webhook. Jellyfin должен отправлять его в заголовке X-Webhook-Token.",
    generalSetupStep3: "Включайте рабочий режим только после настройки всех внешних сервисов.",
    tryDifferentSearch: "Попробуйте изменить поисковый запрос.",
    noSeriesSetup: "Sonarr не вернул сериалов. Сначала настройте Sonarr.",
    noMoviesSetup: "Radarr не вернул фильмов. Сначала настройте Radarr.",
    onDisk: "На диске",
    noFile: "Файла нет",
    episodes: "эпизодов",
    seasons: "сезонов",
    dryRunNoChanges: "Реальные изменения не выполняются.",
    seasonOfSeries: "Сезон {{season}} сериала {{series}}",
    movie: "Фильм",
    item: "Элемент",
    webhookReceived: "Webhook получен",
    tokenMismatch: "Токен не совпадает",
    payloadRejected: "Данные отклонены",
    noDeliveryYet: "Доставок пока нет",
    partialFailure: "Частичная ошибка",
    success: "Успешно",
    failed: "Ошибка",
    deleted: "Удалено",
    queued: "В очереди",
    running: "Выполняется",
    completed: "Завершено",
    skipped: "Пропущено",
    unknown: "Неизвестно",
  },
}

const FALLBACK_UI_TEXTS: Record<string, Partial<UiTextMap>> = {
  de: { series: "Serien", movies: "Filme", deleteSeries: "Serie löschen", deleteItem: "Film löschen" },
  fr: { series: "Séries", movies: "Films", deleteSeries: "Supprimer la série", deleteItem: "Supprimer le film" },
  es: { series: "Series", movies: "Películas", deleteSeries: "Eliminar serie", deleteItem: "Eliminar película" },
  it: { series: "Serie", movies: "Film", deleteSeries: "Elimina serie", deleteItem: "Elimina film" },
  pt: { series: "Séries", movies: "Filmes", deleteSeries: "Eliminar série", deleteItem: "Eliminar filme" },
  tr: { series: "Diziler", movies: "Filmler", deleteSeries: "Diziyi sil", deleteItem: "Filmi sil" },
  pl: { series: "Seriale", movies: "Filmy", deleteSeries: "Usuń serial", deleteItem: "Usuń film" },
  uk: { series: "Серіали", movies: "Фільми", deleteSeries: "Видалити серіал", deleteItem: "Видалити фільм" },
  cs: { series: "Seriály", movies: "Filmy", deleteSeries: "Smazat seriál", deleteItem: "Smazat film" },
  zh: { series: "剧集", movies: "电影", deleteSeries: "删除剧集", deleteItem: "删除电影" },
  ja: { series: "シリーズ", movies: "映画", deleteSeries: "シリーズを削除", deleteItem: "映画を削除" },
}

const DEFAULT_UI_LANG = "en"

function resolveUiLanguage(value: string | null | undefined): string {
  if (!value) return DEFAULT_UI_LANG
  return value.trim().replace("_", "-").toLowerCase().split("-", 1)[0]
}

function getUiText(value: string | null | undefined): UiTextMap {
  const language = resolveUiLanguage(value)
  const languageOverride = UI_TEXTS[language] ?? FALLBACK_UI_TEXTS[language] ?? {}
  const translations = { ...UI_TEXTS[DEFAULT_UI_LANG], ...languageOverride }
  return translations as UiTextMap
}

function getServiceDescription(family: ServiceFamily, text: UiTextMap): string {
  switch (family) {
    case "radarr": return text.serviceRadarrDescription
    case "sonarr": return text.serviceSonarrDescription
    case "jellyseerr": return text.serviceJellyseerrDescription
    case "downloaders": return text.serviceDownloaderDescription
    case "jellyfin_server": return text.serviceJellyfinDescription
  }
}

function getServiceHelp(meta: ServiceMeta, text: UiTextMap): string[] {
  return [`${text.exampleUrl}: ${meta.example}`, text.reverseProxyHint]
}

function getServiceFieldLabel(
  key: ServiceMeta["fields"][number]["key"],
  text: UiTextMap,
): string {
  if (key === "username") return text.username
  if (key === "password") return text.password
  return text.apiKey
}

function getServiceFieldHint(
  family: ServiceFamily,
  key: ServiceMeta["fields"][number]["key"],
  text: UiTextMap,
): string {
  if (key === "username") return text.downloaderUsernameHint
  if (key === "password") return text.downloaderPasswordHint
  switch (family) {
    case "radarr": return text.radarrApiHint
    case "sonarr": return text.sonarrApiHint
    case "jellyseerr": return text.jellyseerrApiHint
    case "jellyfin_server": return text.jellyfinApiHint
    case "downloaders": return text.apiKey
  }
}

function getStatusLabel(status: string, text: UiTextMap): string {
  switch (status.toLowerCase()) {
    case "partial_failure": return text.partialFailure
    case "success": return text.success
    case "failed": return text.failed
    case "deleted": return text.deleted
    case "queued": return text.queued
    case "running": return text.running
    case "completed": return text.completed
    case "skipped": return text.skipped
    case "healthy": return text.healthy
    case "unreachable": return text.unreachable
    case "unconfigured": return text.notConfigured
    default: return status || text.unknown
  }
}

function getItemTypeLabel(itemType: string, text: UiTextMap): string {
  switch (itemType.toLowerCase()) {
    case "movie": return text.movie
    case "series": return text.series
    case "season": return text.season
    default: return itemType || text.item
  }
}

const SSO_MODE_OPTIONS: Array<{
  value: SsoAuthMode
  labelKey: "ssoModePasswordOnly" | "ssoModeSsoOnly" | "ssoModeBoth"
  hintKey: "ssoModePasswordOnlyHint" | "ssoModeSsoOnlyHint" | "ssoModeBothHint"
}> = [
  { value: "password_only", labelKey: "ssoModePasswordOnly", hintKey: "ssoModePasswordOnlyHint" },
  { value: "sso_only", labelKey: "ssoModeSsoOnly", hintKey: "ssoModeSsoOnlyHint" },
  { value: "both", labelKey: "ssoModeBoth", hintKey: "ssoModeBothHint" },
]

// ─── Main component ───────────────────────────────────────────────────────────

function CleanArrApp() {
  const [dashboard, setDashboard] = useState<DashboardPayload | null>(null)
  const [config, setConfig] = useState<RuntimeConfigPayload | null>(null)
  const [authStatus, setAuthStatus] = useState<AuthStatusPayload | null>(null)
  const [isDashboardLoading, setIsDashboardLoading] = useState(true)
  const [isConfigLoading, setIsConfigLoading] = useState(false)
  const [isAuthLoading, setIsAuthLoading] = useState(true)
  const [isAuthSubmitting, setIsAuthSubmitting] = useState(false)
  const [isSsoSubmitting, setIsSsoSubmitting] = useState(false)
  const [activityFilter, setActivityFilter] = useState("")
  const [authMode, setAuthMode] = useState<AuthMode>("login")
  const [showWizard, setShowWizard] = useState(false)
  const [activeTab, setActiveTab] = useState<MainTab>("dashboard")
  const [authForm, setAuthForm] = useState({ username: "", password: "", confirmPassword: "" })
  const [ssoError, setSsoError] = useState<string | null>(null)
  const [generalModalOpen, setGeneralModalOpen] = useState(false)
  const [serviceModal, setServiceModal] = useState<ServiceModalState | null>(null)
  const [sessionToken, setSessionToken] = useState(() => readSessionCookie())
  const hasAutoNavigated = useRef(false)

  const [library, setLibrary] = useState<LibrarySeriesResponse | null>(null)
  const [isLibraryLoading, setIsLibraryLoading] = useState(false)
  const [libraryMovies, setLibraryMovies] = useState<LibraryMoviesResponse | null>(null)
  const [isLibraryMoviesLoading, setIsLibraryMoviesLoading] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<LibraryDeleteTarget | null>(null)
  const [isStartingDelete, setIsStartingDelete] = useState(false)
  const [deleteError, setDeleteError] = useState<string | null>(null)
  const [deleteJobs, setDeleteJobs] = useState<ManualDeleteJob[]>([])
  const knownDeleteJobStates = useRef(new Map<string, ManualDeleteJob["status"]>())
  const hasLoadedDeleteJobs = useRef(false)
  const deleteJobsPollFailed = useRef(false)

  const deferredFilter = useDeferredValue(activityFilter)
  const uiLanguage = useMemo(
    () => resolveUiLanguage(config?.general.ui_language ?? authStatus?.ui_language),
    [authStatus?.ui_language, config?.general.ui_language],
  )
  const uiText = useMemo(() => getUiText(uiLanguage), [uiLanguage])

  const fetchJson = useCallback(
    async <T,>(url: string, init?: RequestInit): Promise<T> => {
      const headers = new Headers(init?.headers)
      headers.set("Accept", "application/json")
      if (init?.body && !headers.has("Content-Type")) {
        headers.set("Content-Type", "application/json")
      }
      if (sessionToken) {
        headers.set("Authorization", `Bearer ${sessionToken}`)
      }

      const response = await fetch(url, { ...init, headers })

      if (!response.ok) {
        if (
          (response.status === 401 || response.status === 403) &&
          url.startsWith("/api/config")
        ) {
          setSessionToken("")
        }
        let message = response.statusText || `HTTP ${response.status}`
        try {
          const body = await response.json()
          if (typeof body.detail === "string") {
            message = body.detail
          } else if (Array.isArray(body.detail) && body.detail.length > 0) {
            message = (body.detail as Array<{ msg?: string; message?: string }>)
              .map((e) => e.msg ?? e.message ?? JSON.stringify(e))
              .join("; ")
          } else if (typeof body.message === "string") {
            message = body.message
          }
        } catch {
          // JSON parse failed — try raw text
          try {
            const text = await response.text()
            if (text) message = text
          } catch {
            // keep statusText
          }
        }
        throw new Error(message)
      }

      if (response.status === 204) {
        return undefined as T
      }

      return (await response.json()) as T
    },
    [sessionToken],
  )

  const loadDashboard = useCallback(
    async (background = false) => {
      if (!background) {
        setIsDashboardLoading(true)
      }
      try {
        const payload = await fetchJson<DashboardPayload>("/api/dashboard")
        setDashboard(payload)
      } catch (error) {
        toast.error(normalizeError(error))
      } finally {
        setIsDashboardLoading(false)
      }
    },
    [fetchJson],
  )

  const loadAuth = useCallback(async () => {
    setIsAuthLoading(true)
    try {
      const payload = await fetchJson<AuthStatusPayload>("/api/auth/status")
      setAuthStatus(payload)
      setAuthMode(payload.requires_registration ? "register" : "login")
      if (!payload.authenticated) {
        setConfig(null)
      }
    } catch (error) {
      toast.error(normalizeError(error))
    } finally {
      setIsAuthLoading(false)
    }
  }, [fetchJson])

  const loadConfig = useCallback(async () => {
    setIsConfigLoading(true)
    try {
      const payload = await fetchJson<RuntimeConfigPayload>("/api/config")
      setConfig(payload)
    } catch (error) {
      setConfig(null)
      toast.error(normalizeError(error))
    } finally {
      setIsConfigLoading(false)
    }
  }, [fetchJson])

  const loadLibrary = useCallback(async () => {
    setIsLibraryLoading(true)
    try {
      const payload = await fetchJson<LibrarySeriesResponse>("/api/library/series")
      setLibrary(payload)
    } catch (error) {
      toast.error(normalizeError(error))
    } finally {
      setIsLibraryLoading(false)
    }
  }, [fetchJson])

  const loadLibraryMovies = useCallback(async () => {
    setIsLibraryMoviesLoading(true)
    try {
      const payload = await fetchJson<LibraryMoviesResponse>("/api/library/movies")
      setLibraryMovies(payload)
    } catch (error) {
      toast.error(normalizeError(error))
    } finally {
      setIsLibraryMoviesLoading(false)
    }
  }, [fetchJson])

  const loadDeleteJobs = useCallback(async () => {
    try {
      const payload = await fetchJson<ManualDeleteJobListResponse>("/api/actions/delete/jobs")
      setDeleteJobs(payload.jobs)
      deleteJobsPollFailed.current = false

      if (!hasLoadedDeleteJobs.current) {
        payload.jobs.forEach((job) => knownDeleteJobStates.current.set(job.id, job.status))
        hasLoadedDeleteJobs.current = true
        return
      }

      payload.jobs.forEach((job) => {
        const previousStatus = knownDeleteJobStates.current.get(job.id)
        const justFinished =
          previousStatus != null &&
          previousStatus !== job.status &&
          (job.status === "completed" || job.status === "failed")

        if (justFinished) {
          const name = job.item_name ?? job.item_type
          if (job.status === "failed" || job.result?.status === "partial_failure") {
            toast.error(`${name}: ${job.error ?? job.message}`)
          } else {
            toast.success(`${name}: background deletion completed.`)
          }
          void loadDashboard(true)
          if (job.item_type === "Movie") {
            void loadLibraryMovies()
          } else {
            void loadLibrary()
          }
        }

        knownDeleteJobStates.current.set(job.id, job.status)
      })
    } catch (error) {
      if (!deleteJobsPollFailed.current) {
        toast.error(`${uiText.backgroundRefreshFailed}: ${normalizeError(error)}`)
        deleteJobsPollFailed.current = true
      }
    }
  }, [fetchJson, loadDashboard, loadLibrary, loadLibraryMovies])

  const executeDelete = useCallback(async () => {
    if (!deleteTarget) return
    const target = deleteTarget
    setIsStartingDelete(true)
    setDeleteError(null)
    try {
      let body: Record<string, unknown>
      if (target.kind === "movie") {
        body = {
          item_type: "Movie",
          radarr_movie_id: target.radarr_movie_id,
          jellyfin_item_id: target.jellyfin_movie_id ?? null,
        }
      } else {
        body = {
          item_type: target.item_type,
          sonarr_series_id: target.sonarr_series_id,
          season_number: target.season_number ?? null,
          jellyfin_item_id: target.jellyfin_item_id ?? null,
        }
      }
      const job = await fetchJson<ManualDeleteJob>("/api/actions/delete/jobs", {
        method: "POST",
        body: JSON.stringify(body),
      })
      knownDeleteJobStates.current.set(job.id, job.status)
      hasLoadedDeleteJobs.current = true
      setDeleteJobs((current) => [job, ...current.filter((item) => item.id !== job.id)])
      setDeleteTarget(null)
      toast.success(uiText.deletionStarted)
    } catch (error) {
      setDeleteError(normalizeError(error))
    } finally {
      setIsStartingDelete(false)
    }
  }, [deleteTarget, fetchJson])

  const dismissDeleteJob = useCallback(
    async (jobId: string) => {
      try {
        await fetchJson<void>(`/api/actions/delete/jobs/${jobId}`, { method: "DELETE" })
        knownDeleteJobStates.current.delete(jobId)
        setDeleteJobs((current) => current.filter((job) => job.id !== jobId))
      } catch (error) {
        toast.error(normalizeError(error))
      }
    },
    [fetchJson],
  )

  // Auto-polls
  useEffect(() => {
    void loadDashboard()
    const id = window.setInterval(() => void loadDashboard(true), 15000)
    return () => window.clearInterval(id)
  }, [loadDashboard])

  useEffect(() => {
    void loadAuth()
  }, [loadAuth])

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const message = params.get("sso_error")
    if (message) {
      setSsoError(message)
      window.history.replaceState({}, "", "/")
    }
  }, [])

  useEffect(() => {
    if (typeof document === "undefined") return
    document.documentElement.lang = uiLanguage
  }, [uiLanguage])

  const hasActiveDeleteJobs = deleteJobs.some(
    (job) => job.status === "queued" || job.status === "running",
  )

  useEffect(() => {
    if (!authStatus?.authenticated) return
    void loadDeleteJobs()
    const id = window.setInterval(
      () => void loadDeleteJobs(),
      hasActiveDeleteJobs ? 1000 : 5000,
    )
    return () => window.clearInterval(id)
  }, [authStatus?.authenticated, hasActiveDeleteJobs, loadDeleteJobs])

  useEffect(() => {
    if (authStatus?.authenticated) {
      void loadConfig()
    } else if (authStatus && !authStatus.authenticated) {
      setConfig(null)
    }
  }, [authStatus, loadConfig])

  useEffect(() => {
    if (activeTab === "library" && authStatus?.authenticated) {
      void loadLibrary()
      void loadLibraryMovies()
    }
  }, [activeTab, authStatus?.authenticated, loadLibrary, loadLibraryMovies])

  // Persist session token to cookie
  useEffect(() => {
    if (sessionToken) {
      writeSessionCookie(sessionToken)
    }
  }, [sessionToken])

  const setupCompletionCount = useMemo(
    () => SETUP_STEPS.reduce((n, step) => n + (isSetupStepReady(step.id, config) ? 1 : 0), 0),
    [config],
  )

  // Auto-navigate to Dashboard once setup is fully complete (one-time)
  useEffect(() => {
    if (!hasAutoNavigated.current && config && setupCompletionCount === SETUP_STEPS.length) {
      hasAutoNavigated.current = true
      setActiveTab("dashboard")
    }
  }, [config, setupCompletionCount])

  const origin =
    typeof window === "undefined"
      ? "https://cleanarr.neelov.family"
      : window.location.origin
  const samplePayloadPreview = JSON.stringify(dashboard?.sample_payload ?? {}, null, 2)
  const webhookToken = config?.general.webhook_shared_token
  const curlPreview = [
    `curl -X POST ${origin}/webhook/jellyfin \\`,
    '  -H "Content-Type: application/json" \\',
    webhookToken
      ? `  -H "X-Webhook-Token: ${webhookToken}" \\`
      : '  -H "X-Webhook-Token: <configure_token_first>" \\',
    `  -d '${samplePayloadPreview.replaceAll("\n", "\n  ")}'`,
  ].join("\n")

  const handleSetupWebhook = useCallback(
    async (webhookUrl: string) => {
      return await fetchJson<{ found: boolean; configured: boolean; message: string }>(
        "/api/config/jellyfin/setup-webhook",
        { method: "POST", body: JSON.stringify({ webhook_url: webhookUrl }) },
      )
    },
    [fetchJson],
  )

  const filteredActivity = useMemo(
    () => (dashboard?.recent_activity ?? []).filter((e) => matchesActivity(e, deferredFilter)),
    [dashboard?.recent_activity, deferredFilter],
  )

  const filteredWebhookAttempts = useMemo(
    () =>
      (dashboard?.webhook_attempts ?? []).filter((attempt) =>
        matchesWebhookAttempt(attempt, deferredFilter),
      ),
    [dashboard?.webhook_attempts, deferredFilter],
  )

  const allServicesConfigured = SERVICE_FAMILIES.every((f) =>
    Boolean(resolveActiveService(getServices(config, f))),
  )

  const deletedActions = (dashboard?.recent_activity ?? []).reduce(
    (n, e) => n + (e.action_summary.deleted ?? 0),
    0,
  )

  const latestActivity = dashboard?.recent_activity[0] ?? null

  const submitAuthForm = async () => {
    if (authMode === "register" && authForm.password !== authForm.confirmPassword) {
      toast.error(uiText.passwordsDoNotMatch)
      return
    }
    setIsAuthSubmitting(true)
    try {
      const payload = await fetchJson<AuthSessionPayload>(
        authMode === "register" ? "/api/auth/register" : "/api/auth/login",
        {
          method: "POST",
          body: JSON.stringify({ username: authForm.username, password: authForm.password }),
        },
      )
      setSessionToken(payload.token)
      setAuthForm({ username: payload.username, password: "", confirmPassword: "" })
      setActiveTab("dashboard")
      if (authMode === "register") {
        setShowWizard(true)
      }
      toast.success(
        authMode === "register" ? uiText.adminCreated : uiText.signedIn,
      )
    } catch (error) {
      toast.error(normalizeError(error))
    } finally {
      setIsAuthSubmitting(false)
    }
  }

  const startSsoAuth = async () => {
    if (isSsoSubmitting || authStatus?.sso_mode === "password_only" || !authStatus?.sso_configured) return
    setIsSsoSubmitting(true)
    setSsoError(null)
    try {
      const payload = await fetchJson<SSOLoginPayload>("/api/auth/sso/start")
      window.location.assign(payload.authorize_url)
    } catch (error) {
      toast.error(normalizeError(error))
      setSsoError(normalizeError(error))
    } finally {
      setIsSsoSubmitting(false)
    }
  }

  const logout = async () => {
    try {
      await fetchJson<void>("/api/auth/logout", { method: "POST" })
    } catch {
      // Session might already be invalid; local reset is enough.
    }
    setSessionToken("")
    setAuthStatus(null)
    setSsoError(null)
    setAuthForm({ username: "", password: "", confirmPassword: "" })
    setDeleteJobs([])
    knownDeleteJobStates.current.clear()
    hasLoadedDeleteJobs.current = false
  }

  const saveGeneralSettings = async (payload: GeneralConfig) => {
    const next = await fetchJson<RuntimeConfigPayload>("/api/config/general", {
      method: "PUT",
      body: JSON.stringify(payload),
    })
    setConfig(next)
    toast.success(uiText.runtimeSettingsSaved)
  }

  const saveServiceDraft = async (family: ServiceFamily, draft: ServiceDraft) => {
    const meta = SERVICE_META[family]
    const body = JSON.stringify(buildServicePayload(family, draft))
    const next = draft.id
      ? await fetchJson<RuntimeConfigPayload>(`${meta.endpoint}/${draft.id}`, { method: "PUT", body })
      : await fetchJson<RuntimeConfigPayload>(meta.endpoint, { method: "POST", body })
    setConfig(next)
    setServiceModal(null)
    toast.success(`${meta.title} ${draft.id ? uiText.serviceUpdated : uiText.serviceAdded}.`)
  }

  const deleteServiceDraft = async (family: ServiceFamily, serviceId: string) => {
    const meta = SERVICE_META[family]
    await fetchJson<void>(`${meta.endpoint}/${serviceId}`, { method: "DELETE" })
    const next = await fetchJson<RuntimeConfigPayload>("/api/config")
    setConfig(next)
    setServiceModal(null)
    toast.success(`${meta.title} ${uiText.serviceRemoved}.`)
  }

  const testServiceDraft = async (family: ServiceFamily, draft: ServiceDraft) => {
    const meta = SERVICE_META[family]
    return fetchJson<ConnectionTestResponse>(`${meta.endpoint}/test`, {
      method: "POST",
      body: JSON.stringify(buildServicePayload(family, draft)),
    })
  }

  // ─── Loading / auth gates ──────────────────────────────────────────────────

  if (isAuthLoading && !authStatus) {
    return <AuthScreenSkeleton />
  }

  if (!authStatus?.authenticated) {
    return (
      <AuthScreen
        authMode={authMode}
        authForm={authForm}
        text={uiText}
        isSubmitting={isAuthSubmitting}
        isSsoSubmitting={isSsoSubmitting}
        requiresRegistration={Boolean(authStatus?.requires_registration)}
        localAuthEnabled={Boolean(authStatus?.requires_registration) || authStatus?.sso_mode !== "sso_only"}
        ssoMode={authStatus?.sso_mode ?? "password_only"}
        ssoConfigured={Boolean(authStatus?.sso_configured)}
        hasSsoError={Boolean(ssoError)}
        ssoError={ssoError}
        onFieldChange={(field, value) => setAuthForm((c) => ({ ...c, [field]: value }))}
        onSubmit={() => void submitAuthForm()}
        onSsoSubmit={() => void startSsoAuth()}
      />
    )
  }

  // Derive from config first (updated immediately after save), fall back to dashboard (polled)
  const isLive = config != null ? !config.general.dry_run : dashboard ? !dashboard.service.dry_run : false

  // ─── Main app ──────────────────────────────────────────────────────────────

  return (
    <Tabs
      value={activeTab}
      onValueChange={(v) => setActiveTab(v as MainTab)}
      className="flex min-h-screen flex-col"
    >
      {/* Sticky navigation header */}
      <header className="sticky top-0 z-50 border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
        <div className="mx-auto flex max-w-6xl items-center gap-3 px-4 py-2.5 sm:px-6">
          {/* Brand */}
          <div className="shrink-0">
            <CleanArrBrand size="sm" />
          </div>

          <div className="h-5 w-px bg-border" />

          {/* Navigation */}
          <TabsList>
            <TabsTrigger value="dashboard" className="gap-1.5">
              <LayoutDashboard className="size-3.5 text-blue-500" />
              {uiText.dashboard}
            </TabsTrigger>
            <TabsTrigger value="settings" className="gap-1.5">
              <Settings2 className="size-3.5 text-orange-500" />
              {uiText.settings}
            </TabsTrigger>
            <TabsTrigger value="activity" className="gap-1.5">
              <Activity className="size-3.5 text-emerald-500" />
              {uiText.activity}
            </TabsTrigger>
            <TabsTrigger value="library" className="gap-1.5">
              <Library className="size-3.5 text-violet-500" />
              {uiText.library}
            </TabsTrigger>
          </TabsList>

          {/* Right side */}
          <div className="ml-auto flex items-center gap-2">
            {dashboard && (
              <div
                className={cn(
                  "flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium",
                isLive
                  ? "border-green-200 bg-green-50 text-green-800 dark:border-green-900 dark:bg-green-950/40 dark:text-green-200"
                  : "border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-200",
                )}
              >
                <span
                  className={cn(
                    "size-1.5 rounded-full",
                    isLive ? "bg-green-500" : "bg-amber-500",
                  )}
                />
                {isLive ? uiText.live : uiText.dryRun}
              </div>
            )}

            <ThemeToggle />

            <div className="flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs text-muted-foreground">
              <UserRound className="size-3.5" />
              {authStatus.username}
            </div>

            <Button
              variant="ghost"
              size="icon"
              className="size-8"
              onClick={() => void logout()}
              title={uiText.logOut}
            >
              <LogOut className="size-4 text-red-500 dark:text-red-400" />
            </Button>
          </div>
        </div>
      </header>

      {/* Page content */}
      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-6 sm:px-6">
        {/* ── Dashboard ── */}
        <TabsContent value="dashboard" className="mt-0">
          <DashboardPanel
            text={uiText}
            dashboard={dashboard}
            isDashboardLoading={isDashboardLoading}
            setupCompletionCount={setupCompletionCount}
            deletedActions={deletedActions}
            latestActivity={latestActivity}
            allServicesConfigured={allServicesConfigured}
            isLive={isLive}
            onToggleDryRun={async () => {
              if (config) await saveGeneralSettings({ ...config.general, dry_run: !config.general.dry_run })
            }}
            onOpenWizard={() => setShowWizard(true)}
            onEditService={(name) => {
              const family = DASHBOARD_NAME_TO_FAMILY[name]
              if (!family) return
              const services = getServices(config, family)
              const active = resolveActiveService(services)
              if (active) {
                setServiceModal({ family, draft: toDraft(active) })
              } else {
                setServiceModal({ family, draft: structuredClone(EMPTY_DRAFTS[family]) })
              }
            }}
          />
        </TabsContent>

        {/* ── Settings ── */}
        <TabsContent value="settings" className="mt-0">
          <SettingsPanel
            text={uiText}
            config={config}
            isConfigLoading={isConfigLoading}
            onSaveGeneral={saveGeneralSettings}
          />
        </TabsContent>

        {/* ── Activity ── */}
        <TabsContent value="activity" className="mt-0">
          <ActivityPanel
            text={uiText}
            filteredActivity={filteredActivity}
            webhookAttempts={filteredWebhookAttempts}
            activityFilter={activityFilter}
            onFilterChange={setActivityFilter}
          />
        </TabsContent>

        {/* ── Library ── */}
        <TabsContent value="library" className="mt-0">
          <LibraryPanel
            text={uiText}
            library={library}
            isLibraryLoading={isLibraryLoading}
            libraryMovies={libraryMovies}
            isLibraryMoviesLoading={isLibraryMoviesLoading}
            isLive={isLive}
            onRefreshSeries={() => void loadLibrary()}
            onRefreshMovies={() => void loadLibraryMovies()}
            onDelete={(target) => {
              setDeleteTarget(target)
              setDeleteError(null)
            }}
          />
        </TabsContent>
      </main>

      {/* ── Setup wizard overlay ── */}
      {showWizard && (
        <SetupWizard
          text={uiText}
          config={config}
          dashboard={dashboard}
          origin={origin}
          curlPreview={curlPreview}
          onSaveGeneral={saveGeneralSettings}
          onSaveService={saveServiceDraft}
          onTestService={testServiceDraft}
          onSetupWebhook={handleSetupWebhook}
          onClose={() => setShowWizard(false)}
        />
      )}

      {/* Modals */}
      <GeneralSettingsModal
        open={generalModalOpen}
        text={uiText}
        config={config?.general ?? null}
        onClose={() => setGeneralModalOpen(false)}
        onSave={async (payload) => {
          await saveGeneralSettings(payload)
          setGeneralModalOpen(false)
        }}
      />

      <ServiceModal
        state={serviceModal}
        text={uiText}
        onClose={() => setServiceModal(null)}
        onSave={saveServiceDraft}
        onDelete={deleteServiceDraft}
        onTest={testServiceDraft}
        jellyfinSetupProps={serviceModal?.family === "jellyfin_server" ? {
          dashboard,
          origin,
          curlPreview,
          tokenConfigured: Boolean(config?.general.webhook_shared_token),
          onSetupWebhook: handleSetupWebhook,
        } : undefined}
      />

      <DeleteConfirmModal
        target={deleteTarget}
        text={uiText}
        isStarting={isStartingDelete}
        error={deleteError}
        isDryRun={!isLive}
        onConfirm={() => void executeDelete()}
        onClose={() => {
          setDeleteTarget(null)
          setDeleteError(null)
        }}
      />

      <BackgroundJobsPanel
        jobs={deleteJobs}
        text={uiText}
        onDismiss={(jobId) => void dismissDeleteJob(jobId)}
      />
    </Tabs>
  )
}

// ─── Auth screens ─────────────────────────────────────────────────────────────

function AuthScreen({
  authMode,
  authForm,
  text,
  isSubmitting,
  isSsoSubmitting,
  requiresRegistration,
  localAuthEnabled,
  ssoMode,
  ssoConfigured,
  hasSsoError,
  ssoError,
  onFieldChange,
  onSubmit,
  onSsoSubmit,
}: {
  authMode: AuthMode
  authForm: { username: string; password: string; confirmPassword: string }
  text: UiTextMap
  isSubmitting: boolean
  isSsoSubmitting: boolean
  requiresRegistration: boolean
  localAuthEnabled: boolean
  ssoMode: SsoAuthMode
  ssoConfigured: boolean
  hasSsoError: boolean
  ssoError: string | null
  onFieldChange: (field: "username" | "password" | "confirmPassword", value: string) => void
  onSubmit: () => void
  onSsoSubmit: () => void
}) {
  const showLocalAuth = requiresRegistration || localAuthEnabled
  const showSsoAuth = ssoMode !== "password_only"
  const authDescription = requiresRegistration
    ? text.firstLaunchCreateAdmin
    : showLocalAuth && showSsoAuth
      ? text.signInWithLocalOrSso
      : showLocalAuth
        ? text.signInWithLocalOnly
        : text.signInWithSso

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4 py-8">
      <div className="w-full max-w-sm space-y-6">
        <div className="flex justify-center">
          <CleanArrBrand size="lg" />
        </div>
      <Card className="w-full shadow-sm">
        <CardHeader className="space-y-1.5">
          <CardTitle className="flex items-center gap-2 text-xl">
            {requiresRegistration ? (
              <UserRoundPlus className="size-5 text-blue-600 dark:text-blue-400" />
            ) : (
              <KeyRound className="size-5 text-blue-600 dark:text-blue-400" />
            )}
            {requiresRegistration ? text.authTitleCreateAdmin : text.authTitleSignIn}
          </CardTitle>
          <CardDescription>
            {authDescription}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {hasSsoError && (
            <Alert variant="destructive">
              <CircleAlert className="size-4" />
              <AlertTitle>{text.ssoSignInError}</AlertTitle>
              <AlertDescription>{ssoError}</AlertDescription>
            </Alert>
          )}

          {showLocalAuth && (
            <>
              <FormField label={text.username} htmlFor="auth-username">
                <Input
                  id="auth-username"
                  value={authForm.username}
                  autoComplete="username"
                  onChange={(e) => onFieldChange("username", e.target.value)}
                />
              </FormField>

              <FormField label={text.password} htmlFor="auth-password">
                <Input
                  id="auth-password"
                  type="password"
                  value={authForm.password}
                  autoComplete="current-password"
                  onChange={(e) => onFieldChange("password", e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !requiresRegistration) onSubmit()
                  }}
                />
              </FormField>

              {requiresRegistration && (
                <FormField label={text.confirmPassword} htmlFor="auth-confirm">
                  <Input
                    id="auth-confirm"
                    type="password"
                    value={authForm.confirmPassword}
                    onChange={(e) => onFieldChange("confirmPassword", e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") onSubmit()
                    }}
                  />
                </FormField>
              )}

              <Button className="w-full" disabled={isSubmitting} onClick={onSubmit}>
                {isSubmitting ? (
                  <LoaderCircle className="size-4 animate-spin" />
                ) : authMode === "register" ? (
                  <UserRoundPlus className="size-4" />
                ) : (
                  <KeyRound className="size-4" />
                )}
                {authMode === "register" ? text.authTitleCreateAdmin : text.signInWithCredentials}
              </Button>
            </>
          )}

          {showSsoAuth && !requiresRegistration && (
            <div className="space-y-2">
              {showLocalAuth && (
                <div className="flex items-center gap-3 text-xs text-muted-foreground">
                  <div className="h-px flex-1 bg-border" />
                  <span>{text.orDivider}</span>
                  <div className="h-px flex-1 bg-border" />
                </div>
              )}
              <Button
                className="w-full"
                variant="outline"
                disabled={isSsoSubmitting || !ssoConfigured}
                onClick={onSsoSubmit}
                title={ssoConfigured ? text.continueWithSso : text.ssoNotConfigured}
              >
                {isSsoSubmitting ? (
                  <LoaderCircle className="size-4 animate-spin" />
                ) : (
                  <ShieldCheck className="size-4" />
                )}
                {isSsoSubmitting ? text.connecting : text.signInWithSso}
              </Button>
              {!ssoConfigured && (
                <p className="text-xs text-muted-foreground">
                  {text.configureSsoBefore}
                </p>
              )}
            </div>
          )}
          {!showLocalAuth && !showSsoAuth ? (
            <p className="rounded-md border border-dashed p-2 text-xs text-muted-foreground">
              {text.noAuthConfigured}
            </p>
          ) : null}
        </CardContent>
      </Card>
      </div>
    </div>
  )
}

function AuthScreenSkeleton() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4 py-8">
      <div className="w-full max-w-sm space-y-4 rounded-xl border p-6">
        <Skeleton className="h-7 w-32" />
        <Skeleton className="h-4 w-48" />
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-10 w-full" />
      </div>
    </div>
  )
}

// ─── Dashboard ────────────────────────────────────────────────────────────────

const DOWNSTREAM_META: Partial<Record<string, { icon: LucideIcon; color: string }>> = {
  Radarr: { icon: Film, color: "text-yellow-500" },
  Sonarr: { icon: Tv, color: "text-sky-500" },
  Jellyfin: { icon: Play, color: "text-purple-500" },
  Jellyseerr: { icon: Star, color: "text-orange-500" },
  Downloader: { icon: Download, color: "text-emerald-500" },
}

function getDashboardServiceRole(name: string, fallback: string, text: UiTextMap): string {
  switch (name) {
    case "Radarr": return text.serviceRadarrDescription
    case "Sonarr": return text.serviceSonarrDescription
    case "Jellyfin": return text.serviceJellyfinDescription
    case "Jellyseerr": return text.serviceJellyseerrDescription
    case "Downloader": return text.serviceDownloaderDescription
    default: return fallback
  }
}

function ServiceHealthCard({
  service,
  text,
  onEdit,
}: {
  service: { name: string; role: string; url: string; configured: boolean; health_status: HealthStatus }
  text: UiTextMap
  onEdit?: () => void
}) {
  const meta = DOWNSTREAM_META[service.name] ?? { icon: Server, color: "text-muted-foreground" }
  const Icon = meta.icon
  return (
    <div className={cn("rounded-xl border p-4 space-y-3", !service.configured && "opacity-60")}>
      <div className="flex items-start justify-between gap-2">
        <div className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-muted">
          <Icon className={cn("size-4", meta.color)} />
        </div>
        <div className="flex items-center gap-1.5">
          <StatusDot healthStatus={service.health_status} text={text} />
          <span
            className={cn(
              "text-xs capitalize",
              service.health_status === "healthy" && "text-green-600 dark:text-green-400",
              service.health_status === "unreachable" && "text-red-500",
              service.health_status === "unconfigured" && "text-muted-foreground",
            )}
          >
            {getStatusLabel(service.health_status, text)}
          </span>
          {onEdit && (
            <button
              type="button"
              onClick={onEdit}
              className="ml-1 rounded p-0.5 text-muted-foreground hover:text-foreground transition-colors"
              title={`${text.edit} ${service.name}`}
            >
              <PenSquare className="size-3.5" />
            </button>
          )}
        </div>
      </div>
      <div>
        <p className="text-sm font-semibold">{service.name}</p>
        <p className="text-xs text-muted-foreground">
          {getDashboardServiceRole(service.name, service.role, text)}
        </p>
      </div>
      {service.url ? (
        <code className="block truncate text-[11px] text-muted-foreground">{service.url}</code>
      ) : (
        <span className="text-[11px] text-muted-foreground italic">{text.notConfigured}</span>
      )}
    </div>
  )
}

function DashboardPanel({
  text,
  dashboard,
  isDashboardLoading,
  setupCompletionCount,
  deletedActions,
  latestActivity,
  allServicesConfigured,
  isLive,
  onToggleDryRun,
  onOpenWizard,
  onEditService,
}: {
  text: UiTextMap
  dashboard: DashboardPayload | null
  isDashboardLoading: boolean
  setupCompletionCount: number
  deletedActions: number
  latestActivity: DashboardActivity | null
  allServicesConfigured: boolean
  isLive: boolean
  onToggleDryRun: () => Promise<void>
  onOpenWizard: () => void
  onEditService: (name: string) => void
}) {
  const webhookStatus = dashboard?.webhook_status

  return (
    <section className="space-y-5">
      {/* Status bar */}
      <div
        className={cn(
          "flex flex-wrap items-center gap-x-5 gap-y-2 rounded-xl border-2 px-5 py-4",
          isLive
            ? "border-green-200/70 bg-green-50/40 dark:border-green-900/60 dark:bg-green-950/20"
            : "border-amber-200/70 bg-amber-50/40 dark:border-amber-900/60 dark:bg-amber-950/20",
        )}
      >
        <div className="flex items-center gap-3">
          {isLive ? (
            <Zap className="size-5 text-green-600 dark:text-green-400" />
          ) : (
            <ShieldAlert className="size-5 text-amber-600 dark:text-amber-400" />
          )}
          <div>
            <p className="text-sm font-semibold leading-tight">
              {isLive ? text.liveMode : text.dryRun}
            </p>
            <p className="text-xs text-muted-foreground">
              {isLive ? text.liveModeDescription : text.dryRunDescription}
            </p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 ml-auto">
          <span className="text-sm text-muted-foreground" title={text.setupCount}>
            {text.setup}{" "}
            <strong className="text-foreground">
              {setupCompletionCount}/{SETUP_STEPS.length}
            </strong>
          </span>
          <span className="text-sm text-muted-foreground">
            <strong className="text-foreground">{deletedActions}</strong> {text.deletionsLogged}
          </span>
          {!allServicesConfigured && (
            <Button variant="outline" size="sm" onClick={onOpenWizard}>
              <Zap className="size-4 text-blue-600 dark:text-blue-400" />
              {text.setupWizard}
            </Button>
          )}
          {/* Mode toggle */}
          <div className="flex items-center rounded-lg border bg-background p-0.5">
            <button
              onClick={() => isLive ? void onToggleDryRun() : undefined}
              className={cn(
                "flex items-center gap-1.5 rounded-md px-3 py-1 text-xs font-medium transition-colors",
                !isLive
                  ? "bg-amber-100 text-amber-800 dark:bg-amber-900/50 dark:text-amber-200"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              <ShieldAlert className="size-3.5" />
              {text.dryRun}
            </button>
            <button
              onClick={() => !isLive ? void onToggleDryRun() : undefined}
              className={cn(
                "flex items-center gap-1.5 rounded-md px-3 py-1 text-xs font-medium transition-colors",
                isLive
                  ? "bg-green-100 text-green-800 dark:bg-green-900/50 dark:text-green-200"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              <Zap className="size-3.5" />
              {text.live}
            </button>
          </div>
        </div>
      </div>

      {/* Connected services */}
      <div>
        <p className="mb-3 text-sm font-medium text-muted-foreground">{text.connectedServices}</p>
        {isDashboardLoading && !dashboard ? (
          <div className="grid gap-3 grid-cols-2 sm:grid-cols-3 lg:grid-cols-5">
            {Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} className="h-32 w-full rounded-xl" />
            ))}
          </div>
        ) : (
          <div className="grid gap-3 grid-cols-2 sm:grid-cols-3 lg:grid-cols-5">
            {(dashboard?.downstream ?? []).map((service) => (
              <ServiceHealthCard
                key={service.name}
                service={service}
                text={text}
                onEdit={() => onEditService(service.name)}
              />
            ))}
          </div>
        )}
      </div>

      {/* Webhook status + latest event */}
      <div className="grid gap-5 lg:grid-cols-2">
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-base">
              <Webhook className="size-4 text-violet-500" />
              {text.webhookStatus}
            </CardTitle>
            <CardDescription>{text.webhookStatusDescription}</CardDescription>
          </CardHeader>
          <CardContent>
            {webhookStatus?.attempted_at ? (
              <div className="space-y-2.5">
                <div className="flex items-center justify-between gap-2">
                  <StatusPill
                    tone={webhookStatus.outcome === "processed" ? "green" : "red"}
                    label={webhookStatus.outcome}
                  />
                  <span className="text-xs text-muted-foreground">
                    {new Date(webhookStatus.attempted_at).toLocaleString()}
                  </span>
                </div>
                <p className="text-sm">{webhookStatus.message}</p>
                {webhookStatus.item_name && (
                  <p className="text-xs text-muted-foreground">{webhookStatus.item_name}</p>
                )}
              </div>
            ) : (
              <EmptyState
                title={text.noWebhookReceived}
                description={text.sendWebhookForStatus}
              />
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-base">
              <Activity className="size-4 text-emerald-500" />
              {text.latestEvent}
            </CardTitle>
            <CardDescription>{text.latestEventDescription}</CardDescription>
          </CardHeader>
          <CardContent>
            {latestActivity ? (
              <div className="space-y-3">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                <p className="truncate text-sm font-medium">
                  {formatMediaTitle(latestActivity.result.item_type, latestActivity.result.name)}
                </p>
                    <p className="mt-0.5 text-xs text-muted-foreground">
                      {new Date(latestActivity.processed_at).toLocaleString()}
                    </p>
                  </div>
                  <StatusPill
                    tone={latestActivity.result.status === "partial_failure" ? "red" : "green"}
                    label={latestActivity.result.status}
                  />
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {Object.entries(latestActivity.action_summary).map(([k, v]) => (
                    <Badge key={k} variant="outline" className="text-xs">
                      {k}: {v}
                    </Badge>
                  ))}
                </div>
              </div>
            ) : (
            <EmptyState
                title={text.noActivity}
                description={text.noWebhookActivity}
              />
            )}
          </CardContent>
        </Card>
      </div>
    </section>
  )
}

// ─── Activity panel ───────────────────────────────────────────────────────────

function ActivityPanel({
  text,
  filteredActivity,
  webhookAttempts,
  activityFilter,
  onFilterChange,
}: {
  text: UiTextMap
  filteredActivity: DashboardActivity[]
  webhookAttempts: DashboardWebhookAttempt[]
  activityFilter: string
  onFilterChange: (v: string) => void
}) {
  const activityItems = useMemo(() => {
    const merged = [
      ...filteredActivity.map((entry) => ({
        kind: "processed_activity" as const,
        ...entry,
        sort_at: Date.parse(entry.processed_at),
      })),
      ...webhookAttempts.map((attempt) => ({
        kind: "webhook_attempt" as const,
        ...attempt,
        sort_at: Date.parse(attempt.attempted_at),
      })),
    ]
      .map((item) => ({ ...item, sort_at: Number.isNaN(item.sort_at) ? 0 : item.sort_at }))
      .sort((left, right) => right.sort_at - left.sort_at) as DashboardUnifiedActivityItem[]

    return merged
  }, [filteredActivity, webhookAttempts])

  const activityCount = activityItems.length

  return (
    <section className="space-y-4">
      <div className="flex items-center gap-3">
        <Input
          value={activityFilter}
          onChange={(e) => onFilterChange(e.target.value)}
          placeholder={text.filter}
          className="max-w-sm"
        />
        {activityFilter && (
          <Button variant="ghost" size="sm" onClick={() => onFilterChange("")}>
            {text.clear}
          </Button>
        )}
        <span className="ml-auto text-sm text-muted-foreground">
          {activityCount} {text.eventCount}
        </span>
      </div>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <Activity className="size-4 text-emerald-500" />
            {text.activityTimeline}
          </CardTitle>
          <CardDescription>{text.activityTimelineDescription}</CardDescription>
        </CardHeader>
        <CardContent>
          <ScrollArea className="h-[480px]">
            {activityItems.length === 0 ? (
              <EmptyState
                title={text.noActivity}
                description={
                  activityFilter
                    ? text.noActivityFiltered
                    : text.sendWebhookToSeeActivity
                }
              />
            ) : (
              <div className="space-y-2 p-px">
                {activityItems.map((item) =>
                  item.kind === "webhook_attempt" ? (
                    <WebhookAttemptEntry
                      key={`${item.kind}-${item.attempted_at}-${item.message}`}
                      attempt={item}
                      text={text}
                    />
                  ) : (
                    <ActivityEntry
                      key={`${item.kind}-${item.processed_at}-${item.result.item_id}`}
                      entry={item}
                      text={text}
                    />
                  ),
                )}
              </div>
            )}
          </ScrollArea>
        </CardContent>
      </Card>
    </section>
  )
}

// ─── Settings panel ───────────────────────────────────────────────────────────

function SsoConfigSection({
  draft,
  onDraftChange,
  namespace,
  isSecretVisible,
  onToggleSecretVisibility,
  text,
}: {
  draft: GeneralConfig
  namespace: "settings" | "wizard" | "general"
  onDraftChange: (next: GeneralConfig) => void
  isSecretVisible: boolean
  onToggleSecretVisibility: () => void
  text: UiTextMap
}) {
  const ssoEnabled = draft.sso_mode !== "password_only"

  const handleModeChange = (nextMode: SsoAuthMode) => {
    onDraftChange({
      ...draft,
      sso_mode: nextMode,
      sso_enabled: nextMode !== "password_only",
    })
  }

  return (
    <div className="space-y-3 border-t pt-4">
      <FormField label={text.ssoAuthMode} htmlFor={`${namespace}-sso-mode`}>
        <select
          id={`${namespace}-sso-mode`}
          value={draft.sso_mode}
          onChange={(e) => handleModeChange(e.target.value as SsoAuthMode)}
          className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-xs outline-none transition-[color,box-shadow] focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50"
        >
          {SSO_MODE_OPTIONS.map((mode) => (
            <option key={mode.value} value={mode.value}>
              {text[mode.labelKey]}
            </option>
          ))}
        </select>
        <FieldHint text={text[SSO_MODE_OPTIONS.find((mode) => mode.value === draft.sso_mode)?.hintKey ?? "ssoModeBothHint"]} />
      </FormField>

      <div className="grid gap-4 sm:grid-cols-2">
        <FormField label={text.ssoIssuer} htmlFor={`${namespace}-sso-issuer`}>
          <Input
            id={`${namespace}-sso-issuer`}
            type="url"
            value={draft.sso_issuer_url ?? ""}
            disabled={!ssoEnabled}
            onChange={(e) => onDraftChange({ ...draft, sso_issuer_url: e.target.value || null })}
            placeholder="https://id.example.com/realms/cleanarr"
          />
          <FieldHint text={text.ssoIssuerHint} />
        </FormField>

        <FormField label={text.ssoClientId} htmlFor={`${namespace}-sso-client-id`}>
          <Input
            id={`${namespace}-sso-client-id`}
            value={draft.sso_client_id ?? ""}
            disabled={!ssoEnabled}
            onChange={(e) => onDraftChange({ ...draft, sso_client_id: e.target.value || null })}
          />
          <FieldHint text={text.ssoClientIdHint} />
        </FormField>

        <FormField label={text.ssoClientSecret} htmlFor={`${namespace}-sso-client-secret`}>
          <div className="flex items-center gap-2">
            <Input
              id={`${namespace}-sso-client-secret`}
              type={isSecretVisible ? "text" : "password"}
              value={draft.sso_client_secret ?? ""}
              disabled={!ssoEnabled}
              onChange={(e) => onDraftChange({ ...draft, sso_client_secret: e.target.value || null })}
            />
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={onToggleSecretVisibility}
              disabled={!ssoEnabled}
            >
              {isSecretVisible ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
            </Button>
          </div>
          <FieldHint text={text.ssoClientSecretHint} />
        </FormField>

        <FormField label={text.ssoRedirectUri} htmlFor={`${namespace}-sso-redirect-uri`}>
          <Input
            id={`${namespace}-sso-redirect-uri`}
            value={draft.sso_redirect_uri ?? ""}
            disabled={!ssoEnabled}
            onChange={(e) => onDraftChange({ ...draft, sso_redirect_uri: e.target.value || null })}
          />
          <FieldHint text={text.ssoRedirectHint} />
        </FormField>

        <FormField label={text.ssoScopes} htmlFor={`${namespace}-sso-scopes`}>
          <Input
            id={`${namespace}-sso-scopes`}
            value={draft.sso_scopes}
            disabled={!ssoEnabled}
            onChange={(e) => onDraftChange({ ...draft, sso_scopes: e.target.value })}
            placeholder="openid profile email"
          />
          <FieldHint text={text.ssoScopesHint} />
        </FormField>
      </div>

      {!ssoEnabled && (
        <p className="text-xs text-muted-foreground">
          {text.ssoFieldDisabledHint}
        </p>
      )}
    </div>
  )
}

function SettingsPanel({
  config,
  isConfigLoading,
  onSaveGeneral,
  text,
}: {
  config: RuntimeConfigPayload | null
  isConfigLoading: boolean
  onSaveGeneral: (payload: GeneralConfig) => Promise<void>
  text: UiTextMap
}) {
  const general = config?.general ?? null
  const [draft, setDraft] = useState<GeneralConfig | null>(null)
  const [isSaving, setIsSaving] = useState(false)
  const [tokenCopied, setTokenCopied] = useState(false)
  const [isTokenVisible, setIsTokenVisible] = useState(false)
  const [isSSOSecretVisible, setIsSSOSecretVisible] = useState(false)

  useEffect(() => {
    setDraft(general ? structuredClone(general) : null)
  }, [general])

  const isDirty = draft && general && JSON.stringify(draft) !== JSON.stringify(general)

  const handleSave = async () => {
    if (!draft) return
    setIsSaving(true)
    try {
      await onSaveGeneral(draft)
    } catch (e) {
      toast.error(normalizeError(e))
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <section className="space-y-5">
      {/* General settings — inline form */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <Settings2 className="size-4 text-blue-600 dark:text-blue-400" />
            {text.general}
          </CardTitle>
          <CardDescription>{text.appBehaviour}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          {isConfigLoading && !config ? (
            <div className="space-y-3">
              <Skeleton className="h-9 w-full" />
              <Skeleton className="h-9 w-full" />
            </div>
          ) : draft ? (
            <>
              <div className="grid gap-4 sm:grid-cols-3">
                <FormField label={text.logLevel} htmlFor="settings-log-level">
                  <select
                    id="settings-log-level"
                    value={draft.log_level}
                    onChange={(e) => setDraft({ ...draft, log_level: e.target.value })}
                    className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-xs outline-none transition-[color,box-shadow] focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50"
                  >
                    {LOG_LEVEL_OPTIONS.map((l) => <option key={l} value={l}>{l}</option>)}
                  </select>
                </FormField>

                <FormField label={text.httpTimeoutSeconds} htmlFor="settings-timeout">
                  <Input
                    id="settings-timeout"
                    type="number"
                    min={1}
                    step={1}
                    value={String(draft.http_timeout_seconds)}
                    onChange={(e) => setDraft({ ...draft, http_timeout_seconds: Number(e.target.value) })}
                  />
                </FormField>

                <FormField label={text.activityRetention} htmlFor="settings-retention">
                  <select
                    id="settings-retention"
                    value={String(draft.activity_retention_days)}
                    onChange={(e) => setDraft({ ...draft, activity_retention_days: Number(e.target.value) })}
                    className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-xs outline-none transition-[color,box-shadow] focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50"
                  >
                    <option value="1">{text.oneDay}</option>
                    <option value="7">{text.sevenDays}</option>
                    <option value="30">{text.thirtyDays}</option>
                    <option value="90">{text.ninetyDays}</option>
                    <option value="365">{text.oneYear}</option>
                  </select>
                </FormField>
              </div>

              <FormField label={text.jellyfinMetadataLanguage} htmlFor="settings-jellyfin-language">
                <select
                  id="settings-jellyfin-language"
                  value={draft.jellyfin_language}
                  onChange={(e) => setDraft({ ...draft, jellyfin_language: e.target.value })}
                  className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-xs transition-[color,box-shadow] outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50"
                >
                  {JELLYFIN_LANGUAGE_OPTIONS.map((language) => (
                    <option key={language.value} value={language.value}>
                      {language.label}
                    </option>
                  ))}
                </select>
                <FieldHint text={text.jellyfinLanguageHint} />
              </FormField>

              <FormField label={text.uiLanguage} htmlFor="settings-ui-language">
                <select
                  id="settings-ui-language"
                  value={draft.ui_language}
                  onChange={(e) => setDraft({ ...draft, ui_language: e.target.value })}
                  className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-xs transition-[color,box-shadow] outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50"
                >
                  {UI_LANGUAGE_OPTIONS.map((language) => (
                    <option key={language.value} value={language.value}>
                      {language.label}
                    </option>
                  ))}
                </select>
                <FieldHint text={text.uiLanguageHint} />
              </FormField>

              <FormField label={text.webhookToken} htmlFor="settings-webhook-token">
                <div className="flex items-center gap-2">
                  <code className="flex-1 rounded-md border border-input bg-muted px-3 py-2 font-mono text-xs break-all select-all">
                    {isTokenVisible ? (draft.webhook_shared_token ?? "—") : "•".repeat(32)}
                  </code>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    title={isTokenVisible ? text.hideToken : text.showToken}
                    onClick={() => setIsTokenVisible((v) => !v)}
                  >
                    {isTokenVisible ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    title={text.regenerateToken}
                    onClick={() => setDraft({ ...draft, webhook_shared_token: generateWebhookToken() })}
                  >
                    <RefreshCw className="size-4" />
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={!draft.webhook_shared_token}
                    title={text.copyToken}
                    onClick={async () => {
                      await navigator.clipboard.writeText(draft.webhook_shared_token ?? "")
                      setTokenCopied(true)
                      setTimeout(() => setTokenCopied(false), 2000)
                    }}
                  >
                    {tokenCopied
                      ? <CheckCircle2 className="size-4 text-green-600 dark:text-green-400" />
                      : <Copy className="size-4" />}
                  </Button>
                </div>
                <FieldHint text={text.tokenHint} />
              </FormField>

              <SsoConfigSection
                text={text}
                namespace="settings"
                draft={draft}
                onDraftChange={setDraft}
                isSecretVisible={isSSOSecretVisible}
                onToggleSecretVisibility={() => setIsSSOSecretVisible((v) => !v)}
              />

              <div className="flex items-center justify-between border-t pt-4">
                <p className="text-xs text-muted-foreground">
                  {isDirty ? text.unsavedChanges : text.allSettingsSaved}
                </p>
                <Button onClick={handleSave} disabled={!isDirty || isSaving}>
                  {isSaving
                    ? <LoaderCircle className="size-4 animate-spin" />
                    : <CheckCircle2 className="size-4 text-green-600 dark:text-green-400" />}
                  {text.saveChanges}
                </Button>
              </div>
            </>
          ) : (
            <EmptyState
              title={text.settingsUnavailable}
              description={text.tryAgain}
            />
          )}
        </CardContent>
      </Card>

    </section>
  )
}

// ─── Setup wizard ─────────────────────────────────────────────────────────────

function WizardGeneralStep({
  config,
  onSave,
  text,
}: {
  config: RuntimeConfigPayload | null
  onSave: (payload: GeneralConfig) => Promise<void>
  text: UiTextMap
}) {
  const general = config?.general ?? null
  const [draft, setDraft] = useState<GeneralConfig | null>(() =>
    general ? structuredClone(general) : null,
  )
  const [isSaving, setIsSaving] = useState(false)
  const [tokenCopied, setTokenCopied] = useState(false)
  const [isTokenVisible, setIsTokenVisible] = useState(false)
  const [isSSOSecretVisible, setIsSSOSecretVisible] = useState(false)

  useEffect(() => {
    setDraft(general ? structuredClone(general) : null)
  }, [general])

  const handleSave = async () => {
    if (!draft) return
    setIsSaving(true)
    try {
      await onSave(draft)
    } catch (e) {
      toast.error(normalizeError(e))
    } finally {
      setIsSaving(false)
    }
  }

  if (!draft) {
    return (
      <EmptyState
        title={text.settingsUnavailable}
        description={text.tryAgain}
      />
    )
  }

  return (
    <div className="space-y-5 pb-4">
      <div>
        <h2 className="text-lg font-semibold">{text.general}</h2>
        <p className="text-sm text-muted-foreground">
          {text.runtimeSettingsSummary}
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        <FormField label={text.logLevel} htmlFor="wizard-log-level">
          <select
            id="wizard-log-level"
            value={draft.log_level}
            onChange={(e) => setDraft({ ...draft, log_level: e.target.value })}
            className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-xs outline-none transition-[color,box-shadow] focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50"
          >
            {LOG_LEVEL_OPTIONS.map((l) => <option key={l} value={l}>{l}</option>)}
          </select>
        </FormField>

        <FormField label={text.httpTimeoutSeconds} htmlFor="wizard-timeout">
          <Input
            id="wizard-timeout"
            type="number"
            min={1}
            step={1}
            value={String(draft.http_timeout_seconds)}
            onChange={(e) => setDraft({ ...draft, http_timeout_seconds: Number(e.target.value) })}
          />
        </FormField>

        <FormField label={text.activityRetention} htmlFor="wizard-retention">
          <select
            id="wizard-retention"
            value={String(draft.activity_retention_days)}
            onChange={(e) => setDraft({ ...draft, activity_retention_days: Number(e.target.value) })}
            className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-xs outline-none transition-[color,box-shadow] focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50"
          >
            <option value="1">{text.oneDay}</option>
            <option value="7">{text.sevenDays}</option>
            <option value="30">{text.thirtyDays}</option>
            <option value="90">{text.ninetyDays}</option>
            <option value="365">{text.oneYear}</option>
          </select>
        </FormField>

        <FormField label={text.jellyfinMetadataLanguage} htmlFor="wizard-jellyfin-language">
          <select
            id="wizard-jellyfin-language"
            value={draft.jellyfin_language}
            onChange={(e) => setDraft({ ...draft, jellyfin_language: e.target.value })}
            className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-xs outline-none transition-[color,box-shadow] focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50"
          >
            {JELLYFIN_LANGUAGE_OPTIONS.map((language) => (
              <option key={language.value} value={language.value}>
                {language.label}
              </option>
            ))}
          </select>
          <FieldHint text={text.jellyfinLanguageHint} />
        </FormField>

        <FormField label={text.uiLanguage} htmlFor="wizard-ui-language">
          <select
            id="wizard-ui-language"
            value={draft.ui_language}
            onChange={(e) => setDraft({ ...draft, ui_language: e.target.value })}
            className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-xs outline-none transition-[color,box-shadow] focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50"
          >
            {UI_LANGUAGE_OPTIONS.map((language) => (
              <option key={language.value} value={language.value}>
                {language.label}
              </option>
            ))}
          </select>
          <FieldHint text={text.uiLanguageHint} />
        </FormField>
      </div>

      <FormField label={text.webhookToken} htmlFor="wizard-webhook-token">
        <div className="flex items-center gap-2">
          <code className="flex-1 rounded-md border border-input bg-muted px-3 py-2 font-mono text-xs break-all select-all">
            {isTokenVisible ? (draft.webhook_shared_token ?? "—") : "•".repeat(32)}
          </code>
          <Button
            type="button"
            variant="outline"
            size="sm"
            title={isTokenVisible ? text.hideToken : text.showToken}
            onClick={() => setIsTokenVisible((v) => !v)}
          >
            {isTokenVisible ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            title={text.regenerateToken}
            onClick={() => setDraft({ ...draft, webhook_shared_token: generateWebhookToken() })}
          >
            <RefreshCw className="size-4" />
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={!draft.webhook_shared_token}
            title={text.copyToken}
            onClick={async () => {
              await navigator.clipboard.writeText(draft.webhook_shared_token ?? "")
              setTokenCopied(true)
              setTimeout(() => setTokenCopied(false), 2000)
            }}
          >
            {tokenCopied
              ? <CheckCircle2 className="size-4 text-green-600 dark:text-green-400" />
              : <Copy className="size-4" />}
          </Button>
        </div>
        <FieldHint text={text.tokenHint} />
      </FormField>

        <SsoConfigSection
          text={text}
          namespace="wizard"
          draft={draft}
          onDraftChange={setDraft}
          isSecretVisible={isSSOSecretVisible}
          onToggleSecretVisibility={() => setIsSSOSecretVisible((v) => !v)}
        />

      <div className="flex justify-end border-t pt-4">
        <Button onClick={() => void handleSave()} disabled={isSaving}>
          {isSaving
            ? <LoaderCircle className="size-4 animate-spin" />
            : <CheckCircle2 className="size-4 text-green-600 dark:text-green-400" />}
          {text.save}
        </Button>
      </div>
    </div>
  )
}

function WizardServiceStep({
  family,
  config,
  text,
  onSave,
  onTest,
  jellyfinSetupProps,
}: {
  family: ServiceFamily
  config: RuntimeConfigPayload | null
  text: UiTextMap
  onSave: (family: ServiceFamily, draft: ServiceDraft) => Promise<void>
  onTest: (family: ServiceFamily, draft: ServiceDraft) => Promise<ConnectionTestResponse>
  jellyfinSetupProps?: {
    dashboard: DashboardPayload | null
    origin: string
    curlPreview: string
    tokenConfigured: boolean
    onSetupWebhook: (webhookUrl: string) => Promise<{ found: boolean; configured: boolean; message: string }>
  }
}) {
  const meta = SERVICE_META[family]
  const existingServices = getServices(config, family)
  const existingService = resolveActiveService(existingServices) ?? existingServices[0] ?? null

  const [draft, setDraft] = useState<ServiceDraft>(() =>
    existingService ? toDraft(existingService) : structuredClone(EMPTY_DRAFTS[family]),
  )
  const [isSaving, setIsSaving] = useState(false)
  const [isTesting, setIsTesting] = useState(false)

  useEffect(() => {
    const svc = resolveActiveService(getServices(config, family)) ?? getServices(config, family)[0] ?? null
    setDraft(svc ? toDraft(svc) : structuredClone(EMPTY_DRAFTS[family]))
  }, [config, family])

  const alreadyConfigured = Boolean(existingService)

  const handleTest = async () => {
    setIsTesting(true)
    try {
      const result = await onTest(family, draft)
      if (result.ok) {
        toast.success(result.message)
      } else {
        toast.error(result.message)
      }
    } catch (e) {
      toast.error(normalizeError(e))
    } finally {
      setIsTesting(false)
    }
  }

  const handleSave = async () => {
    setIsSaving(true)
    try {
      await onSave(family, draft)
    } catch (e) {
      toast.error(normalizeError(e))
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <div className="space-y-5 pb-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">{meta.title}</h2>
          <p className="text-sm text-muted-foreground">{getServiceDescription(family, text)}</p>
        </div>
        {alreadyConfigured && (
          <StatusPill tone="green" label={text.alreadyConfigured} />
        )}
      </div>

      <GuideCard
        tone={meta.accent}
        title={text.beforeYouSave}
        description={text.beforeSaveDescription}
      >
        <InstructionList items={getServiceHelp(meta, text)} />
      </GuideCard>

      <FormField label={text.displayName} htmlFor={`wizard-${family}-name`}>
        <Input
          id={`wizard-${family}-name`}
          value={draft.name}
          onChange={(e) => setDraft({ ...draft, name: e.target.value })}
        />
      </FormField>

      <FormField label={text.baseUrl} htmlFor={`wizard-${family}-url`}>
        <Input
          id={`wizard-${family}-url`}
          type="url"
          value={draft.url}
          onChange={(e) => setDraft({ ...draft, url: e.target.value })}
          placeholder={meta.example}
        />
        <FieldHint
          text={
            family === "downloaders" ? text.downloaderUrlHint : text.serviceUrlHint
          }
        />
      </FormField>

      {meta.fields.map((field) => (
        <FormField
          key={field.key}
          label={getServiceFieldLabel(field.key, text)}
          htmlFor={`wizard-${family}-${field.key}`}
        >
          <Input
            id={`wizard-${family}-${field.key}`}
            type={field.type}
            value={draft[field.key]}
            onChange={(e) => setDraft({ ...draft, [field.key]: e.target.value })}
          />
          <FieldHint text={getServiceFieldHint(family, field.key, text)} />
        </FormField>
      ))}

      <div className="grid gap-2 sm:grid-cols-2">
        <label className="inline-flex cursor-pointer items-center gap-3 rounded-lg border px-3 py-2 text-sm">
          <input
            type="checkbox"
            checked={draft.enabled}
            onChange={(e) => setDraft({ ...draft, enabled: e.target.checked })}
          />
          {text.enabled}
        </label>
        <label className="inline-flex cursor-pointer items-center gap-3 rounded-lg border px-3 py-2 text-sm">
          <input
            type="checkbox"
            checked={draft.is_default}
            onChange={(e) => setDraft({ ...draft, is_default: e.target.checked })}
          />
          {text.runtimeTarget}
        </label>
      </div>

      <div className="flex gap-3 border-t pt-4">
        <Button
          variant="outline"
          disabled={isTesting}
          onClick={() => void handleTest()}
        >
          {isTesting ? (
            <LoaderCircle className="size-4 animate-spin" />
          ) : (
            <TestTubeDiagonal className="size-4 text-blue-600 dark:text-blue-400" />
          )}
          {text.test}
        </Button>
        <Button
          disabled={isSaving}
          onClick={() => void handleSave()}
        >
          {isSaving ? (
            <LoaderCircle className="size-4 animate-spin" />
          ) : (
            <CheckCircle2 className="size-4 text-green-600 dark:text-green-400" />
          )}
          {text.save}
        </Button>
      </div>

      {jellyfinSetupProps && (
        <div className="space-y-5 border-t pt-5">
          <p className="text-sm font-semibold text-muted-foreground uppercase tracking-wider">{text.webhook}</p>
          <JellyfinSetupPanel
            text={text}
            dashboard={jellyfinSetupProps.dashboard}
            origin={jellyfinSetupProps.origin}
            curlPreview={jellyfinSetupProps.curlPreview}
            tokenConfigured={jellyfinSetupProps.tokenConfigured}
            jellyfinConfigured={alreadyConfigured || Boolean(draft.id)}
            onOpenGeneral={() => {}}
            onSetupWebhook={jellyfinSetupProps.onSetupWebhook}
          />
        </div>
      )}
    </div>
  )
}

function SetupWizard({
  config,
  dashboard,
  origin,
  curlPreview,
  text,
  onSaveGeneral,
  onSaveService,
  onTestService,
  onSetupWebhook,
  onClose,
}: {
  config: RuntimeConfigPayload | null
  dashboard: DashboardPayload | null
  origin: string
  curlPreview: string
  text: UiTextMap
  onSaveGeneral: (payload: GeneralConfig) => Promise<void>
  onSaveService: (family: ServiceFamily, draft: ServiceDraft) => Promise<void>
  onTestService: (family: ServiceFamily, draft: ServiceDraft) => Promise<ConnectionTestResponse>
  onSetupWebhook: (webhookUrl: string) => Promise<{ found: boolean; configured: boolean; message: string }>
  onClose: () => void
}) {
  return (
    <div className="fixed inset-0 z-50 overflow-auto bg-background/98 backdrop-blur-sm">
      <div className="mx-auto max-w-4xl px-6 py-6">
        {/* Header */}
        <div className="mb-6 flex items-center justify-between">
          <div>
            <CleanArrBrand size="sm" />
            <p className="mt-1 text-sm text-muted-foreground">
              {text.firstTimeSetup}
            </p>
          </div>
          <Button variant="ghost" size="sm" onClick={onClose}>
            {text.skipForNow}
          </Button>
        </div>

        <Stepper
          onFinalStepCompleted={onClose}
          nextButtonText={text.next}
          backButtonText={text.back}
          stepCircleContainerClassName="bg-card"
        >
          {/* Step 1: General */}
          <Step>
            <WizardGeneralStep config={config} onSave={onSaveGeneral} text={text} />
          </Step>

          {/* Step 2: Jellyfin */}
          <Step>
            <WizardServiceStep
              family="jellyfin_server"
              config={config}
              text={text}
              onSave={onSaveService}
              onTest={onTestService}
              jellyfinSetupProps={{
                dashboard,
                origin,
                curlPreview,
                tokenConfigured: Boolean(config?.general.webhook_shared_token),
                onSetupWebhook,
              }}
            />
          </Step>

          {/* Step 3: Radarr */}
          <Step>
            <WizardServiceStep
              family="radarr"
              config={config}
              text={text}
              onSave={onSaveService}
              onTest={onTestService}
            />
          </Step>

          {/* Step 4: Sonarr */}
          <Step>
            <WizardServiceStep
              family="sonarr"
              config={config}
              text={text}
              onSave={onSaveService}
              onTest={onTestService}
            />
          </Step>

          {/* Step 5: Jellyseerr */}
          <Step>
            <WizardServiceStep
              family="jellyseerr"
              config={config}
              text={text}
              onSave={onSaveService}
              onTest={onTestService}
            />
          </Step>

          {/* Step 6: qBittorrent */}
          <Step>
            <WizardServiceStep
              family="downloaders"
              config={config}
              text={text}
              onSave={onSaveService}
              onTest={onTestService}
            />
          </Step>
        </Stepper>
      </div>
    </div>
  )
}

// ─── Jellyfin setup panel ─────────────────────────────────────────────────────

type SetupState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "success"; message: string }
  | { status: "not_found"; message: string }
  | { status: "error"; message: string }

function JellyfinSetupPanel({
  text,
  dashboard,
  origin,
  curlPreview,
  tokenConfigured,
  jellyfinConfigured,
  onOpenGeneral,
  onSetupWebhook,
}: {
  text: UiTextMap
  dashboard: DashboardPayload | null
  origin: string
  curlPreview: string
  tokenConfigured: boolean
  jellyfinConfigured: boolean
  onOpenGeneral: () => void
  onSetupWebhook: (webhookUrl: string) => Promise<{ found: boolean; configured: boolean; message: string }>
}) {
  const webhookUrl = `${origin}/webhook/jellyfin`
  const [setupState, setSetupState] = useState<SetupState>({ status: "idle" })
  const [curlOpen, setCurlOpen] = useState(false)

  const webhookStatus = dashboard?.webhook_status
  const webhookTone = getWebhookStatusTone(webhookStatus?.outcome ?? "waiting")
  const lastAttemptAt = webhookStatus?.attempted_at
    ? new Date(webhookStatus.attempted_at).toLocaleString()
    : text.notReceivedYet
  const statusLabel = getWebhookStatusLabel(webhookStatus?.outcome ?? "waiting", text)

  async function handleSetup() {
    setSetupState({ status: "loading" })
    try {
      const result = await onSetupWebhook(webhookUrl)
      if (result.configured) {
        setSetupState({ status: "success", message: result.message })
      } else if (!result.found) {
        setSetupState({ status: "not_found", message: result.message })
      } else {
        setSetupState({ status: "error", message: result.message })
      }
    } catch (err) {
      setSetupState({
        status: "error",
        message: err instanceof Error ? err.message : text.unknownError,
      })
    }
  }

  return (
    <div className="space-y-5">
      {/* Auto-configure */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <Webhook className="size-4 text-blue-600 dark:text-blue-400" />
            {text.autoConfigureWebhook}
          </CardTitle>
          <CardDescription>
            {text.autoConfigureWebhookDescription}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {!jellyfinConfigured && (
            <Alert>
              <Info className="size-4 text-blue-600 dark:text-blue-400" />
              <AlertDescription>
                {text.connectJellyfinFirst}
              </AlertDescription>
            </Alert>
          )}
          {jellyfinConfigured && !tokenConfigured && (
            <Alert>
              <CircleAlert className="size-4" />
              <AlertDescription>
                <button
                  type="button"
                  className="underline underline-offset-2"
                  onClick={onOpenGeneral}
                >
                  {text.setWebhookTokenFirst}
                </button>
              </AlertDescription>
            </Alert>
          )}

          <div className="flex items-center gap-3">
            <Button
              disabled={!jellyfinConfigured || setupState.status === "loading"}
              onClick={() => void handleSetup()}
            >
              {setupState.status === "loading" ? (
                <RefreshCw className="size-4 animate-spin" />
              ) : setupState.status === "success" ? (
                <CheckCircle2 className="size-4" />
              ) : (
                <Webhook className="size-4" />
              )}
              {setupState.status === "loading"
                ? text.configuring
                : setupState.status === "success"
                  ? text.configured
                  : text.autoConfigureWebhook}
            </Button>
            {setupState.status === "success" && <StatusPill tone="green" label={text.done} />}
          </div>

          {setupState.status === "success" && (
            <Alert>
              <CheckCircle2 className="size-4 text-green-600 dark:text-green-400" />
              <AlertDescription>{setupState.message}</AlertDescription>
            </Alert>
          )}
          {setupState.status === "error" && (
            <Alert variant="destructive">
              <CircleAlert className="size-4" />
              <AlertDescription>{setupState.message}</AlertDescription>
            </Alert>
          )}
          {setupState.status === "not_found" && (
            <div className="space-y-3">
              <Alert variant="destructive">
                <CircleAlert className="size-4" />
                <AlertDescription>{setupState.message}</AlertDescription>
              </Alert>
              <GuideCard
                tone="blue"
                title={text.installJellyfinWebhook}
                description={text.installJellyfinWebhookDescription}
              >
                <InstructionList items={[
                  text.jellyfinInstallStep1,
                  text.jellyfinInstallStep2,
                  text.jellyfinInstallStep3,
                  text.jellyfinInstallStep4,
                ]} />
              </GuideCard>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Verify delivery */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <TestTubeDiagonal className="size-4 text-green-600 dark:text-green-400" />
            {text.verifyDelivery}
          </CardTitle>
          <CardDescription>
            {text.verifyDeliveryDescription}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
            <ReadOnlyDetail label={text.deliveryStatus} value={statusLabel} />
            <ReadOnlyDetail label={text.lastAttempt} value={lastAttemptAt} />
            <ReadOnlyDetail
              label={text.httpStatus}
              value={webhookStatus?.http_status ? String(webhookStatus.http_status) : text.none}
            />
            <ReadOnlyDetail
              label={text.lastItem}
              value={
                webhookStatus?.item_name
                  ? formatMediaTitle(getItemTypeLabel(webhookStatus.item_type ?? "Item", text), webhookStatus.item_name)
                  : text.noItemReceived
              }
            />
          </div>

          <div className="flex flex-wrap gap-2">
            <StatusPill tone={webhookTone} label={statusLabel} />
            {webhookStatus?.result_status && (
              <StatusPill
                tone={webhookStatus.result_status === "partial_failure" ? "red" : "green"}
                label={`${text.processing}: ${getStatusLabel(webhookStatus.result_status, text)}`}
              />
            )}
            {webhookStatus?.notification_type && (
              <StatusPill
                tone="blue"
                label={`${webhookStatus.notification_type}${webhookStatus.item_type ? ` / ${webhookStatus.item_type}` : ""}`}
              />
            )}
          </div>

          <Alert
            variant={
              webhookStatus?.outcome === "rejected_auth" ||
              webhookStatus?.outcome === "invalid_payload"
                ? "destructive"
                : "default"
            }
          >
            {webhookTone === "green" ? (
              <CheckCircle2 className="size-4 text-green-600 dark:text-green-400" />
            ) : webhookTone === "red" ? (
              <CircleAlert className="size-4" />
            ) : (
              <Info className="size-4 text-blue-600 dark:text-blue-400" />
            )}
            <AlertTitle>{text.latestWebhookAttempt}</AlertTitle>
            <AlertDescription>
              {webhookStatus?.message ?? text.noJellyfinWebhook}
            </AlertDescription>
          </Alert>

          {/* Collapsible smoke-test cURL */}
          <Card className="border-dashed">
            <button
              type="button"
              className="flex w-full items-center gap-2 px-4 py-3 text-left text-sm"
              onClick={() => setCurlOpen((v) => !v)}
            >
              {curlOpen ? (
                <ChevronDown className="size-4 shrink-0 text-muted-foreground" />
              ) : (
                <ChevronRight className="size-4 shrink-0 text-muted-foreground" />
              )}
              <Sparkles className="size-4 shrink-0 text-green-600 dark:text-green-400" />
              <span className="font-medium">{text.smokeTestCurl}</span>
              <span className="ml-auto text-xs text-muted-foreground">
                {tokenConfigured ? text.tokenPrefilled : text.configureTokenFirst}
              </span>
            </button>
            {curlOpen && (
              <CardContent className="space-y-3 border-t pt-3">
                <p className="text-xs text-muted-foreground">
                  {text.smokeTestDescription}
                </p>
                <Textarea
                  readOnly
                  value={curlPreview}
                  className="min-h-[180px] font-mono text-xs"
                />
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => void navigator.clipboard.writeText(curlPreview)}
                >
                  <Copy className="size-4 text-blue-600 dark:text-blue-400" />
                  {text.copyCurl}
                </Button>
              </CardContent>
            )}
          </Card>
        </CardContent>
      </Card>
    </div>
  )
}



// ─── General settings modal ───────────────────────────────────────────────────

function GeneralSettingsModal({
  open,
  config,
  text,
  onClose,
  onSave,
}: {
  open: boolean
  config: GeneralConfig | null
  text: UiTextMap
  onClose: () => void
  onSave: (payload: GeneralConfig) => Promise<void>
  }) {
  const [draft, setDraft] = useState<GeneralConfig | null>(config)
  const [isSaving, setIsSaving] = useState(false)
  const [tokenCopied, setTokenCopied] = useState(false)
  const [isTokenVisible, setIsTokenVisible] = useState(false)
  const [isSSOSecretVisible, setIsSSOSecretVisible] = useState(false)

  useEffect(() => {
    setDraft(config ? structuredClone(config) : null)
    setTokenCopied(false)
  }, [config, open])

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={text.runtimeSettings}
      description={text.runtimeSettingsDescription}
      footer={
        <div className="flex justify-end">
          <Button
            disabled={!draft || isSaving}
            onClick={async () => {
              if (!draft) return
              setIsSaving(true)
              try {
                await onSave(draft)
              } catch (e) {
                toast.error(normalizeError(e))
              } finally {
                setIsSaving(false)
              }
            }}
          >
            {isSaving ? (
              <LoaderCircle className="size-4 animate-spin" />
            ) : (
              <CheckCircle2 className="size-4 text-green-600 dark:text-green-400" />
            )}
            {text.saveSettings}
          </Button>
        </div>
      }
    >
      {draft ? (
        <div className="space-y-5">
          <GuideCard
            tone="blue"
            title={text.recommendedFirstRun}
            description={text.recommendedDryRun}
          >
            <InstructionList items={[
              text.generalSetupStep1,
              text.generalSetupStep2,
              text.generalSetupStep3,
            ]} />
          </GuideCard>

          <div className="grid gap-4 sm:grid-cols-2">
            <FormField label={text.logLevel} htmlFor="general-log-level">
              <select
                id="general-log-level"
                value={draft.log_level}
                onChange={(e) => setDraft({ ...draft, log_level: e.target.value })}
                className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-xs transition-[color,box-shadow] outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50"
              >
                {LOG_LEVEL_OPTIONS.map((level) => (
                  <option key={level} value={level}>
                    {level}
                  </option>
                ))}
              </select>
            </FormField>

            <FormField label={text.httpTimeoutSeconds} htmlFor="general-timeout">
              <Input
                id="general-timeout"
                type="number"
                min={1}
                step={1}
                value={String(draft.http_timeout_seconds)}
                onChange={(e) =>
                  setDraft({ ...draft, http_timeout_seconds: Number(e.target.value) })
                }
              />
              <FieldHint text={text.httpTimeoutHint} />
            </FormField>

            <FormField label={text.activityRetention} htmlFor="general-retention">
              <select
                id="general-retention"
                value={String(draft.activity_retention_days)}
                onChange={(e) =>
                  setDraft({ ...draft, activity_retention_days: Number(e.target.value) })
                }
                className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-xs transition-[color,box-shadow] outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50"
              >
                <option value="1">{text.oneDay}</option>
                <option value="7">{text.sevenDays}</option>
                <option value="30">{text.thirtyDays}</option>
                <option value="90">{text.ninetyDays}</option>
                <option value="365">{text.oneYear}</option>
              </select>
              <FieldHint text={text.retentionHint} />
            </FormField>
          </div>

          <FormField label={text.webhookToken} htmlFor="general-webhook-token">
            <div className="flex items-center gap-2">
              <code className="flex-1 rounded-md border border-input bg-muted px-3 py-2 font-mono text-xs break-all select-all">
                {isTokenVisible ? (draft.webhook_shared_token ?? "—") : "•".repeat(32)}
              </code>
              <Button
                type="button"
                variant="outline"
                size="sm"
                title={isTokenVisible ? text.hideToken : text.showToken}
                onClick={() => setIsTokenVisible((v) => !v)}
              >
                {isTokenVisible ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
              </Button>
              <Button
                type="button"
                variant="outline"
                size="sm"
                title={text.regenerateToken}
                onClick={() => {
                  setDraft({ ...draft, webhook_shared_token: generateWebhookToken() })
                }}
              >
                <RefreshCw className="size-4" />
              </Button>
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={!draft.webhook_shared_token}
                title={text.copyToken}
                onClick={async () => {
                  await navigator.clipboard.writeText(draft.webhook_shared_token ?? "")
                  setTokenCopied(true)
                  setTimeout(() => setTokenCopied(false), 2000)
                }}
              >
                {tokenCopied ? (
                  <CheckCircle2 className="size-4 text-green-600 dark:text-green-400" />
                ) : (
                  <Copy className="size-4" />
                )}
              </Button>
            </div>
            <FieldHint text={text.tokenHint} />
          </FormField>

          <FormField label={text.jellyfinMetadataLanguage} htmlFor="general-jellyfin-language">
            <select
              id="general-jellyfin-language"
              value={draft.jellyfin_language}
              onChange={(e) => setDraft({ ...draft, jellyfin_language: e.target.value })}
              className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-xs transition-[color,box-shadow] outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50"
            >
              {JELLYFIN_LANGUAGE_OPTIONS.map((language) => (
                <option key={language.value} value={language.value}>
                  {language.label}
                </option>
              ))}
            </select>
            <FieldHint text={text.jellyfinLanguageHint} />
          </FormField>

          <FormField label={text.uiLanguage} htmlFor="general-ui-language">
            <select
              id="general-ui-language"
              value={draft.ui_language}
              onChange={(e) => setDraft({ ...draft, ui_language: e.target.value })}
              className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-xs transition-[color,box-shadow] outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50"
            >
              {UI_LANGUAGE_OPTIONS.map((language) => (
                <option key={language.value} value={language.value}>
                  {language.label}
                </option>
              ))}
            </select>
            <FieldHint text={text.uiLanguageHint} />
          </FormField>

          <SsoConfigSection
            text={text}
            draft={draft}
            onDraftChange={setDraft}
            namespace="general"
            isSecretVisible={isSSOSecretVisible}
            onToggleSecretVisibility={() => setIsSSOSecretVisible((v: boolean) => !v)}
          />

          <label className="inline-flex cursor-pointer items-center gap-3 text-sm">
            <input
              type="checkbox"
              checked={draft.dry_run}
              onChange={(e) => setDraft({ ...draft, dry_run: e.target.checked })}
            />
            {text.keepDryRun}
          </label>
        </div>
      ) : (
        <EmptyState
          title={text.settingsUnavailable}
          description={text.closeAndRefresh}
        />
      )}
    </Modal>
  )
}

// ─── Service modal ────────────────────────────────────────────────────────────

function ServiceModal({
  state,
  text,
  onClose,
  onSave,
  onDelete,
  onTest,
  jellyfinSetupProps,
}: {
  state: ServiceModalState | null
  text: UiTextMap
  onClose: () => void
  onSave: (family: ServiceFamily, draft: ServiceDraft) => Promise<void>
  onDelete: (family: ServiceFamily, serviceId: string) => Promise<void>
  onTest: (family: ServiceFamily, draft: ServiceDraft) => Promise<ConnectionTestResponse>
  jellyfinSetupProps?: {
    dashboard: DashboardPayload | null
    origin: string
    curlPreview: string
    tokenConfigured: boolean
    onSetupWebhook: (webhookUrl: string) => Promise<{ found: boolean; configured: boolean; message: string }>
  }
}) {
  const [draft, setDraft] = useState<ServiceDraft | null>(state?.draft ?? null)
  const [isSaving, setIsSaving] = useState(false)
  const [isTesting, setIsTesting] = useState(false)
  const [isDeleting, setIsDeleting] = useState(false)

  useEffect(() => {
    setDraft(state ? structuredClone(state.draft) : null)
  }, [state])

  if (!state) return null

  const meta = SERVICE_META[state.family]

  return (
    <Modal
      open={state !== null}
      onClose={onClose}
      title={`${draft?.id ? text.edit : text.add} ${meta.title}`}
      description={getServiceDescription(state.family, text)}
      footer={
        <div className="flex flex-wrap justify-between gap-3">
          <div>
            {draft?.id && (
              <Button
                variant="destructive"
                disabled={isDeleting}
                onClick={async () => {
                  if (!draft?.id) return
                  setIsDeleting(true)
                  try {
                    await onDelete(state.family, draft.id)
                  } catch (e) {
                    toast.error(normalizeError(e))
                  } finally {
                    setIsDeleting(false)
                  }
                }}
              >
                {isDeleting ? <LoaderCircle className="size-4 animate-spin" /> : <CircleAlert className="size-4" />}
                {text.delete}
              </Button>
            )}
          </div>

          <div className="flex flex-wrap gap-3">
            <Button
              variant="outline"
              disabled={!draft || isTesting}
              onClick={async () => {
                if (!draft) return
                setIsTesting(true)
                try {
                  const result = await onTest(state.family, draft)
                  if (result.ok) {
                    toast.success(result.message)
                  } else {
                    toast.error(result.message)
                  }
                } catch (e) {
                  toast.error(normalizeError(e))
                } finally {
                  setIsTesting(false)
                }
              }}
            >
              {isTesting ? (
                <LoaderCircle className="size-4 animate-spin" />
              ) : (
                <TestTubeDiagonal className="size-4 text-blue-600 dark:text-blue-400" />
              )}
              {text.test}
            </Button>
            <Button
              disabled={!draft || isSaving}
              onClick={async () => {
                if (!draft) return
                setIsSaving(true)
                try {
                  await onSave(state.family, draft)
                } catch (e) {
                  toast.error(normalizeError(e))
                } finally {
                  setIsSaving(false)
                }
              }}
            >
              {isSaving ? (
                <LoaderCircle className="size-4 animate-spin" />
              ) : (
                <CheckCircle2 className="size-4 text-green-600 dark:text-green-400" />
              )}
              {text.save}
            </Button>
          </div>
        </div>
      }
    >
      {draft ? (
        <div className="space-y-4">
          <GuideCard
            tone={meta.accent}
            title={text.beforeYouSave}
            description={text.beforeSaveDescription}
          >
            <InstructionList items={getServiceHelp(meta, text)} />
          </GuideCard>

          <FormField label={text.displayName} htmlFor={`${state.family}-name`}>
            <Input
              id={`${state.family}-name`}
              value={draft.name}
              onChange={(e) => setDraft({ ...draft, name: e.target.value })}
            />
          </FormField>

          <FormField label={text.baseUrl} htmlFor={`${state.family}-url`}>
            <Input
              id={`${state.family}-url`}
              type="url"
              value={draft.url}
              onChange={(e) => setDraft({ ...draft, url: e.target.value })}
              placeholder={meta.example}
            />
            <FieldHint
              text={
                state.family === "downloaders" ? text.downloaderUrlHint : text.serviceUrlHint
              }
            />
          </FormField>

          {meta.fields.map((field) => (
            <FormField
              key={field.key}
              label={getServiceFieldLabel(field.key, text)}
              htmlFor={`${state.family}-${field.key}`}
            >
              <Input
                id={`${state.family}-${field.key}`}
                type={field.type}
                value={draft[field.key]}
                onChange={(e) => setDraft({ ...draft, [field.key]: e.target.value })}
              />
              <FieldHint text={getServiceFieldHint(state.family, field.key, text)} />
            </FormField>
          ))}

          <div className="grid gap-2 sm:grid-cols-2">
            <label className="inline-flex cursor-pointer items-center gap-3 rounded-lg border px-3 py-2 text-sm">
              <input
                type="checkbox"
                checked={draft.enabled}
                onChange={(e) => setDraft({ ...draft, enabled: e.target.checked })}
              />
              {text.enabled}
            </label>
            <label className="inline-flex cursor-pointer items-center gap-3 rounded-lg border px-3 py-2 text-sm">
              <input
                type="checkbox"
                checked={draft.is_default}
                onChange={(e) => setDraft({ ...draft, is_default: e.target.checked })}
              />
              {text.runtimeTarget}
            </label>
          </div>

          {state.family === "jellyfin_server" && jellyfinSetupProps && (
            <div className="mt-6 space-y-5 border-t pt-5">
              <p className="text-sm font-semibold text-muted-foreground uppercase tracking-wider">{text.webhook}</p>
              <JellyfinSetupPanel
                text={text}
                dashboard={jellyfinSetupProps.dashboard}
                origin={jellyfinSetupProps.origin}
                curlPreview={jellyfinSetupProps.curlPreview}
                tokenConfigured={jellyfinSetupProps.tokenConfigured}
                jellyfinConfigured={Boolean(draft?.id)}
                onOpenGeneral={() => {}}
                onSetupWebhook={jellyfinSetupProps.onSetupWebhook}
              />
            </div>
          )}
        </div>
      ) : null}
    </Modal>
  )
}

// ─── Small UI components ──────────────────────────────────────────────────────

function GuideCard({
  tone,
  title,
  description,
  children,
}: {
  tone: "blue" | "green" | "red"
  title: string
  description: string
  children: React.ReactNode
}) {
  return (
    <div
      className={cn(
        "rounded-lg border p-4",
        tone === "blue" &&
          "border-blue-200 bg-blue-50/40 dark:border-blue-900 dark:bg-blue-950/20",
        tone === "green" &&
          "border-green-200 bg-green-50/40 dark:border-green-900 dark:bg-green-950/20",
        tone === "red" &&
          "border-red-200 bg-red-50/40 dark:border-red-900 dark:bg-red-950/20",
      )}
    >
      <div className="space-y-0.5">
        <p className="text-sm font-medium">{title}</p>
        <p className="text-xs text-muted-foreground">{description}</p>
      </div>
      <div className="mt-3">{children}</div>
    </div>
  )
}

function FormField({
  label,
  htmlFor,
  children,
}: {
  label: string
  htmlFor: string
  children: React.ReactNode
}) {
  return (
    <div className="space-y-1.5">
      <label className="text-sm font-medium" htmlFor={htmlFor}>
        {label}
      </label>
      {children}
    </div>
  )
}

function FieldHint({ text }: { text: string }) {
  return (
    <div className="flex items-start gap-1.5 text-xs text-muted-foreground">
      <CircleHelp className="mt-0.5 size-3.5 shrink-0 text-blue-500" />
      <span>{text}</span>
    </div>
  )
}

function ReadOnlyDetail({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border px-3 py-2.5">
      <p className="text-xs uppercase tracking-wide text-muted-foreground">{label}</p>
      <code className="mt-1 block break-all text-sm">{value}</code>
    </div>
  )
}

function InstructionList({ items }: { items: string[] }) {
  return (
    <ul className="space-y-1.5 text-xs text-muted-foreground">
      {items.map((item) => (
        <li key={item} className="flex items-start gap-2">
          <CheckCircle2 className="mt-0.5 size-3.5 shrink-0 text-green-500" />
          <span>{item}</span>
        </li>
      ))}
    </ul>
  )
}



function EmptyState({ title, description }: { title: string; description: string }) {
  return (
    <div className="rounded-lg border border-dashed p-4 text-sm text-muted-foreground">
      <p className="font-medium text-foreground">{title}</p>
      <p className="mt-1 text-xs">{description}</p>
    </div>
  )
}

function StatusPill({
  tone,
  label,
}: {
  tone: "blue" | "green" | "red" | "neutral"
  label: string
}) {
  return (
    <div
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs font-medium",
        tone === "blue" &&
          "border-blue-200 bg-blue-50 text-blue-800 dark:border-blue-900 dark:bg-blue-950/40 dark:text-blue-200",
        tone === "green" &&
          "border-green-200 bg-green-50 text-green-800 dark:border-green-900 dark:bg-green-950/40 dark:text-green-200",
        tone === "red" &&
          "border-red-200 bg-red-50 text-red-800 dark:border-red-900 dark:bg-red-950/40 dark:text-red-200",
        tone === "neutral" && "border-border bg-background text-foreground",
      )}
    >
      <span
        className={cn(
          "size-1.5 rounded-full",
          tone === "blue" && "bg-blue-500",
          tone === "green" && "bg-green-500",
          tone === "red" && "bg-red-500",
          tone === "neutral" && "bg-zinc-400",
        )}
      />
      {label}
    </div>
  )
}

function StatusDot({ healthStatus, text }: { healthStatus: HealthStatus; text: UiTextMap }) {
  if (healthStatus === "healthy") {
    return <span className="inline-flex size-2 rounded-full bg-green-500" title={text.healthy} />
  }
  if (healthStatus === "unreachable") {
    return <span className="inline-flex size-2 rounded-full bg-red-500" title={text.unreachable} />
  }
  return <span className="inline-flex size-2 rounded-full bg-gray-300 dark:bg-gray-600" title={text.notConfigured} />
}


function ErrorBanner({ message, text }: { message: string; text: UiTextMap }) {
  return (
    <Alert variant="destructive">
      <CircleAlert className="size-4" />
      <AlertTitle>{text.requestFailed}</AlertTitle>
      <AlertDescription>{message}</AlertDescription>
    </Alert>
  )
}

function WebhookAttemptEntry({ attempt, text }: { attempt: DashboardWebhookAttempt; text: UiTextMap }) {
  const [open, setOpen] = useState(true)
  const tone = getWebhookStatusTone(attempt.outcome)

  return (
    <Card>
      <button
        type="button"
        className="flex w-full items-center gap-3 px-4 py-3 text-left"
        onClick={() => setOpen((v) => !v)}
      >
        {open ? (
          <ChevronDown className="size-4 shrink-0 text-muted-foreground" />
        ) : (
          <ChevronRight className="size-4 shrink-0 text-muted-foreground" />
        )}
        <Webhook className="size-4 shrink-0 text-blue-500" />
        <div className="min-w-0 flex-1 space-y-1">
          <span className="block truncate text-sm font-medium">{attempt.item_name ?? attempt.message}</span>
          <span className="text-xs text-muted-foreground">
            {new Date(attempt.attempted_at).toLocaleString()}
          </span>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <Badge variant="outline" className="text-xs">
            {attempt.http_status != null ? attempt.http_status : text.noStatus}
          </Badge>
          <StatusPill tone={tone} label={getWebhookStatusLabel(attempt.outcome, text)} />
        </div>
      </button>

      {open && (
        <CardContent className="border-t pb-3 pt-3 space-y-3">
          <div className="space-y-1 text-xs text-muted-foreground">
            <p>
              <span className="text-foreground">{text.webhookMessageLabel}</span> {attempt.message}
            </p>
            {attempt.payload_event_count != null ? (
              <p>
                <span className="text-foreground">{text.webhookPayloadEventsLabel}</span> {attempt.payload_event_count}
              </p>
            ) : null}
            <p>
              <span className="text-foreground">{text.webhookNotificationLabel}</span>{" "}
              {attempt.notification_type ?? "—"}
              {attempt.item_type ? ` / ${attempt.item_type}` : ""}
            </p>
            {attempt.result_status && (
              <p>
                <span className="text-foreground">{text.webhookResultStatusLabel}</span> {getStatusLabel(attempt.result_status, text)}
              </p>
            )}
          </div>
        </CardContent>
      )}
    </Card>
  )
}

function ActivityEntry({ entry, text }: { entry: DashboardActivity; text: UiTextMap }) {
  const [open, setOpen] = useState(true)
  const Icon = entry.result.item_type === "Movie" ? Film : Tv
  const hasActions = entry.result.actions.length > 0
  return (
    <Card>
      <button
        type="button"
        className="flex w-full items-center gap-3 px-4 py-3 text-left"
        onClick={() => setOpen((v) => !v)}
      >
        {open ? (
          <ChevronDown className="size-4 shrink-0 text-muted-foreground" />
        ) : (
          <ChevronRight className="size-4 shrink-0 text-muted-foreground" />
        )}
        <Icon className="size-4 shrink-0 text-blue-500" />
        <span className="flex-1 truncate text-sm font-medium">{entry.result.name}</span>
        <div className="flex shrink-0 items-center gap-2">
          <Badge variant="outline" className="text-xs">{getItemTypeLabel(entry.result.item_type, text)}</Badge>
          <StatusPill
            tone={entry.result.status === "partial_failure" ? "red" : "green"}
            label={getStatusLabel(entry.result.status, text)}
          />
          <span className="hidden text-xs text-muted-foreground sm:block">
            {new Date(entry.processed_at).toLocaleString()}
          </span>
        </div>
      </button>

      {open && (
        <CardContent className="border-t pb-3 pt-3 space-y-3">
          <div className="text-xs text-muted-foreground sm:hidden">
            {new Date(entry.processed_at).toLocaleString()}
          </div>
          <div className="flex flex-wrap gap-1.5">
            {Object.entries(entry.action_summary).map(([k, v]) => (
              <Badge key={k} variant="outline" className="text-xs">
                {k}: {v}
              </Badge>
            ))}
          </div>
          <div className="space-y-1.5">
            {entry.result.actions.map((action, i) => (
              <ActionRow key={`${action.system}-${action.action}-${i}`} action={action} text={text} />
            ))}
          </div>
          {!hasActions && (
            <p className="text-xs text-muted-foreground">{text.noItemsYet}</p>
          )}
        </CardContent>
      )}
    </Card>
  )
}

function ActionRow({ action, text }: { action: DashboardAction; text: UiTextMap }) {
  return (
    <div className="rounded-lg border p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="outline" className="text-xs">{action.system}</Badge>
          <span className="text-sm font-medium">{action.action}</span>
        </div>
        <StatusPill
          tone={action.status === "failed" ? "red" : action.status === "deleted" ? "green" : "blue"}
          label={getStatusLabel(action.status, text)}
        />
      </div>
      <p className="mt-1.5 text-xs text-muted-foreground">{action.message}</p>
      {action.reason && (
      <p className="mt-1 text-xs text-muted-foreground">
          {text.reasonLabel} <span className="font-mono">{action.reason}</span>
        </p>
      )}
    </div>
  )
}

// ─── Library panel ────────────────────────────────────────────────────────────

function LibrarySeriesTab({
  text,
  library,
  isLoading,
  onRefresh,
  onDelete,
}: {
  text: UiTextMap
  library: LibrarySeriesResponse | null
  isLoading: boolean
  onRefresh: () => void
  onDelete: (target: LibraryDeleteTarget) => void
}) {
  const [search, setSearch] = useState("")
  const [expanded, setExpanded] = useState<Set<number>>(new Set())

  const filtered = useMemo(() => {
    if (!library) return []
    if (!search.trim()) return library.series
    const q = search.toLowerCase()
    return library.series.filter((s) => (s.jellyfin_series_title ?? s.title).toLowerCase().includes(q))
  }, [library, search])

  const toggleExpand = (id: number) => {
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(id)) {
        next.delete(id)
      } else {
        next.add(id)
      }
      return next
    })
  }

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <Button variant="outline" size="sm" onClick={onRefresh} disabled={isLoading}>
          <RefreshCw className={cn("size-4", isLoading && "animate-spin")} />
          {text.refresh}
        </Button>
      </div>

      {isLoading && !library && (
        <div className="space-y-3">
          {[1, 2, 3].map((n) => (
            <Skeleton key={n} className="h-14 w-full rounded-lg" />
          ))}
        </div>
      )}

      {!isLoading && library && filtered.length === 0 && (
        <EmptyState
          title={search ? text.noSeriesMatch : text.noSeriesFound}
          description={
            search ? text.tryDifferentSearch : text.noSeriesSetup
          }
        />
      )}

      {library && library.series.length > 0 && (
        <Input
          placeholder={text.searchPlaceholderSeries}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      )}

      {filtered.length > 0 && (
        <div className="space-y-2">
          {filtered.map((series) => {
            const isOpen = expanded.has(series.sonarr_id)
            const totalBytes = series.seasons.reduce((sum, s) => sum + s.size_bytes, 0)
            const seriesTitle = series.jellyfin_series_title ?? series.title
            const hasDownloadedEpisodes = series.seasons.some(
              (season) => season.episode_file_count > 0,
            )
            return (
              <Card key={series.sonarr_id}>
                <div className="flex w-full items-center gap-3 px-4 py-3">
                  <button
                    type="button"
                    className="flex min-w-0 flex-1 items-center gap-3 text-left"
                    onClick={() => toggleExpand(series.sonarr_id)}
                  >
                    {isOpen ? (
                      <ChevronDown className="size-4 shrink-0 text-muted-foreground" />
                    ) : (
                      <ChevronRight className="size-4 shrink-0 text-muted-foreground" />
                    )}
                    <Tv className="size-4 shrink-0 text-blue-500" />
                    <span className="flex-1 text-sm font-medium">{seriesTitle}</span>
                    <span className="text-xs text-muted-foreground">
                      {series.seasons.length} {text.seasons}
                      {totalBytes > 0 && ` · ${formatBytes(totalBytes)}`}
                    </span>
                  </button>
                  {(hasDownloadedEpisodes || series.has_jellyseerr_request) && <Button
                    variant="ghost"
                    size="sm"
                    className="ml-2 shrink-0 text-red-600 hover:bg-red-50 hover:text-red-700 dark:text-red-400 dark:hover:bg-red-950/40"
                    onClick={() => {
                        onDelete({
                          kind: "series",
                          sonarr_series_id: series.sonarr_id,
                          series_title: seriesTitle,
                          item_type: "Series",
                          jellyfin_item_id: series.jellyfin_series_id,
                        })
                    }}
                  >
                    <Trash2 className="size-3.5" />
                    {text.deleteSeries}
                  </Button>}
                </div>

                {isOpen && series.seasons.length > 0 && (
                  <CardContent className="border-t pt-3 pb-3">
                    <div className="space-y-1.5">
                      {series.seasons.map((season) => (
                        <div
                          key={season.season_number}
                          className="flex items-center gap-3 rounded-md px-2 py-2 hover:bg-muted/40"
                        >
                          <span className="min-w-[80px] text-sm font-medium">
                            {text.season} {season.season_number}
                          </span>
                          <span className="flex-1 text-xs text-muted-foreground">
                            {season.episode_file_count}/{season.episode_count} {text.episodes}
                            {season.size_bytes > 0 && ` · ${formatBytes(season.size_bytes)}`}
                          </span>
                          {(season.episode_file_count > 0 || season.has_jellyseerr_request) && <Button
                            variant="outline"
                            size="sm"
                            className="shrink-0 text-red-600 hover:bg-red-50 hover:text-red-700 dark:text-red-400 dark:hover:bg-red-950/40"
                            onClick={() =>
                        onDelete({
                          kind: "series",
                          sonarr_series_id: series.sonarr_id,
                          series_title: seriesTitle,
                          item_type: "Season",
                          season_number: season.season_number,
                          jellyfin_item_id: season.jellyfin_season_id,
                        })
                            }
                          >
                            <Trash2 className="size-3.5" />
                            {text.delete}
                          </Button>}
                        </div>
                      ))}
                    </div>
                  </CardContent>
                )}

                {isOpen && series.seasons.length === 0 && (
                  <CardContent className="border-t pt-3 pb-3">
                    <p className="text-xs text-muted-foreground">{text.noSeasonsFound}</p>
                  </CardContent>
                )}
              </Card>
            )
          })}
        </div>
      )}
    </div>
  )
}

function LibraryMoviesTab({
  text,
  movies,
  isLoading,
  onRefresh,
  onDelete,
}: {
  text: UiTextMap
  movies: LibraryMoviesResponse | null
  isLoading: boolean
  onRefresh: () => void
  onDelete: (target: LibraryDeleteTarget) => void
}) {
  const [search, setSearch] = useState("")

  const filtered = useMemo(() => {
    if (!movies) return []
    if (!search.trim()) return movies.movies
    const q = search.toLowerCase()
    return movies.movies.filter((m) => (m.jellyfin_movie_title ?? m.title).toLowerCase().includes(q))
  }, [movies, search])

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <Button variant="outline" size="sm" onClick={onRefresh} disabled={isLoading}>
          <RefreshCw className={cn("size-4", isLoading && "animate-spin")} />
          {text.refresh}
        </Button>
      </div>

      {isLoading && !movies && (
        <div className="space-y-3">
          {[1, 2, 3].map((n) => (
            <Skeleton key={n} className="h-12 w-full rounded-lg" />
          ))}
        </div>
      )}

      {!isLoading && movies && filtered.length === 0 && (
        <EmptyState
          title={search ? text.noMoviesMatch : text.noMoviesFound}
          description={
            search ? text.tryDifferentSearch : text.noMoviesSetup
          }
        />
      )}

      {movies && movies.movies.length > 0 && (
        <Input
          placeholder={text.searchPlaceholderMovies}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      )}

      {filtered.length > 0 && (
        <div className="space-y-2">
            {filtered.map((movie) => (
            <Card key={movie.radarr_id}>
              <div className="flex items-center gap-3 px-4 py-3">
                <Film className="size-4 shrink-0 text-purple-500" />
                <span className="flex-1 text-sm font-medium">{movie.jellyfin_movie_title ?? movie.title}</span>
                <span className="text-xs text-muted-foreground">
                  {movie.has_file
                    ? movie.size_bytes > 0
                      ? formatBytes(movie.size_bytes)
                      : text.onDisk
                    : text.noFile}
                </span>
                {(movie.has_file || movie.has_jellyseerr_request) && <Button
                  variant="ghost"
                  size="sm"
                  className="ml-2 shrink-0 text-red-600 hover:bg-red-50 hover:text-red-700 dark:text-red-400 dark:hover:bg-red-950/40"
                  onClick={() =>
                    onDelete({
                      kind: "movie",
                      radarr_movie_id: movie.radarr_id,
                      movie_title: movie.jellyfin_movie_title ?? movie.title,
                      jellyfin_movie_id: movie.jellyfin_movie_id,
                    })
                  }
                >
                  <Trash2 className="size-3.5" />
                  {text.deleteItem}
                </Button>}
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}

function LibraryPanel({
  text,
  library,
  isLibraryLoading,
  libraryMovies,
  isLibraryMoviesLoading,
  isLive,
  onRefreshSeries,
  onRefreshMovies,
  onDelete,
}: {
  text: UiTextMap
  library: LibrarySeriesResponse | null
  isLibraryLoading: boolean
  libraryMovies: LibraryMoviesResponse | null
  isLibraryMoviesLoading: boolean
  isLive: boolean
  onRefreshSeries: () => void
  onRefreshMovies: () => void
  onDelete: (target: LibraryDeleteTarget) => void
}) {
  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-lg font-semibold">{text.library}</h2>
        <p className="text-sm text-muted-foreground">
          {text.libraryDescription}
        </p>
      </div>

      {!isLive && (
        <Alert>
          <Info className="size-4 text-amber-600 dark:text-amber-400" />
          <AlertTitle>{text.dryRunModeInfo}</AlertTitle>
          <AlertDescription>
            {text.noLiveChanges}
          </AlertDescription>
        </Alert>
      )}

      <Tabs defaultValue="series">
        <TabsList>
          <TabsTrigger value="series">
            <Tv className="mr-1.5 size-3.5" />
            {text.series}
          </TabsTrigger>
          <TabsTrigger value="movies">
            <Film className="mr-1.5 size-3.5" />
            {text.movies}
          </TabsTrigger>
        </TabsList>
        <TabsContent value="series" className="mt-4">
          <LibrarySeriesTab
            text={text}
            library={library}
            isLoading={isLibraryLoading}
            onRefresh={onRefreshSeries}
            onDelete={onDelete}
          />
        </TabsContent>
        <TabsContent value="movies" className="mt-4">
          <LibraryMoviesTab
            text={text}
            movies={libraryMovies}
            isLoading={isLibraryMoviesLoading}
            onRefresh={onRefreshMovies}
            onDelete={onDelete}
          />
        </TabsContent>
      </Tabs>
    </div>
  )
}

// ─── Delete confirm modal ──────────────────────────────────────────────────────

function DeleteConfirmModal({
  target,
  text,
  isStarting,
  error,
  isDryRun,
  onConfirm,
  onClose,
}: {
  target: LibraryDeleteTarget | null
  text: UiTextMap
  isStarting: boolean
  error: string | null
  isDryRun: boolean
  onConfirm: () => void
  onClose: () => void
}) {
  if (!target) return null

  const label =
    target.kind === "movie"
      ? `"${target.movie_title}"`
      : target.item_type === "Season"
        ? text.seasonOfSeries
            .replace("{{season}}", String(target.season_number))
            .replace("{{series}}", `"${target.series_title}"`)
        : `"${target.series_title}"`

  return (
    <Modal
      open={true}
      title={text.titleDeleteConfirmation.replace("{{title}}", label)}
      onClose={onClose}
      footer={
        <div className="flex gap-2">
          <Button variant="outline" onClick={onClose} disabled={isStarting}>
            {text.cancel}
          </Button>
          <Button variant="destructive" onClick={onConfirm} disabled={isStarting}>
            {isStarting ? (
              <LoaderCircle className="mr-1 size-3.5 animate-spin" />
            ) : (
              <Trash2 className="mr-1 size-3.5" />
            )}
            {isDryRun ? text.simulate : text.delete}
          </Button>
        </div>
      }
    >
      <div className="space-y-4">
        {isDryRun && (
          <Alert>
            <Info className="size-4 text-amber-600 dark:text-amber-400" />
            <AlertTitle>{text.dryRunModeNotice}</AlertTitle>
            <AlertDescription>{text.dryRunNoChanges}</AlertDescription>
          </Alert>
        )}
        <p className="text-sm text-muted-foreground">
          {text.confirmDeleteDescription}
        </p>

        {error && <ErrorBanner message={error} text={text} />}
      </div>
    </Modal>
  )
}

function BackgroundJobsPanel({
  jobs,
  text,
  onDismiss,
}: {
  jobs: ManualDeleteJob[]
  text: UiTextMap
  onDismiss: (jobId: string) => void
}) {
  const [expanded, setExpanded] = useState(true)
  if (jobs.length === 0) return null

  const activeCount = jobs.reduce(
    (count, job) => count + (job.status === "queued" || job.status === "running" ? 1 : 0),
    0,
  )

  return (
    <aside
      className="fixed inset-x-4 bottom-4 z-40 overflow-hidden rounded-xl border bg-background/98 shadow-2xl backdrop-blur sm:left-auto sm:w-[23rem]"
      aria-label={text.backgroundTasks}
    >
      <button
        type="button"
        className="flex w-full items-center gap-2 px-3.5 py-3 text-left transition-colors hover:bg-muted/60"
        onClick={() => setExpanded((current) => !current)}
        aria-expanded={expanded}
      >
        {expanded ? (
          <ChevronDown className="size-4 text-muted-foreground" />
        ) : (
          <ChevronRight className="size-4 text-muted-foreground" />
        )}
        <span className="flex-1 text-sm font-medium">{text.backgroundTasks}</span>
        <Badge variant="outline" className="text-xs">
          {activeCount > 0 ? `${activeCount} ${text.active}` : `${jobs.length} ${text.recent}`}
        </Badge>
      </button>

      {expanded ? (
        <div className="max-h-[min(28rem,65vh)] space-y-2 overflow-y-auto border-t p-2.5" aria-live="polite">
          {jobs.map((job) => {
            const isActive = job.status === "queued" || job.status === "running"
            const hasProblem = job.status === "failed" || job.result?.status === "partial_failure"
            const itemName = job.item_name ?? `${getItemTypeLabel(job.item_type, text)}: ${text.deletion}`

            return (
              <div key={job.id} className="rounded-lg border bg-card p-3" role="status">
                <div className="flex items-start gap-2.5">
                  <div className="mt-0.5 shrink-0">
                    {isActive ? (
                      <LoaderCircle className="size-4 animate-spin text-blue-500" />
                    ) : hasProblem ? (
                      <CircleAlert className="size-4 text-red-500" />
                    ) : (
                      <CheckCircle2 className="size-4 text-emerald-500" />
                    )}
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-start gap-2">
                      <p className="min-w-0 flex-1 truncate text-sm font-medium" title={itemName}>
                        {itemName}
                      </p>
                      {!isActive ? (
                        <Button
                          variant="ghost"
                          size="icon-xs"
                          className="-mr-1 -mt-1 shrink-0 text-muted-foreground"
                          onClick={() => onDismiss(job.id)}
                          aria-label={`${text.dismiss}: ${itemName}`}
                        >
                          <X className="size-3.5" />
                        </Button>
                      ) : null}
                    </div>
                    <p className="mt-0.5 text-xs leading-relaxed text-muted-foreground">
                      {job.error ?? job.message}
                    </p>
                    <div
                      className="mt-2 h-1.5 overflow-hidden rounded-full bg-muted"
                      role="progressbar"
                      aria-label={`${itemName}: ${text.progress}`}
                      aria-valuemin={0}
                      aria-valuemax={100}
                      aria-valuenow={job.progress_percent}
                    >
                      <div
                        className={cn(
                          "h-full rounded-full transition-[width] duration-500",
                          hasProblem
                            ? "bg-red-500"
                            : job.status === "completed"
                              ? "bg-emerald-500"
                              : "bg-blue-500",
                        )}
                        style={{ width: `${job.progress_percent}%` }}
                      />
                    </div>
                    <div className="mt-1.5 flex items-center justify-between gap-2 text-[11px] text-muted-foreground">
                      <span>{getStatusLabel(job.phase, text)}</span>
                      <span>
                        {job.result ? `${job.result.actions.length} ${text.actions} · ` : ""}
                        {job.progress_percent}%
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      ) : null}
    </aside>
  )
}

// ─── Utilities ────────────────────────────────────────────────────────────────

function formatMediaTitle(itemType: string, name: string): string {
  return `${itemType}: ${name}`
}

function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B"
  const k = 1024
  const sizes = ["B", "KB", "MB", "GB", "TB"]
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return `${(bytes / Math.pow(k, i)).toFixed(1)} ${sizes[i]}`
}

function normalizeError(error: unknown): string {
  if (error instanceof Error) return error.message
  return "Unexpected request error"
}

function getWebhookStatusTone(outcome: string): "blue" | "green" | "red" {
  if (outcome === "processed") return "green"
  if (outcome === "rejected_auth" || outcome === "invalid_payload") return "red"
  return "blue"
}

function getWebhookStatusLabel(outcome: string, text: UiTextMap = getUiText(DEFAULT_UI_LANG)): string {
  switch (outcome) {
    case "processed": return text.webhookReceived
    case "rejected_auth": return text.tokenMismatch
    case "invalid_payload": return text.payloadRejected
    default: return text.noDeliveryYet
  }
}

function getServices(config: RuntimeConfigPayload | null, family: ServiceFamily): ServiceRecord[] {
  if (!config) return []
  switch (family) {
    case "radarr": return config.radarr
    case "sonarr": return config.sonarr
    case "jellyseerr": return config.jellyseerr
    case "downloaders": return config.downloaders
    case "jellyfin_server": return config.jellyfin
  }
}

function resolveActiveService(services: ServiceRecord[]): ServiceRecord | null {
  const enabled = services.filter((s) => s.enabled)
  if (enabled.length === 0) return null
  return enabled.find((s) => s.is_default) ?? enabled[0] ?? null
}

function isServiceFamily(step: SetupStepId): step is ServiceFamily {
  return SERVICE_FAMILIES.includes(step as ServiceFamily)
}

function generateWebhookToken(): string {
  const bytes = new Uint8Array(24)
  window.crypto.getRandomValues(bytes)
  return Array.from(bytes, (v) => v.toString(16).padStart(2, "0")).join("")
}

function isSetupStepReady(step: SetupStepId, config: RuntimeConfigPayload | null): boolean {
  if (!config) return false
  if (step === "general") return Boolean(config.general.webhook_shared_token)
  if (!isServiceFamily(step)) return false
  return Boolean(resolveActiveService(getServices(config, step)))
}


function toDraft(service: ServiceRecord): ServiceDraft {
  return {
    id: service.id,
    name: service.name,
    url: service.url,
    enabled: service.enabled,
    is_default: service.is_default,
    api_key: "api_key" in service ? service.api_key : "",
    username: "username" in service ? service.username : "",
    password: "password" in service ? service.password : "",
  }
}

function buildServicePayload(family: ServiceFamily, draft: ServiceDraft) {
  const base = { name: draft.name, url: draft.url, enabled: draft.enabled, is_default: draft.is_default }
  switch (family) {
    case "radarr":
    case "sonarr":
    case "jellyseerr":
    case "jellyfin_server":
      return { ...base, api_key: draft.api_key }
    case "downloaders":
      return { ...base, username: draft.username, password: draft.password }
  }
}

function matchesActivity(entry: DashboardActivity, filter: string): boolean {
  if (!filter.trim()) return true
  const query = filter.toLowerCase()
  const haystack = [
    entry.result.name,
    entry.result.item_type,
    entry.result.status,
    entry.result.item_id,
    ...entry.result.actions.flatMap((a) => [a.system, a.action, a.status, a.message, a.reason ?? ""]),
  ]
    .join(" ")
    .toLowerCase()
  return haystack.includes(query)
}

function matchesWebhookAttempt(attempt: DashboardWebhookAttempt, filter: string): boolean {
  if (!filter.trim()) return true
  const query = filter.toLowerCase()
  const haystack = [
    attempt.outcome,
    attempt.message,
    String(attempt.http_status),
    attempt.notification_type ?? "",
    attempt.item_type ?? "",
    attempt.item_name ?? "",
    attempt.result_status ?? "",
    attempt.payload_event_count != null ? String(attempt.payload_event_count) : "",
  ]
    .join(" ")
    .toLowerCase()
  return haystack.includes(query)
}

export default CleanArrApp
