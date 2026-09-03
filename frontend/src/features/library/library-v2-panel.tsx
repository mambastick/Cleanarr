import {
  AlertCircle,
  Film,
  Info,
  RefreshCw,
  Search,
  Trash2,
  Tv,
  X,
} from "lucide-react"
import { ArrowDown as ArrowDownData, ArrowUp as ArrowUpData } from "lucide"
import { MorphIcon } from "morphicons/react"
import { useCallback, useEffect, useMemo, useRef, useState, type MouseEvent as ReactMouseEvent, type ReactNode } from "react"

import { AnimateIcon, AnimatedIcon } from "@/components/animate-ui/animated-icon"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import { Input } from "@/components/ui/input"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import {
  Sheet,
  SheetBackdrop,
  SheetClose,
  SheetContent,
  SheetDescription,
  SheetPortal,
  SheetTitle,
} from "@/components/ui/sheet"
import { Skeleton } from "@/components/ui/skeleton"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import {
  fetchLibraryArtwork,
  fetchLibraryItem,
  type LibraryDirection,
  type LibraryFetchJson,
  type LibraryItem,
  type LibraryItemDetail,
  type LibraryMediaType,
  type LibrarySort,
} from "@/lib/library"
import { cn } from "@/lib/utils"
import { LIBRARY_COPY, type LibraryLanguage, type LibraryV2Copy } from "./library-copy"
import { libraryDeleteTargetFromItem } from "./library-selection"
import { useLibrary, type LibraryFilters } from "./use-library"

export interface LibraryPanelV2Props {
  active: boolean
  authenticated: boolean
  language?: LibraryLanguage
  copy?: LibraryV2Copy
  fetchJson: LibraryFetchJson
  /** The application owns confirmation; this callback must only prepare a plan. */
  onDeletePreview?: (item: LibraryItem, trigger: HTMLElement) => void
  onBatchPreview?: (items: LibraryItem[], trigger: HTMLElement) => void
  onCatalogRevisionChange?: (revision: string) => void
  resetKey?: string | number
}

