import * as React from "react"

export type StorageServiceType = "radarr" | "sonarr" | string
export type StorageStatus = "healthy" | "warning" | "critical" | "unknown"
export type StorageFreshness = "fresh" | "stale" | "unknown"

export interface StorageVolume {
  volume_id: string
  service_id: string
  service_type: StorageServiceType
  display_label: string
  total_bytes?: number | null
  free_bytes?: number | null
  /** Adapters may use the concise names from the storage read contract. */
  total?: number | null
  free?: number | null
  free_percent: number | null
  status: StorageStatus
  freshness: StorageFreshness
  observed_at: string | null
  error_code: string | null
  possible_duplicate: boolean
}

export interface StorageResponse {
  headline: string | null
  status: StorageStatus
  freshness: StorageFreshness
  partial: boolean
  warning_free_percent: number
  critical_free_percent: number
  thresholds?: { warning_free_percent: number; critical_free_percent: number }
  volumes: StorageVolume[]
}

export type StorageFetchJson = <T>(url: string, init?: RequestInit) => Promise<T>

export function useStorage({ active, authenticated, fetchJson }: { active: boolean; authenticated: boolean; fetchJson: StorageFetchJson }) {
  const [data, setData] = React.useState<StorageResponse | null>(null)
  const [loading, setLoading] = React.useState(false)
  const [refreshing, setRefreshing] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)
  const controllerRef = React.useRef<AbortController | null>(null)
  const generationRef = React.useRef(0)
  const latest = React.useRef({ active, authenticated, fetchJson })
  React.useEffect(() => { latest.current = { active, authenticated, fetchJson } }, [active, authenticated, fetchJson])

  const load = React.useCallback(async (manual = false) => {
    const current = latest.current
    if (!current.active || !current.authenticated) return
    controllerRef.current?.abort()
    const generation = ++generationRef.current
    const controller = new AbortController()
    controllerRef.current = controller
    if (manual) setRefreshing(true); else setLoading(true)
    setError(null)
    try {
      const raw = manual
        ? await current.fetchJson<unknown>("/api/storage/refresh", { method: "POST", signal: controller.signal })
        : await current.fetchJson<unknown>("/api/storage/volumes", { signal: controller.signal })
      if (generation !== generationRef.current || controller.signal.aborted) return
      setData(normalizeStorageResponse(raw))
    } catch (reason) {
      if (generation !== generationRef.current || controller.signal.aborted) return
      setError(storageErrorCode(reason))
    } finally {
      if (controllerRef.current === controller) { controllerRef.current = null; setLoading(false); setRefreshing(false) }
    }
  }, [])

  React.useEffect(() => {
    if (!active || !authenticated) { controllerRef.current?.abort(); setData(null); return }
    void load()
    return () => { controllerRef.current?.abort() }
  }, [active, authenticated, load])

  return { data, loading, refreshing, error, reload: () => load(), refresh: () => load(true) }
}

export function normalizeStorageResponse(value: unknown): StorageResponse {
  const response = record(value)
  const thresholds = record(response.thresholds)
  const warning = numberValue(response.warning_free_percent) ?? numberValue(thresholds.warning_free_percent) ?? 15
  const critical = numberValue(response.critical_free_percent) ?? numberValue(thresholds.critical_free_percent) ?? 5
  const status = storageStatus(response.status ?? response.headline)
  return {
    headline: typeof response.headline === "string" ? response.headline : null,
    status,
    freshness: storageFreshness(response.freshness),
    partial: response.partial === true,
    warning_free_percent: warning,
    critical_free_percent: critical,
    thresholds: { warning_free_percent: warning, critical_free_percent: critical },
    volumes: (Array.isArray(response.volumes) ? response.volumes : []).map((value) => {
      const volume = record(value)
      return {
        volume_id: stringValue(volume.volume_id) ?? "unknown",
        service_id: stringValue(volume.service_id) ?? stringValue(volume.profile_id) ?? "unknown",
        service_type: stringValue(volume.service_type) ?? stringValue(volume.service) ?? "unknown",
        display_label: stringValue(volume.display_label) ?? "Media volume",
        total_bytes: numberValue(volume.total_bytes) ?? numberValue(volume.total),
        free_bytes: numberValue(volume.free_bytes) ?? numberValue(volume.free),
        free_percent: numberValue(volume.free_percent),
        status: storageStatus(volume.status),
        freshness: storageFreshness(volume.freshness),
        observed_at: stringValue(volume.observed_at),
        error_code: stringValue(volume.error_code),
        possible_duplicate: volume.possible_duplicate === true,
      }
    }),
  }
}

function record(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value) ? value as Record<string, unknown> : {}
}

function stringValue(value: unknown): string | null {
  return typeof value === "string" && value.length ? value : null
}

function numberValue(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null
}

function storageStatus(value: unknown): StorageStatus {
  return value === "healthy" || value === "warning" || value === "critical" ? value : "unknown"
}

function storageFreshness(value: unknown): StorageFreshness {
  return value === "fresh" || value === "stale" ? value : "unknown"
}

function storageErrorCode(error: unknown): string {
  return typeof error === "object" && error !== null && "code" in error && typeof error.code === "string" ? error.code : "storage_unavailable"
}
