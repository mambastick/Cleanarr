import { act, renderHook } from "@testing-library/react"
import { afterEach, beforeEach, expect, it, vi } from "vitest"

import { EMPTY_DOWNLOAD_FILTERS, type DownloadRefreshResponse, type DownloadsResponse } from "@/lib/downloads"
import { useDownloads } from "./use-downloads"

type Deferred<T> = { promise: Promise<T>; resolve: (value: T) => void; reject: (error: unknown) => void }
function deferred<T>(): Deferred<T> { let resolve!: (value: T) => void; let reject!: (error: unknown) => void; const promise = new Promise<T>((nextResolve, nextReject) => { resolve = nextResolve; reject = nextReject }); return { promise, resolve, reject } }
const response = (active_count = 1): DownloadsResponse => ({ items: [], next_cursor: null, source_status: "complete", failures: [], failure_details: [], active_count })
let hidden = false
const fetchJson = vi.fn<(<T>(url: string, init?: RequestInit) => Promise<T>)>()
const onActiveCountChange = vi.fn()

beforeEach(() => {
  vi.useFakeTimers()
  hidden = false
  Object.defineProperty(document, "hidden", { configurable: true, get: () => hidden })
  fetchJson.mockReset()
  onActiveCountChange.mockReset()
  fetchJson.mockResolvedValue(response() as never)
})
afterEach(() => vi.useRealTimers())

function hook(overrides: Partial<Parameters<typeof useDownloads>[0]> = {}) {
  return renderHook((props: Partial<Parameters<typeof useDownloads>[0]>) => useDownloads({ active: true, authenticated: true, filters: EMPTY_DOWNLOAD_FILTERS, fetchJson: fetchJson as Parameters<typeof useDownloads>[0]["fetchJson"], onActiveCountChange, ...props }), { initialProps: overrides })
}

it("does not GET while inactive, unauthenticated, or hidden and starts when a hidden mount becomes visible", async () => {
  hook({ active: false }); expect(fetchJson).not.toHaveBeenCalled()
  hook({ authenticated: false }); expect(fetchJson).not.toHaveBeenCalled()
  hidden = true
  const mounted = hook(); expect(fetchJson).not.toHaveBeenCalled()
  hidden = false
  await act(async () => { document.dispatchEvent(new Event("visibilitychange")); await Promise.resolve() })
  expect(fetchJson).toHaveBeenCalledTimes(1)
  mounted.unmount()
})

it("keeps a single GET in flight and polls repeatedly after successful responses", async () => {
  fetchJson.mockResolvedValue(response() as never)
  const mounted = hook()
  await act(async () => { await Promise.resolve() })
  await act(async () => { await vi.advanceTimersByTimeAsync(12_000) })
  await act(async () => { await vi.advanceTimersByTimeAsync(12_000) })
  expect(fetchJson).toHaveBeenCalledTimes(3)
  expect(fetchJson.mock.calls.every(([url, init]) => String(url).startsWith("/api/downloads?") && init?.method == null)).toBe(true)
  mounted.unmount()
})

it("does not overlap requests and silently aborts lifecycle requests", async () => {
  const first = deferred<DownloadsResponse>()
  fetchJson.mockReturnValueOnce(first.promise as never)
  const mounted = hook()
  await act(async () => { await vi.advanceTimersByTimeAsync(24_000) })
  expect(fetchJson).toHaveBeenCalledTimes(1)
  const signal = fetchJson.mock.calls[0]?.[1]?.signal as AbortSignal
  await act(async () => { hidden = true; document.dispatchEvent(new Event("visibilitychange")); await Promise.resolve() })
  expect(signal.aborted).toBe(true)
  await act(async () => { first.reject(new Error("aborted")); await Promise.resolve() })
  expect(mounted.result.current.error).toBeNull()
  mounted.unmount()
})

it("times out, backs off with a cap, and resets the failure backoff after success", async () => {
  const first = deferred<DownloadsResponse>()
  fetchJson.mockReturnValueOnce(first.promise as never).mockRejectedValueOnce(new Error("offline") as never).mockResolvedValueOnce(response() as never)
  const mounted = hook()
  await act(async () => { await vi.advanceTimersByTimeAsync(10_000) })
  expect((fetchJson.mock.calls[0]?.[1]?.signal as AbortSignal).aborted).toBe(true)
  await act(async () => { first.reject(new Error("late")); await Promise.resolve() })
  expect(mounted.result.current.error).toBe("timeout")
  await act(async () => { await vi.advanceTimersByTimeAsync(24_000) })
  expect(fetchJson).toHaveBeenCalledTimes(2)
  await act(async () => { await vi.advanceTimersByTimeAsync(48_000) })
  expect(fetchJson).toHaveBeenCalledTimes(3)
  expect(mounted.result.current.error).toBeNull()
  mounted.unmount()
})

it("aborts stale filtered responses and lets only the latest binding settle state", async () => {
  const old = deferred<DownloadsResponse>(); const fresh = deferred<DownloadsResponse>()
  fetchJson.mockReturnValueOnce(old.promise as never).mockReturnValueOnce(fresh.promise as never)
  const mounted = hook()
  const oldSignal = fetchJson.mock.calls[0]?.[1]?.signal as AbortSignal
  mounted.rerender({ filters: { ...EMPTY_DOWNLOAD_FILTERS, state: "seeding" } })
  expect(oldSignal.aborted).toBe(true)
  await act(async () => { fresh.resolve(response(7)); await Promise.resolve() })
  await act(async () => { old.reject(new Error("late")); await Promise.resolve() })
  expect(mounted.result.current.data?.active_count).toBe(7)
  expect(mounted.result.current.error).toBeNull()
  mounted.unmount()
})

it("keeps polling after a refresh overlaps the scheduled poll time", async () => {
  const refresh = deferred<DownloadRefreshResponse>()
  fetchJson.mockResolvedValueOnce(response() as never).mockReturnValueOnce(refresh.promise as never).mockResolvedValueOnce(response(2) as never)
  const mounted = hook()
  await act(async () => { await Promise.resolve() })
  let refreshPromise!: Promise<void>
  act(() => { refreshPromise = mounted.result.current.refresh() })
  await act(async () => { await vi.advanceTimersByTimeAsync(12_000) })
  expect(fetchJson).toHaveBeenCalledTimes(2)
  await act(async () => { refresh.resolve({ ...response(), refreshed: true }); await refreshPromise })
  await act(async () => { await vi.advanceTimersByTimeAsync(12_000) })
  expect(fetchJson).toHaveBeenCalledTimes(3)
  mounted.unmount()
})

it("preserves partial evidence while merging a later page", async () => {
  fetchJson.mockResolvedValueOnce({ ...response(), next_cursor: "next", source_status: "partial", failures: ["refresh_failed"], failure_details: [{ client_id: "a", code: "refresh_failed" }] } as never)
    .mockResolvedValueOnce(response(3) as never)
  const mounted = hook()
  await act(async () => { await Promise.resolve() })
  await act(async () => { mounted.result.current.loadMore(); await Promise.resolve() })
  expect(mounted.result.current.data?.source_status).toBe("partial")
  expect(mounted.result.current.data?.failures).toEqual(["refresh_failed"])
  expect(mounted.result.current.data?.failure_details).toEqual([{ client_id: "a", code: "refresh_failed" }])
  mounted.unmount()
})
