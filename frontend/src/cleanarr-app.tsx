import { lazy, Suspense, useCallback, useDeferredValue, useEffect, useMemo, useReducer, useRef, useState } from "react"
import { toast } from "sonner"

import { useTheme } from "@/components/theme-provider"
import { AppShell, type AppShellPage, type SettingsSection, type StorageHeadline } from "@/features/app-shell/app-shell"
import { SHELL_COPY } from "@/features/app-shell/shell-copy"
import { ActivityPanel } from "@/features/activity/activity-panel"
import { AuthScreen, AuthScreenSkeleton } from "@/features/auth/auth-screen"
import { validateAuthForm } from "@/features/auth/auth-validation"
import { DashboardPanel } from "@/features/dashboard/dashboard-panel"
import { STORAGE_COPY, type StorageCopy } from "@/features/dashboard/storage-copy"
const DownloadsPanel = lazy(() => import("@/features/downloads/downloads-panel").then((module) => ({ default: module.DownloadsPanel })))
import { DeleteConfirmationDialog } from "@/features/deletion/delete-confirmation-dialog"
import { buildConfirmedDeleteRequest, deleteSessionReducer, initialDeleteSession } from "@/features/deletion/delete-session"
import { BatchDeleteConfirmationDialog } from "@/features/deletion/batch-delete-confirmation-dialog"
import { batchChildRequests, batchDeleteSessionReducer, buildBatchRequest, initialBatchDeleteSession } from "@/features/deletion/batch-delete-session"
import { DELETION_NOTICES, localizedDeletionError, submissionRecovery } from "@/features/deletion/deletion-copy"
import { JobsSheet } from "@/features/jobs/jobs-sheet"
import { batchTransitionAnnouncement, isTerminalBatchStatus } from "@/features/jobs/batch-status"
import { simulationBatchCompletionNotice, simulationJobCompletionNotice } from "@/features/jobs/simulation-outcome"
import { LibraryPanelV2 } from "@/features/library/library-v2-panel"
import { LIBRARY_COPY } from "@/features/library/library-copy"
import { buildManualDeleteRequest, libraryDeleteTargetFromItem, librarySelectionItemFromItem, type BatchSelectionItem, type LibraryDeleteTarget } from "@/features/library/library-selection"
import { GeneralSettingsModal, ServiceModal, SettingsPanel } from "@/features/settings/settings-panel"
import { SetupWizard } from "@/features/setup/setup-wizard"
import { UsersPanel } from "@/features/users/users-panel"
import { Skeleton } from "@/components/ui/skeleton"
import type { AuthSessionPayload, AuthStatusPayload, SSOLoginPayload } from "@/lib/auth"
import type { DashboardActivity, DashboardPayload, DashboardWebhookAttempt } from "@/lib/dashboard"
import { getUiText, resolveUiLanguage, type UiLanguage, type UiTextMap } from "@/lib/i18n"
import { createClientIdempotencyKey } from "@/lib/idempotency"
import type { LibraryItem, ManualDeleteBatch, ManualDeleteBatchListResponse, ManualDeleteJob, ManualDeleteJobListResponse, ManualDeletePreviewResponse } from "@/lib/library"
import type { ConnectionTestResponse, GeneralConfig, RuntimeConfigPayload } from "@/lib/runtime-config"
import { buildServicePayload, DASHBOARD_NAME_TO_FAMILY, EMPTY_DRAFTS, getDownloaderLabel, getServiceEndpoint, getServiceTitle, getServices, isSetupStepConfigured, resolveActiveService, SERVICE_META, SETUP_STEPS, toDraft, type DownloaderKind, type ServiceDraft, type ServiceFamily, type ServiceModalState } from "@/lib/service-config"
import { normalizeError } from "@/lib/status-format"
import { connectionFingerprint } from "@/lib/downloader-profile"
import { useStorage, type StorageResponse } from "@/lib/storage"
import { useApiClient } from "@/lib/use-api-client"

type AuthMode = "register" | "login"

// ─── Main component ───────────────────────────────────────────────────────────

