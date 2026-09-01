import { act, renderHook } from "@testing-library/react"
import { afterEach, beforeEach, expect, it, vi } from "vitest"

import type { CleanupCandidatesResponse } from "@/lib/downloads"
import { useCleanupCandidates } from "./use-cleanup-candidates"

type Deferred<T> = { promise: Promise<T>; resolve: (value: T) => void; reject: (error: unknown) => void }
function deferred<T>(): Deferred<T> { let resolve!: (value: T) => void; let reject!: (error: unknown) => void; const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no }); return { promise, resolve, reject } }
const data = (id: string): CleanupCandidatesResponse => ({ items: [], next_cursor: null, source_status: "complete", failure_codes: [id], truncated: false })
let hidden = false
const fetchJson = vi.fn<(<T>(url: string, init?: RequestInit) => Promise<T>)>()
beforeEach(() => { vi.useFakeTimers(); hidden = false; Object.defineProperty(document, "hidden", { configurable: true, get: () => hidden }); fetchJson.mockReset() })
afterEach(() => vi.useRealTimers())

function hook(overrides: Partial<Parameters<typeof useCleanupCandidates>[0]> = {}) {
  return renderHook((props: Partial<Parameters<typeof useCleanupCandidates>[0]>) => useCleanupCandidates({ active: true, authenticated: true, visible: true, filters: { playback: "", media: "", readiness: "", sort: "library_added", direction: "desc" }, fetchJson: fetchJson as Parameters<typeof useCleanupCandidates>[0]["fetchJson"], ...props }), { initialProps: overrides })
}

it("does not fetch until a hidden mount becomes visible", async () => {
  fetchJson.mockResolvedValue(data("visible") as never)
  hidden = true; const mounted = hook(); expect(fetchJson).not.toHaveBeenCalled()
  hidden = false; await act(async () => { document.dispatchEvent(new Event("visibilitychange")); await Promise.resolve() })
  expect(fetchJson).toHaveBeenCalledTimes(1); mounted.unmount()
})

it("aborts stale bindings, resets pages, and lets the latest filter response win", async () => {
  const old = deferred<CleanupCandidatesResponse>(); const current = deferred<CleanupCandidatesResponse>()
  fetchJson.mockReturnValueOnce(old.promise as never).mockReturnValueOnce(current.promise as never)
  const mounted = hook()
  const signal = fetchJson.mock.calls[0]?.[1]?.signal as AbortSignal
  mounted.rerender({ filters: { playback: "watched", media: "", readiness: "", sort: "library_added", direction: "desc" } })
  expect(signal.aborted).toBe(true)
  await act(async () => { current.resolve(data("fresh")); await Promise.resolve() })
  await act(async () => { old.reject(new Error("late")); await Promise.resolve() })
  expect(mounted.result.current.data?.failure_codes).toEqual(["fresh"])
  expect(mounted.result.current.error).toBeNull(); mounted.unmount()
})

it("has one request, aborts on hide/unmount, and reports a timed-out request", async () => {
  const pending = deferred<CleanupCandidatesResponse>(); fetchJson.mockReturnValue(pending.promise as never)
  const mounted = hook(); await act(async () => { mounted.result.current.loadMore(); await Promise.resolve() })
  expect(fetchJson).toHaveBeenCalledTimes(1)
  await act(async () => { await vi.advanceTimersByTimeAsync(10_000); pending.reject(new Error("late")); await Promise.resolve() })
  expect(mounted.result.current.error).toBe("timeout")
  const second = deferred<CleanupCandidatesResponse>(); fetchJson.mockReturnValueOnce(second.promise as never)
  await act(async () => { mounted.result.current.retry(); await Promise.resolve() })
  hidden = true; document.dispatchEvent(new Event("visibilitychange"))
  expect((fetchJson.mock.calls.at(-1)?.[1]?.signal as AbortSignal).aborted).toBe(true)
  mounted.unmount()
})

it("preserves partial and truncated evidence while merging a later page", async () => {
  fetchJson.mockResolvedValueOnce({ ...data("first"), next_cursor: "next", source_status: "partial", truncated: true } as never)
    .mockResolvedValueOnce(data("second") as never)
  const mounted = hook()
  await act(async () => { await Promise.resolve() })
  await act(async () => { mounted.result.current.loadMore(); await Promise.resolve() })
  expect(mounted.result.current.data?.source_status).toBe("partial")
  expect(mounted.result.current.data?.truncated).toBe(true)
  expect(mounted.result.current.data?.failure_codes).toEqual(["first", "second"])
  mounted.unmount()
})
