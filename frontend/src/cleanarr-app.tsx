import {
  Activity,
  ArrowRight,
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
  Plus,
  RefreshCw,
  Server,
  Settings2,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  TestTubeDiagonal,
  Trash2,
  Tv,
  type LucideIcon,
  UserRound,
  UserRoundPlus,
  Webhook,
  Zap,
} from "lucide-react"
import { useCallback, useDeferredValue, useEffect, useMemo, useRef, useState } from "react"

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
import type { AuthSessionPayload, AuthStatusPayload } from "@/lib/auth"
import type {
  DashboardAction,
  DashboardActivity,
  DashboardPayload,
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
  ManualDeleteResponse,
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

type MainTab = "dashboard" | "setup" | "activity" | "library"
type ServiceFamily = "radarr" | "sonarr" | "jellyseerr" | "downloaders" | "jellyfin_server"
type SetupStepId = "general" | "jellyfin" | ServiceFamily
type AuthMode = "register" | "login"
type ServiceRecord =
  | RadarrServiceConfig
  | SonarrServiceConfig
  | JellyseerrServiceConfig
  | QbittorrentServiceConfig
  | JellyfinServiceConfig

type FlashState =
  | {
      kind: "success" | "error"
      message: string
    }
  | null

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

type JellyfinFieldInstruction = {
  label: string
  value: string
  hint: string
  copyValue?: string
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
    id: "general",
    title: "Runtime settings",
    description: "Dry Run mode, timeout, and the Jellyfin webhook token.",
    accent: "blue",
    icon: Settings2,
  },
  {
    id: "jellyfin",
    title: "Configure Jellyfin",
    description: "Add the Generic webhook that sends ItemDeleted events to CleanArr.",
    accent: "blue",
    icon: Webhook,
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
    icon: ShieldCheck,
  },
  {
    id: "downloaders",
    title: "qBittorrent",
    description: "Downloader used for safe hash deletion.",
    accent: "green",
    icon: Download,
  },
  {
    id: "jellyfin_server",
    title: "Jellyfin Server",
    description: "Optional: enables library browsing and instant removal.",
    accent: "blue",
    icon: Server,
  },
]

const EMPTY_DRAFTS: Record<ServiceFamily, ServiceDraft> = {
  radarr: { name: "Radarr", url: "", api_key: "", username: "", password: "", enabled: true, is_default: true },
  sonarr: { name: "Sonarr", url: "", api_key: "", username: "", password: "", enabled: true, is_default: true },
  jellyseerr: { name: "Jellyseerr", url: "", api_key: "", username: "", password: "", enabled: true, is_default: true },
  downloaders: { name: "qBittorrent", url: "", api_key: "", username: "", password: "", enabled: true, is_default: true },
  jellyfin_server: { name: "Jellyfin", url: "", api_key: "", username: "", password: "", enabled: true, is_default: true },
}

const GENERAL_SETUP_STEPS = [
  "Keep CleanArr in Dry Run until all services test green.",
  "Set a webhook token. Jellyfin must send the same X-Webhook-Token header.",
  "Only switch to Live mode after Radarr, Sonarr, Jellyseerr, and qBittorrent are configured.",
]

const GENERAL_SETUP_HELP = [
  "Jellyfin → Dashboard → Plugins → Webhook → Add Generic.",
  "Header name: X-Webhook-Token. Header value: the same token you save here.",
]

const JELLYFIN_INSTALL_STEPS = [
  "Open Jellyfin → Dashboard → Catalog.",
  "Find the plugin named Webhook and install it.",
  "Restart Jellyfin if the plugin manager asks for it.",
  "After restart, open Jellyfin → Dashboard → Plugins → Webhook.",
]

const JELLYFIN_CONFIG_STEPS = [
  "Open Jellyfin → Dashboard → Plugins → Webhook.",
  "Click Add Generic Destination.",
  "Fill the form exactly like the field guide below.",
  "Paste the exact request body template from CleanArr without editing the variable names.",
  "Save the Webhook plugin page in Jellyfin.",
]

const JELLYFIN_ITEM_TYPE_STEPS = [
  "Leave only ItemDeleted enabled in Notification types for this destination.",
  "Enable Movies, Series, Seasons, and Episodes.",
  "Disable Albums, Songs, and generic Videos.",
  "Leave Send all properties off. CleanArr expects the explicit custom JSON body below.",
]

const JELLYFIN_SAVE_STEPS = [
  "Click Save in Jellyfin after you finish the Generic destination form.",
  "Do not edit the JSON keys in the template body. CleanArr validates them strictly.",
  "If you regenerate the token in CleanArr later, update the X-Webhook-Token header in Jellyfin too.",
]

const JELLYFIN_VERIFY_STEPS = [
  "Jellyfin Generic does not expose a built-in test button in the plugin UI.",
  "First run the cURL smoke test below to prove CleanArr is reachable from the browser side.",
  "Then delete one throwaway movie or episode in Jellyfin to trigger a real ItemDeleted event.",
  "Wait up to 15 seconds for auto-refresh, or press Refresh in the CleanArr header.",
]

const JELLYFIN_TROUBLESHOOTING_STEPS = [
  "If status stays at No delivery yet, double-check the Webhook Url and confirm the destination is enabled in Jellyfin.",
  "If status shows Token mismatch, update the X-Webhook-Token header in Jellyfin so it matches CleanArr runtime settings exactly.",
  "If status shows Payload rejected, paste the exact CleanArr payload template again without editing field names.",
  "If Jellyfin still sends nothing, raise Jellyfin.Plugin.Webhook logging to Debug and inspect Jellyfin server logs.",
]

// ─── Main component ───────────────────────────────────────────────────────────

