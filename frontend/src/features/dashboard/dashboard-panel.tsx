import { Activity, Download, Film, PenSquare, Play, RefreshCw, Server, ShieldAlert, Star, Tv, Zap, type LucideIcon } from "lucide-react"
import { useEffect, useRef, useState } from "react"

import { AnimateIcon, AnimatedIcon } from "@/components/animate-ui/animated-icon"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { EmptyState, StatusDot, StatusPill } from "@/features/settings/service-presentation"
import type { DashboardActivity, DashboardPayload, HealthStatus } from "@/lib/dashboard"
import type { UiTextMap } from "@/lib/i18n"
import { getStatusLabel, SETUP_STEPS } from "@/lib/service-config"
import { getWebhookStatusLabel } from "@/lib/status-format"
import { cn } from "@/lib/utils"
import { useStorage, type StorageFetchJson, type StorageResponse, type StorageVolume } from "@/lib/storage"
import { STORAGE_COPY, type StorageCopy } from "./storage-copy"
import { actionSummaryLabel } from "@/features/activity/action-presentation"

const DOWNSTREAM_META: Partial<Record<string, { icon: LucideIcon; color: string }>> = {
  Radarr: { icon: Film, color: "text-primary" },
  Sonarr: { icon: Tv, color: "text-primary" },
  Jellyfin: { icon: Play, color: "text-primary" },
  Seerr: { icon: Star, color: "text-primary" },
  Downloader: { icon: Download, color: "text-status-success" },
}

function getDashboardServiceRole(name: string, fallback: string, text: UiTextMap): string {
  switch (name) {
    case "Radarr": return text.movies
    case "Sonarr": return text.series
    case "Jellyfin": return text.library
    case "Seerr": return text.serviceSeerrDescription
    case "Downloader": return text.torrentClient
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
  onEdit?: (trigger: HTMLButtonElement) => void
}) {
  const meta = DOWNSTREAM_META[service.name] ?? { icon: Server, color: "text-muted-foreground" }
  const Icon = meta.icon
  return (
    <div className="rounded-xl border p-4 space-y-3">
      <div className="flex items-start justify-between gap-2">
        <div className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-muted">
          <Icon className={cn("size-4", meta.color)} />
        </div>
        {onEdit && (
          <Tooltip><AnimateIcon><TooltipTrigger render={<Button
            variant="ghost"
            size="icon-xs"
            onClick={(event) => onEdit(event.currentTarget)}
            className="text-muted-foreground hover:text-foreground"
            aria-label={`${text.edit} ${service.name}`}
          >
            <AnimatedIcon animation="wiggle"><PenSquare className="size-3.5" /></AnimatedIcon>
          </Button>} /></AnimateIcon><TooltipContent>{text.edit} {service.name}</TooltipContent></Tooltip>
        )}
      </div>
      <div>
        <p className="text-sm font-semibold">{service.name}</p>
        <p className="text-xs text-muted-foreground">
          {getDashboardServiceRole(service.name, service.role, text)}
        </p>
      </div>
      <div className="flex items-center gap-1.5">
        <StatusDot healthStatus={service.health_status} text={text} />
        <span
          className={cn(
            "text-xs capitalize",
            service.health_status === "healthy" && "text-status-success",
            service.health_status === "unreachable" && "text-status-danger",
            service.health_status === "unconfigured" && "text-muted-foreground",
          )}
        >
          {getStatusLabel(service.health_status, text)}
        </span>
      </div>
      {service.url ? <details className="text-xs text-muted-foreground">
        <summary className="cursor-pointer select-none text-xs text-muted-foreground hover:text-foreground">{text.serviceDetails}</summary>
        <div className="mt-2 rounded-md bg-muted/60 p-2">
          <code className="block break-all text-[11px]">{service.url}</code>
        </div>
      </details> : !service.configured ? <span className="text-xs text-muted-foreground">{text.notConfigured}</span> : null}
    </div>
  )
}

