import { useCallback, useEffect, useRef, useState } from "react"
import type { CleanupCandidatesResponse, CleanupSort } from "@/lib/downloads"

type FetchJson = <T>(url: string, init?: RequestInit) => Promise<T>
type Filters = { playback: string; media: string; readiness: string; sort: CleanupSort; direction: "asc" | "desc" }
const TIMEOUT = 10_000
function mergePage(previous: CleanupCandidatesResponse, response: CleanupCandidatesResponse): CleanupCandidatesResponse {
  return {
    ...response,
    items: [...previous.items, ...response.items],
    source_status: previous.source_status === "partial" || response.source_status === "partial" ? "partial" : "complete",
    failure_codes: [...new Set([...previous.failure_codes, ...response.failure_codes])],
    truncated: previous.truncated || response.truncated,
  }
}
export function useCleanupCandidates({ active, authenticated, visible, filters, fetchJson }: { active: boolean; authenticated: boolean; visible: boolean; filters: Filters; fetchJson: FetchJson }) {
  const [data, setData] = useState<CleanupCandidatesResponse | null>(null); const [loading, setLoading] = useState(false); const [error, setError] = useState<string | null>(null); const [visibilityEpoch, setVisibilityEpoch] = useState(0)
  const generation = useRef(0); const controller = useRef<AbortController | null>(null); const running = useRef(false); const rerun = useRef<((cursor?: string | null) => void) | null>(null)
  // Avoid a refetch loop when a panel passes an inline filters object or fetcher.
  const latest = useRef({ active, authenticated, visible, filters, fetchJson })
  useEffect(() => { latest.current = { active, authenticated, visible, filters, fetchJson } })
  const abort = useCallback(() => { generation.current += 1; controller.current?.abort(); controller.current = null; running.current = false }, [])
  useEffect(() => {
    abort()
    const currentGeneration = generation.current
    setData(null)
    setError(null)
    setLoading(false)
    const load = (cursor?: string | null) => {
      const current = latest.current
      if (!current.active || !current.authenticated || !current.visible || document.hidden || running.current) return
      running.current = true; const request = new AbortController(); controller.current = request; let timeouted = false; const timeout = window.setTimeout(() => { timeouted = true; request.abort() }, TIMEOUT)
      const params = new URLSearchParams({ limit: "50", sort: current.filters.sort, direction: current.filters.direction }); if (cursor) params.set("cursor", cursor); if (current.filters.playback) params.set("playback_status", current.filters.playback); if (current.filters.media) params.set("media_type", current.filters.media); if (current.filters.readiness) params.set("seed_readiness", current.filters.readiness)
      setLoading(true); setError(null)
      void current.fetchJson<CleanupCandidatesResponse>(`/api/downloads/cleanup-candidates?${params}`, { signal: request.signal }).then((response) => { if (generation.current !== currentGeneration || controller.current !== request || request.signal.aborted) return; setData((previous) => cursor && previous ? mergePage(previous, response) : response) }).catch(() => { if (generation.current !== currentGeneration || controller.current !== request || (request.signal.aborted && !timeouted)) return; setError(timeouted ? "timeout" : "request_failed") }).finally(() => { window.clearTimeout(timeout); if (generation.current === currentGeneration && controller.current === request) { controller.current = null; running.current = false; setLoading(false) } })
    }
    rerun.current = load
    const visibilityChange = () => { if (document.hidden) abort(); else setVisibilityEpoch((value) => value + 1) }
    document.addEventListener("visibilitychange", visibilityChange); if (!document.hidden) load()
    return () => { document.removeEventListener("visibilitychange", visibilityChange); if (generation.current === currentGeneration) abort() }
  }, [active, authenticated, visible, filters.playback, filters.media, filters.readiness, filters.sort, filters.direction, abort, visibilityEpoch])
  return { data, loading, error, retry: () => rerun.current?.(), loadMore: () => rerun.current?.(data?.next_cursor) }
}
