import { AlertCircle, RefreshCw, ShieldAlert } from "lucide-react"
import { useCallback, useEffect, useRef, useState } from "react"

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Skeleton } from "@/components/ui/skeleton"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { emptyBatchSelection, selectedItems, selectionItem, toggleSelection, type BatchSelectionItem, type LibraryDeleteTarget } from "@/features/library/library-selection"
import { ApiError } from "@/lib/api-client"
import { EMPTY_DOWNLOAD_FILTERS, type CleanupCandidate, type CleanupSort, type DownloadAction, type DownloadActionResponse, type DownloadItem, type DownloadsFilters } from "@/lib/downloads"
import { createClientIdempotencyKey } from "@/lib/idempotency"
import { CleanupView } from "./cleanup-view"
import { cleanupTarget } from "./cleanup-target"
import { DOWNLOADS_COPY, enumLabel, reasonLabel, type DownloadsCopy, type DownloadsLanguage } from "./downloads-copy"
import { TorrentCard, type DownloadActionState } from "./torrent-card"
import { TorrentTable } from "./torrent-table"
import { useCleanupCandidates } from "./use-cleanup-candidates"
import { useDownloads } from "./use-downloads"

type FetchJson = <T>(url: string, init?: RequestInit) => Promise<T>
type ActionLock = { body: string; pending: boolean }
const completed = new Set(["succeeded", "already_in_state", "simulated"])
const apiCode = (error: unknown) => error instanceof ApiError ? error.code : null
const ambiguous = (error: unknown) => !(error instanceof ApiError) || error.status >= 500

