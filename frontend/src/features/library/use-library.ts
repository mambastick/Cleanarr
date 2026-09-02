import { useCallback, useEffect, useRef, useState } from "react"
import { fetchLibraryItems, type LibraryFetchJson, type LibraryItem, type LibraryItemsQuery, type LibraryItemsResponse, type LibraryMediaType, type LibrarySort, type LibraryDirection } from "@/lib/library"

export interface LibraryFilters {
  mediaType: LibraryMediaType
  query: string
  sort: LibrarySort
  direction: LibraryDirection
  refresh: boolean
}

export interface LibraryListState {
  items: LibraryItem[]
  nextCursor: string | null
  sourceStatus: LibraryItemsResponse["source_status"] | null
  sourceFailures: LibraryItemsResponse["source_failures"]
  catalogRevision: string | null
  loading: boolean
  loadingMore: boolean
  error: string | null
}

const initialState: LibraryListState = { items: [], nextCursor: null, sourceStatus: null, sourceFailures: [], catalogRevision: null, loading: false, loadingMore: false, error: null }
const errorCode = (error: unknown) => typeof error === "object" && error !== null && "code" in error && typeof error.code === "string" ? error.code : "request_failed"

export function libraryQuery(filters: LibraryFilters, cursor?: string | null): LibraryItemsQuery {
  return { media_type: filters.mediaType, q: filters.query, sort: filters.sort, direction: filters.direction, limit: 50, cursor, refresh: filters.refresh }
}

/** Server-backed list lifecycle: debounce, abort old queries, ignore stale responses, and merge cursors. */
export function useLibrary({ active, authenticated, filters, fetchJson, onCatalogRevisionChange, debounceMs = 250 }: { active: boolean; authenticated: boolean; filters: LibraryFilters; fetchJson: LibraryFetchJson; onCatalogRevisionChange?: (revision: string) => void; debounceMs?: number }) {
  const [state, setState] = useState<LibraryListState>(initialState)
  const [catalogReset, setCatalogReset] = useState(0)
  const stateRef = useRef(state)
  const controllerRef = useRef<AbortController | null>(null)
  const generationRef = useRef(0)
  const latestRef = useRef({ filters, fetchJson, onCatalogRevisionChange })
  useEffect(() => { stateRef.current = state }, [state])
  useEffect(() => { latestRef.current = { filters, fetchJson, onCatalogRevisionChange } }, [fetchJson, filters, onCatalogRevisionChange])

  const stop = useCallback(() => {
    generationRef.current += 1
    controllerRef.current?.abort()
    controllerRef.current = null
  }, [])

  const load = useCallback(async (cursor?: string | null, explicitRefresh = false) => {
    const generation = generationRef.current
    const latest = latestRef.current
    if (!active || !authenticated) return
    controllerRef.current?.abort()
    const controller = new AbortController()
    controllerRef.current = controller
    const query = libraryQuery({ ...latest.filters, refresh: explicitRefresh || latest.filters.refresh }, cursor)
    setState((previous) => ({ ...previous, loading: !cursor, loadingMore: Boolean(cursor), error: null }))
    try {
      const response = await fetchLibraryItems(latest.fetchJson, query, controller.signal)
      if (generation !== generationRef.current || controller.signal.aborted) return
      const isPage = Boolean(cursor)
      const revisionChanged = isPage && stateRef.current.catalogRevision !== null && stateRef.current.catalogRevision !== response.catalog_revision
      const items = isPage ? [...stateRef.current.items, ...response.items] : response.items
      if (revisionChanged) {
        // A server catalog change invalidates old pages; retain only this response.
        setState((previous) => ({ ...previous, items: response.items, nextCursor: response.next_cursor, sourceStatus: response.source_status, sourceFailures: response.source_failures, catalogRevision: response.catalog_revision, loading: false, loadingMore: false, error: "catalog_changed" }))
      } else {
        setState((previous) => ({ ...previous, items, nextCursor: response.next_cursor, sourceStatus: response.source_status, sourceFailures: response.source_failures, catalogRevision: response.catalog_revision, loading: false, loadingMore: false, error: null }))
      }
      latest.onCatalogRevisionChange?.(response.catalog_revision)
    } catch (error) {
      if (generation !== generationRef.current || controller.signal.aborted) return
      const code = errorCode(error)
      if (cursor && code === "catalog_changed") {
        setState((previous) => ({ ...previous, items: [], nextCursor: null, loading: true, loadingMore: false, error: code }))
        setCatalogReset((value) => value + 1)
      } else {
        setState((previous) => ({ ...previous, loading: false, loadingMore: false, error: code }))
      }
    } finally {
      if (controllerRef.current === controller) controllerRef.current = null
    }
  }, [active, authenticated])

  useEffect(() => {
    stop()
    setState({ ...initialState })
    if (!active || !authenticated) return
    const timer = window.setTimeout(() => { void load() }, debounceMs)
    return () => { window.clearTimeout(timer); stop() }
  }, [active, authenticated, filters.mediaType, filters.query, filters.sort, filters.direction, filters.refresh, catalogReset, debounceMs, load, stop])

  const retry = useCallback(() => { void load() }, [load])
  const refresh = useCallback(() => { void load(null, true) }, [load])
  const loadMore = useCallback(() => { if (state.nextCursor && !state.loadingMore) void load(state.nextCursor) }, [load, state.loadingMore, state.nextCursor])
  return { ...state, retry, refresh, loadMore }
}
