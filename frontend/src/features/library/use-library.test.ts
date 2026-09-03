import { act, renderHook, waitFor } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { useLibrary, type LibraryFilters } from "./use-library"
import type { LibraryItemsResponse } from "@/lib/library"

const filters: LibraryFilters = { mediaType: "movie", query: "", sort: "added", direction: "desc", pageSize: 12, refresh: false }
const response = (overrides: Partial<LibraryItemsResponse> = {}): LibraryItemsResponse => ({ items: [], next_cursor: null, source_status: "complete", source_failures: [], catalog_revision: "rev-1", ...overrides })

describe("useLibrary", () => {
  it("debounces server search and aborts stale requests", async () => {
    vi.useFakeTimers()
    const requests: Array<{ url: string; signal?: AbortSignal | null }> = []
    const fetchJson = vi.fn((url: string, init?: RequestInit) => { requests.push({ url, signal: init?.signal }); return new Promise<LibraryItemsResponse>(() => {}) }) as unknown as Parameters<typeof useLibrary>[0]["fetchJson"]
    const { rerender } = renderHook(({ query }) => useLibrary({ active: true, authenticated: true, filters: { ...filters, query }, fetchJson }), { initialProps: { query: "d" } })
    await act(async () => { vi.advanceTimersByTime(250) })
    expect(fetchJson).toHaveBeenCalledTimes(1)
    expect(requests[0]?.url).toContain("q=d")
    expect(requests[0]?.signal?.aborted).toBe(false)
    rerender({ query: "dune" })
    expect(requests[0]?.signal?.aborted).toBe(true)
    await act(async () => { vi.advanceTimersByTime(249) })
    expect(fetchJson).toHaveBeenCalledTimes(1)
    await act(async () => { vi.advanceTimersByTime(250) })
    expect(fetchJson).toHaveBeenCalledTimes(2)
    expect(requests[1]?.url).toContain("q=dune")
    expect(requests[1]?.signal?.aborted).toBe(false)
    vi.useRealTimers()
  })

  it("does not load inactive or logged-out media types", async () => {
    vi.useFakeTimers()
    const fetchJson = vi.fn(async () => response()) as unknown as Parameters<typeof useLibrary>[0]["fetchJson"]
    const { rerender } = renderHook(
      ({ active, authenticated }) => useLibrary({ active, authenticated, filters, fetchJson }),
      { initialProps: { active: false, authenticated: true } },
    )
    await act(async () => { vi.advanceTimersByTime(300) })
    expect(fetchJson).not.toHaveBeenCalled()
    rerender({ active: true, authenticated: false })
    await act(async () => { vi.advanceTimersByTime(300) })
    expect(fetchJson).not.toHaveBeenCalled()
    rerender({ active: true, authenticated: true })
    await act(async () => { vi.advanceTimersByTime(300) })
    expect(fetchJson).toHaveBeenCalledTimes(1)
    vi.useRealTimers()
  })

  it("moves between cursor pages and surfaces catalog revision changes", async () => {
    const calls: string[] = []
    const fetchJson = vi.fn((url: string) => { calls.push(url); return Promise.resolve(response({ items: [{ resource_id: `item-${calls.length}`, media_type: "movie", display_name: `Item ${calls.length}`, title: `Item ${calls.length}`, year: null, size: null, has_file: null, counts: null, added_at: null, artwork: { status: "missing", url: null }, delete_target: null, fetched_at: null, catalog_revision: calls.length === 1 ? "rev-1" : "rev-2" }], next_cursor: calls.length === 1 ? "next" : null, catalog_revision: calls.length === 1 ? "rev-1" : "rev-2" })) }) as unknown as Parameters<typeof useLibrary>[0]["fetchJson"]
    const { result } = renderHook(() => useLibrary({ active: true, authenticated: true, filters, fetchJson, debounceMs: 0 }))
    await waitFor(() => expect(result.current.items).toHaveLength(1))
    await act(async () => { result.current.nextPage() })
    await waitFor(() => expect(result.current.error).toBe("catalog_changed"))
    expect(result.current.items).toHaveLength(1)
    expect(calls[1]).toContain("cursor=next")
  })
})
