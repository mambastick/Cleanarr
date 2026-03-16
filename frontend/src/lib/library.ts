import type { DashboardProcessingResult, ItemType } from "@/lib/dashboard"

export interface SeasonSummary {
  season_number: number
  episode_count: number
  episode_file_count: number
  size_bytes: number
  jellyfin_season_id?: string | null
}

export interface SeriesSummary {
  sonarr_id: number
  title: string
  seasons: SeasonSummary[]
  jellyfin_series_id?: string | null
}

export interface LibrarySeriesResponse {
  series: SeriesSummary[]
}

export interface MovieSummary {
  radarr_id: number
  title: string
  size_bytes: number
  has_file: boolean
  jellyfin_movie_id?: string | null
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

export interface ManualDeleteResponse extends DashboardProcessingResult {}