function useDesktopInspector() {
  const query = "(min-width: 1200px)"
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

function unknownDetail(item: LibraryItem): LibraryItemDetail {
  return {
    ...item,
    playback: { watched: "unknown", play_count: null, last_played_at: null, freshness: "unknown" },
    library_dates: { added_at: item.added_at, updated_at: null },
    seeding: { state: "unknown", readiness: "unknown", ratio: null, seeded_seconds: null, reason: null },
    seasons: null,
    safety: { status: "unknown", reason: null },
  }
}

export function LibraryPanelV2({
  active,
  authenticated,
  language = "en",
  copy,
  fetchJson,
  onDeletePreview,
  onBatchPreview,
  onCatalogRevisionChange,
  resetKey,
}: LibraryPanelV2Props) {
  const text = copy ?? LIBRARY_COPY[language]
  const desktopInspector = useDesktopInspector()
  const [mediaType, setMediaType] = useState<LibraryMediaType>("movie")
  const [query, setQuery] = useState("")
  const [sort, setSort] = useState<LibrarySort>("added")
  const [direction, setDirection] = useState<LibraryDirection>("desc")
  const [selectMode, setSelectMode] = useState(false)
  const [selected, setSelected] = useState<Record<string, LibraryItem>>({})
  const [catalogRevisions, setCatalogRevisions] = useState<Partial<Record<LibraryMediaType, string>>>({})
  const [selectionError, setSelectionError] = useState<string | null>(null)
  const [detail, setDetail] = useState<LibraryItemDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [detailError, setDetailError] = useState(false)
  const detailTrigger = useRef<HTMLElement | null>(null)
  const detailRequest = useRef(0)
  const filters: LibraryFilters = { mediaType, query, sort, direction, refresh: false }
  const list = useLibrary({ active, authenticated, filters, fetchJson, onCatalogRevisionChange })

  const resetSelection = useCallback(() => {
    setSelected({})
    setSelectionError(null)
  }, [])

  const selectedItems = useMemo(() => Object.values(selected), [selected])
  const visibleIds = useMemo(() => new Set(list.items.map((item) => item.resource_id)), [list.items])
  const hidden = selectedItems.filter((item) => !visibleIds.has(item.resource_id)).length
  const catalogChanging = list.error === "catalog_changed"
  const selectionNeedsReview = selectedItems.some((item) => {
    const currentRevision = catalogRevisions[item.media_type]
    return currentRevision != null && item.catalog_revision !== currentRevision
  })

  useEffect(() => {
    detailRequest.current += 1
    resetSelection()
    setCatalogRevisions({})
    setSelectMode(false)
    setDetail(null)
    setDetailLoading(false)
    setDetailError(false)
  }, [resetKey, resetSelection])
  useEffect(() => {
    if (!authenticated) {
      detailRequest.current += 1
      resetSelection()
      setSelectMode(false)
      setDetail(null)
      setDetailLoading(false)
      setDetailError(false)
    }
  }, [authenticated, resetSelection])
  useEffect(() => {
    if (!list.catalogRevision) return
    setCatalogRevisions((current) => current[mediaType] === list.catalogRevision
      ? current
      : { ...current, [mediaType]: list.catalogRevision })
  }, [list.catalogRevision, mediaType])
  useEffect(() => {
    if (!list.items.length) return
    setSelected((current) => {
      let changed = false
      const next = { ...current }
      for (const item of list.items) {
        if (current[item.resource_id] && current[item.resource_id] !== item) {
          if (item.delete_target) next[item.resource_id] = item
          else delete next[item.resource_id]
          changed = true
        }
      }
      return changed ? next : current
    })
  }, [list.items])

  const openDetail = useCallback(async (item: LibraryItem, trigger: HTMLElement) => {
    detailTrigger.current = trigger
    const request = ++detailRequest.current
    setDetail(unknownDetail(item))
    setDetailError(false)
    setDetailLoading(true)
    try {
      const next = await fetchLibraryItem(fetchJson, item.resource_id)
      if (request === detailRequest.current) setDetail(next)
    } catch {
      if (request === detailRequest.current) setDetailError(true)
    } finally {
      if (request === detailRequest.current) setDetailLoading(false)
    }
  }, [fetchJson])

  const closeDetail = useCallback(() => {
    detailRequest.current += 1
    setDetail(null)
    setDetailLoading(false)
    setDetailError(false)
    window.setTimeout(() => detailTrigger.current?.focus(), 0)
  }, [])

  useEffect(() => {
    if (!detail || !desktopInspector) return
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") closeDetail()
    }
    window.addEventListener("keydown", onKeyDown)
    return () => window.removeEventListener("keydown", onKeyDown)
  }, [closeDetail, desktopInspector, detail])

  const retryDetail = useCallback(() => {
    if (detail && detailTrigger.current) void openDetail(detail, detailTrigger.current)
  }, [detail, openDetail])

  const toggle = (item: LibraryItem) => {
    if (!libraryDeleteTargetFromItem(item)) {
      setSelectionError(text.deleteUnavailable)
      return
    }
    setSelected((current) => {
      if (current[item.resource_id]) {
        const next = { ...current }
        delete next[item.resource_id]
        setSelectionError(null)
        return next
      }
      if (Object.keys(current).length >= 50) {
        setSelectionError(text.selectionLimit)
        return current
      }
      setSelectionError(null)
      return { ...current, [item.resource_id]: item }
    })
  }

  const selectVisibleItems = () => {
    setSelected((current) => {
      const next = { ...current }
      let count = Object.keys(next).length
      for (const item of list.items) {
        if (next[item.resource_id] || !libraryDeleteTargetFromItem(item)) continue
        if (count >= 50) {
          setSelectionError(text.selectionLimit)
          return next
        }
        next[item.resource_id] = item
        count += 1
      }
      setSelectionError(null)
      return next
    })
  }

  const listColumn = (
    <div className="min-w-0 space-y-5">
      <LibraryStatus text={text} status={list.sourceStatus} failures={list.sourceFailures} error={list.error} onRetry={list.retry} />
      {list.loading && !list.items.length ? (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5" aria-label={text.title} aria-busy="true">
          {Array.from({ length: 8 }, (_, index) => <Skeleton key={index} className="aspect-[2/3] w-full rounded-xl" />)}
        </div>
      ) : null}
      {!list.loading && !list.items.length && !list.error ? <div className="rounded-xl border border-dashed border-border p-10 text-center text-sm text-muted-foreground">{text.noItems}</div> : null}
      {list.items.length ? (
        <div role="list" className="grid grid-cols-2 gap-x-3 gap-y-6 sm:grid-cols-3 sm:gap-4 lg:grid-cols-4 xl:grid-cols-5">
          {list.items.map((item) => (
            <LibraryCard
              key={item.resource_id}
              item={item}
              text={text}
              selectMode={selectMode}
              selected={Boolean(selected[item.resource_id])}
              onToggle={() => toggle(item)}
              onOpen={openDetail}
              onDeletePreview={onDeletePreview}
            />
          ))}
        </div>
      ) : null}
      {list.nextCursor ? <AnimateIcon><Button variant="outline" className="w-full sm:w-auto" onClick={list.loadMore} disabled={list.loadingMore}>{list.loadingMore ? <AnimatedIcon animation="rotate"><RefreshCw className="opacity-50" /></AnimatedIcon> : null}{text.loadMore}</Button></AnimateIcon> : null}
    </div>
  )

  return (
    <section className={cn("relative space-y-5 pb-24", detail && desktopInspector && "pr-[384px]")} aria-label={text.title}>
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div><h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">{text.title}</h1><p className="mt-1 text-sm text-muted-foreground">{text.description}</p></div>
        <div className="flex items-center gap-2">
          {selectMode ? <Button variant="outline" onClick={selectVisibleItems} disabled={!list.items.length}>{text.selectVisible}</Button> : null}
          <AnimateIcon><Button data-batch-focus-fallback variant={selectMode ? "secondary" : "outline"} onClick={() => setSelectMode((value) => !value)} aria-pressed={selectMode}>{selectMode ? <AnimatedIcon animation="wiggle"><X /></AnimatedIcon> : null}{selectMode ? text.exitSelectMode : text.selectMode}</Button></AnimateIcon>
          <AnimateIcon><Button variant="outline" size="icon" aria-label={text.refresh} onClick={list.refresh} disabled={list.loading}><AnimatedIcon animation="rotate"><RefreshCw className={cn(list.loading && "opacity-50")} /></AnimatedIcon></Button></AnimateIcon>
        </div>
      </header>

      <Tabs className="md:data-horizontal:grid md:data-horizontal:grid-cols-[auto_minmax(0,1fr)] md:data-horizontal:items-center md:data-horizontal:gap-4" value={mediaType} onValueChange={(value) => setMediaType(value as LibraryMediaType)}>
        <TabsList aria-label={text.title}><AnimateIcon><TabsTrigger value="movie"><AnimatedIcon animation="pulse"><Film /></AnimatedIcon>{text.movies}</TabsTrigger></AnimateIcon><AnimateIcon><TabsTrigger value="series"><AnimatedIcon animation="pulse"><Tv /></AnimatedIcon>{text.series}</TabsTrigger></AnimateIcon></TabsList>
        <TabsContent value="movie" className="mt-3 md:col-start-2 md:row-start-1 md:mt-0"><LibraryControls text={text} query={query} setQuery={setQuery} sort={sort} setSort={setSort} direction={direction} setDirection={setDirection} /></TabsContent>
        <TabsContent value="series" className="mt-3 md:col-start-2 md:row-start-1 md:mt-0"><LibraryControls text={text} query={query} setQuery={setQuery} sort={sort} setSort={setSort} direction={direction} setDirection={setDirection} /></TabsContent>
      </Tabs>

      <div className="min-w-0">
        {listColumn}
        {detail && desktopInspector ? (
          <aside className="fixed inset-y-0 right-0 z-30 w-[360px] overflow-y-auto border-l border-border bg-card shadow-[-18px_0_45px_color-mix(in_srgb,var(--foreground)_8%,transparent)]" aria-label={text.technicalDetails}>
            <Button variant="secondary" size="icon" className="absolute right-4 top-4 z-10 bg-card/85 shadow-sm backdrop-blur" aria-label={text.close} onClick={closeDetail}><X aria-hidden="true" /></Button>
            <div className="h-64 bg-muted"><Artwork resourceId={detail.resource_id} artwork={detail.artwork} fallback={detail.media_type === "movie" ? <Film className="size-12 text-muted-foreground" /> : <Tv className="size-12 text-muted-foreground" />} /></div>
            <div className="relative -mt-8 min-h-[calc(100vh-14rem)] rounded-t-3xl bg-card p-5">
              <p className="sr-only">{text.technicalDetails}</p>
              <Inspector desktop detail={detail} loading={detailLoading} error={detailError} text={text} language={language} onDeletePreview={onDeletePreview} onSelect={() => { toggle(detail); setSelectMode(true) }} onRetry={retryDetail} />
            </div>
          </aside>
        ) : null}
      </div>

      {selectedItems.length ? (
        <aside className="sticky bottom-[calc(5.25rem+env(safe-area-inset-bottom))] z-30 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-primary/40 bg-card/95 p-3 shadow-lg backdrop-blur md:bottom-3" aria-label={`${selectedItems.length} ${text.selected}`}>
          <div><p className="text-sm font-medium">{selectedItems.length} {text.selected}{hidden ? <span className="ml-2 text-muted-foreground">· {hidden} {text.selectedHidden}</span> : null}</p>{selectionError || selectionNeedsReview ? <p role="alert" className="mt-1 text-xs text-status-warning">{selectionError ?? text.selectionNeedsReview}</p> : null}</div>
          <div className="flex gap-2"><Button variant="outline" onClick={resetSelection}>{text.clearSelection}</Button><Button onClick={(event) => onBatchPreview?.(selectedItems, event.currentTarget)} disabled={!onBatchPreview || catalogChanging || selectionNeedsReview || list.loading}>{text.batchDelete}</Button></div>
        </aside>
      ) : null}

      {!desktopInspector ? (
        <Sheet open={Boolean(detail)} onOpenChange={(open) => { if (!open) closeDetail() }}>
          <SheetPortal>
            <SheetBackdrop className="fixed inset-0 z-50 bg-foreground/25 backdrop-blur-[1px]" />
            <SheetContent className="fixed inset-y-0 right-0 z-[51] w-full overflow-y-auto border-l bg-card p-5 shadow-2xl outline-none sm:w-[360px]">
              <div className="flex items-start justify-between gap-3"><div><SheetTitle>{detail?.display_name ?? text.title}</SheetTitle><SheetDescription>{text.technicalDetails}</SheetDescription></div><SheetClose render={<Button variant="ghost" size="icon" aria-label={text.close} />}><X aria-hidden="true" /></SheetClose></div>
              {detail ? <Inspector detail={detail} loading={detailLoading} error={detailError} text={text} language={language} onDeletePreview={onDeletePreview} onSelect={() => { toggle(detail); setSelectMode(true) }} onRetry={retryDetail} /> : null}
            </SheetContent>
          </SheetPortal>
        </Sheet>
      ) : null}
    </section>
  )
}

