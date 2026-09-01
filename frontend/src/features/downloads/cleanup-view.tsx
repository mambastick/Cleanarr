import { AlertCircle, ShieldAlert } from "lucide-react"

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Checkbox } from "@/components/ui/checkbox"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Skeleton } from "@/components/ui/skeleton"
import { emptyBatchSelection, selectionItem, type BatchSelectionItem, type LibraryDeleteTarget } from "@/features/library/library-selection"
import type { CleanupCandidate, CleanupCandidatesResponse, CleanupSort } from "@/lib/downloads"
import { enumLabel, reasonLabel, type DownloadsCopy, type DownloadsLanguage } from "./downloads-copy"
import { bytes, date, duration, knownNumber } from "./downloads-format"
import { cleanupTarget } from "./cleanup-target"

type Props = { language: DownloadsLanguage; text: DownloadsCopy; candidates: CleanupCandidatesResponse | null; error: boolean; loading: boolean; playback: string; media: string; readiness: string; sort: CleanupSort; direction: "asc" | "desc"; setPlayback: (value: string) => void; setMedia: (value: string) => void; setReadiness: (value: string) => void; setSort: (value: CleanupSort) => void; setDirection: (value: "asc" | "desc") => void; onRetry: () => void; onLoadMore: () => void; selection: ReturnType<typeof emptyBatchSelection>; onToggle: (candidate: CleanupCandidate) => void; onDelete: (target: LibraryDeleteTarget, trigger: HTMLElement) => void; onBatchPreview: (items: BatchSelectionItem[], trigger: HTMLElement) => void; selected: BatchSelectionItem[]; selectionError: string | null }

export function CleanupView({ language, text, candidates, error, loading, playback, media, readiness, sort, direction, setPlayback, setMedia, setReadiness, setSort, setDirection, onRetry, onLoadMore, selection, onToggle, onDelete, onBatchPreview, selected, selectionError }: Props) {
  const partial = candidates?.source_status === "partial" || candidates?.truncated || Boolean(candidates?.failure_codes.length)
  const locale = language === "ru" ? "ru-RU" : "en-US"
  return <div className="flex flex-col gap-4">
    <Alert><ShieldAlert /><AlertTitle>{text.watchInfo}</AlertTitle><AlertDescription>{text.unknown}</AlertDescription></Alert>
    <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
      <Select value={playback || "all"} onValueChange={(next) => setPlayback(next && next !== "all" ? next : "")}><SelectTrigger aria-label={text.sourceStatus}><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">{text.all}</SelectItem><SelectItem value="watched">{text.watched}</SelectItem><SelectItem value="never_watched">{text.neverWatched}</SelectItem><SelectItem value="unknown">{text.cleanupUnknown}</SelectItem></SelectContent></Select>
      <Select value={media || "all"} onValueChange={(next) => setMedia(next && next !== "all" ? next : "")}><SelectTrigger aria-label={text.media}><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">{text.all}</SelectItem><SelectItem value="movie">{text.movies}</SelectItem><SelectItem value="series">{text.series}</SelectItem></SelectContent></Select>
      <Select value={readiness || "all"} onValueChange={(next) => setReadiness(next && next !== "all" ? next : "")}><SelectTrigger aria-label={text.readiness}><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">{text.all}</SelectItem>{(["eligible", "blocked", "excluded", "disabled", "unknown"] as const).map((item) => <SelectItem key={item} value={item}>{enumLabel(language, "readiness", item)}</SelectItem>)}</SelectContent></Select>
      <Select value={sort} onValueChange={(next) => next && setSort(next as CleanupSort)}><SelectTrigger aria-label={text.sort}><SelectValue /></SelectTrigger><SelectContent>{(["library_added", "play_count", "last_played", "size", "seed_ratio", "seed_time", "seed_readiness"] as CleanupSort[]).map((item) => <SelectItem key={item} value={item}>{enumLabel(language, "sort", item)}</SelectItem>)}</SelectContent></Select>
      <Select value={direction} onValueChange={(next) => next && setDirection(next as "asc" | "desc")}><SelectTrigger aria-label={text.direction}><SelectValue /></SelectTrigger><SelectContent><SelectItem value="desc">{text.descending}</SelectItem><SelectItem value="asc">{text.ascending}</SelectItem></SelectContent></Select>
    </div>
    {error ? <Alert variant="destructive"><AlertCircle /><AlertTitle>{text.candidatesFailed}</AlertTitle><AlertDescription><Button variant="outline" size="sm" onClick={onRetry}>{text.retry}</Button></AlertDescription></Alert> : null}
    {partial ? <Alert><ShieldAlert /><AlertTitle>{candidates?.truncated ? text.truncated : text.partial}</AlertTitle><AlertDescription>{candidates?.failure_codes.length ? `${text.partialEvidence}: ${candidates.failure_codes.map((code) => reasonLabel(language, code)).join(", ")}` : text.partial}</AlertDescription></Alert> : null}
    {loading && !candidates ? <Skeleton className="h-32 w-full" /> : null}
    {!loading && candidates?.items.length === 0 ? <Card><CardContent className="py-8 text-center text-muted-foreground">{text.noCandidates}</CardContent></Card> : null}
    <div className="grid gap-3">{candidates?.items.map((candidate) => <CandidateCard key={candidate.jellyfin_item_id} candidate={candidate} language={language} text={text} selected={selection} onToggle={onToggle} onDelete={onDelete} locale={locale} />)}</div>
    {candidates?.next_cursor ? <Button variant="outline" onClick={onLoadMore} disabled={loading}>{text.loadMore}</Button> : null}
    {selected.length ? <aside className="sticky bottom-3 flex flex-wrap items-center justify-between gap-3 rounded-xl border bg-card p-3 shadow-lg"><span className="text-sm">{selected.length} {text.selection}</span><Button onClick={(event) => onBatchPreview(selected, event.currentTarget)}>{text.preview}</Button>{selectionError ? <span role="alert" className="text-xs text-status-warning">{selectionError === "batch_limit_exceeded" ? text.limit : text.overlapping}</span> : null}</aside> : null}
  </div>
}