function CleanArrApp() {
  const { theme, setTheme } = useTheme()
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
  const [activeTab, setActiveTab] = useState<AppShellPage>("overview")
  const [settingsSection, setSettingsSection] = useState<SettingsSection>("cleanarr")
  const [, setDownloadsActiveCount] = useState<number | null>(null)
  const [authForm, setAuthForm] = useState({ username: "", password: "", confirmPassword: "" })
  const [ssoError, setSsoError] = useState<string | null>(null)
  const [generalModalOpen, setGeneralModalOpen] = useState(false)
  const [serviceModal, setServiceModal] = useState<ServiceModalState | null>(null)
  const [testedDownloaderFingerprints, setTestedDownloaderFingerprints] = useState<Set<string>>(() => new Set())
  const [csrfToken, setCsrfToken] = useState("")
  const [libraryResetKey, setLibraryResetKey] = useState(0)
  const hasAutoNavigated = useRef(false)

  const [deleteSession, dispatchDeleteSession] = useReducer(deleteSessionReducer<LibraryDeleteTarget>, undefined, initialDeleteSession<LibraryDeleteTarget>)
  const [batchDeleteSession, dispatchBatchDeleteSession] = useReducer(batchDeleteSessionReducer, undefined, initialBatchDeleteSession)
  const [deleteJobs, setDeleteJobs] = useState<ManualDeleteJob[]>([])
  const [deleteBatches, setDeleteBatches] = useState<ManualDeleteBatch[]>([])
  const [deleteJobAnnouncement, setDeleteJobAnnouncement] = useState<string | null>(null)
  const [deleteJobAnnouncementTone, setDeleteJobAnnouncementTone] = useState<"polite" | "assertive">("polite")
  const knownDeleteJobStates = useRef(new Map<string, ManualDeleteJob["status"]>())
  const knownDeleteBatchStates = useRef(new Map<string, ManualDeleteBatch["status"]>())
  const hasLoadedDeleteJobs = useRef(false)
  const hasLoadedDeleteBatches = useRef(false)
  const deleteJobsPollFailed = useRef(false)
  const deleteBatchesPollFailed = useRef(false)
  const deleteSubmitLock = useRef(false)
  const batchSubmitLock = useRef(false)
  const deleteReturnFocusRef = useRef<HTMLElement | null>(null)
  const batchDeleteReturnFocusRef = useRef<HTMLElement | null>(null)
  const setupWizardReturnFocusRef = useRef<HTMLElement | null>(null)
  const settingsModalReturnFocusRef = useRef<HTMLElement | null>(null)

  useEffect(() => {
    window.scrollTo({ top: 0, left: 0, behavior: "auto" })
  }, [activeTab])

  const deferredFilter = useDeferredValue(activityFilter)
  const uiLanguage = useMemo(
    () => resolveUiLanguage(config?.general.ui_language ?? authStatus?.ui_language),
    [authStatus?.ui_language, config?.general.ui_language],
  )
  const uiText = useMemo(() => getUiText(uiLanguage), [uiLanguage])

  const fetchJson = useApiClient(csrfToken, setCsrfToken)
  const storage = useStorage({
    active: Boolean(authStatus?.authenticated),
    authenticated: Boolean(authStatus?.authenticated),
    fetchJson,
  })

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
      setCsrfToken(payload.csrf_token ?? "")
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
          const name = job.display_name || job.item_name || job.item_type
          if (job.status === "failed" || job.result?.status === "partial_failure") {
            const message = `${name}: ${DELETION_NOTICES[uiLanguage === "ru" ? "ru" : "en"].jobNeedsAttention}`
            toast.error(message)
            setDeleteJobAnnouncement(message)
            setDeleteJobAnnouncementTone("assertive")
          } else {
            const completedMessage = simulationJobCompletionNotice(job, uiLanguage === "ru" ? "ru" : "en") ?? DELETION_NOTICES[uiLanguage === "ru" ? "ru" : "en"].jobCompleted
            toast.success(`${name}: ${completedMessage}`)
            setDeleteJobAnnouncement(`${name}: ${completedMessage}`)
            setDeleteJobAnnouncementTone("polite")
          }
          void loadDashboard(true)
          setLibraryResetKey((current) => current + 1)
        }

        knownDeleteJobStates.current.set(job.id, job.status)
      })
    } catch (error) {
      if (!deleteJobsPollFailed.current) {
        toast.error(`${uiText.backgroundRefreshFailed}: ${normalizeError(error)}`)
        deleteJobsPollFailed.current = true
      }
    }
  }, [fetchJson, loadDashboard, uiLanguage, uiText.backgroundRefreshFailed])

  const loadDeleteBatches = useCallback(async () => {
    try {
      const payload = await fetchJson<ManualDeleteBatchListResponse>("/api/actions/delete/batches?limit=20")
      setDeleteBatches(payload.batches)
      deleteBatchesPollFailed.current = false
      if (!hasLoadedDeleteBatches.current) {
        payload.batches.forEach((batch) => knownDeleteBatchStates.current.set(batch.id, batch.status))
        hasLoadedDeleteBatches.current = true
        return
      }
      payload.batches.forEach((batch) => {
        const previousStatus = knownDeleteBatchStates.current.get(batch.id)
        if (previousStatus != null && previousStatus !== batch.status && isTerminalBatchStatus(batch.status)) {
          const simulationMessage = simulationBatchCompletionNotice(batch, uiLanguage === "ru" ? "ru" : "en")
          const announcement = simulationMessage
            ? { message: simulationMessage, tone: "polite" as const }
            : batchTransitionAnnouncement(batch, uiLanguage === "ru" ? "ru" : "en")
          setDeleteJobAnnouncement(announcement.message)
          setDeleteJobAnnouncementTone(announcement.tone)
          if (announcement.tone === "assertive") toast.error(announcement.message)
          else toast.success(announcement.message)
          void loadDashboard(true)
          setLibraryResetKey((current) => current + 1)
        }
        knownDeleteBatchStates.current.set(batch.id, batch.status)
      })
    } catch (error) {
      if (!deleteBatchesPollFailed.current) {
        toast.error(`${uiText.backgroundRefreshFailed}: ${normalizeError(error)}`)
        deleteBatchesPollFailed.current = true
      }
    }
  }, [fetchJson, loadDashboard, uiLanguage, uiText.backgroundRefreshFailed])

  useEffect(() => {
    if (deleteSession.phase !== "preparing" || !deleteSession.target) return
    const controller = new AbortController()
    const { sessionId, attempt, target } = deleteSession
    void fetchJson<ManualDeletePreviewResponse>("/api/actions/delete/preview", {
      method: "POST",
      body: JSON.stringify(buildManualDeleteRequest(target, deleteSession.displayName ?? "")),
      signal: controller.signal,
    })
      .then((preview) => dispatchDeleteSession({ type: "preflight_ready", sessionId, attempt, preview }))
      .catch((error) => {
        if (controller.signal.aborted) return
        const outcome = localizedDeletionError(error, uiLanguage === "ru" ? "ru" : "en")
        dispatchDeleteSession({ type: "preflight_failed", sessionId, attempt, code: outcome.code, message: outcome.message })
      })
    return () => controller.abort()
  }, [deleteSession, fetchJson, uiLanguage])

  useEffect(() => {
    if (batchDeleteSession.phase !== "preparing" || !batchDeleteSession.items.length) return
    const controller = new AbortController()
    const { sessionId, attempt, items } = batchDeleteSession
    void fetchJson<import("@/lib/library").ManualDeleteBatchPreviewResponse>("/api/actions/delete/batches/preview", {
      method: "POST",
      body: JSON.stringify({ children: batchChildRequests(items) }),
      signal: controller.signal,
    }).then((preview) => dispatchBatchDeleteSession({ type: "preflight_ready", sessionId, attempt, preview })).catch((error) => {
      if (controller.signal.aborted) return
      const outcome = localizedDeletionError(error, uiLanguage === "ru" ? "ru" : "en")
      dispatchBatchDeleteSession({ type: "preflight_failed", sessionId, attempt, code: outcome.code, message: outcome.message })
    })
    return () => controller.abort()
  }, [batchDeleteSession, fetchJson, uiLanguage])

  const executeDelete = useCallback(async () => {
    if (deleteSubmitLock.current) return
    const retryingExact = deleteSession.phase === "submission_failed" && deleteSession.recovery === "resend_exact"
    if (deleteSession.phase !== "ready" && !retryingExact) return
    const request = retryingExact ? deleteSession.submittedRequest : buildConfirmedDeleteRequest(deleteSession, buildManualDeleteRequest)
    const serializedRequest = retryingExact ? deleteSession.serializedRequest : request ? JSON.stringify(request) : null
    if (!request || !serializedRequest) return
    deleteSubmitLock.current = true
    dispatchDeleteSession(retryingExact ? { type: "resend_exact" } : { type: "submit", request, serializedRequest })
    try {
      const job = await fetchJson<ManualDeleteJob>("/api/actions/delete/jobs", {
        method: "POST",
        body: serializedRequest,
      })
      knownDeleteJobStates.current.set(job.id, job.status)
      hasLoadedDeleteJobs.current = true
      setDeleteJobs((current) => [job, ...current.filter((item) => item.id !== job.id)])
      dispatchDeleteSession({ type: "submitted", jobId: job.id })
      toast.success(uiText.deletionStarted)
    } catch (error) {
      const outcome = localizedDeletionError(error, uiLanguage === "ru" ? "ru" : "en")
      dispatchDeleteSession({ type: "submission_failed", code: outcome.code, message: outcome.message, recovery: submissionRecovery(error) })
    } finally {
      deleteSubmitLock.current = false
    }
  }, [deleteSession, fetchJson, uiLanguage, uiText.deletionStarted])

  const executeBatchDelete = useCallback(async () => {
    if (batchSubmitLock.current) return
    const retryingExact = batchDeleteSession.phase === "submission_failed" && batchDeleteSession.recovery === "resend_exact"
    if (batchDeleteSession.phase !== "ready" && !retryingExact) return
    const request = retryingExact ? batchDeleteSession.submittedRequest : buildBatchRequest(batchDeleteSession)
    const serializedRequest = retryingExact ? batchDeleteSession.serializedRequest : request ? JSON.stringify(request) : null
    if (!request || !serializedRequest) return
    batchSubmitLock.current = true
    dispatchBatchDeleteSession(retryingExact ? { type: "resend_exact" } : { type: "submit", request, serializedRequest })
    try {
      const batch = await fetchJson<ManualDeleteBatch>("/api/actions/delete/batches", { method: "POST", body: serializedRequest })
      knownDeleteBatchStates.current.set(batch.id, batch.status)
      hasLoadedDeleteBatches.current = true
      setDeleteBatches((current) => [batch, ...current.filter((item) => item.id !== batch.id)])
      dispatchBatchDeleteSession({ type: "submitted", batch })
      setLibraryResetKey((current) => current + 1)
      toast.success(DELETION_NOTICES[uiLanguage === "ru" ? "ru" : "en"].batchAccepted)
    } catch (error) {
      const outcome = localizedDeletionError(error, uiLanguage === "ru" ? "ru" : "en")
      dispatchBatchDeleteSession({ type: "submission_failed", code: outcome.code, message: outcome.message, recovery: submissionRecovery(error) })
    } finally { batchSubmitLock.current = false }
  }, [batchDeleteSession, fetchJson, uiLanguage])

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
    if (!authStatus?.authenticated) {
      setDashboard(null)
      setIsDashboardLoading(false)
      return
    }
    void loadDashboard()
    const id = window.setInterval(() => void loadDashboard(true), 15000)
    return () => window.clearInterval(id)
  }, [authStatus?.authenticated, loadDashboard])

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
    (job) => job.status === "queued" || job.status === "running" || job.status === "retry_wait",
  )

  const hasActiveBatches = deleteBatches.some((batch) => batch.status === "queued" || batch.status === "running")
  useEffect(() => {
    if (!authStatus?.authenticated) return
    void loadDeleteJobs()
    void loadDeleteBatches()
    const id = window.setInterval(
      () => { void loadDeleteJobs(); void loadDeleteBatches() },
      hasActiveDeleteJobs || hasActiveBatches ? 1000 : 5000,
    )
    return () => window.clearInterval(id)
  }, [authStatus?.authenticated, hasActiveBatches, hasActiveDeleteJobs, loadDeleteBatches, loadDeleteJobs])

  useEffect(() => {
    if (authStatus?.authenticated && authStatus.role === "admin") {
      void loadConfig()
    } else if (authStatus) {
      setConfig(null)
    }
  }, [authStatus, loadConfig])

  const setupCompletionCount = useMemo(
    () => SETUP_STEPS.reduce((n, step) => n + (isSetupStepConfigured(step.id, config) ? 1 : 0), 0),
    [config],
  )

  // Auto-navigate to Dashboard once setup is fully complete (one-time)
  useEffect(() => {
    if (!hasAutoNavigated.current && config && setupCompletionCount === SETUP_STEPS.length) {
      hasAutoNavigated.current = true
      setActiveTab("overview")
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

  const allServicesConfigured = SETUP_STEPS.every((step) =>
    isSetupStepConfigured(step.id, config),
  )

  const deletedActions = (dashboard?.recent_activity ?? []).reduce(
    (n, e) => n + (e.action_summary.deleted ?? 0),
    0,
  )

  const latestActivity = dashboard?.recent_activity[0] ?? null

  const submitAuthForm = async () => {
    const validationError = validateAuthForm(authMode, authForm)
    if (validationError) {
      toast.error(uiText[validationError])
      return
    }
    setIsAuthSubmitting(true)
    try {
      const payload = await fetchJson<AuthSessionPayload>(
        authMode === "register" ? "/api/auth/register" : "/api/auth/login",
        {
          method: "POST",
          body: JSON.stringify({ username: authForm.username.trim(), password: authForm.password }),
        },
      )
      setCsrfToken(payload.csrf_token)
      setAuthForm({ username: payload.username, password: "", confirmPassword: "" })
      setActiveTab("overview")
      await loadAuth()
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
      // Refresh below will resolve whether the server-side session is still valid.
    }
    setCsrfToken("")
    setAuthStatus((current) => current ? {
      ...current,
      authenticated: false,
      username: null,
      role: null,
      csrf_token: null,
    } : current)
    setSsoError(null)
    setAuthForm({ username: "", password: "", confirmPassword: "" })
    setDeleteJobs([])
    setDeleteBatches([])
    knownDeleteJobStates.current.clear()
    knownDeleteBatchStates.current.clear()
    hasLoadedDeleteJobs.current = false
    hasLoadedDeleteBatches.current = false
    deleteJobsPollFailed.current = false
    deleteBatchesPollFailed.current = false
    setLibraryResetKey((current) => current + 1)
    await loadAuth()
  }

  const saveGeneralSettings = async (payload: GeneralConfig) => {
    const next = await fetchJson<RuntimeConfigPayload>("/api/config/general", {
      method: "PUT",
      body: JSON.stringify(payload),
    })
    setConfig(next)
    setLibraryResetKey((current) => current + 1)
    await loadAuth()
    toast.success(getUiText(resolveUiLanguage(next.general.ui_language)).runtimeSettingsSaved)
  }

  const saveServiceDraft = async (family: ServiceFamily, draft: ServiceDraft) => {
    const endpoint = getServiceEndpoint(family, draft.downloader_kind)
    const body = JSON.stringify(buildServicePayload(family, draft))
    const next = draft.id
      ? await fetchJson<RuntimeConfigPayload>(`${endpoint}/${draft.id}`, { method: "PUT", body })
      : await fetchJson<RuntimeConfigPayload>(endpoint, { method: "POST", body })
    setConfig(next)
    await loadDashboard(true)
    setLibraryResetKey((current) => current + 1)
    setServiceModal(null)
    toast.success(`${getServiceTitle(family, draft)} ${draft.id ? uiText.serviceUpdated : uiText.serviceAdded}.`)
  }

  const deleteServiceDraft = async (family: ServiceFamily, serviceId: string) => {
    const existing = getServices(config, family).find((service) => service.id === serviceId)
    const kind = existing && "kind" in existing && family === "downloaders"
      ? existing.kind as DownloaderKind
      : null
    await fetchJson<void>(`${getServiceEndpoint(family, kind)}/${serviceId}`, { method: "DELETE" })
    const next = await fetchJson<RuntimeConfigPayload>("/api/config")
    setConfig(next)
    await loadDashboard(true)
    setLibraryResetKey((current) => current + 1)
    setServiceModal(null)
    toast.success(`${family === "downloaders" ? getDownloaderLabel(kind) : SERVICE_META[family].title} ${uiText.serviceRemoved}.`)
  }

  const testServiceDraft = async (family: ServiceFamily, draft: ServiceDraft) => {
    const result = await fetchJson<ConnectionTestResponse>(`${getServiceEndpoint(family, draft.downloader_kind)}/test`, {
      method: "POST",
      body: JSON.stringify(buildServicePayload(family, draft)),
    })
    if (family === "downloaders" && result.ok) {
      setTestedDownloaderFingerprints((current) => new Set(current).add(connectionFingerprint(draft)))
    }
    return result
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
  const isAdmin = authStatus.role === "admin"

  // ─── Main app ──────────────────────────────────────────────────────────────

  const shellLanguage = uiLanguage === "ru" ? "ru" : "en"
  const shellStorage = toShellStorage(storage.data, STORAGE_COPY[shellLanguage])
  const libraryCopy = LIBRARY_COPY[shellLanguage]
  const openDeletePreview = (target: LibraryDeleteTarget, trigger: HTMLElement) => {
    deleteReturnFocusRef.current = trigger
    dispatchDeleteSession({ type: "open", target, displayName: getDeleteTargetLabel(target, uiText), idempotencyKey: createDeleteSessionKey() })
  }
  const openLibraryDeletePreview = (item: LibraryItem, trigger: HTMLElement) => {
    const target = libraryDeleteTargetFromItem(item)
    if (!target) {
      toast.error(libraryCopy.itemChanged)
      return
    }
    openDeletePreview(target, trigger)
  }
  const openLibraryBatchPreview = (items: LibraryItem[], trigger: HTMLElement) => {
    const selected: BatchSelectionItem[] = []
    for (const item of items) {
      const candidate = librarySelectionItemFromItem(item)
      if (!candidate) {
        toast.error(libraryCopy.selectedItemChanged)
        return
      }
      selected.push(candidate)
    }
    batchDeleteReturnFocusRef.current = trigger
    dispatchBatchDeleteSession({ type: "open", items: selected, idempotencyKey: createDeleteSessionKey() })
  }

  return (
    <>
      <AppShell
        activePage={activeTab}
        onPageChange={setActiveTab}
        settingsSection={settingsSection}
        onSettingsSectionChange={setSettingsSection}
        username={authStatus.username}
        theme={theme}
        onThemeChange={setTheme}
        language={shellLanguage}
        onLanguageChange={(language) => {
          if (config && config.general.ui_language !== language) {
            void saveGeneralSettings({ ...config.general, ui_language: language })
          }
        }}
        onLogout={() => void logout()}
        dryRun={!isLive}
        storageHeadline={shellStorage}
        labels={SHELL_COPY[shellLanguage]}
        canAdmin={isAdmin}
        jobsSlot={deleteJobs.length || deleteBatches.length ? <JobsSheet
          jobs={deleteJobs}
          batches={deleteBatches}
          title={uiText.backgroundTasks}
          activeLabel={uiText.active}
          recentLabel={uiText.recent}
          dismissLabel={uiText.dismiss}
          closeLabel={uiLanguage === "ru" ? "Закрыть" : "Close"}
          progressLabel={uiText.progress}
          language={uiLanguage === "ru" ? "ru" : "en"}
          announcement={deleteJobAnnouncement}
          announcementTone={deleteJobAnnouncementTone}
          canDismiss={isAdmin}
          onDismiss={(jobId) => void dismissDeleteJob(jobId)}
        /> : null}
      >
        <div className={activeTab === "library" ? "mx-auto w-full max-w-[100rem]" : "mx-auto w-full max-w-6xl"}>
          <div hidden={activeTab !== "overview"}>
            <DashboardPanel
              text={uiText}
              dashboard={dashboard}
              isDashboardLoading={isDashboardLoading}
              setupCompletionCount={setupCompletionCount}
              deletedActions={deletedActions}
              latestActivity={latestActivity}
              allServicesConfigured={allServicesConfigured}
              isLive={isLive}
              storage={storage.data}
              storageLoading={storage.loading || storage.refreshing}
              storageError={storage.error}
              storageLanguage={shellLanguage}
              readOnly={!isAdmin}
              onRefreshStorage={isAdmin ? () => void storage.refresh() : undefined}
              onToggleDryRun={async () => {
                if (config) await saveGeneralSettings({ ...config.general, dry_run: !config.general.dry_run })
              }}
              onOpenWizard={(trigger) => {
                setupWizardReturnFocusRef.current = trigger
                setShowWizard(true)
              }}
              onEditService={(name, trigger) => {
                const family = DASHBOARD_NAME_TO_FAMILY[name]
                if (!family) return
                settingsModalReturnFocusRef.current = trigger
                const services = getServices(config, family)
                const active = resolveActiveService(services)
                setServiceModal({ family, draft: active ? toDraft(active) : structuredClone(EMPTY_DRAFTS[family]) })
              }}
            />
          </div>

          <div hidden={activeTab !== "library"}>
            <LibraryPanelV2
              key={libraryResetKey}
              active={activeTab === "library"}
              authenticated={Boolean(authStatus.authenticated)}
              language={shellLanguage}
              fetchJson={fetchJson}
              resetKey={libraryResetKey}
              onDeletePreview={isAdmin ? openLibraryDeletePreview : undefined}
              onBatchPreview={isAdmin ? openLibraryBatchPreview : undefined}
            />
          </div>

          <div hidden={activeTab !== "downloads"}>
            <Suspense fallback={<div className="space-y-3"><Skeleton className="h-8 w-40" /><Skeleton className="h-32 w-full" /></div>}>
              <DownloadsPanel
                active={activeTab === "downloads"}
                authenticated={Boolean(authStatus.authenticated)}
                language={shellLanguage}
                isLive={isLive}
                canMutate={isAdmin}
                fetchJson={fetchJson}
                onActiveCountChange={setDownloadsActiveCount}
                onDelete={openDeletePreview}
                onBatchPreview={(items, trigger) => {
                  batchDeleteReturnFocusRef.current = trigger
                  dispatchBatchDeleteSession({ type: "open", items, idempotencyKey: createDeleteSessionKey() })
                }}
              />
            </Suspense>
          </div>

          <div hidden={activeTab !== "activity"}>
            <ActivityPanel text={uiText} language={shellLanguage} filteredActivity={filteredActivity} webhookAttempts={filteredWebhookAttempts} activityFilter={activityFilter} onFilterChange={setActivityFilter} />
          </div>

          {isAdmin ? <div hidden={activeTab !== "users"}>
            <UsersPanel active={activeTab === "users"} language={shellLanguage} currentUsername={authStatus.username} currentRole={authStatus.role} fetchJson={fetchJson} onCurrentRoleChange={(role) => setAuthStatus((current) => current ? { ...current, role } : current)} />
          </div> : null}

          {isAdmin ? <div hidden={activeTab !== "settings"}>
            <SettingsPanel
              text={uiText}
              language={uiLanguage}
              settingsSection={settingsSection}
              onSettingsSectionChange={setSettingsSection}
              config={config}
              isConfigLoading={isConfigLoading}
              onSaveGeneral={saveGeneralSettings}
              onAddService={(family, trigger) => {
                settingsModalReturnFocusRef.current = trigger
                setServiceModal({ family, draft: structuredClone(EMPTY_DRAFTS[family]) })
              }}
              onEditService={(family, service, trigger) => {
                settingsModalReturnFocusRef.current = trigger
                setServiceModal({ family, draft: toDraft(service) })
              }}
            />
          </div> : null}
        </div>
      </AppShell>

      {/* ── Setup wizard overlay ── */}
      {isAdmin && showWizard && (
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
          returnFocusRef={setupWizardReturnFocusRef}
          testedDownloaderFingerprints={testedDownloaderFingerprints}
        />
      )}

      {/* Modals */}
      {isAdmin ? <GeneralSettingsModal
        open={generalModalOpen}
        text={uiText}
        config={config?.general ?? null}
        onClose={() => setGeneralModalOpen(false)}
        onSave={async (payload) => {
          await saveGeneralSettings(payload)
          setGeneralModalOpen(false)
        }}
        returnFocusRef={settingsModalReturnFocusRef}
      /> : null}

      {isAdmin ? <ServiceModal
        state={serviceModal}
        text={uiText}
        onClose={() => setServiceModal(null)}
        onSave={saveServiceDraft}
        onDelete={deleteServiceDraft}
        onTest={testServiceDraft}
        returnFocusRef={settingsModalReturnFocusRef}
        jellyfinSetupProps={serviceModal?.family === "jellyfin_server" ? {
          dashboard,
          origin,
          curlPreview,
          tokenConfigured: Boolean(config?.general.webhook_shared_token),
          onSetupWebhook: handleSetupWebhook,
        } : undefined}
      /> : null}

      <DeleteConfirmationDialog
        open={deleteSession.phase !== "closed"}
        title={uiText.titleDeleteConfirmation.replace("{{title}}", deleteSession.displayName ?? "")}
        phase={deleteSession.phase}
        preview={deleteSession.preview}
        error={deleteSession.errorMessage}
        isDryRun={!isLive}
        language={uiLanguage === "ru" ? "ru" : "en"}
        copy={getDeleteDialogCopy(uiLanguage, uiText)}
        returnFocusRef={deleteReturnFocusRef}
        onConfirm={() => void executeDelete()}
        onRetry={() => {
          if (deleteSession.phase === "submission_failed" && deleteSession.recovery === "resend_exact") {
            void executeDelete()
          } else if (deleteSession.phase === "submission_failed" && deleteSession.recovery === "rotate_session" && deleteSession.target && deleteSession.displayName) {
            dispatchDeleteSession({ type: "open", target: deleteSession.target, displayName: deleteSession.displayName, idempotencyKey: createDeleteSessionKey() })
          } else {
            dispatchDeleteSession({ type: "retry_preflight" })
          }
        }}
        onClose={() => dispatchDeleteSession({ type: "close" })}
      />

      <BatchDeleteConfirmationDialog
        open={batchDeleteSession.phase !== "closed"}
        phase={batchDeleteSession.phase}
        preview={batchDeleteSession.preview}
        items={batchDeleteSession.items}
        error={batchDeleteSession.errorMessage}
        isDryRun={!isLive}
        language={uiLanguage === "ru" ? "ru" : "en"}
        returnFocusRef={batchDeleteReturnFocusRef}
        onConfirm={() => void executeBatchDelete()}
        onRetry={() => {
          if (batchDeleteSession.phase === "submission_failed" && batchDeleteSession.recovery === "resend_exact") void executeBatchDelete()
          else if (batchDeleteSession.phase === "submission_failed" && batchDeleteSession.recovery === "rotate_session") dispatchBatchDeleteSession({ type: "open", items: batchDeleteSession.items, idempotencyKey: createDeleteSessionKey() })
          else dispatchBatchDeleteSession({ type: "retry_preflight" })
        }}
        onClose={() => {
          if (!batchDeleteReturnFocusRef.current?.isConnected) {
            batchDeleteReturnFocusRef.current = document.querySelector<HTMLElement>("[data-batch-focus-fallback]")
          }
          dispatchBatchDeleteSession({ type: "close" })
        }}
      />

    </>
  )
}

// ─── Auth screens ─────────────────────────────────────────────────────────────

// ─── Setup wizard ─────────────────────────────────────────────────────────────

// ─── Small UI components ──────────────────────────────────────────────────────

// ─── Utilities ────────────────────────────────────────────────────────────────

const createDeleteSessionKey = createClientIdempotencyKey

function getDeleteTargetLabel(target: LibraryDeleteTarget, text: UiTextMap): string {
  if (target.kind === "movie" || target.kind === "jellyfin_movie") return target.movie_title
  return target.item_type === "Season"
    ? text.seasonOfSeries.replace("{{season}}", String(target.season_number)).replace("{{series}}", target.series_title)
    : target.series_title
}

function toShellStorage(data: StorageResponse | null, text: StorageCopy): StorageHeadline {
  if (!data) {
    return { status: "unknown", headline: text.unavailable }
  }
  const representative = data.volumes.find((volume) => volume.status === data.status && volume.freshness === "fresh")
    ?? data.volumes.find((volume) => volume.status === data.status)
    ?? data.volumes[0]
  const freePercent = representative?.free_percent
  const headline = typeof freePercent === "number"
    ? `${Math.round(freePercent)}% ${text.free.toLocaleLowerCase()}`
    : text.unknown
  return {
    status: data.status,
    headline,
    detail: representative?.display_label,
    percent: typeof freePercent === "number" ? 100 - freePercent : undefined,
    partial: data.partial,
    freshness: data.freshness === "stale" ? text.stale : undefined,
  }
}

function getDeleteDialogCopy(language: UiLanguage, text: UiTextMap) {
  const russian = language === "ru"
  return {
    cancel: text.cancel,
    delete: text.delete,
    simulateAction: russian ? "Симулировать" : "Simulate",
    dryRunNotice: russian ? "Режим проверки: изменения не будут выполнены." : "Dry-run: no changes will be made.",
    retry: russian ? "Повторить" : "Retry",
    technicalDetails: russian ? "Технические сведения" : "Technical details",
    remove: russian ? "Будет удалено" : "Will be removed",
    retain: russian ? "Останется" : "Will be retained",
    attention: russian ? "Требует внимания" : "Needs attention",
    unknownSize: russian ? "Точный объём в плане не указан." : "The plan does not provide an estimated size.",
    preparing: russian ? "Готовим безопасный план… подтверждение пока недоступно." : "Preparing a safe plan… confirmation is not available yet.",
    ready: russian ? "Проверьте план; одного подтверждения достаточно." : "Review the plan; one confirmation is enough.",
    submitting: russian ? "Отправляем подтверждённую задачу. Закрытие временно недоступно." : "Submitting the confirmed job. Closing is temporarily unavailable.",
    submitted: russian ? "Задача принята. Следите за её состоянием в списке задач." : "The job was accepted. Follow its status in jobs.",
    unavailable: russian ? "Подтверждение недоступно, пока безопасный план не готов." : "Confirmation is unavailable until a safe plan is ready.",
    close: russian ? "Закрыть" : "Close",
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