function LibraryControls({ text, query, setQuery, sort, setSort, direction, setDirection }: { text: LibraryV2Copy; query: string; setQuery: (value: string) => void; sort: LibrarySort; setSort: (value: LibrarySort) => void; direction: LibraryDirection; setDirection: (value: LibraryDirection) => void }) {
  const directionIcon = direction === "desc" ? ArrowDownData : ArrowUpData
  return (
    <div className="flex flex-wrap items-center gap-2">
      <div className="relative min-w-[220px] flex-1"><Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden="true" /><Input className="pl-9" aria-label={text.search} placeholder={text.search} value={query} onChange={(event) => setQuery(event.target.value)} /></div>
      <Select items={{ added: text.added, title: text.titleSort, size: text.size }} value={sort} onValueChange={(value) => setSort(value as LibrarySort)}><SelectTrigger aria-label={text.sort} className="w-[180px]"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="added">{text.added}</SelectItem><SelectItem value="title">{text.titleSort}</SelectItem><SelectItem value="size">{text.size}</SelectItem></SelectContent></Select>
      <AnimateIcon><Button variant="outline" size="icon" aria-label={direction === "desc" ? text.descending : text.ascending} onClick={() => setDirection(direction === "desc" ? "asc" : "desc")}><AnimatedIcon animation="pulse"><MorphIcon icon={directionIcon} reducedMotion="user" size={16} /></AnimatedIcon></Button></AnimateIcon>
    </div>
  )
}

