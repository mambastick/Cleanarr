import { test, type Page } from "@playwright/test"

export type ApiRequest = { method: string; pathname: string; query: URLSearchParams; body: string | null }
export type ApiResponse = { body: unknown; status?: number; contentType?: string }
export type ApiHandler = (request: ApiRequest) => ApiResponse | Promise<ApiResponse | undefined> | undefined

const general = {
  dry_run: true, log_level: "INFO", webhook_shared_token: "fixture-token", http_timeout_seconds: 10,
  activity_retention_days: 30, jellyfin_language: "en", ui_language: "en", sso_enabled: false,
  sso_mode: "password_only", sso_issuer_url: null, sso_client_id: null, sso_client_secret: null,
  sso_redirect_uri: null, sso_scopes: "openid profile", sso_allowed_users: [], sso_allowed_groups: [],
  sso_group_claim: "groups", sso_required_claim: null, sso_required_value: null,
  storage_warning_free_percent: 15, storage_critical_free_percent: 5,
  seeding_stop_policy: { enabled: false, mode: "all", min_ratio: null, min_seeding_minutes: null, include_categories: [], exclude_categories: [], include_tags: [], exclude_tags: [], interval_seconds: 300, max_attempts: 3 },
}

export const runtimeConfig = { general, radarr: [] as unknown[], sonarr: [] as unknown[], seerr: [] as unknown[], downloaders: [] as unknown[], jellyfin: [] as unknown[], admin_token_configured: true }
export const dashboard = {
  service: { name: "CleanArr", version: "fixture", dry_run: true, log_level: "INFO", downloader_kind: "qbittorrent", webhook_token_configured: true, activity_retention_days: 30 },
  endpoints: [], downstream: [{ name: "Jellyfin", role: "Media server", url: "", configured: false, health_status: "unconfigured" }],
  rules: [], jellyfin_template: "{}", sample_payload: {}, recent_activity: [],
  webhook_status: { attempted_at: null, outcome: "waiting", http_status: null, message: "No delivery", notification_type: null, item_type: null, item_name: null, result_status: null }, webhook_attempts: [],
}
export const fixtureMovie = { radarr_id: 101, title: "Fixture Movie", jellyfin_movie_title: "Fixture Movie", size_bytes: 1_000_000, has_file: true, jellyfin_movie_id: "fixture-movie", has_seerr_request: false }
export const fixtureSeries = { sonarr_id: 201, title: "Fixture Series", jellyfin_series_title: "Fixture Series", jellyfin_series_id: "fixture-series", has_seerr_request: false, seasons: [{ season_number: 1, episode_count: 1, episode_file_count: 1, size_bytes: 1_000_000, jellyfin_title: "Fixture Series · Season 1", jellyfin_season_id: "fixture-season", has_seerr_request: false }] }
export const safePlan = { status: "success", display_name: "Fixture Movie", actions: [{ system: "qbittorrent", action: "remove_torrent", details: { client_name: "Fixture downloader", client_kind: "qbittorrent" } }], correlation_id: "fixture-correlation" }
export const storage = { headline: "Healthy", status: "healthy", freshness: "fresh", partial: false, warning_free_percent: 15, critical_free_percent: 5, observed_at: "2026-01-01T00:00:00Z", volumes: [{ volume_id: "volume-1", service: "radarr", profile_id: "fixture-radarr", display_label: "Media", total_bytes: 1_000_000_000, free_bytes: 500_000_000, free_percent: 50, status: "healthy", freshness: "fresh", observed_at: "2026-01-01T00:00:00Z", error_code: null, possible_duplicate: false }] }
export const fixtureUsers = [{ username: "fixture-admin", role: "admin", auth_source: "local", created_at: "2026-01-01T00:00:00Z", last_seen_at: "2026-09-03T12:00:00Z" }]
export function clone<T>(value: T): T { return structuredClone(value) }
export function downloadItem(overrides: Record<string, unknown> = {}) { return { client_id: "fixture-client", client_name: "Fixture downloader", client_kind: "qbittorrent", info_hash: "fixture-hash", observed_at: "2026-01-01T00:00:00Z", display_name: "Fixture torrent", state: "seeding", freshness: "fresh", ownership: "managed", progress: 1, total_bytes: 1_000_000, downloaded_bytes: 1_000_000, uploaded_bytes: 2_000_000, ratio: 2, seeding_time_seconds: 3600, download_speed_bytes_per_second: 0, upload_speed_bytes_per_second: 0, eta_seconds: null, added_at: null, completed_at: null, activity_at: null, category: null, tags: [], tracker_summary: null, unavailable_reason: null, policy_decision: "eligible", policy_reason_code: null, policy_facts: null, latest_action: null, ...overrides } }

