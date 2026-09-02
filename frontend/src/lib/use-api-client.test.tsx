import { act, renderHook } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

import { useApiClient } from "@/lib/use-api-client"

afterEach(() => {
  vi.unstubAllGlobals()
})

describe("useApiClient", () => {
  it("adds JSON and CSRF headers to mutations", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    )
    vi.stubGlobal("fetch", fetchMock)
    const setCsrfToken = vi.fn()
    const { result } = renderHook(() => useApiClient("csrf-1", setCsrfToken))

    await act(() => result.current<{ ok: boolean }>("/api/config", { method: "PUT", body: "{}" }))

    const init = fetchMock.mock.calls[0][1] as RequestInit
    const headers = new Headers(init.headers)
    expect(headers.get("Accept")).toBe("application/json")
    expect(headers.get("Content-Type")).toBe("application/json")
    expect(headers.get("X-CSRF-Token")).toBe("csrf-1")
  })

  it("clears the local CSRF token after config authentication rejection", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: "expired" }), {
          status: 401,
          statusText: "Unauthorized",
          headers: { "Content-Type": "application/json" },
        }),
      ),
    )
    const setCsrfToken = vi.fn()
    const { result } = renderHook(() => useApiClient("expired", setCsrfToken))

    await expect(result.current("/api/config")).rejects.toMatchObject({ status: 401 })
    expect(setCsrfToken).toHaveBeenCalledWith("")
  })
})
