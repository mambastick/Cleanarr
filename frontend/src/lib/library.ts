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
}

export type ManualDeleteResponse = DashboardProcessingResult

export type ManualDeleteJobStatus = "queued" | "running" | "completed" | "failed"

export type ManualDeleteJobPhase =
  | "queued"
  | "locating"
  | "cleaning"
  | "recording"
  | "jellyfin"
  | "completed"
  | "failed"

export interface ManualDeleteJob {
  id: string
  item_type: ItemType
  item_name: string | null
  status: ManualDeleteJobStatus
  phase: ManualDeleteJobPhase
  progress_percent: number
  message: string
  created_at: string
  started_at: string | null
  completed_at: string | null
  result: ManualDeleteResponse | null
  error: string | null
}

export interface ManualDeleteJobListResponse {
  jobs: ManualDeleteJob[]
}
