import { useCallback, useEffect, useRef, useState } from "react"

import type { DownloadRefreshResponse, DownloadsFilters, DownloadsResponse } from "@/lib/downloads"

const REQUEST_TIMEOUT_MS = 10_000
const POLL_INTERVAL_MS = 12_000
const MAX_BACKOFF_MS = 60_000
type FetchJson = <T>(url: string, init?: RequestInit) => Promise<T>
type State = { data: DownloadsResponse | null; loading: boolean; refreshing: boolean; error: string | null; retryAt: number | null }
function query(filters: DownloadsFilters, cursor?: string | null) { const params = new URLSearchParams({ limit: "50" }); for (const [key, value] of Object.entries(filters)) if (value.trim()) params.set(key, value.trim()); if (cursor) params.set("cursor", cursor); return `/api/downloads?${params}` }
function errorCode(error: unknown) { return typeof error === "object" && error && "code" in error && typeof error.code === "string" ? error.code : "request_failed" }
function mergePage(previous: DownloadsResponse, response: DownloadsResponse): DownloadsResponse {
  const failures = [...new Set([...previous.failures, ...response.failures])]
  const details = new Map([...previous.failure_details, ...response.failure_details].map((item) => [`${item.client_id}:${item.code}`, item]))
  return {
    ...response,
    items: [...previous.items, ...response.items],
    source_status: previous.source_status === "partial" || response.source_status === "partial" ? "partial" : "complete",
    failures,
    failure_details: [...details.values()],
  }
}

export function useDownloads({ active, authenticated, filters, fetchJson, onActiveCountChange }: { active: boolean; authenticated: boolean; filters: DownloadsFilters; fetchJson: FetchJson; onActiveCountChange: (count: number) => void }) {
  const [state, setState] = useState<State>({ data: null, loading: false, refreshing: false, error: null, retryAt: null })
  const [visibilityEpoch, setVisibilityEpoch] = useState(0)
  const controllerRef = useRef<AbortController | null>(null); const timerRef = useRef<number | null>(null); const inFlightRef = useRef(false); const generationRef = useRef(0); const runRef = useRef<((cursor?: string | null) => void) | null>(null); const scheduleRef = useRef<(() => void) | null>(null); const failuresRef = useRef(0)
  // Consumers often create callbacks and filter objects inline. Keep their latest
  // values without making a request lifecycle restart on every render.
  const latest = useRef({ active, authenticated, filters, fetchJson, onActiveCountChange }); latest.current = { active, authenticated, filters, fetchJson, onActiveCountChange }
  const stop = useCallback(() => {
    generationRef.current += 1
    controllerRef.current?.abort()
    controllerRef.current = null
    if (timerRef.current != null) window.clearTimeout(timerRef.current)
    timerRef.current = null
    inFlightRef.current = false
  }, [])
  useEffect(() => {
    stop()
    failuresRef.current = 0
    setState((previous) => ({ ...previous, loading: false, refreshing: false }))
    const generation = generationRef.current
    const schedule = (delay: number) => {
      if (timerRef.current != null) window.clearTimeout(timerRef.current)
      timerRef.current = window.setTimeout(() => run(), delay)
    }
    const run = (cursor?: string | null) => {
      const current = latest.current
      if (generation !== generationRef.current || !current.active || !current.authenticated || document.hidden || inFlightRef.current) return
      inFlightRef.current = true
      const controller = new AbortController()
      controllerRef.current = controller
      let timedOut = false
      const timeout = window.setTimeout(() => { timedOut = true; controller.abort() }, REQUEST_TIMEOUT_MS)
      setState((previous) => ({ ...previous, loading: !cursor && previous.data == null, error: null, retryAt: null }))
      void current.fetchJson<DownloadsResponse>(query(current.filters, cursor), { signal: controller.signal }).then((response) => {
        if (generation !== generationRef.current || controller.signal.aborted) return
        failuresRef.current = 0; current.onActiveCountChange(response.active_count)
        setState((previous) => ({ ...previous, loading: false, error: null, retryAt: null, data: cursor && previous.data ? mergePage(previous.data, response) : response })); schedule(POLL_INTERVAL_MS)
      }).catch((error) => {
        if (generation !== generationRef.current || (controller.signal.aborted && !timedOut)) return
        failuresRef.current = Math.min(failuresRef.current + 1, 6); const delay = Math.min(POLL_INTERVAL_MS * 2 ** failuresRef.current, MAX_BACKOFF_MS)
        setState((previous) => ({ ...previous, loading: false, error: timedOut ? "timeout" : errorCode(error), retryAt: Date.now() + delay })); schedule(delay)
      }).finally(() => {
        window.clearTimeout(timeout)
        // An older completion must never release a newer request's lock.
        if (generation === generationRef.current && controllerRef.current === controller) {
          controllerRef.current = null
          inFlightRef.current = false
        }
      })
    }
    runRef.current = run
    scheduleRef.current = () => schedule(POLL_INTERVAL_MS)
    const visibility = () => { if (document.hidden) stop(); else setVisibilityEpoch((value) => value + 1) }
    document.addEventListener("visibilitychange", visibility); if (!document.hidden) run()
    return () => { document.removeEventListener("visibilitychange", visibility); if (generation === generationRef.current) { scheduleRef.current = null; stop() } }
  }, [active, authenticated, filters.client, filters.kind, filters.state, filters.ownership, filters.category, filters.tag, stop, visibilityEpoch])
  const refresh = useCallback(async () => {
    const current = latest.current; if (!current.active || !current.authenticated || document.hidden || inFlightRef.current) return
    inFlightRef.current = true; const controller = new AbortController(); controllerRef.current = controller; let timedOut = false; const timeout = window.setTimeout(() => { timedOut = true; controller.abort() }, REQUEST_TIMEOUT_MS); setState((previous) => ({ ...previous, refreshing: true, error: null }))
    try { const response = await current.fetchJson<DownloadRefreshResponse>("/api/downloads/refresh", { method: "POST", signal: controller.signal }); if (controllerRef.current === controller && !controller.signal.aborted) { current.onActiveCountChange(response.active_count); failuresRef.current = 0; setState({ data: response, loading: false, refreshing: false, error: null, retryAt: null }) } }
    catch (error) { if (!controller.signal.aborted || timedOut) setState((previous) => ({ ...previous, refreshing: false, error: timedOut ? "timeout" : errorCode(error) })) }
    finally {
      window.clearTimeout(timeout)
      if (controllerRef.current === controller) {
        controllerRef.current = null
        inFlightRef.current = false
        if (current.active && current.authenticated && !document.hidden) scheduleRef.current?.()
      }
    }
  }, [])
  return { ...state, reload: () => runRef.current?.(), loadMore: () => runRef.current?.(state.data?.next_cursor), refresh }
}
