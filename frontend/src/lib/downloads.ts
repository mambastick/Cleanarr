import type { SeedingStopPolicyConfig } from "@/lib/runtime-config"

export type DownloadAction = "pause" | "resume"
export type DownloadActionStatus = "queued" | "running" | "already_in_state" | "succeeded" | "failed" | "uncertain" | "reconcile_required" | "simulated"
export type TorrentState = "downloading" | "seeding" | "stopped" | "queued" | "checking" | "error" | "unknown"
export type TorrentOwnership = "managed" | "unmanaged" | "conflict" | "unknown"
export type ListingFreshness = "fresh" | "stale" | "unknown"
export type SourceStatus = "complete" | "partial"
export type CleanupMediaType = "movie" | "series"
export type CleanupTorrentState = TorrentState | "mixed" | "not_present"

export interface DownloadActionProjection {
  action_id: string
  source: string
  status: DownloadActionStatus
  code: string | null
  attempt_count: number
  max_attempts: number
  created_at: string
  updated_at: string
  result: Record<string, string | null> | null
}

export interface DownloadItem {
  client_id: string
  client_name: string
  client_kind: string
  info_hash: string
  observed_at: string
  display_name: string | null
  state: TorrentState
  freshness: ListingFreshness
  ownership: TorrentOwnership
  progress: number | null
  total_bytes: number | null
  downloaded_bytes: number | null
  uploaded_bytes: number | null
  ratio: number | null
  seeding_time_seconds: number | null
  download_speed_bytes_per_second: number | null
  upload_speed_bytes_per_second: number | null
  eta_seconds: number | null
  added_at: string | null
  completed_at: string | null
  activity_at: string | null
  category: string | null
  tags: string[] | null
  tracker_summary: string | null
  unavailable_reason: string | null
  policy_decision: string | null
  policy_reason_code: string | null
  policy_facts: Record<string, unknown> | null
  latest_action: DownloadActionProjection | null
}

export interface DownloadsResponse {
  items: DownloadItem[]
  next_cursor: string | null
  source_status: SourceStatus
  failures: string[]
  failure_details: Array<{ client_id: string; code: string }>
  active_count: number
}

export interface DownloadRefreshResponse extends DownloadsResponse { refreshed: boolean }
export interface DownloadActionRequest { client_id: string; info_hash: string; action: DownloadAction; idempotency_key: string }
export interface DownloadActionResponse { action_id: string; status: DownloadActionStatus; code: string | null }

export type PlaybackStatus = "watched" | "never_watched" | "unknown"
export type SeedReadiness = "eligible" | "blocked" | "excluded" | "disabled" | "unknown"
export type CleanupSort = "play_count" | "last_played" | "library_added" | "size" | "seed_ratio" | "seed_time" | "seed_readiness"

export interface CleanupDeletionLink {
  item_type: "Movie" | "Series"
  radarr_movie_id: number | null
  sonarr_series_id: number | null
  jellyfin_item_id: string
  display_name: string
  jellyfin_only?: boolean
}
export interface CleanupCandidate {
  jellyfin_item_id: string
  display_name: string
  media_type: CleanupMediaType
  created_at: string | null
  added_at: string | null
  size_bytes: number | null
  playback_status: PlaybackStatus
  play_count: number | null
  watched_user_count: number | null
  last_played_at: string | null
  playback_unavailable_reason: string | null
  data_source: "jellyfin_standard"
  fetched_at: string
  unavailable_reason: string | null
  seeding: {
    torrent_state: CleanupTorrentState
    readiness: SeedReadiness
    readiness_reason: string | null
    torrent_count: number | null
    ratio: number | null
    seeding_time_seconds: number | null
    unavailable_reason: string | null
  }
  deletion_link: CleanupDeletionLink | null
}
export interface CleanupCandidatesResponse {
  items: CleanupCandidate[]
  next_cursor: string | null
  source_status: SourceStatus
  failure_codes: string[]
  truncated: boolean
}

export interface DownloadsFilters {
  client: string
  kind: string
  state: string
  ownership: string
  category: string
  tag: string
}

export type StopPolicyValidationIssue =
  | "threshold_required"
  | "ratio_invalid"
  | "minutes_invalid"
  | "interval_invalid"
  | "attempts_invalid"
  | "scope_invalid"

export function normalizeStopPolicyScope(value: string) {
  const seen = new Set<string>()
  return value.split(",").map((item) => item.trim()).filter((item) => {
    const key = item.toLocaleLowerCase()
    if (!item || seen.has(key)) return false
    seen.add(key)
    return true
  }).slice(0, 100)
}

export function stopPolicyValidationIssues(policy: SeedingStopPolicyConfig): StopPolicyValidationIssue[] {
  const ratioValid = policy.min_ratio == null || (Number.isFinite(policy.min_ratio) && policy.min_ratio >= 0)
  const minutesValid = policy.min_seeding_minutes == null || (Number.isInteger(policy.min_seeding_minutes) && policy.min_seeding_minutes >= 1)
  const intervalValid = Number.isInteger(policy.interval_seconds) && policy.interval_seconds >= 30 && policy.interval_seconds <= 86_400
  const attemptsValid = Number.isInteger(policy.max_attempts) && policy.max_attempts >= 1 && policy.max_attempts <= 5
  const scopesValid = [policy.include_categories, policy.exclude_categories, policy.include_tags, policy.exclude_tags].every((items) => items.length <= 100 && items.every((item) => item.trim().length > 0) && new Set(items.map((item) => item.trim().toLocaleLowerCase())).size === items.length)
  const issues: StopPolicyValidationIssue[] = []
  if (!ratioValid) issues.push("ratio_invalid")
  if (!minutesValid) issues.push("minutes_invalid")
  if (!intervalValid) issues.push("interval_invalid")
  if (!attemptsValid) issues.push("attempts_invalid")
  if (!scopesValid) issues.push("scope_invalid")
  if (policy.enabled && policy.min_ratio == null && policy.min_seeding_minutes == null) issues.push("threshold_required")
  return issues
}

export function stopPolicyIsValid(policy: SeedingStopPolicyConfig) { return stopPolicyValidationIssues(policy).length === 0 }

export const EMPTY_DOWNLOAD_FILTERS: DownloadsFilters = { client: "", kind: "", state: "", ownership: "", category: "", tag: "" }
