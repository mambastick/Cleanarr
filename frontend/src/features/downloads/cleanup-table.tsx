import { Eye, ShieldAlert, Trash2 } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { selectionItem, type BatchSelection, type LibraryDeleteTarget } from "@/features/library/library-selection"
import type { CleanupCandidate } from "@/lib/downloads"
import { cn } from "@/lib/utils"
import { enumLabel, type DownloadsCopy, type DownloadsLanguage } from "./downloads-copy"
import { bytes, duration, knownNumber } from "./downloads-format"
import { cleanupTarget } from "./cleanup-target"

function readinessTone(candidate: CleanupCandidate) {
  if (candidate.seeding.readiness === "eligible") return "border-status-success-border bg-status-success-bg text-status-success"
  if (candidate.seeding.readiness === "blocked") return "border-status-danger-border bg-status-danger-bg text-status-danger"
  if (candidate.seeding.readiness === "excluded" || candidate.seeding.readiness === "disabled") return "border-status-warning-border bg-status-warning-bg text-status-warning"
  return "border-status-unknown-border bg-status-unknown-bg text-status-unknown"
}

export function CleanupTable({ candidates, language, text, selected, onToggle, onInspect, onDelete }: { candidates: CleanupCandidate[]; language: DownloadsLanguage; text: DownloadsCopy; selected: BatchSelection; onToggle: (candidate: CleanupCandidate) => void; onInspect: (candidate: CleanupCandidate, trigger: HTMLElement) => void; onDelete: (target: LibraryDeleteTarget, trigger: HTMLElement) => void }) {
  return (
    <div className="overflow-hidden rounded-xl border bg-card">
      <Table>
        <TableHeader className="bg-muted/55"><TableRow><TableHead className="w-12 px-4"><span className="sr-only">{text.select}</span></TableHead><TableHead className="min-w-56">{text.name}</TableHead><TableHead>{text.media}</TableHead><TableHead>{text.playback}</TableHead><TableHead>{text.size}</TableHead><TableHead>{text.seeding}</TableHead><TableHead>{text.readiness}</TableHead><TableHead className="px-4">{text.actions}</TableHead></TableRow></TableHeader>
        <TableBody>
          {candidates.map((candidate) => {
            const target = cleanupTarget(candidate)
            const displayName = candidate.deletion_link?.display_name ?? candidate.display_name
            const selection = target ? selectionItem(target, displayName, candidate.size_bytes) : null
            return (
              <TableRow key={candidate.jellyfin_item_id}>
                <TableCell className="px-4">{selection ? <Checkbox checked={Boolean(selected.items[selection.key])} aria-label={`${text.select}: ${candidate.deletion_link?.display_name ?? candidate.display_name}`} onCheckedChange={() => onToggle(candidate)} /> : null}</TableCell>
                <TableCell className="max-w-72 whitespace-normal"><button type="button" className="line-clamp-2 min-h-11 rounded text-left font-medium hover:text-primary focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/50" onClick={(event) => onInspect(candidate, event.currentTarget)}>{candidate.deletion_link?.display_name ?? candidate.display_name}</button></TableCell>
                <TableCell>{candidate.media_type === "movie" ? text.movies : text.series}</TableCell>
                <TableCell>{candidate.playback_status === "watched" ? text.watched : candidate.playback_status === "never_watched" ? text.neverWatched : text.cleanupUnknown}</TableCell>
                <TableCell className="tabular-nums">{bytes(candidate.size_bytes, text)}</TableCell>
                <TableCell><p className="tabular-nums">{knownNumber(candidate.seeding.ratio, (number) => number.toFixed(2), text)}</p><p className="text-xs text-muted-foreground">{duration(candidate.seeding.seeding_time_seconds, text)}</p></TableCell>
                <TableCell><Badge variant="outline" className={cn("font-medium", readinessTone(candidate))}><ShieldAlert aria-hidden="true" />{enumLabel(language, "readiness", candidate.seeding.readiness)}</Badge></TableCell>
                <TableCell className="px-4"><div className="flex items-center gap-1"><Button variant="ghost" size="icon" aria-label={`${text.details}: ${displayName}`} onClick={(event) => onInspect(candidate, event.currentTarget)}><Eye aria-hidden="true" /></Button><Button variant="ghost" size="icon" aria-label={`${text.plan}: ${displayName}`} disabled={!target} onClick={(event) => target && onDelete(target, event.currentTarget)}><Trash2 className="text-status-danger" aria-hidden="true" /></Button></div>{!target ? <p className="max-w-52 whitespace-normal text-xs text-muted-foreground">{text.missingLink}</p> : null}</TableCell>
              </TableRow>
            )
          })}
        </TableBody>
      </Table>
    </div>
  )
}