export class ApiController {
  readonly requests: ApiRequest[] = []
  readonly unmatchedRequests: ApiRequest[] = []
  readonly pageErrors: string[] = []
  readonly consoleMessages: string[] = []
  readonly failedApiRequests: string[] = []
  readonly abortedApiRequests: string[] = []
  readonly intentionalFailureUrls = new Set<string>()
  readonly config: typeof runtimeConfig
  readonly handlers: ApiHandler[]
  readonly auth: Record<string, unknown>
  constructor(options: { config?: typeof runtimeConfig; dashboard?: typeof dashboard; auth?: Record<string, unknown>; handlers?: ApiHandler[]; movies?: unknown[]; series?: unknown[]; downloads?: unknown[]; cleanup?: unknown[]; jobs?: unknown[]; batches?: unknown[]; users?: unknown[] } = {}) {
    this.config = clone(options.config ?? runtimeConfig)
    this.handlers = options.handlers ?? []
    this.auth = { authenticated: true, username: "fixture-admin", role: "admin", csrf_token: "fixture-csrf", requires_registration: false, sso_mode: "password_only", sso_configured: false, ui_language: this.config.general.ui_language, ...options.auth }
    const currentDashboard = clone(options.dashboard ?? dashboard); const movies = options.movies ?? []; const series = options.series ?? []; const downloads = options.downloads ?? []; const cleanup = options.cleanup ?? []; const jobs = options.jobs ?? []; const batches = options.batches ?? []; const users = options.users ?? fixtureUsers
    const libraryMovies = movies.map((value, index) => toLibraryMovie(value, index))
    const librarySeries = series.map((value, index) => toLibrarySeries(value, index))
    this.handlers.push((request) => {
      if (request.pathname === "/api/auth/status") return { body: this.auth }
      if (request.pathname === "/api/config") return { body: this.config }
      if (request.pathname === "/api/config/general" && request.method === "PUT") { Object.assign(this.config.general, JSON.parse(request.body ?? "{}")); this.auth.ui_language = this.config.general.ui_language; return { body: this.config } }
      if (request.pathname === "/api/dashboard") return { body: currentDashboard }
      if (request.pathname === "/api/storage/volumes") return { body: storage }
      if (request.pathname === "/api/storage/refresh" && request.method === "POST") return { body: storage }
      if (request.pathname === "/api/users") return { body: { users } }
      if (request.pathname.startsWith("/api/library/artwork/")) return {
        body: '<svg xmlns="http://www.w3.org/2000/svg" width="240" height="360"><rect width="240" height="360" fill="#6d5ce7"/></svg>',
        contentType: "image/svg+xml",
      }
      if (request.pathname === "/api/library/items") {
        const items = request.query.get("media_type") === "series" ? librarySeries : libraryMovies
        return { body: { items, state: "complete", failures: [], next_cursor: null, revision: "fixture-catalog", catalog_revision: "fixture-catalog" } }
      }
      if (request.pathname.startsWith("/api/library/items/")) {
        const resourceId = decodeURIComponent(request.pathname.slice("/api/library/items/".length))
        const item = [...libraryMovies, ...librarySeries].find((candidate) => candidate.resource_id === resourceId)
        if (!item) return { status: 404, body: { detail: { code: "library_item_not_found", message: "Fixture item not found" } } }
        return { body: { item: { ...item, playback_status: "unknown", playback_freshness: "unknown", play_count: null, last_played_at: null, seeding_state: "unknown", seeding_readiness: "unknown", seeding_ratio: null, seeding_time_seconds: null, safety: { status: "unknown", reason: "fixture_unknown" }, unknown_reasons: ["fixture_unknown"] }, state: "complete", failures: [], catalog_revision: "fixture-catalog" } }
      }
      if (request.pathname === "/api/library/series") return { body: { series } }
      if (request.pathname === "/api/library/movies") return { body: { movies } }
      if (request.pathname === "/api/actions/delete/jobs" && request.method === "GET") return { body: { jobs } }
      if (request.pathname === "/api/actions/delete/batches" && request.method === "GET") return { body: { batches, next_before: null } }
      if (request.pathname === "/api/downloads") return { body: { items: downloads, next_cursor: null, source_status: "complete", failures: [], failure_details: [], active_count: downloads.length } }
      if (request.pathname === "/api/downloads/cleanup-candidates") return { body: { items: cleanup, next_cursor: null, source_status: "complete", failure_codes: [], truncated: false } }
      return undefined
    })
  }
  async install(page: Page) {
    controllers.set(page, this)
    page.on("pageerror", (error) => this.pageErrors.push(error.message))
    page.on("console", (message) => {
      if (message.type() !== "error" && message.type() !== "warning") return
      const location = message.location().url
      const genericFixtureFailure = message.type() === "error"
        && /^Failed to load resource: the server responded with a status of \d+/.test(message.text())
        && this.intentionalFailureUrls.has(location)
      if (!genericFixtureFailure) this.consoleMessages.push(`${message.type()}: ${message.text()}${location ? ` (${location})` : ""}`)
    })
    page.on("requestfailed", (request) => {
      const url = new URL(request.url())
      const error = request.failure()?.errorText ?? "unknown failure"
      if (!url.pathname.startsWith("/api/")) return
      if (error === "net::ERR_ABORTED") {
        this.abortedApiRequests.push(`${request.method()} ${url.pathname}`)
        return
      }
      this.failedApiRequests.push(`${request.method()} ${url.pathname}: ${error}`)
    })
    await page.route("**/api/**", async (route) => {
      const url = new URL(route.request().url())
      const request = { method: route.request().method(), pathname: url.pathname, query: url.searchParams, body: route.request().postData() }
      this.requests.push(request)
      for (const handler of this.handlers) {
        const response = await handler(request)
        if (response) {
          const status = response.status ?? 200
          if (status >= 400) this.intentionalFailureUrls.add(url.href)
          const body = typeof response.body === "string" ? response.body : JSON.stringify(response.body)
          return route.fulfill({ status, contentType: response.contentType ?? "application/json", body })
        }
      }
      this.unmatchedRequests.push(request)
      return route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ detail: { code: "fixture_route_missing", message: `No fixture for ${request.method} ${request.pathname}` } }) })
    })
  }
  assertHealthy() {
    const failures = [
      ...this.unmatchedRequests.map((request) => `unmatched API route: ${request.method} ${request.pathname}`),
      ...this.pageErrors.map((error) => `page error: ${error}`),
      ...this.consoleMessages.map((message) => `console ${message}`),
      ...this.failedApiRequests.map((failure) => `failed API request: ${failure}`),
    ]
    if (failures.length) throw new Error(`Browser harness health check failed:\n${failures.join("\n")}`)
  }
  count(pathname: string, method?: string) { return this.requests.filter((request) => request.pathname === pathname && (!method || request.method === method)).length }
  last(pathname: string, method?: string) { return [...this.requests].reverse().find((request) => request.pathname === pathname && (!method || request.method === method)) }
}
const controllers = new WeakMap<Page, ApiController>()