function CandidateCard({ candidate, language, text, selected, onToggle, onDelete, locale }: { candidate: CleanupCandidate; language: DownloadsLanguage; text: DownloadsCopy; selected: ReturnType<typeof emptyBatchSelection>; onToggle: (candidate: CleanupCandidate) => void; onDelete: (target: LibraryDeleteTarget, trigger: HTMLElement) => void; locale: string }) {
  const target = cleanupTarget(candidate)
  const selection = target ? selectionItem(target, candidate.deletion_link?.display_name ?? candidate.display_name, candidate.size_bytes) : null
  return <Card><CardContent className="flex flex-wrap items-start gap-3 py-4">
    {selection ? <Checkbox checked={Boolean(selected.items[selection.key])} aria-label={`${text.select}: ${candidate.deletion_link?.display_name ?? candidate.display_name}`} onCheckedChange={() => onToggle(candidate)} /> : null}
    <div className="min-w-0 flex-1"><p className="truncate font-medium">{candidate.deletion_link?.display_name ?? candidate.display_name}</p><p className="text-xs text-muted-foreground">{candidate.media_type === "movie" ? text.movies : text.series} · {candidate.playback_status === "watched" ? text.watched : candidate.playback_status === "never_watched" ? text.neverWatched : text.cleanupUnknown}</p>
      <div className="mt-2 grid gap-1 text-xs text-muted-foreground sm:grid-cols-2 lg:grid-cols-4"><span>{text.playCount}: {knownNumber(candidate.play_count, String, text)}</span><span>{text.watchedUsers}: {knownNumber(candidate.watched_user_count, String, text)}</span><span>{text.lastPlayed}: {date(candidate.last_played_at, text, locale)}</span><span>{text.libraryAge}: {date(candidate.added_at ?? candidate.created_at, text, locale)}</span><span>{text.size}: {bytes(candidate.size_bytes, text)}</span><span>{text.seedRatio}: {knownNumber(candidate.seeding.ratio, (number) => number.toFixed(2), text)}</span><span>{text.seedTime}: {duration(candidate.seeding.seeding_time_seconds, text)}</span><span>{text.readiness}: {enumLabel(language, "readiness", candidate.seeding.readiness)}</span><span>{text.torrentState}: {enumLabel(language, "state", candidate.seeding.torrent_state)}</span><span>{text.torrentCount}: {knownNumber(candidate.seeding.torrent_count, String, text)}</span><span>{text.readinessReason}: {reasonLabel(language, candidate.seeding.readiness_reason)}</span><span>{text.source}: {text.sourceJellyfin}</span><span>{text.fetched}: {date(candidate.fetched_at, text, locale)}</span><span>{text.unavailableReason}: {reasonLabel(language, candidate.unavailable_reason ?? candidate.playback_unavailable_reason ?? candidate.seeding.unavailable_reason)}</span></div>
    </div>
    {target ? <Button variant="outline" size="sm" onClick={(event) => onDelete(target, event.currentTarget)}>{text.plan}</Button> : <span className="max-w-52 text-xs text-muted-foreground">{text.missingLink}</span>}
  </CardContent></Card>
}
