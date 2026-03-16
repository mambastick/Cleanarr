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
  Plus,
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

const GENERAL_SETUP_STEPS = [
  "Keep CleanArr in Dry Run until all services test green.",
  "Set a webhook token. Jellyfin must send the same X-Webhook-Token header.",
  "Only switch to Live mode after Radarr, Sonarr, Jellyseerr, and qBittorrent are configured.",
]

const JELLYFIN_INSTALL_STEPS = [
  "Open Jellyfin → Dashboard → Catalog.",
  "Find the plugin named Webhook and install it.",
  "Restart Jellyfin if the plugin manager asks for it.",
  "After restart, open Jellyfin → Dashboard → Plugins → Webhook.",
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
  const [activityFilter, setActivityFilter] = useState("")
  const [authMode, setAuthMode] = useState<AuthMode>("login")
  const [showWizard, setShowWizard] = useState(false)
  const [activeTab, setActiveTab] = useState<MainTab>("dashboard")
  const [authForm, setAuthForm] = useState({ username: "", password: "", confirmPassword: "" })
  const [generalModalOpen, setGeneralModalOpen] = useState(false)
  const [serviceModal, setServiceModal] = useState<ServiceModalState | null>(null)
  const [sessionToken, setSessionToken] = useState(() => readSessionCookie())
  const hasAutoNavigated = useRef(false)

  const [library, setLibrary] = useState<LibrarySeriesResponse | null>(null)
  const [isLibraryLoading, setIsLibraryLoading] = useState(false)
  const [libraryMovies, setLibraryMovies] = useState<LibraryMoviesResponse | null>(null)
  const [isLibraryMoviesLoading, setIsLibraryMoviesLoading] = useState(false)
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
      toast.error("Passwords do not match.")
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
        authMode === "register"
          ? "Administrator created. Use the setup wizard to configure your services."
          : "Signed in successfully.",
      )
    } catch (error) {
      toast.error(normalizeError(error))
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
  }

  const saveGeneralSettings = async (payload: GeneralConfig) => {
    const next = await fetchJson<RuntimeConfigPayload>("/api/config/general", {
      method: "PUT",
      body: JSON.stringify(payload),
    })
    setConfig(next)
    toast.success("Runtime settings saved.")
  }

  const saveServiceDraft = async (family: ServiceFamily, draft: ServiceDraft) => {
    const meta = SERVICE_META[family]
    const body = JSON.stringify(buildServicePayload(family, draft))
    const next = draft.id
      ? await fetchJson<RuntimeConfigPayload>(`${meta.endpoint}/${draft.id}`, { method: "PUT", body })
      : await fetchJson<RuntimeConfigPayload>(meta.endpoint, { method: "POST", body })
    setConfig(next)
    setServiceModal(null)
    toast.success(`${meta.title} ${draft.id ? "updated" : "added"}.`)
  }

  const deleteServiceDraft = async (family: ServiceFamily, serviceId: string) => {
    const meta = SERVICE_META[family]
    await fetchJson<void>(`${meta.endpoint}/${serviceId}`, { method: "DELETE" })
    const next = await fetchJson<RuntimeConfigPayload>("/api/config")
    setConfig(next)
    setServiceModal(null)
    toast.success(`${meta.title} removed.`)
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
        isSubmitting={isAuthSubmitting}
        requiresRegistration={Boolean(authStatus?.requires_registration)}
        onFieldChange={(field, value) => setAuthForm((c) => ({ ...c, [field]: value }))}
        onSubmit={() => void submitAuthForm()}
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
              Dashboard
            </TabsTrigger>
            <TabsTrigger value="settings" className="gap-1.5">
              <Settings2 className="size-3.5 text-orange-500" />
              Settings
            </TabsTrigger>
            <TabsTrigger value="activity" className="gap-1.5">
              <Activity className="size-3.5 text-emerald-500" />
              Activity
            </TabsTrigger>
            <TabsTrigger value="library" className="gap-1.5">
              <Library className="size-3.5 text-violet-500" />
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
        {/* ── Dashboard ── */}
        <TabsContent value="dashboard" className="mt-0">
          <DashboardPanel
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
            config={config}
            isConfigLoading={isConfigLoading}
            onSaveGeneral={saveGeneralSettings}
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
            libraryMovies={libraryMovies}
            isLibraryMoviesLoading={isLibraryMoviesLoading}
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

      {/* ── Setup wizard overlay ── */}
      {showWizard && (
        <SetupWizard
          config={config}
          dashboard={dashboard}
          isConfigLoading={isConfigLoading}
          origin={origin}
          curlPreview={curlPreview}
          onAddService={(family) => {
            setServiceModal({ family, draft: structuredClone(EMPTY_DRAFTS[family]) })
          }}
          onEditService={(family, service) => {
            setServiceModal({ family, draft: toDraft(service) })
          }}
          onEditGeneral={() => setGeneralModalOpen(true)}
          onSetupWebhook={handleSetupWebhook}
          onClose={() => setShowWizard(false)}
        />
      )}

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
  isSubmitting,
  requiresRegistration,
  onFieldChange,
  onSubmit,
}: {
  authMode: AuthMode
  authForm: { username: string; password: string; confirmPassword: string }
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

const DOWNSTREAM_META: Partial<Record<string, { icon: LucideIcon; color: string }>> = {
  Radarr: { icon: Film, color: "text-yellow-500" },
  Sonarr: { icon: Tv, color: "text-sky-500" },
  Jellyfin: { icon: Play, color: "text-purple-500" },
  Jellyseerr: { icon: Star, color: "text-orange-500" },
  Downloader: { icon: Download, color: "text-emerald-500" },
}

function ServiceHealthCard({
  service,
  onEdit,
}: {
  service: { name: string; role: string; url: string; configured: boolean; health_status: HealthStatus }
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
          <StatusDot healthStatus={service.health_status} />
          <span
            className={cn(
              "text-xs capitalize",
              service.health_status === "healthy" && "text-green-600 dark:text-green-400",
              service.health_status === "unreachable" && "text-red-500",
              service.health_status === "unconfigured" && "text-muted-foreground",
            )}
          >
            {service.health_status}
          </span>
          {onEdit && (
            <button
              type="button"
              onClick={onEdit}
              className="ml-1 rounded p-0.5 text-muted-foreground hover:text-foreground transition-colors"
              title={`Edit ${service.name}`}
            >
              <PenSquare className="size-3.5" />
            </button>
          )}
        </div>
      </div>
      <div>
        <p className="text-sm font-semibold">{service.name}</p>
        <p className="text-xs text-muted-foreground">{service.role}</p>
      </div>
      {service.url ? (
        <code className="block truncate text-[11px] text-muted-foreground">{service.url}</code>
      ) : (
        <span className="text-[11px] text-muted-foreground italic">Not configured</span>
      )}
    </div>
  )
}

function DashboardPanel({
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
            <p className="text-sm font-semibold leading-tight">{isLive ? "Live mode" : "Dry run"}</p>
            <p className="text-xs text-muted-foreground">
              {isLive ? "Real deletions are active" : "No deletions will be performed"}
            </p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 ml-auto">
          <span className="text-sm text-muted-foreground">
            Setup{" "}
            <strong className="text-foreground">
              {setupCompletionCount}/{SETUP_STEPS.length}
            </strong>
          </span>
          <span className="text-sm text-muted-foreground">
            <strong className="text-foreground">{deletedActions}</strong> deletions logged
          </span>
          {!allServicesConfigured && (
            <Button variant="outline" size="sm" onClick={onOpenWizard}>
              <Zap className="size-4 text-blue-600 dark:text-blue-400" />
              Setup wizard
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
              Dry run
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
              Live
            </button>
          </div>
        </div>
      </div>

      {/* Connected services */}
      <div>
        <p className="mb-3 text-sm font-medium text-muted-foreground">Connected services</p>
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
              Webhook status
            </CardTitle>
            <CardDescription>Last Jellyfin delivery attempt.</CardDescription>
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
                title="No webhook received"
                description="Send a Jellyfin ItemDeleted webhook to see status here."
              />
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-base">
              <Activity className="size-4 text-emerald-500" />
              Latest event
            </CardTitle>
            <CardDescription>Most recent processed item.</CardDescription>
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
          <div className="space-y-2 p-px">
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

// ─── Settings panel ───────────────────────────────────────────────────────────

function SettingsPanel({
  config,
  isConfigLoading,
  onSaveGeneral,
}: {
  config: RuntimeConfigPayload | null
  isConfigLoading: boolean
  onSaveGeneral: (payload: GeneralConfig) => Promise<void>
}) {
  const general = config?.general ?? null
  const [draft, setDraft] = useState<GeneralConfig | null>(null)
  const [isSaving, setIsSaving] = useState(false)
  const [tokenCopied, setTokenCopied] = useState(false)
  const [isTokenVisible, setIsTokenVisible] = useState(false)

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
            General
          </CardTitle>
          <CardDescription>Application behaviour and operational parameters.</CardDescription>
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
                <FormField label="Log level" htmlFor="settings-log-level">
                  <select
                    id="settings-log-level"
                    value={draft.log_level}
                    onChange={(e) => setDraft({ ...draft, log_level: e.target.value })}
                    className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-xs outline-none transition-[color,box-shadow] focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50"
                  >
                    {LOG_LEVEL_OPTIONS.map((l) => <option key={l} value={l}>{l}</option>)}
                  </select>
                </FormField>

                <FormField label="HTTP timeout (s)" htmlFor="settings-timeout">
                  <Input
                    id="settings-timeout"
                    type="number"
                    min={1}
                    step={1}
                    value={String(draft.http_timeout_seconds)}
                    onChange={(e) => setDraft({ ...draft, http_timeout_seconds: Number(e.target.value) })}
                  />
                </FormField>

                <FormField label="Activity retention" htmlFor="settings-retention">
                  <select
                    id="settings-retention"
                    value={String(draft.activity_retention_days)}
                    onChange={(e) => setDraft({ ...draft, activity_retention_days: Number(e.target.value) })}
                    className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-xs outline-none transition-[color,box-shadow] focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50"
                  >
                    <option value="1">1 day</option>
                    <option value="7">7 days</option>
                    <option value="30">30 days</option>
                    <option value="90">90 days</option>
                    <option value="365">1 year</option>
                  </select>
                </FormField>
              </div>

              <FormField label="Webhook token" htmlFor="settings-webhook-token">
                <div className="flex items-center gap-2">
                  <code className="flex-1 rounded-md border border-input bg-muted px-3 py-2 font-mono text-xs break-all select-all">
                    {isTokenVisible ? (draft.webhook_shared_token ?? "—") : "•".repeat(32)}
                  </code>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    title={isTokenVisible ? "Hide token" : "Show token"}
                    onClick={() => setIsTokenVisible((v) => !v)}
                  >
                    {isTokenVisible ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    title="Regenerate token"
                    onClick={() => setDraft({ ...draft, webhook_shared_token: generateWebhookToken() })}
                  >
                    <RefreshCw className="size-4" />
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={!draft.webhook_shared_token}
                    title="Copy token"
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
                <FieldHint text="Auto-generated. Regenerate only if you need to rotate it — then re-run auto-configure in the Jellyfin step." />
              </FormField>

              <div className="flex items-center justify-between border-t pt-4">
                <p className="text-xs text-muted-foreground">
                  {isDirty ? "You have unsaved changes." : "All settings saved."}
                </p>
                <Button onClick={handleSave} disabled={!isDirty || isSaving}>
                  {isSaving
                    ? <LoaderCircle className="size-4 animate-spin" />
                    : <CheckCircle2 className="size-4 text-green-600 dark:text-green-400" />}
                  Save changes
                </Button>
              </div>
            </>
          ) : (
            <EmptyState
              title="Settings unavailable"
              description="Refresh the configuration and try again."
            />
          )}
        </CardContent>
      </Card>

    </section>
  )
}

// ─── Setup wizard ─────────────────────────────────────────────────────────────

function SetupWizard({
  config,
  dashboard,
  isConfigLoading,
  origin,
  curlPreview,
  onAddService,
  onEditService,
  onEditGeneral,
  onSetupWebhook,
  onClose,
}: {
  config: RuntimeConfigPayload | null
  dashboard: DashboardPayload | null
  isConfigLoading: boolean
  origin: string
  curlPreview: string
  onAddService: (family: ServiceFamily) => void
  onEditService: (family: ServiceFamily, service: ServiceRecord) => void
  onEditGeneral: () => void
  onSetupWebhook: (webhookUrl: string) => Promise<{ found: boolean; configured: boolean; message: string }>
  onClose: () => void
}) {
  const WIZARD_STEPS: Array<{ family: ServiceFamily | null; label: string }> = [
    { family: "jellyfin_server", label: "Jellyfin" },
    { family: "radarr", label: "Radarr" },
    { family: "sonarr", label: "Sonarr" },
    { family: "jellyseerr", label: "Jellyseerr" },
    { family: "downloaders", label: "qBittorrent" },
  ]

  return (
    <div className="fixed inset-0 z-50 overflow-auto bg-background/98 backdrop-blur-sm">
      <div className="mx-auto max-w-4xl px-6 py-6">
        {/* Header */}
        <div className="mb-6 flex items-center justify-between">
          <div>
            <CleanArrBrand size="sm" />
            <p className="mt-1 text-sm text-muted-foreground">
              First-time setup — configure each service to get started.
            </p>
          </div>
          <Button variant="ghost" size="sm" onClick={onClose}>
            Skip for now
          </Button>
        </div>

        <Stepper
          onFinalStepCompleted={onClose}
          nextButtonText="Next"
          backButtonText="Back"
          stepCircleContainerClassName="bg-card"
        >
          {/* Step 1: Jellyfin */}
          <Step>
            <div className="space-y-5 pb-4">
              <div>
                <h2 className="text-lg font-semibold">Jellyfin setup</h2>
                <p className="text-sm text-muted-foreground">
                  Connect your Jellyfin server and configure the webhook plugin.
                </p>
              </div>

              {/* 1.1 Runtime settings (webhook token) */}
              <div className="space-y-2">
                <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  1.1 — Runtime settings
                </p>
                <RuntimeSettingsCard
                  config={config?.general ?? null}
                  isLoading={isConfigLoading}
                  onEdit={onEditGeneral}
                />
              </div>

              {/* 1.2 Jellyfin server connection */}
              <div className="space-y-2">
                <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  1.2 — Server connection
                </p>
                <ServiceSetupPanel
                  meta={SERVICE_META.jellyfin_server}
                  services={getServices(config, "jellyfin_server")}
                  isLoading={isConfigLoading}
                  onAdd={() => onAddService("jellyfin_server")}
                  onEdit={(service) => onEditService("jellyfin_server", service)}
                />
              </div>

              {/* 1.3 Webhook configuration */}
              <div className="space-y-2">
                <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  1.3 — Webhook plugin
                </p>
                <JellyfinSetupPanel
                  dashboard={dashboard}
                  origin={origin}
                  curlPreview={curlPreview}
                  tokenConfigured={Boolean(config?.general.webhook_shared_token)}
                  jellyfinConfigured={Boolean(resolveActiveService(getServices(config, "jellyfin_server")))}
                  onOpenGeneral={onEditGeneral}
                  onSetupWebhook={onSetupWebhook}
                />
              </div>
            </div>
          </Step>

          {/* Steps 2–5: *arr services */}
          {WIZARD_STEPS.slice(1).map(({ family, label }) =>
            family ? (
              <Step key={family}>
                <div className="space-y-5 pb-4">
                  <div>
                    <h2 className="text-lg font-semibold">{label}</h2>
                    <p className="text-sm text-muted-foreground">
                      {SERVICE_META[family].description}
                    </p>
                  </div>
                  <ServiceSetupPanel
                    meta={SERVICE_META[family]}
                    services={getServices(config, family)}
                    isLoading={isConfigLoading}
                    onAdd={() => onAddService(family)}
                    onEdit={(service) => onEditService(family, service)}
                  />
                </div>
              </Step>
            ) : null,
          )}
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
  dashboard,
  origin,
  curlPreview,
  tokenConfigured,
  jellyfinConfigured,
  onOpenGeneral,
  onSetupWebhook,
}: {
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
    : "Not received yet"
  const statusLabel = getWebhookStatusLabel(webhookStatus?.outcome ?? "waiting")

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
        message: err instanceof Error ? err.message : "Unknown error",
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
            Auto-configure webhook
          </CardTitle>
          <CardDescription>
            CleanArr configures the Jellyfin Webhook plugin automatically. The plugin must already be
            installed in Jellyfin → Dashboard → Plugins → Catalog.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {!jellyfinConfigured && (
            <Alert>
              <Info className="size-4 text-blue-600 dark:text-blue-400" />
              <AlertDescription>
                Connect the Jellyfin server (step 1.2) before auto-configuring the webhook.
              </AlertDescription>
            </Alert>
          )}
          {jellyfinConfigured && !tokenConfigured && (
            <Alert>
              <CircleAlert className="size-4" />
              <AlertDescription>
                Set a webhook token in{" "}
                <button
                  type="button"
                  className="underline underline-offset-2"
                  onClick={onOpenGeneral}
                >
                  Runtime settings
                </button>{" "}
                first — it will be included in the plugin config.
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
                ? "Configuring…"
                : setupState.status === "success"
                  ? "Configured"
                  : "Auto-configure webhook"}
            </Button>
            {setupState.status === "success" && <StatusPill tone="green" label="Done" />}
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
                title="Install the Jellyfin Webhook plugin"
                description="Jellyfin → Dashboard → Plugins → Catalog → search Webhook → install → restart if prompted."
              >
                <InstructionList items={JELLYFIN_INSTALL_STEPS} />
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
            Verify delivery
          </CardTitle>
          <CardDescription>
            CleanArr records every inbound webhook attempt so you can confirm delivery without a real
            deletion event.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
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
              <span className="font-medium">Smoke test (cURL)</span>
              <span className="ml-auto text-xs text-muted-foreground">
                {tokenConfigured ? "token pre-filled" : "configure token first"}
              </span>
            </button>
            {curlOpen && (
              <CardContent className="space-y-3 border-t pt-3">
                <p className="text-xs text-muted-foreground">
                  Sends a synthetic ItemDeleted event to CleanArr. Use this to confirm network
                  connectivity and token auth before a real deletion.
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
                  Copy cURL
                </Button>
              </CardContent>
            )}
          </Card>
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
  const [tokenCopied, setTokenCopied] = useState(false)

  useEffect(() => {
    setDraft(config ? structuredClone(config) : null)
    setTokenCopied(false)
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
            Save settings
          </Button>
        </div>
      }
    >
      {draft ? (
        <div className="space-y-5">
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

          <FormField label="Webhook token" htmlFor="general-webhook-token">
            <div className="flex items-center gap-2">
              <code className="flex-1 rounded-md border border-input bg-muted px-3 py-2 font-mono text-xs break-all select-all">
                {draft.webhook_shared_token ?? "—"}
              </code>
              <Button
                type="button"
                variant="outline"
                size="sm"
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
            <FieldHint text="Auto-generated. Regenerate only if you need to rotate it — then re-run auto-configure in the Jellyfin step." />
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
  jellyfinSetupProps,
}: {
  state: ServiceModalState | null
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
              Test
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
              Save
            </Button>
          </div>
        </div>
      }
    >
      {draft ? (
        <div className="space-y-4">
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

          {state.family === "jellyfin_server" && jellyfinSetupProps && (
            <div className="mt-6 space-y-5 border-t pt-5">
              <p className="text-sm font-semibold text-muted-foreground uppercase tracking-wider">Webhook</p>
              <JellyfinSetupPanel
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

// ─── Library panel ────────────────────────────────────────────────────────────

function LibrarySeriesTab({
  library,
  isLoading,
  onRefresh,
  onDelete,
}: {
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
  onRefresh,
  onDelete,
}: {
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
  libraryMovies,
  isLibraryMoviesLoading,
  isLive,
  onRefreshSeries,
  onRefreshMovies,
  onDelete,
}: {
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
            onRefresh={onRefreshSeries}
            onDelete={onDelete}
          />
        </TabsContent>
        <TabsContent value="movies" className="mt-4">
          <LibraryMoviesTab
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

export default CleanArrApp
