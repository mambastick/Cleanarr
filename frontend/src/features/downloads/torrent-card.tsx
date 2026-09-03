import { LoaderCircle, Pause, Play } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Progress } from "@/components/ui/progress"
import type { DownloadAction, DownloadItem } from "@/lib/downloads"
import { cn } from "@/lib/utils"
import { actionForItem, actionResultCopy, enumLabel, reasonLabel, type DownloadsCopy, type DownloadsLanguage } from "./downloads-copy"
import { bytes, date, duration, knownNumber, rate } from "./downloads-format"

export type DownloadActionPhase = "pending" | "completed" | "retry" | "conflict" | "failed"
export type DownloadActionState = { phase: DownloadActionPhase; action: DownloadAction; code: string | null; status: string | null }

export function TorrentCard({ item, language, text, actionStates, onControl, canMutate = true }: { item: DownloadItem; language: DownloadsLanguage; text: DownloadsCopy; actionStates: Record<string, DownloadActionState>; onControl: (item: DownloadItem, action: DownloadAction) => void; canMutate?: boolean }) {
  const action = actionForItem(item)
  const actionKey = action ? `${item.client_id}:${item.info_hash}:${action}` : null
  const controlReasonId = `${item.client_id}-${item.info_hash}-control-reason`
  const status = actionKey ? actionStates[actionKey] : undefined
  const canControl = canMutate && action != null && item.freshness === "fresh" && item.ownership === "managed" && item.unavailable_reason == null
  const disabledReason = !canMutate ? text.adminOnly : !canControl ? item.unavailable_reason ? reasonLabel(language, item.unavailable_reason) : text.actionUnavailable : null
  const statusText = status?.phase === "pending" ? text.pending : status?.phase === "completed" ? actionResultCopy(text, status.status as never) : status?.phase === "retry" ? status.status === "reconcile_required" ? text.reconcile : status.status === "queued" || status.status === "running" ? text.inProgress : text.ambiguous : status?.phase === "conflict" ? text.conflict : status?.phase === "failed" ? text.actionFailed : null
  const locale = language === "ru" ? "ru-RU" : "en-US"

  return <Card>
    <CardHeader className="pb-2">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0"><CardTitle className="truncate">{item.display_name ?? text.nameUnavailable}</CardTitle><CardDescription>{text.client}: {item.client_name} · {text.kind}: {item.client_kind} · {text.observed}: {date(item.observed_at, text, locale)}</CardDescription></div>
        <div className="flex flex-wrap gap-1"><Badge variant="outline">{enumLabel(language, "state", item.state)}</Badge><Badge variant="outline">{enumLabel(language, "ownership", item.ownership)}</Badge><Badge variant="outline">{enumLabel(language, "freshness", item.freshness)}</Badge></div>
      </div>
    </CardHeader>
    <CardContent className="flex flex-col gap-3">
      <Progress value={typeof item.progress === "number" ? Math.max(0, Math.min(100, item.progress * 100)) : null} aria-label={text.progress} />
      <div className="grid gap-2 text-xs text-muted-foreground sm:grid-cols-2 lg:grid-cols-4">
        <span>{text.progress}: {knownNumber(item.progress, (number) => `${Math.round(number * 100)}%`, text)}</span><span>{text.total}: {bytes(item.total_bytes, text)}</span><span>{text.downloaded}: {bytes(item.downloaded_bytes, text)}</span><span>{text.uploaded}: {bytes(item.uploaded_bytes, text)}</span>
        <span>{text.downloadSpeed}: {rate(item.download_speed_bytes_per_second, text)}</span><span>{text.uploadSpeed}: {rate(item.upload_speed_bytes_per_second, text)}</span><span>{text.seedRatio}: {knownNumber(item.ratio, (number) => number.toFixed(2), text)}</span><span>{text.seedTime}: {duration(item.seeding_time_seconds, text)}</span>
        <span>{text.eta}: {duration(item.eta_seconds, text)}</span><span>{text.added}: {date(item.added_at, text, locale)}</span><span>{text.completedAt}: {date(item.completed_at, text, locale)}</span><span>{text.activity}: {date(item.activity_at, text, locale)}</span>
        <span>{text.category}: {item.category ?? text.unknown}</span><span>{text.tags}: {item.tags == null ? text.unknown : item.tags.length ? item.tags.join(", ") : text.none}</span><span>{text.tracker}: {item.tracker_summary ?? text.unknown}</span><span>{text.policy}: {reasonLabel(language, item.policy_reason_code ?? item.policy_decision)}</span>
      </div>
      {item.policy_facts ? <details className="text-xs text-muted-foreground"><summary>{text.policyFacts}</summary><pre className="mt-2 overflow-x-auto rounded-md bg-muted p-2 font-mono">{JSON.stringify(item.policy_facts, null, 2)}</pre></details> : null}
      {item.latest_action ? <details className="text-xs text-muted-foreground"><summary>{text.latestAction}: {enumLabel(language, "action", item.latest_action.status)}</summary><div className="mt-2 grid gap-1 rounded-md bg-muted p-2 sm:grid-cols-2"><span>{text.actionSource}: {item.latest_action.source === "policy" ? text.policy : text.controls}</span><span>{text.actionAttempts}: {item.latest_action.attempt_count}/{item.latest_action.max_attempts}</span><span>{text.actionUpdated}: {date(item.latest_action.updated_at, text, locale)}</span><span>{text.unavailableReason}: {reasonLabel(language, item.latest_action.code)}</span></div></details> : null}
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="outline" size="sm" disabled={!canControl || status?.phase === "pending"} aria-describedby={disabledReason ? controlReasonId : undefined} onClick={() => action && onControl(item, action)}>
          {status?.phase === "pending" ? <LoaderCircle data-icon="inline-start" className={cn("animate-spin")} /> : action === "pause" ? <Pause data-icon="inline-start" /> : <Play data-icon="inline-start" />}{action === "pause" ? text.pause : action === "resume" ? text.resume : text.controls}
        </Button>
        {status?.phase === "retry" ? <Button variant="outline" size="sm" disabled={!canMutate} onClick={() => action && onControl(item, action)}>{text.retryAction}</Button> : null}
        {disabledReason ? <span id={controlReasonId} className="text-xs text-muted-foreground">{disabledReason}</span> : null}
        {statusText ? <span role="status" className="min-h-5 text-xs text-muted-foreground">{statusText}</span> : null}
      </div>
    </CardContent>
  </Card>
}