function LibraryStatus({ text, status, failures, error, onRetry }: { text: LibraryV2Copy; status: "complete" | "partial" | "unavailable" | null; failures: Array<{ source: string; code: string; message?: string | null }>; error: string | null; onRetry: () => void }) {
  const failureSummary = failures.length ? `${text.sourceFailure}: ${failures.map((failure) => `${failure.source} (${failure.code})`).join(", ")}` : null
  if (error && error !== "catalog_changed") return <Alert variant="destructive"><AlertCircle /><AlertTitle>{text.unavailable}</AlertTitle><AlertDescription className="flex flex-wrap items-center gap-2"><span>{failureSummary}</span><Button variant="outline" size="sm" onClick={onRetry}>{text.retry}</Button></AlertDescription></Alert>
  if (error === "catalog_changed") return <Alert><Info /><AlertTitle>{text.catalogChanged}</AlertTitle><AlertDescription><Button variant="outline" size="sm" onClick={onRetry}>{text.retry}</Button></AlertDescription></Alert>
  if (status === "unavailable") return <Alert variant="destructive"><AlertCircle /><AlertTitle>{text.unavailable}</AlertTitle><AlertDescription className="flex flex-wrap items-center gap-2"><span>{failureSummary}</span><Button variant="outline" size="sm" onClick={onRetry}>{text.retry}</Button></AlertDescription></Alert>
  if (status === "partial") return <Alert><Info /><AlertTitle>{text.partial}</AlertTitle><AlertDescription>{failureSummary}</AlertDescription></Alert>
  return null
}

