import type { DashboardProcessingResult, ItemType } from "@/lib/dashboard"

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
  confirmed_plan_hash?: string | null
  idempotency_key?: string | null
  display_name?: string | null
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
