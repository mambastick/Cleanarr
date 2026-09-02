import { renderHook, waitFor } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { validateStorageThresholds } from "@/features/settings/storage-thresholds"
import { useStorage, type StorageResponse } from "./storage"

describe("storage thresholds", () => {
  it("requires critical to be strictly below warning within 0..100", () => {
    expect(validateStorageThresholds(15, 5)).toBe(true)
    expect(validateStorageThresholds(5, 5)).toBe(false)
    expect(validateStorageThresholds(101, 5)).toBe(false)
    expect(validateStorageThresholds(15, -1)).toBe(false)
  })
})

it("loads storage and uses the refresh endpoint only for explicit refresh", async () => {
  const data: StorageResponse = { headline: "Healthy", status: "healthy", freshness: "fresh", partial: false, warning_free_percent: 15, critical_free_percent: 5, volumes: [] }
  const fetchJson = vi.fn(async () => data) as unknown as Parameters<typeof useStorage>[0]["fetchJson"]
  const { result } = renderHook(() => useStorage({ active: true, authenticated: true, fetchJson }))
  await waitFor(() => expect(result.current.data).toEqual(expect.objectContaining(data)))
  expect(fetchJson).toHaveBeenCalledWith("/api/storage/volumes", expect.anything())
  await result.current.refresh()
  expect(fetchJson).toHaveBeenCalledWith("/api/storage/refresh", expect.objectContaining({ method: "POST" }))
})
