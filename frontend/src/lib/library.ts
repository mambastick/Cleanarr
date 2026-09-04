import type { DashboardProcessingResult, ItemType } from "@/lib/dashboard"

/** The resource contract used by the post-1.0 Library surface. */
export type LibraryMediaType = "movie" | "series"
export type LibrarySort = "added" | "title" | "size"
export type LibraryDirection = "asc" | "desc"
export type LibrarySourceStatus = "complete" | "partial" | "unavailable"
export type LibraryArtworkStatus = "available" | "missing" | "unknown"

export interface LibraryArtwork {
  status: LibraryArtworkStatus
  url: string | null
}

export interface LibraryItem {
  resource_id: string
  media_type: LibraryMediaType
  display_name: string
  title: string
  year: number | null
  size: number | null
  has_file: boolean | null
  counts: { seasons?: number | null; episodes?: number | null; files?: number | null } | null
  added_at: string | null
  artwork: LibraryArtwork
  delete_target: Record<string, unknown> | null
  fetched_at: string | null
  catalog_revision: string
}

export interface LibraryItemDetail extends LibraryItem {
  playback?: {
    watched: "watched" | "never_watched" | "unknown" | null
    play_count: number | null
    last_played_at: string | null
    freshness: "fresh" | "stale" | "unknown" | null
  }
  library_dates?: { added_at: string | null; updated_at: string | null } | null
  seeding?: {
    state: "downloading" | "seeding" | "stopped" | "unknown" | null
    readiness: "ready" | "not_ready" | "unknown" | null
    ratio: number | null
    seeded_seconds: number | null
    reason: string | null
  }
  seasons?: Array<{
    season_number: number
    title: string | null
    episode_count: number | null
    episode_file_count: number | null
    size: number | null
  }> | null
  safety?: { status: "safe" | "blocked" | "unknown"; reason: string | null } | null
  // Flat aliases are accepted for adapters that serialize the detail contract
  // without nested playback/seeding objects.
  playback_status?: "watched" | "never_watched" | "unknown" | null
  playback_freshness?: "fresh" | "stale" | "unknown" | null
  play_count?: number | null
  last_played_at?: string | null
  seeding_state?: "downloading" | "seeding" | "stopped" | "unknown" | null
  seeding_readiness?: "ready" | "not_ready" | "unknown" | null
  seeding_ratio?: number | null
  seeding_time_seconds?: number | null
  seeding_reason?: string | null
  unknown_reasons?: string[] | null
  series_counts?: { seasons?: number | null; episodes?: number | null } | null
  torrent_client?: string | null
  torrent_name?: string | null
}

export interface LibraryItemsResponse {
  items: LibraryItem[]
  next_cursor: string | null
  source_status: LibrarySourceStatus
  source_failures: Array<{ source: string; code: string; message?: string | null }>
  catalog_revision: string
}

export interface LibraryItemsQuery {
  media_type: LibraryMediaType
  q?: string
  sort?: LibrarySort
  direction?: LibraryDirection
  limit?: number
  cursor?: string | null
  refresh?: boolean
}

export type LibraryFetchJson = <T>(url: string, init?: RequestInit) => Promise<T>

export function buildLibraryItemsUrl(query: LibraryItemsQuery): string {
  const params = new URLSearchParams({
    media_type: query.media_type,
    q: query.q?.trim() ?? "",
    sort: query.sort ?? "added",
    direction: query.direction ?? "desc",
    limit: String(Math.min(50, Math.max(1, query.limit ?? 50))),
    refresh: query.refresh ? "true" : "false",
  })
  if (query.cursor) params.set("cursor", query.cursor)
  return `/api/library/items?${params.toString()}`
}

export function fetchLibraryItems(fetchJson: LibraryFetchJson, query: LibraryItemsQuery, signal?: AbortSignal) {
  return fetchJson<unknown>(buildLibraryItemsUrl(query), { signal }).then(normalizeLibraryItemsResponse)
}

export function fetchLibraryItem(fetchJson: LibraryFetchJson, resourceId: string, signal?: AbortSignal) {
  return fetchJson<unknown>(`/api/library/items/${encodeURIComponent(resourceId)}`, { signal }).then(normalizeLibraryItemDetail)
}