function LibraryCard({ item, text, selectMode, selected, onToggle, onOpen, onDeletePreview }: { item: LibraryItem; text: LibraryV2Copy; selectMode: boolean; selected: boolean; onToggle: () => void; onOpen: (item: LibraryItem, trigger: HTMLElement) => void; onDeletePreview?: (item: LibraryItem, trigger: HTMLElement) => void }) {
  const typeLabel = item.media_type === "movie" ? text.movie : text.seriesType
  const selectable = Boolean(libraryDeleteTargetFromItem(item))
  const deleteAvailable = Boolean(onDeletePreview && libraryDeleteTargetFromItem(item))
  const selectionUnavailableId = `selection-unavailable-${item.resource_id.replace(/[^a-zA-Z0-9_-]/g, "-")}`
  const handleCardAction = (event: ReactMouseEvent<HTMLButtonElement>) => {
    if (selectMode) onToggle()
    else onOpen(item, event.currentTarget)
  }
  return (
    <article role="listitem" className="group relative min-w-0 transition-transform duration-200 hover:-translate-y-0.5">
      <div className={cn("relative aspect-[2/3] overflow-hidden rounded-lg bg-muted shadow-sm", selected && "ring-3 ring-primary ring-offset-2 ring-offset-background")}>
        <button type="button" className="absolute inset-0 z-0 block size-full rounded-lg text-left focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/50 disabled:cursor-not-allowed" aria-label={selectMode ? `${text.select}: ${item.display_name}` : `${item.display_name}, ${typeLabel}`} aria-describedby={selectMode && !selectable ? selectionUnavailableId : undefined} disabled={selectMode && !selectable} onClick={handleCardAction}><Artwork resourceId={item.resource_id} artwork={item.artwork} fallback={item.media_type === "movie" ? <Film className="size-10 text-muted-foreground" /> : <Tv className="size-10 text-muted-foreground" />} /></button>
        {selectMode ? <Checkbox className="absolute left-2 top-2 z-10 size-6 bg-card/90" checked={selected} disabled={!selectable} aria-label={`${text.select}: ${item.display_name}`} aria-describedby={!selectable ? selectionUnavailableId : undefined} onCheckedChange={onToggle} /> : null}
        <AnimateIcon><Button variant="destructive" size="icon" className="absolute right-2 top-2 z-10 size-11 opacity-0 shadow-md transition-opacity duration-200 group-hover:opacity-100 group-focus-within:opacity-100 [@media(hover:none)]:opacity-100" aria-label={`${text.reviewPlan}: ${item.display_name}`} title={deleteAvailable ? text.reviewPlan : text.deleteUnavailable} onClick={(event) => onDeletePreview?.(item, event.currentTarget)} disabled={!deleteAvailable}><AnimatedIcon animation="wiggle"><Trash2 /></AnimatedIcon></Button></AnimateIcon>
      </div>
      <button type="button" className="mt-2 block min-h-11 w-full rounded text-left focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/50 disabled:cursor-not-allowed" aria-describedby={selectMode && !selectable ? selectionUnavailableId : undefined} disabled={selectMode && !selectable} onClick={handleCardAction}><span className="block truncate text-sm font-medium">{item.display_name}</span><span className="block truncate text-xs text-muted-foreground">{item.year ?? text.unknown}{item.size != null ? ` · ${formatSize(item.size)}` : ""}</span></button>
      {selectMode && !selectable ? <p id={selectionUnavailableId} className="mt-1 text-xs text-muted-foreground">{text.selectionUnavailable}</p> : null}
    </article>
  )
}

