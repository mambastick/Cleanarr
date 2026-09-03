import { useCallback, useEffect, useRef, useState } from "react"

import { fetchLibraryItems, type LibraryDirection, type LibraryFetchJson, type LibraryItem, type LibraryItemsQuery, type LibraryItemsResponse, type LibraryMediaType, type LibrarySort } from "@/lib/library"

export interface LibraryFilters {
  mediaType: LibraryMediaType
  query: string
  sort: LibrarySort
  direction: LibraryDirection
  pageSize: number
  refresh: boolean
}

export interface LibraryListState {
  items: LibraryItem[]
  nextCursor: string | null
  sourceStatus: LibraryItemsResponse["source_status"] | null
  sourceFailures: LibraryItemsResponse["source_failures"]
  catalogRevision: string | null
  loading: boolean
  error: string | null
}

const initialState: LibraryListState = { items: [], nextCursor: null, sourceStatus: null, sourceFailures: [], catalogRevision: null, loading: false, error: null }
const errorCode = (error: unknown) => typeof error === "object" && error !== null && "code" in error && typeof error.code === "string" ? error.code : "request_failed"

export function libraryQuery(filters: LibraryFilters, cursor?: string | null): LibraryItemsQuery {
  return { media_type: filters.mediaType, q: filters.query, sort: filters.sort, direction: filters.direction, limit: filters.pageSize, cursor, refresh: filters.refresh }
}

/** Cursor pagination with stable pages, cancellation, and fail-closed catalog revision checks. */
export function useLibrary({ active, authenticated, filters, fetchJson, onCatalogRevisionChange, debounceMs = 250 }: { active: boolean; authenticated: boolean; filters: LibraryFilters; fetchJson: LibraryFetchJson; onCatalogRevisionChange?: (revision: string) => void; debounceMs?: number }) {
  const [state, setState] = useState<LibraryListState>(initialState)
  const [pageCursors, setPageCursors] = useState<Array<string | null>>([null])
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

  const load = useCallback(async (cursor: string | null, explicitRefresh = false, expectedRevision?: string | null) => {
    const generation = generationRef.current
    const latest = latestRef.current
    if (!active || !authenticated) return false
    controllerRef.current?.abort()
    const controller = new AbortController()
    controllerRef.current = controller
    const query = libraryQuery({ ...latest.filters, refresh: explicitRefresh || latest.filters.refresh }, cursor)
    setState((previous) => ({ ...previous, loading: true, error: null }))
    try {
      const response = await fetchLibraryItems(latest.fetchJson, query, controller.signal)
      if (generation !== generationRef.current || controller.signal.aborted) return false
      if (expectedRevision && expectedRevision !== response.catalog_revision) {
        setState((previous) => ({ ...previous, items: response.items, nextCursor: response.next_cursor, sourceStatus: response.source_status, sourceFailures: response.source_failures, catalogRevision: response.catalog_revision, loading: false, error: "catalog_changed" }))
        setPageCursors([null])
        return false
      }
      setState({ items: response.items, nextCursor: response.next_cursor, sourceStatus: response.source_status, sourceFailures: response.source_failures, catalogRevision: response.catalog_revision, loading: false, error: null })
      latest.onCatalogRevisionChange?.(response.catalog_revision)
      return true
    } catch (error) {
      if (generation !== generationRef.current || controller.signal.aborted) return false
      setState((previous) => ({ ...previous, loading: false, error: errorCode(error) }))
      return false
    } finally {
      if (controllerRef.current === controller) controllerRef.current = null
    }
  }, [active, authenticated])

  useEffect(() => {
    stop()
    setState({ ...initialState })
    setPageCursors([null])
    if (!active || !authenticated) return
    const timer = window.setTimeout(() => { void load(null) }, debounceMs)
    return () => { window.clearTimeout(timer); stop() }
  }, [active, authenticated, filters.mediaType, filters.query, filters.sort, filters.direction, filters.pageSize, filters.refresh, debounceMs, load, stop])

  const retry = useCallback(() => { void load(pageCursors.at(-1) ?? null, false, stateRef.current.catalogRevision) }, [load, pageCursors])
  const refresh = useCallback(() => { setPageCursors([null]); void load(null, true) }, [load])
  const nextPage = useCallback(() => {
    if (!state.nextCursor || state.loading) return
    const nextCursor = state.nextCursor
    void load(nextCursor, false, state.catalogRevision).then((loaded) => { if (loaded) setPageCursors((current) => [...current, nextCursor]) })
  }, [load, state.catalogRevision, state.loading, state.nextCursor])
  const previousPage = useCallback(() => {
    if (pageCursors.length <= 1 || state.loading) return
    const previousCursors = pageCursors.slice(0, -1)
    const previousCursor = previousCursors.at(-1) ?? null
    void load(previousCursor, false, state.catalogRevision).then((loaded) => { if (loaded) setPageCursors(previousCursors) })
  }, [load, pageCursors, state.catalogRevision, state.loading])

  return { ...state, page: pageCursors.length, hasPreviousPage: pageCursors.length > 1, retry, refresh, nextPage, previousPage, loadMore: nextPage, loadingMore: state.loading && pageCursors.length > 1 }
}
