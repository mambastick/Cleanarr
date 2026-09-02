import { useCallback, type Dispatch, type SetStateAction } from "react"

import { apiErrorFromResponse } from "@/lib/api-client"

export type FetchJson = <T>(url: string, init?: RequestInit) => Promise<T>

/** Keep authenticated JSON transport policy out of the application composer. */
export function useApiClient(
  csrfToken: string,
  setCsrfToken: Dispatch<SetStateAction<string>>,
): FetchJson {
  return useCallback(
    async <T,>(url: string, init?: RequestInit): Promise<T> => {
      const headers = new Headers(init?.headers)
      headers.set("Accept", "application/json")
      if (init?.body && !headers.has("Content-Type")) {
        headers.set("Content-Type", "application/json")
      }
      const method = (init?.method ?? "GET").toUpperCase()
      if (csrfToken && !["GET", "HEAD", "OPTIONS"].includes(method)) {
        headers.set("X-CSRF-Token", csrfToken)
      }

      const response = await fetch(url, { ...init, headers })
      if (!response.ok) {
        if (
          (response.status === 401 || response.status === 403)
          && url.startsWith("/api/config")
        ) {
          setCsrfToken("")
        }
        let body: unknown = null
        try {
          body = await response.json()
        } catch {
          // A non-JSON proxy response still receives a stable API error shape.
        }
        throw apiErrorFromResponse(response.status, response.statusText, body)
      }
      if (response.status === 204) return undefined as T
      return (await response.json()) as T
    },
    [csrfToken, setCsrfToken],
  )
}