export function DownloadsPanel({ active, authenticated, language, isLive, canMutate = true, fetchJson, onActiveCountChange, onDelete, onBatchPreview }: { active: boolean; authenticated: boolean; language: DownloadsLanguage; isLive: boolean; canMutate?: boolean; fetchJson: FetchJson; onActiveCountChange: (count: number) => void; onDelete: (target: LibraryDeleteTarget, trigger: HTMLElement) => void; onBatchPreview: (items: BatchSelectionItem[], trigger: HTMLElement) => void }) {
  const text = DOWNLOADS_COPY[language]
  const [subtab, setSubtab] = useState("torrents")
  const [filters, setFilters] = useState<DownloadsFilters>(EMPTY_DOWNLOAD_FILTERS)
  const [selection, setSelection] = useState(emptyBatchSelection)
  const [selectionError, setSelectionError] = useState<string | null>(null)
  const [playback, setPlayback] = useState("")
  const [media, setMedia] = useState("")
  const [readiness, setReadiness] = useState("")
  const [sort, setSort] = useState<CleanupSort>("library_added")
  const [direction, setDirection] = useState<"asc" | "desc">("desc")
  const actionLocks = useRef(new Map<string, ActionLock>())
  const desktopRows = useDesktopRows()
  const [actionStates, setActionStates] = useState<Record<string, DownloadActionState>>({})
  const downloads = useDownloads({ active, authenticated, filters, fetchJson, onActiveCountChange })
  const cleanupFilters = { playback, media, readiness, sort, direction }
  const cleanup = useCleanupCandidates({ active, authenticated, visible: subtab === "cleanup", filters: cleanupFilters, fetchJson })

  const control = useCallback(async (item: DownloadItem, action: DownloadAction) => {
    if (!canMutate) return
    const itemKey = `${item.client_id}:${item.info_hash}:${action}`
    const previous = actionLocks.current.get(itemKey)
    if (previous?.pending) return
    const body = previous?.body ?? JSON.stringify({ client_id: item.client_id, info_hash: item.info_hash, action, idempotency_key: createClientIdempotencyKey() })
    actionLocks.current.set(itemKey, { body, pending: true })
    setActionStates((states) => ({ ...states, [itemKey]: { phase: "pending", action, code: null, status: null } }))
    try {
      const response = await fetchJson<DownloadActionResponse>("/api/downloads/actions", { method: "POST", body })
      if (completed.has(response.status)) {
        actionLocks.current.delete(itemKey)
        setActionStates((states) => ({ ...states, [itemKey]: { phase: "completed", action, code: response.code, status: response.status } }))
        downloads.reload()
      } else if (response.status === "uncertain" || response.status === "reconcile_required" || response.status === "queued" || response.status === "running") {
        // A 200 response is not proof that the reversible action happened.
        actionLocks.current.set(itemKey, { body, pending: false })
        setActionStates((states) => ({ ...states, [itemKey]: { phase: "retry", action, code: response.code, status: response.status } }))
      } else {
        actionLocks.current.delete(itemKey)
        setActionStates((states) => ({ ...states, [itemKey]: { phase: "failed", action, code: response.code, status: response.status } }))
      }
    } catch (error) {
      const code = apiCode(error)
      if (code === "idempotency_conflict") {
        actionLocks.current.delete(itemKey)
        setActionStates((states) => ({ ...states, [itemKey]: { phase: "conflict", action, code, status: null } }))
      } else if (ambiguous(error)) {
        actionLocks.current.set(itemKey, { body, pending: false })
        setActionStates((states) => ({ ...states, [itemKey]: { phase: "retry", action, code, status: "uncertain" } }))
      } else {
        actionLocks.current.delete(itemKey)
        setActionStates((states) => ({ ...states, [itemKey]: { phase: "failed", action, code, status: "failed" } }))
      }
    }
  }, [canMutate, downloads, fetchJson])

  const toggleCandidate = (candidate: CleanupCandidate) => {
    const target = cleanupTarget(candidate)
    if (!target || target.kind === "jellyfin_movie") return
    const displayName = candidate.deletion_link?.display_name ?? candidate.display_name
    const result = toggleSelection(selection, selectionItem(target, displayName, candidate.size_bytes))
    setSelection(result.selection)
    setSelectionError(result.error)
  }
  const selected = selectedItems(selection)
  return <section className="flex flex-col gap-5">
    <div className="flex flex-wrap items-start justify-between gap-3"><div><h2 className="text-lg font-semibold">{text.title}</h2><p className="text-sm text-muted-foreground">{text.description}</p></div><Button variant="outline" onClick={() => void downloads.refresh()} disabled={downloads.refreshing}><RefreshCw data-icon="inline-start" className={downloads.refreshing ? "animate-spin" : undefined} />{text.refresh}</Button></div>
    {!isLive ? <Alert><AlertTitle>{text.dryRun}</AlertTitle><AlertDescription>{text.refreshHint}</AlertDescription></Alert> : null}
    {!canMutate ? <p className="text-xs text-muted-foreground">{text.adminOnly}</p> : null}
    <Tabs value={subtab} onValueChange={setSubtab}><TabsList aria-label={text.title} className="max-w-full"><TabsTrigger value="torrents">{text.torrents}{downloads.data ? <Badge variant="secondary">{downloads.data.active_count}</Badge> : null}</TabsTrigger><TabsTrigger value="cleanup">{text.cleanup}</TabsTrigger></TabsList>
      <TabsContent value="torrents" className="mt-4"><TorrentsView language={language} text={text} filters={filters} setFilters={setFilters} downloads={downloads} actionStates={actionStates} onControl={control} desktopRows={desktopRows} canMutate={canMutate} /></TabsContent>
      <TabsContent value="cleanup" className="mt-4"><CleanupView language={language} text={text} candidates={cleanup.data} error={Boolean(cleanup.error)} loading={cleanup.loading} {...cleanupFilters} setPlayback={setPlayback} setMedia={setMedia} setReadiness={setReadiness} setSort={setSort} setDirection={setDirection} onRetry={cleanup.retry} onLoadMore={cleanup.loadMore} selection={selection} onToggle={toggleCandidate} onDelete={onDelete} onBatchPreview={onBatchPreview} selected={selected} selectionError={selectionError} desktopRows={desktopRows} canMutate={canMutate} /></TabsContent>
    </Tabs>
  </section>
}

