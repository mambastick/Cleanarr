import { Activity, Download, Film, PenSquare, Play, RefreshCw, Server, ShieldAlert, Star, Tv, Webhook, Zap, type LucideIcon } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { EmptyState, StatusDot, StatusPill } from "@/features/settings/service-presentation"
import type { DashboardActivity, DashboardPayload, HealthStatus } from "@/lib/dashboard"
import type { UiTextMap } from "@/lib/i18n"
import { getStatusLabel, SETUP_STEPS } from "@/lib/service-config"
import { formatMediaTitle } from "@/lib/status-format"
import { cn } from "@/lib/utils"
import { useStorage, type StorageFetchJson, type StorageResponse, type StorageVolume } from "@/lib/storage"
import { STORAGE_COPY, type StorageCopy } from "./storage-copy"

const DOWNSTREAM_META: Partial<Record<string, { icon: LucideIcon; color: string }>> = {
  Radarr: { icon: Film, color: "text-primary" },
  Sonarr: { icon: Tv, color: "text-primary" },
  Jellyfin: { icon: Play, color: "text-primary" },
  Seerr: { icon: Star, color: "text-primary" },
  Downloader: { icon: Download, color: "text-status-success" },
}

function getDashboardServiceRole(name: string, fallback: string, text: UiTextMap): string {
  switch (name) {
    case "Radarr": return text.serviceRadarrDescription
    case "Sonarr": return text.serviceSonarrDescription
    case "Jellyfin": return text.serviceJellyfinDescription
    case "Seerr": return text.serviceSeerrDescription
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
          {onEdit && (
            <Button
              variant="ghost"
              size="icon-xs"
              onClick={(event) => onEdit(event.currentTarget)}
              className="ml-1 text-muted-foreground hover:text-foreground"
              aria-label={`${text.edit} ${service.name}`}
            >
              <PenSquare className="size-3.5" />
            </Button>
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
  fetchJson?: StorageFetchJson
}) {
  const webhookStatus = dashboard?.webhook_status
  const internalStorage = useStorage({ active: Boolean(fetchJson) && storage === undefined, authenticated: Boolean(fetchJson) && storage === undefined, fetchJson: fetchJson ?? (async () => { throw new Error("storage client unavailable") }) })
  const storageData = storage === undefined ? internalStorage.data : storage
  const storageCopy = STORAGE_COPY[storageLanguage]
  const effectiveStorageLoading = storage === undefined ? internalStorage.loading : storageLoading
  const effectiveStorageError = storage === undefined ? internalStorage.error : storageError

  return (
    <section className="space-y-5">
      <div><h1 className="text-xl font-semibold">{text.dashboard}</h1><p className="text-sm text-muted-foreground">{text.status}</p></div>
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
          {!allServicesConfigured && (
            <Button variant="outline" size="sm" onClick={(event) => onOpenWizard(event.currentTarget)}>
              <Zap className="size-4 text-primary" />
              {text.setupWizard}
            </Button>
          )}
          {/* Mode toggle */}
          <div className="flex items-center rounded-lg border bg-background p-0.5">
            <button
              onClick={() => isLive ? void onToggleDryRun() : undefined}
              className={cn(
                "flex min-h-11 items-center gap-1.5 rounded-md px-3 py-1 text-xs font-medium transition-colors",
                !isLive
                  ? "bg-status-warning-bg text-status-warning"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              <ShieldAlert className="size-3.5" />
              {text.dryRun}
            </button>
            <button
              onClick={() => !isLive ? void onToggleDryRun() : undefined}
              className={cn(
                "flex min-h-11 items-center gap-1.5 rounded-md px-3 py-1 text-xs font-medium transition-colors",
                isLive
                  ? "bg-status-success-bg text-status-success"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              <Zap className="size-3.5" />
              {text.live}
            </button>
          </div>
        </div>
      </div>

      <StorageHealthCard data={storageData} loading={effectiveStorageLoading} error={effectiveStorageError} text={storageCopy} onRefresh={onRefreshStorage ?? (() => void internalStorage.refresh())} />

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
                onEdit={(trigger) => onEditService(service.name, trigger)}
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
              <Webhook className="size-4 text-primary" />
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
              <Activity className="size-4 text-status-success" />
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

function StorageHealthCard({ data, loading, error, text, onRefresh }: { data: StorageResponse | null | undefined; loading: boolean; error: string | null; text: StorageCopy; onRefresh: () => void }) {
  return <Card><CardHeader className="flex flex-row items-start justify-between gap-3 pb-3"><div><CardTitle className="text-base">{text.title}</CardTitle>{data ? <CardDescription>{storageStatusLabel(data.status, text)}</CardDescription> : null}</div><Button variant="outline" size="sm" onClick={onRefresh} disabled={loading}><RefreshCw className={cn(loading && "animate-spin")} />{text.refresh}</Button></CardHeader><CardContent>{error ? <div className="flex items-center justify-between gap-3 rounded-lg border border-status-danger/30 bg-status-danger/5 p-3 text-sm"><span>{text.unavailable}</span><Button variant="outline" size="sm" onClick={onRefresh}>{text.retry}</Button></div> : loading && !data ? <p className="text-sm text-muted-foreground">{text.loading}</p> : data ? <div className="space-y-3"><div className="flex flex-wrap items-center gap-2"><StatusPill tone={data.status === "critical" ? "red" : data.status === "warning" ? "yellow" : data.status === "healthy" ? "green" : "blue"} label={storageStatusLabel(data.status, text)} />{data.partial || data.freshness !== "fresh" ? <span className="text-xs text-muted-foreground">{data.partial ? text.partial : text.stale}</span> : null}</div><div role="table" aria-label={text.title} className="grid gap-2">{data.volumes.map((volume) => <StorageVolumeRow key={volume.volume_id} volume={volume} text={text} />)}</div></div> : <p className="text-sm text-muted-foreground">{text.unknown}</p>}</CardContent></Card>
}
function StorageVolumeRow({ volume, text }: { volume: StorageVolume; text: StorageCopy }) { const total = volume.total_bytes ?? volume.total; const free = volume.free_bytes ?? volume.free; const capacity = free != null ? `${text.free} ${formatBytes(free)}${volume.free_percent != null ? ` · ${volume.free_percent.toFixed(1)}%` : ""}` : volume.free_percent == null ? text.unknown : `${text.free} ${volume.free_percent.toFixed(1)}%`; return <div role="row" className="grid gap-2 rounded-lg border p-3 text-sm sm:grid-cols-[minmax(0,1.4fr)_minmax(8rem,1fr)_auto] sm:items-center"><div role="cell" className="min-w-0"><p className="truncate font-medium">{volume.display_label}</p><p className="truncate text-xs text-muted-foreground">{volume.service_type} · {volume.service_id}</p></div><div role="cell" className="text-xs text-muted-foreground">{capacity}{total != null ? ` / ${formatBytes(total)}` : ""}</div><div role="cell" className="flex items-center gap-2 sm:justify-end"><StatusPill tone={volume.status === "critical" ? "red" : volume.status === "warning" ? "yellow" : volume.status === "healthy" ? "green" : "blue"} label={storageStatusLabel(volume.status, text)} />{volume.possible_duplicate ? <span className="sr-only">{text.possibleDuplicate}</span> : null}</div></div> }
function storageStatusLabel(status: StorageResponse["status"] | StorageVolume["status"], text: StorageCopy) { return status === "critical" ? text.critical : status === "warning" ? text.warning : status === "healthy" ? text.healthy : text.unknown }
function formatBytes(bytes: number) { if (!bytes) return "0 B"; const index = Math.min(4, Math.floor(Math.log(bytes) / Math.log(1024))); return `${(bytes / 1024 ** index).toFixed(1)} ${["B", "KB", "MB", "GB", "TB"][index]}` }

// ─── Activity panel ───────────────────────────────────────────────────────────