export function DashboardPanel({
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
  storage,
  storageLoading = false,
  storageError = null,
  onRefreshStorage,
  storageLanguage = "en",
  readOnly = false,
  fetchJson,
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
  onOpenWizard: (trigger: HTMLButtonElement) => void
  onEditService: (name: string, trigger: HTMLButtonElement) => void
  storage?: StorageResponse | null
  storageLoading?: boolean
  storageError?: string | null
  onRefreshStorage?: () => void
  storageLanguage?: "en" | "ru"
  readOnly?: boolean
  fetchJson?: StorageFetchJson
}) {
  const webhookStatus = dashboard?.webhook_status
  const internalStorage = useStorage({ active: Boolean(fetchJson) && storage === undefined, authenticated: Boolean(fetchJson) && storage === undefined, fetchJson: fetchJson ?? (async () => { throw new Error("storage client unavailable") }) })
  const storageData = storage === undefined ? internalStorage.data : storage
  const storageCopy = STORAGE_COPY[storageLanguage]
  const readOnlyLabel = storageLanguage === "ru"
    ? "Роль «Зритель»: доступен только безопасный просмотр. Изменения выполняет администратор."
    : "Viewer role: safe read-only access. An administrator can make changes."
  const effectiveStorageLoading = storage === undefined ? internalStorage.loading : storageLoading
  const effectiveStorageError = storage === undefined ? internalStorage.error : storageError
  const [isChangingRuntime, setIsChangingRuntime] = useState(false)
  const [requestedRuntime, setRequestedRuntime] = useState<string | null>(null)
  const runtimeRequestRef = useRef<string | null>(null)
  const runtimeValue = isLive ? "live" : "dry-run"

  useEffect(() => {
    if (requestedRuntime === runtimeValue) {
      runtimeRequestRef.current = null
      setRequestedRuntime(null)
    }
  }, [requestedRuntime, runtimeValue])

  const changeRuntime = async (next: string | null) => {
    if (next == null || next === runtimeValue || isChangingRuntime || runtimeRequestRef.current != null) return
    runtimeRequestRef.current = next
    setRequestedRuntime(next)
    setIsChangingRuntime(true)
    try {
      await onToggleDryRun()
    } catch (error) {
      runtimeRequestRef.current = null
      setRequestedRuntime(null)
      throw error
    } finally {
      setIsChangingRuntime(false)
    }
  }

  return (
    <section className="space-y-5">
      <div><h1 className="text-xl font-semibold">{text.dashboard}</h1><p className="text-sm text-muted-foreground">{text.status}</p>{readOnly ? <p className="mt-2 text-xs text-muted-foreground">{readOnlyLabel}</p> : null}</div>
      {/* Status bar */}
      <div
        className={cn(
          "flex flex-wrap items-center gap-x-5 gap-y-2 rounded-xl border-2 px-5 py-4",
          isLive
            ? "border-status-success-border bg-status-success-bg"
            : "border-status-warning-border bg-status-warning-bg",
        )}
      >
        <div className="flex items-center gap-3">
          {isLive ? (
            <Zap className="size-5 text-status-success" />
          ) : (
            <ShieldAlert className="size-5 text-status-warning" />
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
          {!readOnly && !allServicesConfigured && (
            <AnimateIcon><Button variant="outline" size="sm" onClick={(event) => onOpenWizard(event.currentTarget)}>
              <AnimatedIcon animation="pulse"><Zap className="size-4 text-primary" /></AnimatedIcon>
              {text.setupWizard}
            </Button></AnimateIcon>
          )}
          <Tabs value={runtimeValue} onValueChange={changeRuntime} aria-label={text.runtimeSettings}>
            <TabsList>
              <AnimateIcon><TabsTrigger value="dry-run" disabled={readOnly || isChangingRuntime}>
                <AnimatedIcon animation="pulse"><ShieldAlert className="size-3.5" /></AnimatedIcon>
                {text.dryRun}
              </TabsTrigger></AnimateIcon>
              <AnimateIcon><TabsTrigger value="live" disabled={readOnly || isChangingRuntime}>
                <AnimatedIcon animation="pulse"><Zap className="size-3.5" /></AnimatedIcon>
                {text.live}
              </TabsTrigger></AnimateIcon>
            </TabsList>
            <TabsContent value="dry-run" className="sr-only">{text.dryRunDescription}</TabsContent>
            <TabsContent value="live" className="sr-only">{text.liveModeDescription}</TabsContent>
          </Tabs>
        </div>
      </div>

      <StorageHealthCard data={storageData} loading={effectiveStorageLoading} error={effectiveStorageError} text={storageCopy} onRefresh={readOnly ? undefined : onRefreshStorage ?? (() => void internalStorage.refresh())} />

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
                onEdit={readOnly ? undefined : (trigger) => onEditService(service.name, trigger)}
              />
            ))}
          </div>
        )}
      </div>

      <RecentActivitySummary text={text} language={storageLanguage} latestActivity={latestActivity} webhookStatus={webhookStatus} />
    </section>
  )
}