function Artwork({ resourceId, artwork, fallback }: { resourceId: string; artwork: LibraryItem["artwork"]; fallback: ReactNode }) {
  const [url, setUrl] = useState<string | null>(null)
  const [failed, setFailed] = useState(artwork.status !== "available")
  const host = useRef<HTMLDivElement | null>(null)
  useEffect(() => {
    setFailed(artwork.status !== "available")
    setUrl((current) => { if (current) URL.revokeObjectURL(current); return null })
    if (artwork.status !== "available") return
    const controller = new AbortController()
    let objectUrl: string | null = null
    let started = false
    const start = () => {
      if (started) return
      started = true
      void fetchLibraryArtwork(resourceId, controller.signal).then((blob) => {
        if (controller.signal.aborted) return
        objectUrl = URL.createObjectURL(blob)
        setUrl(objectUrl)
      }).catch(() => { if (!controller.signal.aborted) setFailed(true) })
    }
    let observer: IntersectionObserver | null = null
    if (typeof IntersectionObserver === "undefined" || !host.current) start()
    else {
      observer = new IntersectionObserver((entries) => {
        if (entries.some((entry) => entry.isIntersecting)) { start(); observer?.disconnect() }
      }, { rootMargin: "200px" })
      observer.observe(host.current)
    }
    return () => { observer?.disconnect(); controller.abort(); if (objectUrl) URL.revokeObjectURL(objectUrl) }
  }, [artwork.status, resourceId])
  return <div ref={host} className="size-full">{url && !failed ? <img src={url} alt="" className="size-full object-cover" onError={() => { URL.revokeObjectURL(url); setUrl(null); setFailed(true) }} /> : <div className="grid size-full place-items-center" aria-hidden="true">{fallback}</div>}</div>
}