function normalizeLibraryItemsResponse(value: unknown): LibraryItemsResponse {
  if (!isRecord(value)) throw new Error("Invalid library list response")
  const response = record(value)
  const revision = stringValue(response.catalog_revision) ?? stringValue(response.revision)
  const status = response.source_status ?? response.state
  if (!revision || !Array.isArray(response.items) || !isSourceStatus(status)) {
    throw new Error("Invalid library list response")
  }
  const rawItems = response.items
  const rawFailures = Array.isArray(response.source_failures)
    ? response.source_failures
    : Array.isArray(response.failures) ? response.failures : []
  return {
    items: rawItems.map((item) => normalizeLibraryItem(item, revision)).filter((item): item is LibraryItem => item != null),
    next_cursor: stringValue(response.next_cursor),
    source_status: sourceStatus(status),
    source_failures: rawFailures.map((failure) => {
      const entry = record(failure)
      return {
        source: stringValue(entry.source) ?? "library",
        code: stringValue(entry.code) ?? "library_unavailable",
        message: stringValue(entry.message),
      }
    }),
    catalog_revision: revision,
  }
}

function normalizeLibraryItemDetail(value: unknown): LibraryItemDetail {
  const response = record(value)
  const rawItem = "item" in response ? record(response.item) : response
  const revision = stringValue(response.catalog_revision) ?? stringValue(response.revision) ?? stringValue(rawItem.catalog_revision) ?? "unknown"
  const item = normalizeLibraryItem(rawItem, revision)
  if (!item) throw new Error("Invalid library item response")
  const playback = recordOrNull(rawItem.playback)
  const seeding = recordOrNull(rawItem.seeding)
  const safety = recordOrNull(rawItem.safety)
  const rawFailures = Array.isArray(response.failures) ? response.failures : []
  const providedUnknownReasons = Array.isArray(rawItem.unknown_reasons)
    ? rawItem.unknown_reasons.map(stringValue).filter((reason): reason is string => Boolean(reason))
    : []
  const unknownReasons = [
    ...providedUnknownReasons,
    stringValue(rawItem.playback_reason),
    stringValue(rawItem.seeding_reason),
    stringValue(response.error_code),
    ...rawFailures.map((failure) => stringValue(record(failure).code)),
  ].filter((reason): reason is string => Boolean(reason))
  return {
    ...item,
    playback: playback ? {
      watched: playbackState(playback.watched),
      play_count: nullableNumber(playback.play_count),
      last_played_at: stringValue(playback.last_played_at),
      freshness: freshness(playback.freshness),
    } : {
      watched: playbackState(rawItem.playback_status),
      play_count: nullableNumber(rawItem.play_count),
      last_played_at: stringValue(rawItem.last_played_at),
      freshness: freshness(rawItem.playback_freshness),
    },
    library_dates: recordOrNull(rawItem.library_dates) ? {
      added_at: stringValue(record(rawItem.library_dates).added_at),
      updated_at: stringValue(record(rawItem.library_dates).updated_at),
    } : { added_at: item.added_at, updated_at: null },
    seeding: seeding ? {
      state: seedingState(seeding.state),
      readiness: seedingReadiness(seeding.readiness),
      ratio: nullableNumber(seeding.ratio),
      seeded_seconds: nullableNumber(seeding.seeded_seconds),
      reason: stringValue(seeding.reason),
    } : {
      state: seedingState(rawItem.seeding_state),
      readiness: seedingReadiness(rawItem.seeding_readiness),
      ratio: nullableNumber(rawItem.seeding_ratio),
      seeded_seconds: nullableNumber(rawItem.seeding_time_seconds),
      reason: stringValue(rawItem.seeding_reason),
    },
    seasons: normalizeSeasons(response, rawItem),
    safety: safety ? {
      status: safetyStatus(safety.status),
      reason: stringValue(safety.reason),
    } : {
      status: "unknown",
      reason: stringValue(response.error_code) ?? "safety_evidence_unavailable",
    },
    unknown_reasons: [...new Set(unknownReasons)],
    series_counts: normalizeSeriesCounts(rawItem.series_counts),
    torrent_client: stringValue(rawItem.torrent_client),
    torrent_name: stringValue(rawItem.torrent_name),
  }
}

