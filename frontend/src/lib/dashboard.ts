export type ItemType = "Movie" | "Series" | "Season" | "Episode"

export type ActionStatus =
  | "deleted"
  | "skipped"
  | "ignored"
  | "failed"
  | "already_absent"
  | "dry_run"

export type OverallStatus = "success" | "partial_failure" | "ignored"

export interface DashboardService {
  name: string
  version: string
  dry_run: boolean
  log_level: string
  downloader_kind: string
  webhook_token_configured: boolean
  activity_retention_days: number
}

export interface DashboardEndpoint {
  method: string
  path: string
  description: string
  auth: string
}

export type HealthStatus = "healthy" | "unreachable" | "unconfigured"

export interface DashboardDownstream {
  name: string
  role: string
  url: string
  configured: boolean
  health_status: HealthStatus
}

export interface DashboardRule {
  item_type: ItemType
  matching_order: string[]
  cleanup_steps: string[]
  guardrails: string[]
}

export interface DashboardAction {
  system: string
  action: string
  status: ActionStatus
  message: string
  reason: string | null
  details: Record<string, string | number | boolean | null>
}

export interface DashboardProcessingResult {
  item_type: ItemType
  item_id: string
  name: string
  status: OverallStatus
  actions: DashboardAction[]
}

export interface DashboardActivity {
  processed_at: string
  action_summary: Record<string, number>
  result: DashboardProcessingResult
}

export interface DashboardWebhookStatus {
  attempted_at: string | null
  outcome: string
  http_status: number | null
  message: string
  notification_type: string | null
  item_type: string | null
  item_name: string | null
  result_status: string | null
}

export interface DashboardPayload {
  service: DashboardService
  endpoints: DashboardEndpoint[]
  downstream: DashboardDownstream[]
  rules: DashboardRule[]
  jellyfin_template: string
  sample_payload: Record<string, string | number | null>
  recent_activity: DashboardActivity[]
  webhook_status: DashboardWebhookStatus
}