test.afterEach(async ({ page }) => controllers.get(page)?.assertHealthy())

export async function boot(page: Page, options: ConstructorParameters<typeof ApiController>[0] = {}) {
  const api = new ApiController(options)
  await api.install(page)
  await page.goto("/")
  await page.getByRole("button", { name: /overview|обзор/i }).first().waitFor()
  return api
}

export function navButton(page: Page, name: string | RegExp) {
  return page.getByRole("button", { name }).filter({ visible: true }).first()
}

function toLibraryMovie(value: unknown, index: number) {
  const movie = value as typeof fixtureMovie
  const resourceId = `library-v1:radarr:fixture:${movie.radarr_id ?? index + 1}`
  return {
    resource_id: resourceId,
    media_type: "movie",
    title: movie.title,
    display_title: movie.jellyfin_movie_title ?? movie.title,
    year: 2026,
    size_bytes: movie.size_bytes,
    has_file: movie.has_file,
    added_at: "2026-01-01T00:00:00Z",
    artwork_status: "available",
    artwork_url: `/api/library/artwork/${encodeURIComponent(resourceId)}`,
    delete_target: { item_type: "Movie", radarr_movie_id: movie.radarr_id, jellyfin_item_id: movie.jellyfin_movie_id },
    catalog_revision: "fixture-catalog",
  }
}

function toLibrarySeries(value: unknown, index: number) {
  const seriesItem = value as typeof fixtureSeries
  const resourceId = `library-v1:sonarr:fixture:${seriesItem.sonarr_id ?? index + 1}`
  return {
    resource_id: resourceId,
    media_type: "series",
    title: seriesItem.title,
    display_title: seriesItem.jellyfin_series_title ?? seriesItem.title,
    year: 2026,
    size_bytes: seriesItem.seasons.reduce((sum, season) => sum + season.size_bytes, 0),
    episode_count: seriesItem.seasons.reduce((sum, season) => sum + season.episode_count, 0),
    episode_file_count: seriesItem.seasons.reduce((sum, season) => sum + season.episode_file_count, 0),
    added_at: "2026-01-01T00:00:00Z",
    artwork_status: "available",
    artwork_url: `/api/library/artwork/${encodeURIComponent(resourceId)}`,
    seasons: seriesItem.seasons.map((season) => ({
      season_number: season.season_number,
      title: `Season ${season.season_number}`,
      episode_count: season.episode_count,
      episode_file_count: season.episode_file_count,
      size_bytes: season.size_bytes,
    })),
    delete_target: { item_type: "Series", sonarr_series_id: seriesItem.sonarr_id, jellyfin_item_id: seriesItem.jellyfin_series_id },
    catalog_revision: "fixture-catalog",
  }
}