function normalizeLibraryItem(value: unknown, revision: string): LibraryItem | null {
  const item = record(value)
  const resourceId = stringValue(item.resource_id)
  const mediaType = item.media_type === "series" ? "series" : item.media_type === "movie" ? "movie" : null
  const title = stringValue(item.title)
  if (!resourceId || !mediaType || !title) return null
  const artworkRecord = recordOrNull(item.artwork)
  const artworkState = artworkRecord?.status ?? item.artwork_status
  const counts = recordOrNull(item.counts)
  return {
    resource_id: resourceId,
    media_type: mediaType,
    display_name: stringValue(item.display_name) ?? stringValue(item.display_title) ?? title,
    title,
    year: nullableNumber(item.year),
    size: nullableNumber(item.size) ?? nullableNumber(item.size_bytes),
    has_file: typeof item.has_file === "boolean" ? item.has_file : null,
    counts: counts ? {
      seasons: nullableNumber(counts.seasons),
      episodes: nullableNumber(counts.episodes),
      files: nullableNumber(counts.files),
    } : {
      seasons: null,
      episodes: nullableNumber(item.episode_count),
      files: nullableNumber(item.file_count) ?? nullableNumber(item.episode_file_count),
    },
    added_at: stringValue(item.added_at),
    artwork: {
      status: artworkState === "available" ? "available" : artworkState === "unknown" ? "unknown" : "missing",
      url: artworkRecord ? stringValue(artworkRecord.url) : stringValue(item.artwork_url),
    },
    delete_target: recordOrNull(item.delete_target),
    fetched_at: stringValue(item.fetched_at),
    catalog_revision: stringValue(item.catalog_revision) ?? revision,
  }
}

function normalizeSeasons(response: Record<string, unknown>, rawItem: Record<string, unknown>): LibraryItemDetail["seasons"] {
  if (Array.isArray(rawItem.seasons)) {
    return rawItem.seasons.map((value) => {
      const season = record(value)
      return {
        season_number: nullableNumber(season.season_number) ?? 0,
        title: stringValue(season.title),
        episode_count: nullableNumber(season.episode_count),
        episode_file_count: nullableNumber(season.episode_file_count),
        size: nullableNumber(season.size) ?? nullableNumber(season.size_bytes),
      }
    })
  }
  if (!Array.isArray(response.episodes) && !Array.isArray(response.files)) return null
  const grouped = new Map<number, { episodes: number; files: number; size: number }>()
  for (const value of Array.isArray(response.episodes) ? response.episodes : []) {
    const episode = record(value)
    const number = nullableNumber(episode.season_number)
    if (number == null) continue
    const current = grouped.get(number) ?? { episodes: 0, files: 0, size: 0 }
    current.episodes += 1
    if (episode.has_file === true) current.files += 1
    grouped.set(number, current)
  }
  for (const value of Array.isArray(response.files) ? response.files : []) {
    const file = record(value)
    const number = nullableNumber(file.season_number)
    if (number == null) continue
    const current = grouped.get(number) ?? { episodes: 0, files: 0, size: 0 }
    current.size += nullableNumber(file.size_bytes) ?? 0
    grouped.set(number, current)
  }
  return [...grouped.entries()].sort(([left], [right]) => left - right).map(([seasonNumber, summary]) => ({
    season_number: seasonNumber,
    title: null,
    episode_count: summary.episodes,
    episode_file_count: summary.files,
    size: summary.size,
  }))
}

function record(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value) ? value as Record<string, unknown> : {}
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
}

function recordOrNull(value: unknown): Record<string, unknown> | null {
  const result = record(value)
  return Object.keys(result).length ? result : null
}

function stringValue(value: unknown): string | null {
  return typeof value === "string" && value.length ? value : null
}

function nullableNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null
}

function sourceStatus(value: unknown): LibrarySourceStatus {
  return value === "partial" || value === "unavailable" ? value : "complete"
}

function isSourceStatus(value: unknown): value is LibrarySourceStatus {
  return value === "complete" || value === "partial" || value === "unavailable"
}

function normalizeSeriesCounts(value: unknown): LibraryItemDetail["series_counts"] {
  const counts = recordOrNull(value)
  if (!counts) return null
  return {
    seasons: nullableNumber(counts.seasons),
    episodes: nullableNumber(counts.episodes),
  }
}

function playbackState(value: unknown): "watched" | "never_watched" | "unknown" {
  return value === "watched" || value === "never_watched" ? value : "unknown"
}

function freshness(value: unknown): "fresh" | "stale" | "unknown" {
  return value === "fresh" || value === "stale" ? value : "unknown"
}

function seedingState(value: unknown): "downloading" | "seeding" | "stopped" | "unknown" {
  return value === "downloading" || value === "seeding" || value === "stopped" ? value : "unknown"
}

function seedingReadiness(value: unknown): "ready" | "not_ready" | "unknown" {
  return value === "ready" || value === "not_ready" ? value : "unknown"
}

function safetyStatus(value: unknown): "safe" | "blocked" | "unknown" {
  return value === "safe" || value === "blocked" ? value : "unknown"
}

