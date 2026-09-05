import { afterEach, beforeEach, expect, it, vi } from "vitest"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"

import { ThemeProvider } from "@/components/theme-provider"
import { TooltipProvider } from "@/components/ui/tooltip"
import CleanArrApp from "./cleanarr-app"

type Deferred<T> = { promise: Promise<T>; resolve: (value: T) => void }

function deferred<T>(): Deferred<T> {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((next) => { resolve = next })
  return { promise, resolve }
}

function json(body: unknown): Response {
  return new Response(JSON.stringify(body), { headers: { "Content-Type": "application/json" } })
}

const general = {
  dry_run: false, log_level: "INFO", webhook_shared_token: null, http_timeout_seconds: 10,
  activity_retention_days: 30, jellyfin_language: "en", ui_language: "en", sso_enabled: false,
  sso_mode: "password_only", sso_issuer_url: null, sso_client_id: null, sso_client_secret: null,
  sso_redirect_uri: null, sso_scopes: "openid profile", sso_allowed_users: [], sso_allowed_groups: [],
  sso_group_claim: "groups", sso_required_claim: null, sso_required_value: null,
  seeding_stop_policy: { enabled: false, mode: "all", min_ratio: null, min_seeding_minutes: null, include_categories: [], exclude_categories: [], include_tags: [], exclude_tags: [], interval_seconds: 300, max_attempts: 3 },
}

afterEach(() => vi.unstubAllGlobals())

beforeEach(() => {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: vi.fn().mockImplementation((query: string) => ({ matches: false, media: query, onchange: null, addEventListener: vi.fn(), removeEventListener: vi.fn() })),
  })
})

it("does not claim a deletion mode or enable deletion planning while authoritative responses are pending", async () => {
  const user = userEvent.setup()
  const config = deferred<Response>()
  const dashboard = deferred<Response>()
  const fetch = vi.fn((input: RequestInfo | URL) => {
    const url = String(input)
    if (url === "/api/auth/status") return Promise.resolve(json({ authenticated: true, username: "fixture-admin", role: "admin", csrf_token: "fixture-csrf", requires_registration: false, sso_mode: "password_only", sso_configured: false, ui_language: "en" }))
    if (url === "/api/config") return config.promise
    if (url === "/api/dashboard") return dashboard.promise
    if (url === "/api/actions/delete/jobs") return Promise.resolve(json({ jobs: [] }))
    if (url.startsWith("/api/actions/delete/batches")) return Promise.resolve(json({ batches: [], next_before: null }))
    if (url === "/api/storage/volumes") return Promise.resolve(json({ headline: "Unknown", status: "unknown", freshness: "unknown", partial: false, warning_free_percent: 15, critical_free_percent: 5, observed_at: null, volumes: [] }))
    if (url.startsWith("/api/library/items")) return Promise.resolve(json({ items: [{ resource_id: "fixture-movie", media_type: "movie", title: "Fixture Movie", display_title: "Fixture Movie", year: 2026, size_bytes: 1, has_file: true, added_at: "2026-01-01T00:00:00Z", artwork_status: "unavailable", artwork_url: null, delete_target: { item_type: "Movie", radarr_movie_id: 1, jellyfin_item_id: "fixture-movie" }, catalog_revision: "fixture" }], state: "complete", failures: [], next_cursor: null, revision: "fixture", catalog_revision: "fixture" }))
    return Promise.resolve(json({}))
  })
  vi.stubGlobal("fetch", fetch)

  render(<ThemeProvider><TooltipProvider><CleanArrApp /></TooltipProvider></ThemeProvider>)

  await expect(screen.findByText("Checking deletion mode")).resolves.toBeVisible()
  expect(screen.getAllByRole("status", { name: "Runtime status: Checking mode…" })).toHaveLength(2)
  expect(screen.getByRole("tab", { name: "Dry run" })).toHaveAttribute("aria-disabled", "true")
  expect(screen.getByRole("tab", { name: "Real deletion" })).toHaveAttribute("aria-disabled", "true")

  await user.click(screen.getAllByRole("button", { name: "Library" })[0])
  const plan = await screen.findByRole("button", { name: "Review deletion plan: Fixture Movie" })
  expect(plan).toBeDisabled()
  expect(screen.getByRole("button", { name: "Select" })).toBeDisabled()
  expect(screen.getAllByText("CleanArr has not loaded the current deletion mode yet. Deletion controls stay unavailable until it does.")).toHaveLength(2)

  config.resolve(json({ general, radarr: [], sonarr: [], seerr: [], downloaders: [], jellyfin: [], admin_token_configured: true }))
  dashboard.resolve(json({ service: { name: "CleanArr", version: "fixture", dry_run: false, log_level: "INFO", downloader_kind: "qbittorrent", webhook_token_configured: true, activity_retention_days: 30 }, endpoints: [], downstream: [], rules: [], jellyfin_template: "{}", sample_payload: {}, recent_activity: [], webhook_status: { attempted_at: null, outcome: "waiting", http_status: null, message: "", notification_type: null, item_type: null, item_name: null, result_status: null }, webhook_attempts: [] }))

  await waitFor(() => expect(screen.getAllByRole("status", { name: "Runtime status: Deletion on" })).toHaveLength(2))
  await waitFor(() => expect(plan).toBeEnabled())
})

it("uses the Russian unknown-mode copy before delayed runtime evidence arrives", async () => {
  const config = deferred<Response>()
  const dashboard = deferred<Response>()
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
    const url = String(input)
    if (url === "/api/auth/status") return Promise.resolve(json({ authenticated: true, username: "fixture-admin", role: "admin", csrf_token: "fixture-csrf", requires_registration: false, sso_mode: "password_only", sso_configured: false, ui_language: "ru" }))
    if (url === "/api/config") return config.promise
    if (url === "/api/dashboard") return dashboard.promise
    if (url === "/api/actions/delete/jobs") return Promise.resolve(json({ jobs: [] }))
    if (url.startsWith("/api/actions/delete/batches")) return Promise.resolve(json({ batches: [], next_before: null }))
    if (url === "/api/storage/volumes") return Promise.resolve(json({ headline: "Неизвестно", status: "unknown", freshness: "unknown", partial: false, warning_free_percent: 15, critical_free_percent: 5, observed_at: null, volumes: [] }))
    return Promise.resolve(json({}))
  }))

  render(<ThemeProvider><TooltipProvider><CleanArrApp /></TooltipProvider></ThemeProvider>)

  await expect(screen.findByText("Проверяем режим удаления")).resolves.toBeVisible()
  expect(screen.getAllByRole("status", { name: "Режим работы: Проверяем режим…" })).toHaveLength(2)
  expect(screen.getByRole("tab", { name: "Тестовый" })).toHaveAttribute("aria-disabled", "true")
  expect(screen.getByRole("tab", { name: "Реальные удаления" })).toHaveAttribute("aria-disabled", "true")

  config.resolve(json({ general: { ...general, ui_language: "ru" }, radarr: [], sonarr: [], seerr: [], downloaders: [], jellyfin: [], admin_token_configured: true }))
  dashboard.resolve(json({ service: { name: "CleanArr", version: "fixture", dry_run: false, log_level: "INFO", downloader_kind: "qbittorrent", webhook_token_configured: true, activity_retention_days: 30 }, endpoints: [], downstream: [], rules: [], jellyfin_template: "{}", sample_payload: {}, recent_activity: [], webhook_status: { attempted_at: null, outcome: "waiting", http_status: null, message: "", notification_type: null, item_type: null, item_name: null, result_status: null }, webhook_attempts: [] }))
})