function TorrentsView({ language, text, filters, setFilters, downloads, actionStates, onControl, desktopRows, canMutate }: { language: DownloadsLanguage; text: DownloadsCopy; filters: DownloadsFilters; setFilters: (next: DownloadsFilters) => void; downloads: ReturnType<typeof useDownloads>; actionStates: Record<string, DownloadActionState>; onControl: (item: DownloadItem, action: DownloadAction) => void; desktopRows: boolean; canMutate: boolean }) {
  const field = (key: keyof DownloadsFilters, label: string) => <Input aria-label={label} value={filters[key]} placeholder={label} onChange={(event) => setFilters({ ...filters, [key]: event.target.value })} />
  const partial = downloads.data?.source_status === "partial" || Boolean(downloads.data?.failures.length) || Boolean(downloads.data?.failure_details.length)
  return <div className="flex flex-col gap-4"><div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">{field("client", text.filterClient)}{field("kind", text.kind)}{field("category", text.filterCategory)}{field("tag", text.filterTag)}<EnumSelect label={text.state} value={filters.state} values={["downloading", "seeding", "stopped", "queued", "checking", "error", "unknown"]} onChange={(state) => setFilters({ ...filters, state })} render={(value) => enumLabel(language, "state", value as never)} all={text.all} /><EnumSelect label={text.ownership} value={filters.ownership} values={["managed", "unmanaged", "conflict", "unknown"]} onChange={(ownership) => setFilters({ ...filters, ownership })} render={(value) => enumLabel(language, "ownership", value as never)} all={text.all} /></div>
    <Button variant="ghost" size="sm" onClick={() => setFilters(EMPTY_DOWNLOAD_FILTERS)}>{text.clear}</Button>
    {downloads.error ? <Alert variant="destructive"><AlertCircle /><AlertTitle>{text.failed}</AlertTitle><AlertDescription><Button variant="outline" size="sm" onClick={() => void downloads.reload()}>{text.retry}</Button></AlertDescription></Alert> : null}
    {partial ? <Alert><ShieldAlert /><AlertTitle>{text.partial}</AlertTitle><AlertDescription>{downloads.data?.failure_details.length ? `${text.partialEvidence}: ${downloads.data.failure_details.map((failure) => reasonLabel(language, failure.code)).join(", ")}` : text.partial}</AlertDescription></Alert> : null}
    {downloads.loading ? <div className="flex flex-col gap-3">{[1, 2, 3].map((number) => <Skeleton key={number} className="h-28 w-full" />)}</div> : null}
    {!downloads.loading && downloads.data?.items.length === 0 ? <Card><CardContent className="py-8 text-center text-muted-foreground">{text.noTorrents}</CardContent></Card> : null}
    {desktopRows && downloads.data?.items.length ? <TorrentTable items={downloads.data.items} language={language} text={text} actionStates={actionStates} onControl={onControl} canMutate={canMutate} /> : null}
    {!desktopRows ? <div className="grid gap-3">{downloads.data?.items.map((item) => <TorrentCard key={`${item.client_id}:${item.info_hash}`} item={item} language={language} text={text} actionStates={actionStates} onControl={onControl} canMutate={canMutate} />)}</div> : null}
    {downloads.data?.next_cursor ? <Button variant="outline" onClick={() => void downloads.loadMore()} disabled={downloads.loading}>{text.loadMore}</Button> : null}
  </div>
}

function EnumSelect({ label, value, values, onChange, render, all }: { label: string; value: string; values: string[]; onChange: (value: string) => void; render: (value: string) => string; all: string }) { const items = Object.fromEntries([["all", all], ...values.map((item) => [item, render(item)])]); return <Select items={items} value={value || "all"} onValueChange={(next) => onChange(next && next !== "all" ? next : "")}><SelectTrigger aria-label={label}><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">{all}</SelectItem>{values.map((item) => <SelectItem key={item} value={item}>{render(item)}</SelectItem>)}</SelectContent></Select> }

function useDesktopRows() {
  const query = "(min-width: 768px)"
  const [desktop, setDesktop] = useState(() => typeof window !== "undefined" && typeof window.matchMedia === "function" && window.matchMedia(query).matches)
  useEffect(() => {
    if (typeof window.matchMedia !== "function") return
    const media = window.matchMedia(query)
    const update = () => setDesktop(media.matches)
    update()
    media.addEventListener("change", update)
    return () => media.removeEventListener("change", update)
  }, [])
  return desktop
}