function StorageHealthCard({ data, loading, error, text, onRefresh }: { data: StorageResponse | null | undefined; loading: boolean; error: string | null; text: StorageCopy; onRefresh?: () => void }) {
  return <Card><CardHeader className="flex flex-col items-stretch gap-3 pb-3 sm:flex-row sm:items-start sm:justify-between"><div><CardTitle className="text-base">{text.title}</CardTitle><CardDescription>{text.provenance}</CardDescription></div>{onRefresh ? <AnimateIcon><Button className="w-full sm:w-auto" variant="outline" size="sm" onClick={onRefresh} disabled={loading}><AnimatedIcon animation="rotate"><RefreshCw className={cn(loading && "opacity-50")} /></AnimatedIcon>{text.refresh}</Button></AnimateIcon> : null}</CardHeader><CardContent>{error ? <div className="flex items-center justify-between gap-3 rounded-lg border border-status-danger/30 bg-status-danger/5 p-3 text-sm"><span>{text.unavailable}</span>{onRefresh ? <Button variant="outline" size="sm" onClick={onRefresh}>{text.retry}</Button> : null}</div> : loading && !data ? <p className="text-sm text-muted-foreground">{text.loading}</p> : data ? <div className="space-y-3"><div className="flex flex-wrap items-center gap-2"><StatusPill tone={data.status === "critical" ? "red" : data.status === "warning" ? "yellow" : data.status === "healthy" ? "green" : "blue"} label={storageStatusLabel(data.status, text)} />{data.partial || data.freshness !== "fresh" ? <span className="text-xs text-muted-foreground">{data.partial ? text.partial : text.stale}</span> : null}</div><div role="table" aria-label={text.title} className="grid gap-2">{data.volumes.map((volume) => <StorageVolumeRow key={volume.volume_id} volume={volume} text={text} />)}</div></div> : <p className="text-sm text-muted-foreground">{text.unknown}</p>}</CardContent></Card>
}
function StorageVolumeRow({ volume, text }: { volume: StorageVolume; text: StorageCopy }) { const total = volume.total_bytes ?? volume.total; const free = volume.free_bytes ?? volume.free; const capacity = free != null ? `${text.free} ${formatBytes(free)}${volume.free_percent != null ? ` · ${volume.free_percent.toFixed(1)}%` : ""}` : volume.free_percent == null ? text.unknown : `${text.free} ${volume.free_percent.toFixed(1)}%`; const service = volume.service_type.charAt(0).toUpperCase() + volume.service_type.slice(1); return <div role="row" className="grid gap-2 rounded-lg border p-3 text-sm sm:grid-cols-[minmax(0,1.4fr)_minmax(8rem,1fr)_auto] sm:items-center"><div role="cell" className="min-w-0"><p className="truncate font-medium">{volume.display_label}</p><p className="truncate text-xs text-muted-foreground">{text.source}: {service}</p></div><div role="cell" className="text-xs text-muted-foreground">{capacity}{total != null ? ` / ${formatBytes(total)}` : ""}</div><div role="cell" className="flex items-center gap-2 sm:justify-end"><StatusPill tone={volume.status === "critical" ? "red" : volume.status === "warning" ? "yellow" : volume.status === "healthy" ? "green" : "blue"} label={storageStatusLabel(volume.status, text)} />{volume.possible_duplicate ? <span className="sr-only">{text.possibleDuplicate}</span> : null}</div></div> }
function storageStatusLabel(status: StorageResponse["status"] | StorageVolume["status"], text: StorageCopy) { return status === "critical" ? text.critical : status === "warning" ? text.warning : status === "healthy" ? text.healthy : text.unknown }
function formatBytes(bytes: number) { if (!bytes) return "0 B"; const index = Math.min(4, Math.floor(Math.log(bytes) / Math.log(1024))); return `${(bytes / 1024 ** index).toFixed(1)} ${["B", "KB", "MB", "GB", "TB"][index]}` }