function CleanArrApp() {
  const [dashboard, setDashboard] = useState<DashboardPayload | null>(null)
  const [config, setConfig] = useState<RuntimeConfigPayload | null>(null)
  const [authStatus, setAuthStatus] = useState<AuthStatusPayload | null>(null)
  const [dashboardError, setDashboardError] = useState<string | null>(null)
  const [configError, setConfigError] = useState<string | null>(null)
  const [authError, setAuthError] = useState<string | null>(null)
  const [flash, setFlash] = useState<FlashState>(null)
  const [isDashboardLoading, setIsDashboardLoading] = useState(true)
  const [isConfigLoading, setIsConfigLoading] = useState(false)
  const [isAuthLoading, setIsAuthLoading] = useState(true)
  const [isAuthSubmitting, setIsAuthSubmitting] = useState(false)
  const [activityFilter, setActivityFilter] = useState("")
  const [authMode, setAuthMode] = useState<AuthMode>("login")
  const [activeTab, setActiveTab] = useState<MainTab>("setup")
  const [activeSetupStep, setActiveSetupStep] = useState<SetupStepId>("general")
  const [authForm, setAuthForm] = useState({ username: "", password: "", confirmPassword: "" })
  const [generalModalOpen, setGeneralModalOpen] = useState(false)
  const [serviceModal, setServiceModal] = useState<ServiceModalState | null>(null)
  const [sessionToken, setSessionToken] = useState(() => readSessionCookie())
  const hasAutoNavigated = useRef(false)

  const [library, setLibrary] = useState<LibrarySeriesResponse | null>(null)
  const [isLibraryLoading, setIsLibraryLoading] = useState(false)
  const [libraryError, setLibraryError] = useState<string | null>(null)
  const [libraryMovies, setLibraryMovies] = useState<LibraryMoviesResponse | null>(null)
  const [isLibraryMoviesLoading, setIsLibraryMoviesLoading] = useState(false)
  const [libraryMoviesError, setLibraryMoviesError] = useState<string | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<LibraryDeleteTarget | null>(null)
  const [isDeleting, setIsDeleting] = useState(false)
  const [deleteResult, setDeleteResult] = useState<ManualDeleteResponse | null>(null)
  const [deleteError, setDeleteError] = useState<string | null>(null)

  const deferredFilter = useDeferredValue(activityFilter)

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
        const detail = await response.text()
        if (
          (response.status === 401 || response.status === 403) &&
          url.startsWith("/api/config")
        ) {
          setSessionToken("")
        }
        throw new Error(`${response.status}: ${detail || response.statusText}`)
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
        setDashboardError(null)
      }
      try {
        const payload = await fetchJson<DashboardPayload>("/api/dashboard")
        setDashboard(payload)
        setDashboardError(null)
      } catch (error) {
        setDashboardError(normalizeError(error))
      } finally {
        setIsDashboardLoading(false)
      }
    },
    [fetchJson],
  )

  const loadAuth = useCallback(async () => {
    setIsAuthLoading(true)
    setAuthError(null)
    try {
      const payload = await fetchJson<AuthStatusPayload>("/api/auth/status")
      setAuthStatus(payload)
      setAuthMode(payload.requires_registration ? "register" : "login")
      if (!payload.authenticated) {
        setConfig(null)
      }
    } catch (error) {
      setAuthError(normalizeError(error))
    } finally {
      setIsAuthLoading(false)
    }
  }, [fetchJson])

  const loadConfig = useCallback(async () => {
    setIsConfigLoading(true)
    setConfigError(null)
    try {
      const payload = await fetchJson<RuntimeConfigPayload>("/api/config")
      setConfig(payload)
    } catch (error) {
      setConfig(null)
      setConfigError(normalizeError(error))
    } finally {
      setIsConfigLoading(false)
    }
  }, [fetchJson])

  const loadLibrary = useCallback(async () => {
    setIsLibraryLoading(true)
    setLibraryError(null)
    try {
      const payload = await fetchJson<LibrarySeriesResponse>("/api/library/series")
      setLibrary(payload)
    } catch (error) {
      setLibraryError(normalizeError(error))
    } finally {
      setIsLibraryLoading(false)
    }
  }, [fetchJson])

  const loadLibraryMovies = useCallback(async () => {
    setIsLibraryMoviesLoading(true)
    setLibraryMoviesError(null)
    try {
      const payload = await fetchJson<LibraryMoviesResponse>("/api/library/movies")
      setLibraryMovies(payload)
    } catch (error) {
      setLibraryMoviesError(normalizeError(error))
    } finally {
      setIsLibraryMoviesLoading(false)
    }
  }, [fetchJson])

  const executeDelete = useCallback(async () => {
    if (!deleteTarget) return
    setIsDeleting(true)
    setDeleteError(null)
    setDeleteResult(null)
    try {
      let body: Record<string, unknown>
      if (deleteTarget.kind === "movie") {
        body = {
          item_type: "Movie",
          radarr_movie_id: deleteTarget.radarr_movie_id,
          jellyfin_item_id: deleteTarget.jellyfin_movie_id ?? null,
        }
      } else {
        body = {
          item_type: deleteTarget.item_type,
          sonarr_series_id: deleteTarget.sonarr_series_id,
          season_number: deleteTarget.season_number ?? null,
          jellyfin_item_id: deleteTarget.jellyfin_item_id ?? null,
        }
      }
      const result = await fetchJson<ManualDeleteResponse>("/api/actions/delete", {
        method: "POST",
        body: JSON.stringify(body),
      })
      setDeleteResult(result)
      if (deleteTarget.kind === "movie") {
        void loadLibraryMovies()
      } else {
        void loadLibrary()
      }
    } catch (error) {
      setDeleteError(normalizeError(error))
    } finally {
      setIsDeleting(false)
    }
  }, [deleteTarget, fetchJson, loadLibrary, loadLibraryMovies])

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
    if (authStatus?.authenticated) {
      void loadConfig()
    } else if (authStatus && !authStatus.authenticated) {
      setConfig(null)
      setConfigError(null)
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
    writeSessionCookie(sessionToken)
  }, [sessionToken])

  // Auto-dismiss flash after 4s
  useEffect(() => {
    if (!flash) return undefined
    const id = window.setTimeout(() => setFlash(null), 4000)
    return () => window.clearTimeout(id)
  }, [flash])

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
  const jellyfinTemplatePreview = dashboard?.jellyfin_template ?? ""
  const samplePayloadPreview = JSON.stringify(dashboard?.sample_payload ?? {}, null, 2)
  const curlPreview = [
    `curl -X POST ${origin}/webhook/jellyfin \\`,
    '  -H "Content-Type: application/json" \\',
    '  -H "X-Webhook-Token: <WEBHOOK_SHARED_TOKEN>" \\',
    `  -d '${samplePayloadPreview.replaceAll("\n", "\n  ")}'`,
  ].join("\n")

  const filteredActivity = useMemo(
    () => (dashboard?.recent_activity ?? []).filter((e) => matchesActivity(e, deferredFilter)),
    [dashboard?.recent_activity, deferredFilter],
  )

  const configuredServicesCount = useMemo(
    () => SERVICE_FAMILIES.reduce((n, f) => n + getServices(config, f).length, 0),
    [config],
  )

  const allServicesConfigured = SERVICE_FAMILIES.every((f) =>
    Boolean(resolveActiveService(getServices(config, f))),
  )

  const activeServiceCount =
    dashboard?.downstream.filter((s) => s.configured).length ?? 0

  const deletedActions = (dashboard?.recent_activity ?? []).reduce(
    (n, e) => n + (e.action_summary.deleted ?? 0),
    0,
  )

  const latestActivity = dashboard?.recent_activity[0] ?? null
  const activeStepMeta = SETUP_STEPS.find((s) => s.id === activeSetupStep)
  const activeStepServiceMeta = isServiceFamily(activeSetupStep)
    ? SERVICE_META[activeSetupStep]
    : null

  const submitAuthForm = async () => {
    if (authMode === "register" && authForm.password !== authForm.confirmPassword) {
      setAuthError("Passwords do not match.")
      return
    }
    setIsAuthSubmitting(true)
    setAuthError(null)
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
      setActiveTab("setup")
      setActiveSetupStep("general")
      setFlash({
        kind: "success",
        message:
          authMode === "register"
            ? "Administrator created. Start with runtime settings and service setup."
            : "Signed in successfully.",
      })
    } catch (error) {
      setAuthError(normalizeError(error))
    } finally {
      setIsAuthSubmitting(false)
    }
  }

  const logout = async () => {
    try {
      await fetchJson<void>("/api/auth/logout", { method: "POST" })
    } catch {
      // Session might already be invalid; local reset is enough.
    }
    setSessionToken("")
    setAuthForm({ username: "", password: "", confirmPassword: "" })
    setFlash(null)
  }

  const saveGeneralSettings = async (payload: GeneralConfig) => {
    const next = await fetchJson<RuntimeConfigPayload>("/api/config/general", {
      method: "PUT",
      body: JSON.stringify(payload),
    })
    setConfig(next)
    setFlash({ kind: "success", message: "Runtime settings saved." })
    const nextStep = findNextIncompleteSetupStep(next)
    if (nextStep) setActiveSetupStep(nextStep)
  }

  const saveServiceDraft = async (family: ServiceFamily, draft: ServiceDraft) => {
    const meta = SERVICE_META[family]
    const body = JSON.stringify(buildServicePayload(family, draft))
    const next = draft.id
      ? await fetchJson<RuntimeConfigPayload>(`${meta.endpoint}/${draft.id}`, { method: "PUT", body })
      : await fetchJson<RuntimeConfigPayload>(meta.endpoint, { method: "POST", body })
    setConfig(next)
    setServiceModal(null)
    setFlash({ kind: "success", message: `${meta.title} ${draft.id ? "updated" : "added"}.` })
    const nextStep = findNextIncompleteSetupStep(next)
    if (nextStep) setActiveSetupStep(nextStep)
  }

  const deleteServiceDraft = async (family: ServiceFamily, serviceId: string) => {
    const meta = SERVICE_META[family]
    await fetchJson<void>(`${meta.endpoint}/${serviceId}`, { method: "DELETE" })
    const next = await fetchJson<RuntimeConfigPayload>("/api/config")
    setConfig(next)
    setServiceModal(null)
    setFlash({ kind: "success", message: `${meta.title} removed.` })
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
        authError={authError}
        isSubmitting={isAuthSubmitting}
        requiresRegistration={Boolean(authStatus?.requires_registration)}
        onFieldChange={(field, value) => setAuthForm((c) => ({ ...c, [field]: value }))}
        onSubmit={() => void submitAuthForm()}
      />
    )
  }

  const isLive = dashboard ? !dashboard.service.dry_run : false

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
          <TabsList className="h-8 gap-0.5 bg-transparent p-0">
            <TabsTrigger
              value="dashboard"
              className="h-8 gap-1.5 rounded-md px-3 text-sm data-[state=active]:bg-muted"
            >
              <LayoutDashboard className="size-3.5" />
              Dashboard
            </TabsTrigger>
            <TabsTrigger
              value="setup"
              className="h-8 gap-1.5 rounded-md px-3 text-sm data-[state=active]:bg-muted"
            >
              <Settings2 className="size-3.5" />
              Setup
              {setupCompletionCount < SETUP_STEPS.length && (
                <span className="ml-0.5 flex size-4 items-center justify-center rounded-full bg-amber-500 text-[10px] font-semibold text-white">
                  {SETUP_STEPS.length - setupCompletionCount}
                </span>
              )}
              {setupCompletionCount === SETUP_STEPS.length && (
                <CheckCircle2 className="ml-0.5 size-3.5 text-green-500" />
              )}
            </TabsTrigger>
            <TabsTrigger
              value="activity"
              className="h-8 gap-1.5 rounded-md px-3 text-sm data-[state=active]:bg-muted"
            >
              <Activity className="size-3.5" />
              Activity
            </TabsTrigger>
            <TabsTrigger
              value="library"
              className="h-8 gap-1.5 rounded-md px-3 text-sm data-[state=active]:bg-muted"
            >
              <Library className="size-3.5" />
              Library
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
                {isLive ? "Live" : "Dry run"}
              </div>
            )}

            <Button
              variant="ghost"
              size="icon"
              className="size-8"
              onClick={() => {
                void loadDashboard()
                void loadConfig()
              }}
              title="Refresh"
            >
              <RefreshCw
                className={cn(
                  "size-4",
                  (isDashboardLoading || isConfigLoading) && "animate-spin",
                )}
              />
            </Button>

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
              title="Log out"
            >
              <LogOut className="size-4 text-red-500 dark:text-red-400" />
            </Button>
          </div>
        </div>
      </header>

      {/* Page content */}
      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-6 sm:px-6">
        {flash && (
          <div className="mb-5">
            <Alert variant={flash.kind === "error" ? "destructive" : "default"}>
              {flash.kind === "error" ? (
                <CircleAlert className="size-4" />
              ) : (
                <CheckCircle2 className="size-4 text-green-600 dark:text-green-400" />
              )}
              <AlertTitle>{flash.kind === "error" ? "Action failed" : "Saved"}</AlertTitle>
              <AlertDescription>{flash.message}</AlertDescription>
            </Alert>
          </div>
        )}

        {(activeTab === "dashboard" || activeTab === "activity") && dashboardError && (
          <div className="mb-5">
            <Alert variant="destructive">
              <CircleAlert className="size-4" />
              <AlertTitle>Dashboard unavailable</AlertTitle>
              <AlertDescription>{dashboardError}</AlertDescription>
            </Alert>
          </div>
        )}

        {/* ── Dashboard ── */}
        <TabsContent value="dashboard" className="mt-0">
          <DashboardPanel
            config={config}
            dashboard={dashboard}
            isDashboardLoading={isDashboardLoading}
            setupCompletionCount={setupCompletionCount}
            configuredServicesCount={configuredServicesCount}
            activeServiceCount={activeServiceCount}
            deletedActions={deletedActions}
            latestActivity={latestActivity}
            allServicesConfigured={allServicesConfigured}
            isLive={isLive}
            onOpenSetup={() => setActiveTab("setup")}
          />
        </TabsContent>

        {/* ── Setup ── */}
        <TabsContent value="setup" className="mt-0">
          {configError && (
            <div className="mb-5">
              <Alert variant="destructive">
                <CircleAlert className="size-4" />
                <AlertTitle>Config unavailable</AlertTitle>
                <AlertDescription>{configError}</AlertDescription>
              </Alert>
            </div>
          )}
          <SetupWorkspace
            activeStep={activeSetupStep}
            activeStepMeta={activeStepMeta ?? SETUP_STEPS[0]}
            activeServiceMeta={activeStepServiceMeta}
            config={config}
            dashboard={dashboard}
            isConfigLoading={isConfigLoading}
            completionCount={setupCompletionCount}
            origin={origin}
            jellyfinTemplatePreview={jellyfinTemplatePreview}
            curlPreview={curlPreview}
            onSelectStep={setActiveSetupStep}
            onEditGeneral={() => setGeneralModalOpen(true)}
            onGoToDashboard={() => setActiveTab("dashboard")}
            onAddService={(family) => {
              setActiveSetupStep(family)
              setServiceModal({ family, draft: structuredClone(EMPTY_DRAFTS[family]) })
            }}
            onEditService={(family, service) => {
              setActiveSetupStep(family)
              setServiceModal({ family, draft: toDraft(service) })
            }}
          />
        </TabsContent>

        {/* ── Activity ── */}
        <TabsContent value="activity" className="mt-0">
          <ActivityPanel
            filteredActivity={filteredActivity}
            activityFilter={activityFilter}
            onFilterChange={setActivityFilter}
          />
        </TabsContent>

        {/* ── Library ── */}
        <TabsContent value="library" className="mt-0">
          <LibraryPanel
            library={library}
            isLibraryLoading={isLibraryLoading}
            libraryError={libraryError}
            libraryMovies={libraryMovies}
            isLibraryMoviesLoading={isLibraryMoviesLoading}
            libraryMoviesError={libraryMoviesError}
            isLive={isLive}
            onRefreshSeries={() => void loadLibrary()}
            onRefreshMovies={() => void loadLibraryMovies()}
            onDelete={(target) => {
              setDeleteTarget(target)
              setDeleteResult(null)
              setDeleteError(null)
            }}
          />
        </TabsContent>
      </main>

      {/* Modals */}
      <GeneralSettingsModal
        open={generalModalOpen}
        config={config?.general ?? null}
        onClose={() => setGeneralModalOpen(false)}
        onSave={async (payload) => {
          await saveGeneralSettings(payload)
          setGeneralModalOpen(false)
        }}
      />

      <ServiceModal
        state={serviceModal}
        onClose={() => setServiceModal(null)}
        onSave={saveServiceDraft}
        onDelete={deleteServiceDraft}
        onTest={testServiceDraft}
      />

      <DeleteConfirmModal
        target={deleteTarget}
        isDeleting={isDeleting}
        result={deleteResult}
        error={deleteError}
        isDryRun={!isLive}
        onConfirm={() => void executeDelete()}
        onClose={() => {
          setDeleteTarget(null)
          setDeleteResult(null)
          setDeleteError(null)
        }}
      />
    </Tabs>
  )
}