/** GET artwork with browser session cookies; artwork URLs never carry credentials. */
export async function fetchLibraryArtwork(resourceId: string, signal?: AbortSignal): Promise<Blob> {
  const response = await fetch(`/api/library/artwork/${encodeURIComponent(resourceId)}`, {
    credentials: "same-origin",
    headers: { Accept: "image/*" },
    signal,
  })
  if (!response.ok) throw new Error(`Artwork request failed (${response.status})`)
  return response.blob()
}

export interface SeasonSummary {
  season_number: number
  episode_count: number
  episode_file_count: number
  size_bytes: number
  jellyfin_title?: string | null
  jellyfin_season_id?: string | null
  has_seerr_request: boolean
}

export interface SeriesSummary {
  sonarr_id: number
  title: string
  jellyfin_series_title?: string | null
  seasons: SeasonSummary[]
  jellyfin_series_id?: string | null
  has_seerr_request: boolean
}

export interface LibrarySeriesResponse {
  series: SeriesSummary[]
}

export interface MovieSummary {
  radarr_id: number
  title: string
  jellyfin_movie_title?: string | null
  size_bytes: number
  has_file: boolean
  jellyfin_movie_id?: string | null
  has_seerr_request: boolean
}

export interface LibraryMoviesResponse {
  movies: MovieSummary[]
}

export interface ManualDeleteRequest {
  item_type: ItemType
  sonarr_series_id?: number | null
  radarr_movie_id?: number | null
  season_number?: number | null
  jellyfin_item_id?: string | null
  jellyfin_only?: boolean
  confirmed_plan_hash?: string | null
  idempotency_key?: string | null
  display_name?: string | null
  library_resource_id?: string | null
}

export interface ManualDeleteResponse extends DashboardProcessingResult {
  correlation_id: string | null
  display_name: string
}

export interface ManualDeleteJobRequest extends ManualDeleteRequest {
  confirmed_plan_hash: string
  idempotency_key: string
  display_name: string
}

export type ManualDeleteJobStatus = "queued" | "running" | "retry_wait" | "completed" | "failed"

export type ManualDeleteJobPhase =
  | "queued"
  | "planning"
  | "locating"
  | "cleaning"
  | "recording"
  | "jellyfin"
  | "retrying"
  | "completed"
  | "failed"

export interface ManualDeletePreviewResponse {
  generated_at: string
  plan_hash: string
  plan: ManualDeleteResponse
}

export interface ManualDeleteJob {
  id: string
  item_type: ItemType
  item_name: string | null
  display_name: string
  status: ManualDeleteJobStatus
  phase: ManualDeleteJobPhase
  progress_percent: number
  message: string
  created_at: string
  started_at: string | null
  completed_at: string | null
  next_retry_at: string | null
  attempt_count: number
  max_attempts: number
  preflight: ManualDeleteResponse
  result: ManualDeleteResponse | null
  error: string | null
}

export interface ManualDeleteJobListResponse {
  jobs: ManualDeleteJob[]
}

export type BatchChildPreviewStatus = "ready" | "blocked"
export type BatchChildStatus = "queued" | "running" | "completed" | "blocked" | "failed" | "cancelled"
export type ManualDeleteBatchStatus = "queued" | "running" | "completed" | "partial" | "failed" | "cancelled"

export interface ManualDeleteBatchChildPreview {
  mutation_identity: string
  display_name: string
  status: BatchChildPreviewStatus
  plan_hash: string | null
  plan: ManualDeleteResponse | null
  blocked_code: string | null
  blocked_message: string | null
}

export interface ManualDeleteBatchPreviewResponse {
  generated_at: string
  batch_hash: string
  children: ManualDeleteBatchChildPreview[]
  ready_count: number
  blocked_count: number
}

export interface ManualDeleteBatchChild {
  id: string
  mutation_identity: string
  display_name: string
  status: BatchChildStatus
  message: string
  blocked_code: string | null
  error_code: string | null
  error_message: string | null
  preflight: ManualDeleteResponse | null
  result: ManualDeleteResponse | null
  started_at: string | null
  completed_at: string | null
}

export interface ManualDeleteBatch {
  id: string
  status: ManualDeleteBatchStatus
  message: string
  created_at: string
  started_at: string | null
  completed_at: string | null
  error_code: string | null
  error_message: string | null
  total_count: number
  queued_count: number
  running_count: number
  completed_count: number
  blocked_count: number
  failed_count: number
  cancelled_count: number
  children: ManualDeleteBatchChild[]
}

export interface ManualDeleteBatchListResponse {
  batches: ManualDeleteBatch[]
  next_before: string | null
}

export interface ManualDeleteBatchRequest {
  children: ManualDeleteRequest[]
  idempotency_key: string
  confirmed_batch_hash: string
  confirmed_item_count: number
}
