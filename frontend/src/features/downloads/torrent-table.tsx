import { LoaderCircle, Pause, Play } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Progress } from "@/components/ui/progress"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import type { DownloadAction, DownloadItem } from "@/lib/downloads"
import { cn } from "@/lib/utils"
import { actionForItem, actionResultCopy, enumLabel, reasonLabel, type DownloadsCopy, type DownloadsLanguage } from "./downloads-copy"
import { bytes, duration, knownNumber } from "./downloads-format"
import type { DownloadActionState } from "./torrent-card"

function stateTone(item: DownloadItem) {
  if (item.state === "error" || item.ownership === "conflict") return "border-status-danger-border bg-status-danger-bg text-status-danger"
  if (item.freshness !== "fresh" || item.ownership === "unknown" || item.state === "unknown") return "border-status-unknown-border bg-status-unknown-bg text-status-unknown"
  if (item.state === "stopped") return "border-status-warning-border bg-status-warning-bg text-status-warning"
  return "border-status-success-border bg-status-success-bg text-status-success"
}

function TorrentControl({ item, text, language, actionStates, onControl, canMutate, mutationUnavailableReason }: { item: DownloadItem; text: DownloadsCopy; language: DownloadsLanguage; actionStates: Record<string, DownloadActionState>; onControl: (item: DownloadItem, action: DownloadAction) => void; canMutate: boolean; mutationUnavailableReason?: string }) {
  const action = actionForItem(item)
  const actionKey = action ? `${item.client_id}:${item.info_hash}:${action}` : null
  const status = actionKey ? actionStates[actionKey] : undefined
  const canControl = canMutate && action != null && item.freshness === "fresh" && item.ownership === "managed" && item.unavailable_reason == null
  const disabledReason = !canMutate
    ? mutationUnavailableReason ?? text.adminOnly
    : !canControl
    ? item.unavailable_reason ? reasonLabel(language, item.unavailable_reason) : text.actionUnavailable
    : null
  const statusText = status?.phase === "pending" ? text.pending
    : status?.phase === "completed" ? actionResultCopy(text, status.status as never)
      : status?.phase === "retry" ? status.status === "reconcile_required" ? text.reconcile : status.status === "queued" || status.status === "running" ? text.inProgress : text.ambiguous
        : status?.phase === "conflict" ? text.conflict
          : status?.phase === "failed" ? text.actionFailed
            : null

  return (
    <div className="flex min-w-36 flex-col items-start gap-1.5">
      <Button
        variant="outline"
        size="sm"
        disabled={!canControl || status?.phase === "pending"}
        onClick={() => action && onControl(item, action)}
      >
        {status?.phase === "pending" ? <LoaderCircle className="animate-spin" aria-hidden="true" /> : action === "pause" ? <Pause aria-hidden="true" /> : <Play aria-hidden="true" />}
        {action === "pause" ? text.pause : action === "resume" ? text.resume : text.controls}
      </Button>
      {status?.phase === "retry" ? <Button variant="ghost" size="xs" disabled={!canMutate} onClick={() => action && onControl(item, action)}>{text.retryAction}</Button> : null}
      {disabledReason ? <span className="max-w-48 whitespace-normal text-[11px] leading-4 text-muted-foreground">{disabledReason}</span> : null}
      {statusText ? <span role="status" className="max-w-48 whitespace-normal text-[11px] leading-4 text-muted-foreground">{statusText}</span> : null}
    </div>
  )
}

export function TorrentTable({ items, language, text, actionStates, onControl, canMutate = true, mutationUnavailableReason }: { items: DownloadItem[]; language: DownloadsLanguage; text: DownloadsCopy; actionStates: Record<string, DownloadActionState>; onControl: (item: DownloadItem, action: DownloadAction) => void; canMutate?: boolean; mutationUnavailableReason?: string }) {
  return (
    <div className="overflow-hidden rounded-xl border bg-card">
      <Table>
        <TableHeader className="bg-muted/55">
          <TableRow>
            <TableHead className="min-w-64 px-4">{text.name}</TableHead>
            <TableHead>{text.client}</TableHead>
            <TableHead>{text.size}</TableHead>
            <TableHead className="min-w-40">{text.progress}</TableHead>
            <TableHead>{text.seedRatio}</TableHead>
            <TableHead>{text.seedTime}</TableHead>
            <TableHead>{text.state}</TableHead>
            <TableHead className="px-4">{text.actions}</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {items.map((item) => (
            <TableRow key={`${item.client_id}:${item.info_hash}`}>
              <TableCell className="max-w-80 px-4 whitespace-normal">
                <p className="line-clamp-2 font-medium leading-5">{item.display_name ?? text.nameUnavailable}</p>
                <p className="mt-1 truncate font-mono text-[11px] text-muted-foreground">{item.info_hash}</p>
              </TableCell>
              <TableCell>
                <p className="font-medium">{item.client_name}</p>
                <p className="text-xs text-muted-foreground">{item.client_kind}</p>
              </TableCell>
              <TableCell className="tabular-nums">{bytes(item.total_bytes, text)}</TableCell>
              <TableCell>
                <div className="grid gap-1.5">
                  <span className="text-xs tabular-nums">{knownNumber(item.progress, (number) => `${Math.round(number * 100)}%`, text)}</span>
                  <Progress value={typeof item.progress === "number" ? Math.max(0, Math.min(100, item.progress * 100)) : null} aria-label={`${item.display_name ?? text.nameUnavailable}: ${text.progress}`} className="h-1.5" />
                </div>
              </TableCell>
              <TableCell className="tabular-nums">{knownNumber(item.ratio, (number) => number.toFixed(2), text)}</TableCell>
              <TableCell className="tabular-nums">{duration(item.seeding_time_seconds, text)}</TableCell>
              <TableCell>
                <div className="flex flex-col items-start gap-1.5">
                  <Badge variant="outline" className={cn("font-medium", stateTone(item))}>{enumLabel(language, "state", item.state)}</Badge>
                  <span className="text-[11px] text-muted-foreground">{enumLabel(language, "ownership", item.ownership)}</span>
                </div>
              </TableCell>
              <TableCell className="px-4"><TorrentControl item={item} text={text} language={language} actionStates={actionStates} onControl={onControl} canMutate={canMutate} mutationUnavailableReason={mutationUnavailableReason} /></TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}