function Inspector({ detail, loading, error, text, language, onDeletePreview, onSelect, onRetry, desktop = false }: { detail: LibraryItemDetail; loading: boolean; error: boolean; text: LibraryV2Copy; language: LibraryLanguage; onDeletePreview?: (item: LibraryItem, trigger: HTMLElement) => void; onSelect: () => void; onRetry: () => void; desktop?: boolean }) {
  const playback = detail.playback
  const seeding = detail.seeding
  const watched = playback?.watched ?? detail.playback_status
  const playCount = playback?.play_count ?? detail.play_count
  const freshness = playback?.freshness ?? detail.playback_freshness
  const ratio = seeding?.ratio ?? detail.seeding_ratio
  const readiness = seeding?.readiness ?? detail.seeding_readiness
  const seededTime = seeding?.seeded_seconds ?? detail.seeding_time_seconds
  const seedReason = seeding?.reason ?? detail.seeding_reason
  const safetyStatus = detail.safety?.status ?? "unknown"
  const seasonCount = detail.seasons?.length ?? detail.series_counts?.seasons ?? detail.counts?.seasons
  const episodeCount = detail.seasons?.reduce((sum, season) => sum + (season.episode_count ?? 0), 0) ?? detail.series_counts?.episodes ?? detail.counts?.episodes
  const hasDeleteTarget = Boolean(libraryDeleteTargetFromItem(detail))
  const deleteAvailable = Boolean(onDeletePreview && hasDeleteTarget && !loading && !error)
  const safetyClass = safetyStatus === "safe" ? "border-status-success-border bg-status-success-bg text-status-success" : safetyStatus === "blocked" ? "border-status-danger-border bg-status-danger-bg text-status-danger" : "border-status-unknown-border bg-status-unknown-bg text-status-unknown"

  return (
    <div className="space-y-5 py-4">
      <div className={cn("flex gap-3", desktop && "-mt-20 items-center pr-10")}><div className="h-32 w-[85px] shrink-0 overflow-hidden rounded-lg bg-muted shadow-sm"><Artwork resourceId={detail.resource_id} artwork={detail.artwork} fallback={detail.media_type === "movie" ? <Film className="size-8 text-muted-foreground" /> : <Tv className="size-8 text-muted-foreground" />} /></div><div className="min-w-0"><h2 className="text-lg font-semibold leading-tight">{detail.display_name}</h2><p className="mt-1 text-sm text-muted-foreground">{detail.media_type === "movie" ? text.movie : text.seriesType}{detail.year != null ? ` · ${detail.year}` : ""}</p>{detail.torrent_client ? <p className="mt-2 text-xs text-muted-foreground">{text.torrentClient}: {detail.torrent_client}</p> : null}</div></div>
      {loading ? <p role="status" className="text-xs text-muted-foreground">{text.loadingDetails}</p> : null}
      {error ? <Alert><Info /><AlertTitle>{text.unknown}</AlertTitle><AlertDescription className="flex flex-wrap items-center gap-2"><span>{text.deleteUnavailable}</span><Button variant="outline" size="sm" onClick={onRetry}>{text.retry}</Button></AlertDescription></Alert> : null}
      <dl className="grid grid-cols-2 gap-3 rounded-xl border border-border p-3 text-sm">
        <Metric label={text.sizeLabel} value={detail.size == null ? text.unknown : formatSize(detail.size)} />
        <Metric label={text.addedLabel} value={formatDate(detail.library_dates?.added_at ?? detail.added_at, language, text.unknown)} />
        <Metric label={text.playback} value={watched === "watched" ? text.watched : watched === "never_watched" ? text.neverPlayed : text.unknown} />
        <Metric label={text.playCount} value={playCount == null ? text.unknown : String(playCount)} />
        <Metric label={text.lastPlayed} value={formatDate(playback?.last_played_at ?? detail.last_played_at, language, text.unknown)} />
        <Metric label={text.freshness} value={freshness === "fresh" ? text.fresh : freshness === "stale" ? text.stale : text.unknown} />
        <Metric label={text.ratio} value={ratio == null ? text.unknown : ratio.toFixed(2)} />
        <Metric label={text.seededTime} value={seededTime == null ? text.unknown : formatDuration(seededTime, language)} />
        <Metric label={text.readiness} value={readiness === "ready" ? text.ready : readiness === "not_ready" ? text.notReady : text.unknown} />
      </dl>
      {seedReason ? <p className="text-xs text-muted-foreground">{text.signalUnavailable}</p> : null}
      {detail.unknown_reasons?.length ? <div className="rounded-xl border border-status-unknown-border bg-status-unknown-bg p-3 text-xs"><p className="font-medium">{text.unknownReasons}</p><p className="mt-1">{text.signalUnavailable}</p></div> : null}
      {detail.media_type === "series" && seasonCount != null ? <div className="rounded-xl border border-border p-3 text-sm"><p className="font-medium">{text.seasons}</p><p className="text-muted-foreground">{seasonCount} · {episodeCount ?? text.unknown} {text.episodes}</p></div> : null}
      <div className={cn("rounded-xl border p-3 text-sm", safetyClass)}><p className="font-medium">{text.safety}</p><p className="mt-1 text-current/80">{safetyStatus === "safe" ? text.safe : safetyStatus === "blocked" ? text.blocked : text.signalUnavailable}</p></div>
      <div className="grid gap-2"><Button variant="destructive" className="w-full" disabled={!deleteAvailable} onClick={(event) => onDeletePreview?.(detail, event.currentTarget)}><Trash2 aria-hidden="true" />{text.reviewPlan}</Button>{!deleteAvailable ? <p className="text-xs text-muted-foreground">{text.deleteUnavailable}</p> : null}<Button variant="outline" className="w-full" disabled={!hasDeleteTarget || loading || error} onClick={onSelect}>{text.selectForGroup}</Button></div>
      <details><summary className="cursor-pointer text-sm font-medium">{text.additional}</summary><pre className="mt-2 max-h-40 overflow-auto rounded-lg bg-muted p-2 text-xs">{JSON.stringify({ resource_id: detail.resource_id, catalog_revision: detail.catalog_revision, fetched_at: detail.fetched_at, seeding_reason: seedReason, safety_reason: detail.safety?.reason, unknown_reasons: detail.unknown_reasons }, null, 2)}</pre></details>
    </div>
  )
}

function Metric({ label, value }: { label: string; value: string }) { return <div><dt className="text-xs text-muted-foreground">{label}</dt><dd className="mt-0.5 break-words font-medium">{value}</dd></div> }
function formatSize(size: number) { if (!size) return "0 B"; const index = Math.min(4, Math.floor(Math.log(size) / Math.log(1024))); return `${(size / 1024 ** index).toFixed(1)} ${["B", "KB", "MB", "GB", "TB"][index]}` }
function formatDuration(seconds: number, language: LibraryLanguage) { const days = Math.floor(seconds / 86_400); const hours = Math.floor((seconds % 86_400) / 3_600); return days ? `${days}${language === "ru" ? "д" : "d"} ${hours}${language === "ru" ? "ч" : "h"}` : `${hours}${language === "ru" ? "ч" : "h"}` }
function formatDate(value: string | null | undefined, language: LibraryLanguage, fallback: string) { if (!value) return fallback; const date = new Date(value); return Number.isNaN(date.getTime()) ? fallback : date.toLocaleDateString(language === "ru" ? "ru-RU" : "en-US") }