function RecentActivitySummary({ text, language, latestActivity, webhookStatus }: { text: UiTextMap; language: "en" | "ru"; latestActivity: DashboardActivity | null; webhookStatus: DashboardPayload["webhook_status"] | undefined }) {
  const latestIsProcessed = latestActivity && (!webhookStatus?.attempted_at || Date.parse(latestActivity.processed_at) >= Date.parse(webhookStatus.attempted_at))
  if (!latestActivity && !webhookStatus?.attempted_at) return <Card><CardHeader className="pb-3"><CardTitle className="flex items-center gap-2 text-base"><Activity className="size-4 text-status-success" />{text.recentActivitySummary}</CardTitle><CardDescription>{text.recentActivitySummaryDescription}</CardDescription></CardHeader><CardContent><EmptyState title={text.noActivity} description={text.noWebhookActivity} /></CardContent></Card>
  const item = latestIsProcessed && latestActivity ? latestActivity.result.name : webhookStatus?.item_name ?? text.item
  const status = latestIsProcessed && latestActivity ? latestActivity.result.status : webhookStatus?.result_status ?? webhookStatus?.outcome ?? "unknown"
  const statusLabel = latestIsProcessed && latestActivity ? friendlyOutcome(status, text) : webhookStatus?.result_status ? friendlyOutcome(webhookStatus.result_status, text) : getWebhookStatusLabel(webhookStatus?.outcome ?? "", text)
  const occurredAt = latestIsProcessed && latestActivity ? latestActivity.processed_at : webhookStatus?.attempted_at
  const detailsLabel = language === "ru" ? "Что произошло" : "What happened"
  const webhookMessage = language === "ru" ? "CleanArr получил событие от Jellyfin и сохранил результат обработки." : "CleanArr received a Jellyfin event and saved its processing result."
  return <Card><CardHeader className="pb-3"><CardTitle className="flex items-center gap-2 text-base"><Activity className="size-4 text-status-success" />{text.recentActivitySummary}</CardTitle><CardDescription>{text.recentActivitySummaryDescription}</CardDescription></CardHeader><CardContent className="space-y-3"><div className="flex flex-wrap items-start justify-between gap-3"><div className="min-w-0"><p className="text-sm font-medium">{latestIsProcessed ? text.recentActivityProcessed.replace("{{item}}", item) : text.recentActivityWebhook.replace("{{item}}", item)}</p>{occurredAt ? <p className="mt-1 text-xs text-muted-foreground">{new Date(occurredAt).toLocaleString()}</p> : null}</div><StatusPill tone={status === "partial_failure" || status === "failed" ? "red" : "green"} label={statusLabel} /></div><details className="text-xs text-muted-foreground"><summary className="cursor-pointer select-none hover:text-foreground">{detailsLabel}</summary><div className="mt-2 space-y-1 rounded-md bg-muted/60 p-2">{latestIsProcessed && latestActivity ? Object.entries(latestActivity.action_summary).map(([code, count]) => <p key={code}>{actionSummaryLabel(code, count, language)}</p>) : <p>{webhookMessage}</p>}</div></details></CardContent></Card>
}

function friendlyOutcome(status: string, text: UiTextMap) {
  if (status === "dry_run") return text.dryRun
  if (status === "ignored") return text.skipped
  if (status === "already_absent") return text.deleted
  const label = getStatusLabel(status, text)
  return label === status ? text.unknown : label
}

// ─── Activity panel ───────────────────────────────────────────────────────────