// ─── Auth screens ─────────────────────────────────────────────────────────────

function AuthScreen({
  authMode,
  authForm,
  authError,
  isSubmitting,
  requiresRegistration,
  onFieldChange,
  onSubmit,
}: {
  authMode: AuthMode
  authForm: { username: string; password: string; confirmPassword: string }
  authError: string | null
  isSubmitting: boolean
  requiresRegistration: boolean
  onFieldChange: (field: "username" | "password" | "confirmPassword", value: string) => void
  onSubmit: () => void
}) {
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
            {requiresRegistration ? "Create administrator" : "Sign in"}
          </CardTitle>
          <CardDescription>
            {requiresRegistration
              ? "First launch — create the admin account."
              : "Enter your CleanArr credentials."}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {authError && (
            <Alert variant="destructive">
              <CircleAlert className="size-4" />
              <AlertTitle>Authentication failed</AlertTitle>
              <AlertDescription>{authError}</AlertDescription>
            </Alert>
          )}

          <FormField label="Username" htmlFor="auth-username">
            <Input
              id="auth-username"
              value={authForm.username}
              onChange={(e) => onFieldChange("username", e.target.value)}
            />
          </FormField>

          <FormField label="Password" htmlFor="auth-password">
            <Input
              id="auth-password"
              type="password"
              value={authForm.password}
              onChange={(e) => onFieldChange("password", e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !requiresRegistration) onSubmit()
              }}
            />
          </FormField>

          {requiresRegistration && (
            <FormField label="Confirm password" htmlFor="auth-confirm">
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
            {authMode === "register" ? "Create administrator" : "Sign in"}
          </Button>
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

function DashboardPanel({
  config,
  dashboard,
  isDashboardLoading,
  setupCompletionCount,
  configuredServicesCount,
  activeServiceCount,
  deletedActions,
  latestActivity,
  allServicesConfigured,
  isLive,
  onOpenSetup,
}: {
  config: RuntimeConfigPayload | null
  dashboard: DashboardPayload | null
  isDashboardLoading: boolean
  setupCompletionCount: number
  configuredServicesCount: number
  activeServiceCount: number
  deletedActions: number
  latestActivity: DashboardActivity | null
  allServicesConfigured: boolean
  isLive: boolean
  onOpenSetup: () => void
}) {
  return (
    <section className="space-y-5">
      {/* Mode hero */}
      <div
        className={cn(
          "flex items-center gap-5 rounded-xl border-2 p-5",
          isLive
            ? "border-green-200/70 bg-green-50/40 dark:border-green-900/60 dark:bg-green-950/20"
            : "border-amber-200/70 bg-amber-50/40 dark:border-amber-900/60 dark:bg-amber-950/20",
        )}
      >
        <div
          className={cn(
            "flex size-14 shrink-0 items-center justify-center rounded-full",
            isLive
              ? "bg-green-100 dark:bg-green-950/60"
              : "bg-amber-100 dark:bg-amber-950/60",
          )}
        >
          {isLive ? (
            <Zap className="size-7 text-green-600 dark:text-green-400" />
          ) : (
            <ShieldAlert className="size-7 text-amber-600 dark:text-amber-400" />
          )}
        </div>
        <div className="flex-1">
          <p className="text-xl font-semibold">{isLive ? "Live mode" : "Dry run"}</p>
          <p className="mt-0.5 text-sm text-muted-foreground">
            {isLive
              ? "Real deletions are active across all downstream services."
              : "No deletions will be performed. Safe for testing and validation."}
          </p>
        </div>
        {!allServicesConfigured && (
          <Button variant="outline" size="sm" onClick={onOpenSetup} className="shrink-0">
            <ArrowRight className="size-4 text-blue-600 dark:text-blue-400" />
            Complete setup
          </Button>
        )}
        {allServicesConfigured && !isLive && (
          <Button variant="outline" size="sm" onClick={onOpenSetup} className="shrink-0">
            <Settings2 className="size-4 text-blue-600 dark:text-blue-400" />
            Enable live mode
          </Button>
        )}
      </div>

      {/* Metrics */}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <MetricCard
          title="Mode"
          value={isLive ? "Live" : "Dry run"}
          description="Current deletion mode"
          icon={ShieldAlert}
          tone={isLive ? "green" : "red"}
        />
        <MetricCard
          title="Setup"
          value={`${setupCompletionCount}/${SETUP_STEPS.length}`}
          description="Steps complete"
          icon={Settings2}
          tone="blue"
        />
        <MetricCard
          title="Integrations"
          value={String(configuredServicesCount)}
          description="Saved service profiles"
          icon={Server}
          tone="green"
        />
        <MetricCard
          title="Deletions"
          value={String(deletedActions)}
          description="Observed in activity log"
          icon={Activity}
          tone="red"
        />
      </div>

      {/* Services + snapshot */}
      <div className="grid gap-5 xl:grid-cols-2">
        {/* Service health */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-base">
              <Server className="size-4 text-green-600 dark:text-green-400" />
              Downstream services
            </CardTitle>
            <CardDescription>Active targets seen by the live runtime.</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-2 sm:grid-cols-2">
            {isDashboardLoading && !dashboard ? (
              <>
                <Skeleton className="h-16 w-full" />
                <Skeleton className="h-16 w-full" />
                <Skeleton className="h-16 w-full" />
                <Skeleton className="h-16 w-full" />
              </>
            ) : (
              (dashboard?.downstream ?? []).map((service) => (
                <div key={service.name} className="rounded-lg border p-3">
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-sm font-medium">{service.name}</p>
                    <div className="flex items-center gap-1.5">
                      <StatusDot healthStatus={service.health_status} />
                      <span
                        className={cn(
                          "text-xs capitalize",
                          service.health_status === "healthy" && "text-green-600 dark:text-green-400",
                          service.health_status === "unreachable" && "text-red-600 dark:text-red-400",
                          service.health_status === "unconfigured" && "text-muted-foreground",
                        )}
                      >
                        {service.health_status}
                      </span>
                    </div>
                  </div>
                  <p className="mt-0.5 text-xs text-muted-foreground">{service.role}</p>
                  <code className="mt-1.5 block truncate text-xs text-muted-foreground">
                    {service.url || "Not configured"}
                  </code>
                </div>
              ))
            )}
          </CardContent>
        </Card>

        {/* Snapshot + latest event */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-base">
              <LayoutDashboard className="size-4 text-blue-600 dark:text-blue-400" />
              Runtime snapshot
            </CardTitle>
            <CardDescription>Current configuration at a glance.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-2 sm:grid-cols-2">
              <SummaryTile label="Log level" value={config?.general.log_level ?? "INFO"} />
              <SummaryTile
                label="Timeout"
                value={`${config?.general.http_timeout_seconds ?? 15}s`}
              />
              <SummaryTile
                label="Webhook token"
                value={config?.general.webhook_shared_token ? "Configured" : "Missing"}
              />
              <SummaryTile label="Live targets" value={`${activeServiceCount} / 4`} />
            </div>

            {latestActivity ? (
              <div className="rounded-lg border p-3">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium">
                      {formatMediaTitle(latestActivity.result.item_type, latestActivity.result.name)}
                    </p>
                    <p className="mt-0.5 text-xs text-muted-foreground">Latest processed item</p>
                  </div>
                  <StatusPill
                    tone={latestActivity.result.status === "partial_failure" ? "red" : "green"}
                    label={latestActivity.result.status}
                  />
                </div>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {Object.entries(latestActivity.action_summary).map(([k, v]) => (
                    <Badge key={k} variant="outline" className="text-xs">
                      {k}: {v}
                    </Badge>
                  ))}
                </div>
              </div>
            ) : (
              <EmptyState
                title="No activity yet"
                description="Send a Jellyfin webhook after setup to see runtime events here."
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
  filteredActivity,
  activityFilter,
  onFilterChange,
}: {
  filteredActivity: DashboardActivity[]
  activityFilter: string
  onFilterChange: (v: string) => void
}) {
  return (
    <section className="space-y-4">
      <div className="flex items-center gap-3">
        <Input
          value={activityFilter}
          onChange={(e) => onFilterChange(e.target.value)}
          placeholder="Filter by title, system, action, or status…"
          className="max-w-sm"
        />
        {activityFilter && (
          <Button variant="ghost" size="sm" onClick={() => onFilterChange("")}>
            Clear
          </Button>
        )}
        <span className="ml-auto text-sm text-muted-foreground">
          {filteredActivity.length} event{filteredActivity.length !== 1 ? "s" : ""}
        </span>
      </div>

      <ScrollArea className="h-[580px]">
        {filteredActivity.length === 0 ? (
          <EmptyState
            title="No events"
            description={
              activityFilter
                ? "No activity matches the current filter."
                : "Send a Jellyfin webhook to populate the activity log."
            }
          />
        ) : (
          <div className="space-y-2 px-px pb-px">
            {filteredActivity.map((entry) => (
              <ActivityEntry
                key={`${entry.processed_at}-${entry.result.item_id}`}
                entry={entry}
              />
            ))}
          </div>
        )}
      </ScrollArea>
    </section>
  )
}

// ─── Setup workspace ──────────────────────────────────────────────────────────

function SetupWorkspace({
  activeStep,
  activeStepMeta,
  activeServiceMeta,
  config,
  dashboard,
  isConfigLoading,
  completionCount,
  origin,
  jellyfinTemplatePreview,
  curlPreview,
  onSelectStep,
  onEditGeneral,
  onGoToDashboard,
  onAddService,
  onEditService,
}: {
  activeStep: SetupStepId
  activeStepMeta: SetupStepMeta
  activeServiceMeta: ServiceMeta | null
  config: RuntimeConfigPayload | null
  dashboard: DashboardPayload | null
  isConfigLoading: boolean
  completionCount: number
  origin: string
  jellyfinTemplatePreview: string
  curlPreview: string
  onSelectStep: (step: SetupStepId) => void
  onEditGeneral: () => void
  onGoToDashboard: () => void
  onAddService: (family: ServiceFamily) => void
  onEditService: (family: ServiceFamily, service: ServiceRecord) => void
}) {
  const allComplete = completionCount === SETUP_STEPS.length

  return (
    <section className="space-y-4">
      {/* All-done banner */}
      {allComplete && (
        <div className="flex items-center gap-3 rounded-xl border border-green-200 bg-green-50/60 p-4 dark:border-green-900 dark:bg-green-950/20">
          <CheckCircle2 className="size-5 shrink-0 text-green-600 dark:text-green-400" />
          <div className="flex-1 min-w-0">
            <p className="font-medium">All steps complete</p>
            <p className="text-sm text-muted-foreground">
              Switch to Live mode in Runtime settings when you're ready.
            </p>
          </div>
          <Button variant="outline" size="sm" onClick={onGoToDashboard} className="shrink-0">
            <LayoutDashboard className="size-4 text-blue-600 dark:text-blue-400" />
            Dashboard
          </Button>
        </div>
      )}

      <div className="grid gap-4 xl:grid-cols-[220px_minmax(0,1fr)]">
        {/* Step sidebar */}
        <div className="flex flex-col gap-0.5">
          {SETUP_STEPS.map((step) => {
            const ready = isSetupStepReady(step.id, config)
            const count = isServiceFamily(step.id) ? getServices(config, step.id).length : undefined
            return (
              <button
                key={step.id}
                type="button"
                onClick={() => onSelectStep(step.id)}
                className={cn(
                  "flex w-full items-center gap-2.5 rounded-lg px-3 py-2.5 text-left text-sm transition-colors",
                  activeStep === step.id
                    ? "bg-muted font-medium text-foreground"
                    : "text-muted-foreground hover:bg-muted/60 hover:text-foreground",
                )}
              >
                {ready ? (
                  <CheckCircle2 className="size-4 shrink-0 text-green-500" />
                ) : (
                  <CircleAlert className="size-4 shrink-0 text-amber-500" />
                )}
                <span className="flex-1 truncate">{step.title}</span>
                {typeof count === "number" && count > 0 && (
                  <span className="text-xs tabular-nums text-muted-foreground">{count}</span>
                )}
              </button>
            )
          })}
        </div>

        {/* Step content */}
        <Card>
          <CardHeader className="pb-4">
            <CardTitle className="flex items-center gap-2 text-base">
              <activeStepMeta.icon
                className={cn(
                  "size-4",
                  activeStepMeta.accent === "blue" && "text-blue-600 dark:text-blue-400",
                  activeStepMeta.accent === "green" && "text-green-600 dark:text-green-400",
                  activeStepMeta.accent === "red" && "text-red-600 dark:text-red-400",
                )}
              />
              {activeStepMeta.title}
            </CardTitle>
            <CardDescription>{activeStepMeta.description}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-5">
            {activeStep === "general" ? (
              <>
                <GuideCard
                  tone="blue"
                  title="What to configure"
                  description="Start with the runtime mode, timeout, and webhook token before connecting downstream services."
                >
                  <InstructionList items={GENERAL_SETUP_STEPS} />
                </GuideCard>
                <GuideCard
                  tone="green"
                  title="Where the token is used"
                  description="The webhook token must match the header you configure in Jellyfin."
                >
                  <InstructionList items={GENERAL_SETUP_HELP} />
                </GuideCard>
                <RuntimeSettingsCard
                  config={config?.general ?? null}
                  isLoading={isConfigLoading}
                  onEdit={onEditGeneral}
                />
              </>
            ) : activeStep === "jellyfin" ? (
              <JellyfinSetupPanel
                dashboard={dashboard}
                origin={origin}
                jellyfinTemplatePreview={jellyfinTemplatePreview}
                curlPreview={curlPreview}
                tokenConfigured={Boolean(config?.general.webhook_shared_token)}
                onOpenGeneral={onEditGeneral}
              />
            ) : activeServiceMeta ? (
              <ServiceSetupPanel
                meta={activeServiceMeta}
                services={getServices(config, activeStep)}
                isLoading={isConfigLoading}
                onAdd={() => onAddService(activeStep)}
                onEdit={(service) => onEditService(activeStep, service)}
              />
            ) : null}
          </CardContent>
        </Card>
      </div>
    </section>
  )
}

// ─── Jellyfin setup panel ─────────────────────────────────────────────────────

function JellyfinSetupPanel({
  dashboard,
  origin,
  jellyfinTemplatePreview,
  curlPreview,
  tokenConfigured,
  onOpenGeneral,
}: {
  dashboard: DashboardPayload | null
  origin: string
  jellyfinTemplatePreview: string
  curlPreview: string
  tokenConfigured: boolean
  onOpenGeneral: () => void
}) {
  const webhookUrl = `${origin}/webhook/jellyfin`
  const genericFieldRows: JellyfinFieldInstruction[] = [
    {
      label: "Webhook name",
      value: "CleanArr",
      hint: "Any display name works. CleanArr makes it easy to spot.",
      copyValue: "CleanArr",
    },
    {
      label: "Webhook URL",
      value: webhookUrl,
      hint: "Paste this into Jellyfin's Webhook Url field exactly as-is.",
      copyValue: webhookUrl,
    },
    {
      label: "Method",
      value: "POST",
      hint: "The Generic destination must send a POST request.",
      copyValue: "POST",
    },
    {
      label: "Header name",
      value: "X-Webhook-Token",
      hint: "Add exactly one custom header with this name.",
      copyValue: "X-Webhook-Token",
    },
    {
      label: "Header value",
      value: tokenConfigured
        ? "Use the exact token from Runtime settings"
        : "Open Runtime settings first and save a webhook token",
      hint: "The value must match CleanArr runtime settings exactly, character for character.",
    },
    {
      label: "Notification types",
      value: "Enable only ItemDeleted",
      hint: "CleanArr ignores non-destructive events.",
    },
  ]

  const webhookStatus = dashboard?.webhook_status
  const webhookTone = getWebhookStatusTone(webhookStatus?.outcome ?? "waiting")
  const lastAttemptAt = webhookStatus?.attempted_at
    ? new Date(webhookStatus.attempted_at).toLocaleString()
    : "Not received yet"
  const statusLabel = getWebhookStatusLabel(webhookStatus?.outcome ?? "waiting")

  return (
    <div className="space-y-5">
      <GuideCard
        tone="blue"
        title="Step 1 — Install the Jellyfin Webhook plugin"
        description="CleanArr needs the Webhook plugin. Jellyfin is an event source only, not a saved downstream integration."
      >
        <InstructionList items={JELLYFIN_INSTALL_STEPS} />
      </GuideCard>

      <GuideCard
        tone={tokenConfigured ? "green" : "red"}
        title={tokenConfigured ? "Step 2 — Webhook token ready" : "Step 2 — Create the webhook token first"}
        description={
          tokenConfigured
            ? "Use the same token in the Jellyfin Generic webhook header."
            : "Open Runtime settings and save the shared webhook token before continuing."
        }
      >
        <div className="flex flex-wrap items-center gap-3">
          <StatusPill
            tone={tokenConfigured ? "green" : "red"}
            label={tokenConfigured ? "Token configured" : "Token missing"}
          />
          <Button variant="outline" size="sm" onClick={onOpenGeneral}>
            <Settings2 className="size-4 text-blue-600 dark:text-blue-400" />
            Open runtime settings
          </Button>
        </div>
      </GuideCard>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <Webhook className="size-4 text-blue-600 dark:text-blue-400" />
            Step 3 — Add a Generic destination in Jellyfin
          </CardTitle>
          <CardDescription>
            Follow these sub-steps inside Jellyfin so the destination sends ItemDeleted events to CleanArr.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <GuideCard
            tone="blue"
            title="3.1 Open the Generic destination form"
            description="Jellyfin → Dashboard → Plugins → Webhook → Click Add Generic Destination."
          >
            <InstructionList items={JELLYFIN_CONFIG_STEPS} />
          </GuideCard>

          <GuideCard
            tone="green"
            title="3.2 Fill these fields exactly"
            description="These values map directly to fields in Jellyfin's Webhook plugin."
          >
            <div className="space-y-2">
              {genericFieldRows.map((row) => (
                <JellyfinFieldRow key={row.label} row={row} />
              ))}
            </div>
          </GuideCard>

          <GuideCard
            tone="blue"
            title="3.3 Enable only supported item types"
            description="CleanArr handles movie and TV deletion events."
          >
            <InstructionList items={JELLYFIN_ITEM_TYPE_STEPS} />
          </GuideCard>

          <GuideCard
            tone="green"
            title="3.4 Paste the request body template"
            description="Do not replace the placeholders. Jellyfin resolves them when it sends the webhook."
          >
            <Textarea
              readOnly
              value={jellyfinTemplatePreview}
              className="min-h-[280px] font-mono text-xs"
            />
            <div className="mt-3">
              <Button
                variant="outline"
                size="sm"
                onClick={() => void navigator.clipboard.writeText(jellyfinTemplatePreview)}
              >
                <Copy className="size-4 text-blue-600 dark:text-blue-400" />
                Copy template
              </Button>
            </div>
          </GuideCard>

          <GuideCard
            tone="blue"
            title="3.5 Save the destination"
            description="The destination is active only after Jellyfin saves the whole Webhook plugin page."
          >
            <InstructionList items={JELLYFIN_SAVE_STEPS} />
          </GuideCard>
        </CardContent>
      </Card>

      {/* Verification */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <TestTubeDiagonal className="size-4 text-green-600 dark:text-green-400" />
            Step 4 — Verify delivery
          </CardTitle>
          <CardDescription>
            CleanArr exposes webhook diagnostics because the Jellyfin plugin has no built-in test button.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Status row */}
          <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
            <ReadOnlyDetail label="Delivery status" value={statusLabel} />
            <ReadOnlyDetail label="Last attempt" value={lastAttemptAt} />
            <ReadOnlyDetail
              label="HTTP status"
              value={webhookStatus?.http_status ? String(webhookStatus.http_status) : "None"}
            />
            <ReadOnlyDetail
              label="Last item"
              value={
                webhookStatus?.item_name
                  ? formatMediaTitle(webhookStatus.item_type ?? "Item", webhookStatus.item_name)
                  : "No item received yet"
              }
            />
          </div>

          <div className="flex flex-wrap gap-2">
            <StatusPill tone={webhookTone} label={statusLabel} />
            {webhookStatus?.result_status && (
              <StatusPill
                tone={webhookStatus.result_status === "partial_failure" ? "red" : "green"}
                label={`Processing: ${webhookStatus.result_status}`}
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
            <AlertTitle>Latest webhook attempt</AlertTitle>
            <AlertDescription>
              {webhookStatus?.message ?? "No Jellyfin webhook has reached CleanArr yet."}
            </AlertDescription>
          </Alert>

          <div className="grid gap-4 xl:grid-cols-2">
            <Card className="border-dashed">
              <CardHeader className="pb-3">
                <CardTitle className="flex items-center gap-2 text-sm">
                  <Sparkles className="size-4 text-green-600 dark:text-green-400" />
                  Browser-side smoke test
                </CardTitle>
                <CardDescription className="text-xs">
                  Tests connectivity only. Use the template above for the actual Jellyfin plugin body.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
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
                  Copy cURL
                </Button>
              </CardContent>
            </Card>

            <div className="space-y-3">
              <GuideCard
                tone="blue"
                title="How to verify"
                description="Use both the smoke test and a real Jellyfin deletion."
              >
                <InstructionList items={JELLYFIN_VERIFY_STEPS} />
              </GuideCard>

              <GuideCard
                tone={webhookTone}
                title="If verification fails"
                description="Use the diagnostics above to decide what to fix."
              >
                <InstructionList items={JELLYFIN_TROUBLESHOOTING_STEPS} />
              </GuideCard>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}

// ─── Service setup panel ──────────────────────────────────────────────────────

function ServiceSetupPanel({
  meta,
  services,
  isLoading,
  onAdd,
  onEdit,
}: {
  meta: ServiceMeta
  services: ServiceRecord[]
  isLoading: boolean
  onAdd: () => void
  onEdit: (service: ServiceRecord) => void
}) {
  const activeService = resolveActiveService(services)
  return (
    <div className="space-y-5">
      <GuideCard
        tone={meta.accent}
        title={`How to add ${meta.title}`}
        description={`Configure ${meta.singular} connection details, test them, then keep one enabled target live.`}
      >
        <InstructionList items={meta.steps} />
      </GuideCard>

      <GuideCard
        tone={meta.accent === "green" ? "blue" : "green"}
        title="URL examples"
        description="Use an internal cluster URL when CleanArr runs in the same network."
      >
        <InstructionList items={meta.help} />
      </GuideCard>

      <Card>
        <CardHeader className="flex flex-row items-start justify-between gap-4 space-y-0 pb-3">
          <div className="space-y-0.5">
            <CardTitle className="flex items-center gap-2 text-base">
              <meta.icon
                className={cn(
                  "size-4",
                  meta.accent === "blue" && "text-blue-600 dark:text-blue-400",
                  meta.accent === "green" && "text-green-600 dark:text-green-400",
                  meta.accent === "red" && "text-red-600 dark:text-red-400",
                )}
              />
              Saved {meta.title} integrations
            </CardTitle>
          </div>
          <Button size="sm" onClick={onAdd}>
            <Plus className="size-4" />
            Add {meta.title}
          </Button>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex flex-wrap gap-2">
            <StatusPill
              tone={activeService ? "green" : "red"}
              label={activeService ? "Runtime target active" : "No runtime target"}
            />
            <StatusPill
              tone="blue"
              label={`${services.length} saved`}
            />
          </div>

          {isLoading && services.length === 0 ? (
            <div className="space-y-2">
              <Skeleton className="h-16 w-full" />
              <Skeleton className="h-16 w-full" />
            </div>
          ) : services.length === 0 ? (
            <EmptyState
              title={`No ${meta.title} integrations yet`}
              description={`Press "Add ${meta.title}" to open the form, paste the URL and credentials, then run Test.`}
            />
          ) : (
            services.map((service) => (
              <IntegrationRow
                key={service.id}
                service={service}
                onEdit={() => onEdit(service)}
              />
            ))
          )}
        </CardContent>
      </Card>
    </div>
  )
}

// ─── Runtime settings card ────────────────────────────────────────────────────

function RuntimeSettingsCard({
  config,
  isLoading,
  onEdit,
}: {
  config: GeneralConfig | null
  isLoading: boolean
  onEdit: () => void
}) {
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <Settings2 className="size-4 text-blue-600 dark:text-blue-400" />
          Current runtime settings
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {isLoading && !config ? (
          <div className="space-y-2">
            <Skeleton className="h-12 w-full" />
            <Skeleton className="h-12 w-full" />
          </div>
        ) : config ? (
          <>
            <div className="grid gap-2 sm:grid-cols-2">
              <SummaryTile label="Mode" value={config.dry_run ? "Dry run" : "Live mode"} />
              <SummaryTile
                label="Webhook token"
                value={config.webhook_shared_token ? "Configured" : "Missing"}
              />
              <SummaryTile label="Log level" value={config.log_level} />
              <SummaryTile label="Timeout" value={`${config.http_timeout_seconds}s`} />
            </div>
            <Button variant="outline" className="w-full" onClick={onEdit}>
              <PenSquare className="size-4 text-blue-600 dark:text-blue-400" />
              Edit runtime settings
            </Button>
          </>
        ) : (
          <EmptyState
            title="Runtime settings unavailable"
            description="Refresh the configuration and try again."
          />
        )}
      </CardContent>
    </Card>
  )
}

// ─── Integration row ──────────────────────────────────────────────────────────

function IntegrationRow({
  service,
  onEdit,
}: {
  service: ServiceRecord
  onEdit: () => void
}) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-lg border p-3">
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-1.5">
          <p className="text-sm font-medium">{service.name}</p>
          {service.is_default && (
            <StatusPill tone="blue" label="Default" />
          )}
          <StatusPill
            tone={service.enabled ? "green" : "red"}
            label={service.enabled ? "Enabled" : "Disabled"}
          />
        </div>
        <p className="mt-0.5 truncate text-xs text-muted-foreground">{service.url}</p>
      </div>
      <Button variant="outline" size="sm" onClick={onEdit} className="shrink-0">
        <PenSquare className="size-4 text-blue-600 dark:text-blue-400" />
        Edit
      </Button>
    </div>
  )
}

// ─── General settings modal ───────────────────────────────────────────────────

function GeneralSettingsModal({
  open,
  config,
  onClose,
  onSave,
}: {
  open: boolean
  config: GeneralConfig | null
  onClose: () => void
  onSave: (payload: GeneralConfig) => Promise<void>
}) {
  const [draft, setDraft] = useState<GeneralConfig | null>(config)
  const [isSaving, setIsSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [tokenFeedback, setTokenFeedback] = useState<FlashState>(null)
  const [isWebhookTokenVisible, setIsWebhookTokenVisible] = useState(false)

  useEffect(() => {
    setDraft(config ? structuredClone(config) : null)
    setError(null)
    setTokenFeedback(null)
    setIsWebhookTokenVisible(false)
  }, [config, open])

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Runtime settings"
      description="Changes are persisted and immediately rebuild the live runtime."
      footer={
        <div className="flex justify-end">
          <Button
            disabled={!draft || isSaving}
            onClick={async () => {
              if (!draft) return
              setIsSaving(true)
              setError(null)
              try {
                await onSave(draft)
              } catch (e) {
                setError(normalizeError(e))
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
            Save settings
          </Button>
        </div>
      }
    >
      {draft ? (
        <div className="space-y-5">
          {error && <ErrorBanner message={error} />}

          <GuideCard
            tone="blue"
            title="Recommended first-run settings"
            description="Leave Dry Run enabled while you validate every downstream integration."
          >
            <InstructionList items={GENERAL_SETUP_STEPS} />
          </GuideCard>

          <div className="grid gap-4 sm:grid-cols-2">
            <FormField label="Log level" htmlFor="general-log-level">
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

            <FormField label="HTTP timeout (seconds)" htmlFor="general-timeout">
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
              <FieldHint text="Increase only if your Arr services are slow to respond." />
            </FormField>

            <FormField label="Activity history retention" htmlFor="general-retention">
              <select
                id="general-retention"
                value={String(draft.activity_retention_days)}
                onChange={(e) =>
                  setDraft({ ...draft, activity_retention_days: Number(e.target.value) })
                }
                className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-xs transition-[color,box-shadow] outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50"
              >
                <option value="1">1 day</option>
                <option value="7">7 days</option>
                <option value="30">30 days</option>
                <option value="90">90 days</option>
                <option value="365">1 year</option>
              </select>
              <FieldHint text="Events older than this are deleted from the SQLite database." />
            </FormField>
          </div>

          <FormField label="Webhook shared token" htmlFor="general-webhook-token">
            <div className="relative">
              <Input
                id="general-webhook-token"
                type={isWebhookTokenVisible ? "text" : "password"}
                value={draft.webhook_shared_token ?? ""}
                onChange={(e) =>
                  setDraft({ ...draft, webhook_shared_token: e.target.value || null })
                }
                className="pr-11"
              />
              <button
                type="button"
                className="absolute inset-y-0 right-0 inline-flex items-center justify-center px-3 text-muted-foreground transition-colors hover:text-foreground"
                aria-label={isWebhookTokenVisible ? "Hide token" : "Show token"}
                onClick={() => setIsWebhookTokenVisible((v) => !v)}
              >
                {isWebhookTokenVisible ? (
                  <EyeOff className="size-4 text-blue-600 dark:text-blue-400" />
                ) : (
                  <Eye className="size-4 text-blue-600 dark:text-blue-400" />
                )}
              </button>
            </div>
            <div className="mt-2 flex flex-wrap gap-2">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => {
                  const next = generateWebhookToken()
                  setDraft({ ...draft, webhook_shared_token: next })
                  setTokenFeedback({ kind: "success", message: "New token generated." })
                }}
              >
                <RefreshCw className="size-4 text-blue-600 dark:text-blue-400" />
                Generate
              </Button>
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={!draft.webhook_shared_token}
                onClick={async () => {
                  try {
                    await navigator.clipboard.writeText(draft.webhook_shared_token ?? "")
                    setTokenFeedback({ kind: "success", message: "Copied to clipboard." })
                  } catch (e) {
                    setTokenFeedback({ kind: "error", message: normalizeError(e) })
                  }
                }}
              >
                <Copy className="size-4 text-blue-600 dark:text-blue-400" />
                Copy
              </Button>
            </div>
            <FieldHint text="Jellyfin must send this exact token in the X-Webhook-Token header." />
            {tokenFeedback && (
              <p
                className={cn(
                  "text-xs",
                  tokenFeedback.kind === "success"
                    ? "text-green-700 dark:text-green-300"
                    : "text-red-700 dark:text-red-300",
                )}
              >
                {tokenFeedback.message}
              </p>
            )}
          </FormField>

          <label className="inline-flex cursor-pointer items-center gap-3 text-sm">
            <input
              type="checkbox"
              checked={draft.dry_run}
              onChange={(e) => setDraft({ ...draft, dry_run: e.target.checked })}
            />
            Keep CleanArr in Dry Run
          </label>
        </div>
      ) : (
        <EmptyState
          title="Settings unavailable"
          description="Close the modal and refresh the configuration."
        />
      )}
    </Modal>
  )
}

// ─── Service modal ────────────────────────────────────────────────────────────

function ServiceModal({
  state,
  onClose,
  onSave,
  onDelete,
  onTest,
}: {
  state: ServiceModalState | null
  onClose: () => void
  onSave: (family: ServiceFamily, draft: ServiceDraft) => Promise<void>
  onDelete: (family: ServiceFamily, serviceId: string) => Promise<void>
  onTest: (family: ServiceFamily, draft: ServiceDraft) => Promise<ConnectionTestResponse>
}) {
  const [draft, setDraft] = useState<ServiceDraft | null>(state?.draft ?? null)
  const [testResult, setTestResult] = useState<ConnectionTestResponse | null>(null)
  const [isSaving, setIsSaving] = useState(false)
  const [isTesting, setIsTesting] = useState(false)
  const [isDeleting, setIsDeleting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setDraft(state ? structuredClone(state.draft) : null)
    setTestResult(null)
    setError(null)
  }, [state])

  if (!state) return null

  const meta = SERVICE_META[state.family]

  return (
    <Modal
      open={state !== null}
      onClose={onClose}
      title={`${draft?.id ? "Edit" : "Add"} ${meta.title}`}
      description={meta.description}
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
                  setError(null)
                  try {
                    await onDelete(state.family, draft.id)
                  } catch (e) {
                    setError(normalizeError(e))
                  } finally {
                    setIsDeleting(false)
                  }
                }}
              >
                {isDeleting ? <LoaderCircle className="size-4 animate-spin" /> : <CircleAlert className="size-4" />}
                Delete
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
                setError(null)
                setTestResult(null)
                try {
                  const result = await onTest(state.family, draft)
                  setTestResult(result)
                } catch (e) {
                  setTestResult({ ok: false, message: normalizeError(e) })
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
              Test
            </Button>
            <Button
              disabled={!draft || isSaving}
              onClick={async () => {
                if (!draft) return
                setIsSaving(true)
                setError(null)
                try {
                  await onSave(state.family, draft)
                } catch (e) {
                  setError(normalizeError(e))
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
              Save
            </Button>
          </div>
        </div>
      }
    >
      {draft ? (
        <div className="space-y-4">
          {error && <ErrorBanner message={error} />}
          {testResult && <ConnectionResultBanner result={testResult} />}

          <GuideCard
            tone={meta.accent}
            title="Before you save"
            description="Paste the service URL and credentials, then run Test. The result must turn green before switching live."
          >
            <InstructionList items={meta.help} />
          </GuideCard>

          <FormField label="Display name" htmlFor={`${state.family}-name`}>
            <Input
              id={`${state.family}-name`}
              value={draft.name}
              onChange={(e) => setDraft({ ...draft, name: e.target.value })}
            />
          </FormField>

          <FormField label="Base URL" htmlFor={`${state.family}-url`}>
            <Input
              id={`${state.family}-url`}
              type="url"
              value={draft.url}
              onChange={(e) => setDraft({ ...draft, url: e.target.value })}
              placeholder={meta.example}
            />
            <FieldHint
              text={
                state.family === "downloaders"
                  ? "Paste the qBittorrent Web UI URL only. CleanArr strips /api/v2 automatically."
                  : `Paste the service URL only. CleanArr appends the correct API path for ${meta.title} automatically.`
              }
            />
          </FormField>

          {meta.fields.map((field) => (
            <FormField
              key={field.key}
              label={field.label}
              htmlFor={`${state.family}-${field.key}`}
            >
              <Input
                id={`${state.family}-${field.key}`}
                type={field.type}
                value={draft[field.key]}
                onChange={(e) => setDraft({ ...draft, [field.key]: e.target.value })}
              />
              <FieldHint text={field.hint} />
            </FormField>
          ))}

          <div className="grid gap-2 sm:grid-cols-2">
            <label className="inline-flex cursor-pointer items-center gap-3 rounded-lg border px-3 py-2 text-sm">
              <input
                type="checkbox"
                checked={draft.enabled}
                onChange={(e) => setDraft({ ...draft, enabled: e.target.checked })}
              />
              Enabled
            </label>
            <label className="inline-flex cursor-pointer items-center gap-3 rounded-lg border px-3 py-2 text-sm">
              <input
                type="checkbox"
                checked={draft.is_default}
                onChange={(e) => setDraft({ ...draft, is_default: e.target.checked })}
              />
              Use as runtime target
            </label>
          </div>
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

function JellyfinFieldRow({ row }: { row: JellyfinFieldInstruction }) {
  return (
    <div className="flex items-start justify-between gap-3 rounded-lg border px-3 py-2.5">
      <div className="min-w-0 space-y-1">
        <p className="text-xs uppercase tracking-wide text-muted-foreground">{row.label}</p>
        <code className="block break-all text-sm">{row.value}</code>
        <p className="text-xs text-muted-foreground">{row.hint}</p>
      </div>
      {row.copyValue && (
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="shrink-0"
          onClick={() => void navigator.clipboard.writeText(row.copyValue!)}
        >
          <Copy className="size-3.5 text-blue-600 dark:text-blue-400" />
          Copy
        </Button>
      )}
    </div>
  )
}

function SummaryTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border px-3 py-2.5">
      <p className="text-xs uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className="mt-1 text-sm font-medium">{value}</p>
    </div>
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

function StatusDot({ healthStatus }: { healthStatus: HealthStatus }) {
  if (healthStatus === "healthy") {
    return <span className="inline-flex size-2 rounded-full bg-green-500" title="Healthy" />
  }
  if (healthStatus === "unreachable") {
    return <span className="inline-flex size-2 rounded-full bg-red-500" title="Unreachable" />
  }
  return <span className="inline-flex size-2 rounded-full bg-gray-300 dark:bg-gray-600" title="Not configured" />
}

function ConnectionResultBanner({ result }: { result: ConnectionTestResponse }) {
  return (
    <div
      className={cn(
        "rounded-lg border px-4 py-3 text-sm",
        result.ok
          ? "border-green-200 bg-green-50 text-green-800 dark:border-green-900 dark:bg-green-950/40 dark:text-green-200"
          : "border-red-200 bg-red-50 text-red-800 dark:border-red-900 dark:bg-red-950/40 dark:text-red-200",
      )}
    >
      <div className="flex items-center gap-2 font-medium">
        {result.ok ? (
          <CheckCircle2 className="size-4 text-green-600 dark:text-green-400" />
        ) : (
          <CircleAlert className="size-4 text-red-600 dark:text-red-400" />
        )}
        {result.ok ? "Connection successful" : "Connection failed"}
      </div>
      <p className="mt-1.5 text-xs">{result.message}</p>
    </div>
  )
}

function ErrorBanner({ message }: { message: string }) {
  return (
    <Alert variant="destructive">
      <CircleAlert className="size-4" />
      <AlertTitle>Request failed</AlertTitle>
      <AlertDescription>{message}</AlertDescription>
    </Alert>
  )
}

function ActivityEntry({ entry }: { entry: DashboardActivity }) {
  const [open, setOpen] = useState(false)
  const Icon = entry.result.item_type === "Movie" ? Film : Tv
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
          <Badge variant="outline" className="text-xs">{entry.result.item_type}</Badge>
          <StatusPill
            tone={entry.result.status === "partial_failure" ? "red" : "green"}
            label={entry.result.status}
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
              <ActionRow key={`${action.system}-${action.action}-${i}`} action={action} />
            ))}
          </div>
        </CardContent>
      )}
    </Card>
  )
}

function ActionRow({ action }: { action: DashboardAction }) {
  return (
    <div className="rounded-lg border p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="outline" className="text-xs">{action.system}</Badge>
          <span className="text-sm font-medium">{action.action}</span>
        </div>
        <StatusPill
          tone={action.status === "failed" ? "red" : action.status === "deleted" ? "green" : "blue"}
          label={action.status}
        />
      </div>
      <p className="mt-1.5 text-xs text-muted-foreground">{action.message}</p>
      {action.reason && (
        <p className="mt-1 text-xs text-muted-foreground">
          reason: <span className="font-mono">{action.reason}</span>
        </p>
      )}
    </div>
  )
}

function MetricCard({
  title,
  value,
  description,
  icon: Icon,
  tone,
}: {
  title: string
  value: string
  description: string
  icon: LucideIcon
  tone: "blue" | "green" | "red"
}) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between gap-2">
          <CardDescription className="text-xs">{title}</CardDescription>
          <Icon
            className={cn(
              "size-4",
              tone === "blue" && "text-blue-600 dark:text-blue-400",
              tone === "green" && "text-green-600 dark:text-green-400",
              tone === "red" && "text-red-600 dark:text-red-400",
            )}
          />
        </div>
        <CardTitle className="text-2xl">{value}</CardTitle>
      </CardHeader>
      <CardContent className="pt-0">
        <p className="text-xs text-muted-foreground">{description}</p>
      </CardContent>
    </Card>
  )
}

// ─── Library panel ────────────────────────────────────────────────────────────

function LibrarySeriesTab({
  library,
  isLoading,
  error,
  onRefresh,
  onDelete,
}: {
  library: LibrarySeriesResponse | null
  isLoading: boolean
  error: string | null
  onRefresh: () => void
  onDelete: (target: LibraryDeleteTarget) => void
}) {
  const [search, setSearch] = useState("")
  const [expanded, setExpanded] = useState<Set<number>>(new Set())

  const filtered = useMemo(() => {
    if (!library) return []
    if (!search.trim()) return library.series
    const q = search.toLowerCase()
    return library.series.filter((s) => s.title.toLowerCase().includes(q))
  }, [library, search])

  const toggleExpand = (id: number) => {
    setExpanded((prev) => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <Button variant="outline" size="sm" onClick={onRefresh} disabled={isLoading}>
          <RefreshCw className={cn("size-4", isLoading && "animate-spin")} />
          Refresh
        </Button>
      </div>

      {error && <ErrorBanner message={error} />}

      {isLoading && !library && (
        <div className="space-y-3">
          {[1, 2, 3].map((n) => (
            <Skeleton key={n} className="h-14 w-full rounded-lg" />
          ))}
        </div>
      )}

      {!isLoading && library && filtered.length === 0 && (
        <EmptyState
          title={search ? "No series match your search" : "No series found"}
          description={
            search
              ? "Try a different search term."
              : "Sonarr returned no series. Configure Sonarr in Setup first."
          }
        />
      )}

      {library && library.series.length > 0 && (
        <Input
          placeholder="Search series…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      )}

      {filtered.length > 0 && (
        <div className="space-y-2">
          {filtered.map((series) => {
            const isOpen = expanded.has(series.sonarr_id)
            const totalBytes = series.seasons.reduce((sum, s) => sum + s.size_bytes, 0)
            return (
              <Card key={series.sonarr_id}>
                <button
                  type="button"
                  className="flex w-full items-center gap-3 px-4 py-3 text-left"
                  onClick={() => toggleExpand(series.sonarr_id)}
                >
                  {isOpen ? (
                    <ChevronDown className="size-4 shrink-0 text-muted-foreground" />
                  ) : (
                    <ChevronRight className="size-4 shrink-0 text-muted-foreground" />
                  )}
                  <Tv className="size-4 shrink-0 text-blue-500" />
                  <span className="flex-1 text-sm font-medium">{series.title}</span>
                  <span className="text-xs text-muted-foreground">
                    {series.seasons.length} season{series.seasons.length !== 1 ? "s" : ""}
                    {totalBytes > 0 && ` · ${formatBytes(totalBytes)}`}
                  </span>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="ml-2 shrink-0 text-red-600 hover:bg-red-50 hover:text-red-700 dark:text-red-400 dark:hover:bg-red-950/40"
                    onClick={(e) => {
                      e.stopPropagation()
                      onDelete({
                        kind: "series",
                        sonarr_series_id: series.sonarr_id,
                        series_title: series.title,
                        item_type: "Series",
                        jellyfin_item_id: series.jellyfin_series_id,
                      })
                    }}
                  >
                    <Trash2 className="size-3.5" />
                    Delete series
                  </Button>
                </button>

                {isOpen && series.seasons.length > 0 && (
                  <CardContent className="border-t pt-3 pb-3">
                    <div className="space-y-1.5">
                      {series.seasons.map((season) => (
                        <div
                          key={season.season_number}
                          className="flex items-center gap-3 rounded-md px-2 py-2 hover:bg-muted/40"
                        >
                          <span className="min-w-[80px] text-sm font-medium">
                            Season {season.season_number}
                          </span>
                          <span className="flex-1 text-xs text-muted-foreground">
                            {season.episode_file_count}/{season.episode_count} episodes
                            {season.size_bytes > 0 && ` · ${formatBytes(season.size_bytes)}`}
                          </span>
                          {season.episode_file_count > 0 ? (
                            <Button
                              variant="outline"
                              size="sm"
                              className="shrink-0 text-red-600 hover:bg-red-50 hover:text-red-700 dark:text-red-400 dark:hover:bg-red-950/40"
                              onClick={() =>
                                onDelete({
                                  kind: "series",
                                  sonarr_series_id: series.sonarr_id,
                                  series_title: series.title,
                                  item_type: "Season",
                                  season_number: season.season_number,
                                  jellyfin_item_id: season.jellyfin_season_id,
                                })
                              }
                            >
                              <Trash2 className="size-3.5" />
                              Delete
                            </Button>
                          ) : (
                            <span className="text-xs text-muted-foreground">No files</span>
                          )}
                        </div>
                      ))}
                    </div>
                  </CardContent>
                )}

                {isOpen && series.seasons.length === 0 && (
                  <CardContent className="border-t pt-3 pb-3">
                    <p className="text-xs text-muted-foreground">No seasons with episodes found.</p>
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
  movies,
  isLoading,
  error,
  onRefresh,
  onDelete,
}: {
  movies: LibraryMoviesResponse | null
  isLoading: boolean
  error: string | null
  onRefresh: () => void
  onDelete: (target: LibraryDeleteTarget) => void
}) {
  const [search, setSearch] = useState("")

  const filtered = useMemo(() => {
    if (!movies) return []
    if (!search.trim()) return movies.movies
    const q = search.toLowerCase()
    return movies.movies.filter((m) => m.title.toLowerCase().includes(q))
  }, [movies, search])

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <Button variant="outline" size="sm" onClick={onRefresh} disabled={isLoading}>
          <RefreshCw className={cn("size-4", isLoading && "animate-spin")} />
          Refresh
        </Button>
      </div>

      {error && <ErrorBanner message={error} />}

      {isLoading && !movies && (
        <div className="space-y-3">
          {[1, 2, 3].map((n) => (
            <Skeleton key={n} className="h-12 w-full rounded-lg" />
          ))}
        </div>
      )}

      {!isLoading && movies && filtered.length === 0 && (
        <EmptyState
          title={search ? "No movies match your search" : "No movies found"}
          description={
            search
              ? "Try a different search term."
              : "Radarr returned no movies. Configure Radarr in Setup first."
          }
        />
      )}

      {movies && movies.movies.length > 0 && (
        <Input
          placeholder="Search movies…"
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
                <span className="flex-1 text-sm font-medium">{movie.title}</span>
                <span className="text-xs text-muted-foreground">
                  {movie.has_file
                    ? movie.size_bytes > 0
                      ? formatBytes(movie.size_bytes)
                      : "On disk"
                    : "No file"}
                </span>
                {movie.has_file ? (
                  <Button
                    variant="ghost"
                    size="sm"
                    className="ml-2 shrink-0 text-red-600 hover:bg-red-50 hover:text-red-700 dark:text-red-400 dark:hover:bg-red-950/40"
                    onClick={() =>
                      onDelete({
                        kind: "movie",
                        radarr_movie_id: movie.radarr_id,
                        movie_title: movie.title,
                        jellyfin_movie_id: movie.jellyfin_movie_id,
                      })
                    }
                  >
                    <Trash2 className="size-3.5" />
                    Delete
                  </Button>
                ) : (
                  <span className="ml-2 text-xs text-muted-foreground">No files</span>
                )}
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}

function LibraryPanel({
  library,
  isLibraryLoading,
  libraryError,
  libraryMovies,
  isLibraryMoviesLoading,
  libraryMoviesError,
  isLive,
  onRefreshSeries,
  onRefreshMovies,
  onDelete,
}: {
  library: LibrarySeriesResponse | null
  isLibraryLoading: boolean
  libraryError: string | null
  libraryMovies: LibraryMoviesResponse | null
  isLibraryMoviesLoading: boolean
  libraryMoviesError: string | null
  isLive: boolean
  onRefreshSeries: () => void
  onRefreshMovies: () => void
  onDelete: (target: LibraryDeleteTarget) => void
}) {
  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-lg font-semibold">Library</h2>
        <p className="text-sm text-muted-foreground">
          Browse your media library and delete items — cascades to Sonarr/Radarr, qBittorrent, Jellyseerr, and Jellyfin.
        </p>
      </div>

      {!isLive && (
        <Alert>
          <Info className="size-4 text-amber-600 dark:text-amber-400" />
          <AlertTitle>Dry run mode</AlertTitle>
          <AlertDescription>
            No actual changes will be made. Enable Live mode in Runtime settings to execute real deletions.
          </AlertDescription>
        </Alert>
      )}

      <Tabs defaultValue="series">
        <TabsList>
          <TabsTrigger value="series">
            <Tv className="mr-1.5 size-3.5" />
            Series
          </TabsTrigger>
          <TabsTrigger value="movies">
            <Film className="mr-1.5 size-3.5" />
            Movies
          </TabsTrigger>
        </TabsList>
        <TabsContent value="series" className="mt-4">
          <LibrarySeriesTab
            library={library}
            isLoading={isLibraryLoading}
            error={libraryError}
            onRefresh={onRefreshSeries}
            onDelete={onDelete}
          />
        </TabsContent>
        <TabsContent value="movies" className="mt-4">
          <LibraryMoviesTab
            movies={libraryMovies}
            isLoading={isLibraryMoviesLoading}
            error={libraryMoviesError}
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
  isDeleting,
  result,
  error,
  isDryRun,
  onConfirm,
  onClose,
}: {
  target: LibraryDeleteTarget | null
  isDeleting: boolean
  result: ManualDeleteResponse | null
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
        ? `Season ${target.season_number} of "${target.series_title}"`
        : `"${target.series_title}"`

  const isDone = Boolean(result || error)

  return (
    <Modal
      open={true}
      title={isDone ? "Deletion result" : `Delete ${label}?`}
      onClose={onClose}
      footer={
        isDone ? (
          <Button onClick={onClose}>Close</Button>
        ) : (
          <div className="flex gap-2">
            <Button variant="outline" onClick={onClose} disabled={isDeleting}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={onConfirm}
              disabled={isDeleting}
            >
              {isDeleting ? (
                <LoaderCircle className="mr-1 size-3.5 animate-spin" />
              ) : (
                <Trash2 className="mr-1 size-3.5" />
              )}
              {isDryRun ? "Simulate (dry run)" : "Delete"}
            </Button>
          </div>
        )
      }
    >
      <div className="space-y-4">
        {!isDone && (
          <>
            {isDryRun && (
              <Alert>
                <Info className="size-4 text-amber-600 dark:text-amber-400" />
                <AlertTitle>Dry run mode</AlertTitle>
                <AlertDescription>No actual changes will be made.</AlertDescription>
              </Alert>
            )}
            <p className="text-sm text-muted-foreground">
              This will remove files from Sonarr, delete matching torrents from qBittorrent,
              and clean up requests in Jellyseerr.
            </p>
          </>
        )}

        {error && <ErrorBanner message={error} />}

        {result && (
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <StatusPill
                tone={result.status === "partial_failure" ? "red" : result.status === "ignored" ? "neutral" : "green"}
                label={result.status}
              />
            </div>
            <div className="space-y-1.5">
              {result.actions.map((action, i) => (
                <ActionRow key={`${action.system}-${action.action}-${i}`} action={action} />
              ))}
            </div>
          </div>
        )}
      </div>
    </Modal>
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

function generateWebhookToken(): string {
  const bytes = new Uint8Array(24)
  window.crypto.getRandomValues(bytes)
  return Array.from(bytes, (v) => v.toString(16).padStart(2, "0")).join("")
}

function getWebhookStatusTone(outcome: string): "blue" | "green" | "red" {
  if (outcome === "processed") return "green"
  if (outcome === "rejected_auth" || outcome === "invalid_payload") return "red"
  return "blue"
}

function getWebhookStatusLabel(outcome: string): string {
  switch (outcome) {
    case "processed": return "Webhook received"
    case "rejected_auth": return "Token mismatch"
    case "invalid_payload": return "Payload rejected"
    default: return "No delivery yet"
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

function isSetupStepReady(step: SetupStepId, config: RuntimeConfigPayload | null): boolean {
  if (!config) return false
  if (step === "general" || step === "jellyfin") {
    return Boolean(config.general.webhook_shared_token)
  }
  if (step === "jellyfin_server") {
    // Jellyfin server is optional — always considered ready
    return true
  }
  return Boolean(resolveActiveService(getServices(config, step)))
}

function findNextIncompleteSetupStep(config: RuntimeConfigPayload | null): SetupStepId | null {
  return SETUP_STEPS.find((step) => !isSetupStepReady(step.id, config))?.id ?? null
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

export default CleanArrApp
