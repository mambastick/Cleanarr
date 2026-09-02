import { expect, test } from "@playwright/test"
import { boot, clone, fixtureMovie, navButton, runtimeConfig, safePlan } from "./fixtures"

test("downloader wizard uses client-specific test routes and invalidates visible readiness after a draft edit", async ({ page }) => {
  const tested: string[] = []
  await boot(page, { handlers: [(request) => { if (!request.pathname.endsWith("/test")) return undefined; tested.push(request.pathname); return { body: { ok: true, message: "Fixture connection succeeded", version: "fixture", details: {} } } }] })
  await page.getByRole("button", { name: /setup wizard/i }).click(); await page.getByRole("button", { name: "Setup 6" }).click()
  const kind = page.locator("#wizard-downloader-kind")
  for (const [label, endpoint] of [["qBittorrent", "/api/config/downloaders/qbittorrent/test"], ["Transmission", "/api/config/downloaders/transmission/test"], ["Deluge", "/api/config/downloaders/deluge/test"], ["rTorrent", "/api/config/downloaders/rtorrent/test"]] as const) {
    await kind.click(); await page.getByRole("option", { name: label }).click(); await page.getByRole("button", { name: /test current profile/i }).click(); await expect.poll(() => tested.includes(endpoint)).toBeTruthy()
  }
  await expect(page.getByText(/tested with current connection settings/i)).toBeVisible(); await page.locator("#wizard-downloaders-url").fill("https://changed.invalid"); await expect(page.getByText(/not ready.*exact connection/i).last()).toBeVisible()
})

test("downloader wizard shows existing profiles and saves a tested kind-specific enabled default draft", async ({ page }) => {
  const config = clone(runtimeConfig)
  config.downloaders.push({ id: "existing-downloader", name: "Existing qBittorrent", url: "https://existing.invalid", enabled: true, is_default: true, kind: "qbittorrent", username: "existing-user", password: "existing-pass", api_key: null, seeding_policy: "immediate", min_seed_ratio: null, min_seed_time_minutes: null })
  const savedConfig = clone(config)
  const api = await boot(page, { config, handlers: [
    (request) => request.pathname === "/api/config/downloaders/transmission/test" ? { body: { ok: true, message: "Fixture connection succeeded" } } : undefined,
    (request) => { if (request.pathname !== "/api/config/downloaders/transmission" || request.method !== "POST") return undefined; const payload = JSON.parse(request.body ?? "{}"); savedConfig.downloaders.push({ ...payload, id: "saved-transmission", kind: "transmission" }); return { body: savedConfig } },
  ] })
  await page.getByRole("button", { name: /setup wizard/i }).click(); await page.getByRole("button", { name: "Setup 6" }).click(); await expect(page.getByText("Existing qBittorrent · qBittorrent")).toBeVisible(); await expect(page.getByText("Enabled · default", { exact: true })).toBeVisible()
  await page.getByRole("button", { name: /add another (client|profile)/i }).click(); await page.locator("#wizard-downloader-kind").click(); await page.getByRole("option", { name: "Transmission" }).click(); await page.locator("#wizard-downloaders-name").fill("Transmission fixture"); await page.locator("#wizard-downloaders-url").fill("https://transmission.fixture.invalid"); await page.locator("#wizard-downloaders-username").fill("fixture-user"); await page.locator("#wizard-downloaders-password").fill("fixture-pass")
  const enabled = page.getByRole("switch", { name: "Enabled" }); const preferred = page.getByRole("switch", { name: "Mark as preferred/default" }); await enabled.click(); await enabled.click(); await preferred.click(); await preferred.click(); await page.getByRole("button", { name: /test current profile/i }).click(); await expect(page.getByText(/tested with current connection settings/i)).toBeVisible(); await page.getByRole("button", { name: "Save" }).click(); await expect.poll(() => api.count("/api/config/downloaders/transmission", "POST")).toBe(1)
  const payload = JSON.parse(api.last("/api/config/downloaders/transmission", "POST")?.body ?? "{}"); expect(payload).toEqual({ name: "Transmission fixture", url: "https://transmission.fixture.invalid", enabled: true, is_default: true, seeding_policy: "immediate", min_seed_ratio: null, min_seed_time_minutes: null, username: "fixture-user", password: "fixture-pass" })
})

test("batch preview binds a hash, shows blocked children, requires exact count, and submits once", async ({ page }) => {
  const config = clone(runtimeConfig); config.general.dry_run = false
  const secondMovie = { ...fixtureMovie, radarr_id: 102, title: "Fixture Movie Two", jellyfin_movie_title: "Fixture Movie Two", jellyfin_movie_id: "fixture-movie-two" }
  const batch = { id: "fixture-batch", status: "partial", message: "Fixture partial", created_at: "2026-01-01T00:00:00Z", started_at: null, completed_at: null, error_code: null, error_message: null, total_count: 2, queued_count: 0, running_count: 0, completed_count: 1, blocked_count: 1, failed_count: 0, cancelled_count: 0, children: [{ id: "fixture-child-a", mutation_identity: "fixture-a", display_name: "Fixture Movie", status: "completed", message: "Complete", blocked_code: null, error_code: null, error_message: null, preflight: safePlan, result: safePlan, started_at: null, completed_at: null }, { id: "fixture-child-b", mutation_identity: "fixture-b", display_name: "Fixture Movie Two", status: "blocked", message: "Blocked", blocked_code: "ownership_unknown", error_code: null, error_message: null, preflight: null, result: null, started_at: null, completed_at: null }] }
  let submits = 0
  const acceptedBatches: unknown[] = []
  const api = await boot(page, { config, movies: [fixtureMovie, secondMovie], batches: acceptedBatches, handlers: [
    (request) => request.pathname === "/api/actions/delete/batches/preview" ? { body: { generated_at: "2026-01-01T00:00:00Z", batch_hash: "fixture-batch-hash", ready_count: 1, blocked_count: 1, children: [{ mutation_identity: "fixture-a", display_name: "Fixture Movie", status: "ready", plan_hash: "fixture-plan-a", plan: safePlan, blocked_code: null, blocked_message: null }, { mutation_identity: "fixture-b", display_name: "Fixture Movie Two", status: "blocked", plan_hash: null, plan: null, blocked_code: "ownership_unknown", blocked_message: "Fixture ownership is unknown" }] } } : undefined,
    (request) => { if (request.pathname !== "/api/actions/delete/batches" || request.method !== "POST") return undefined; submits += 1; acceptedBatches.push(batch); return { body: batch } },
  ] })
  await navButton(page, "Library").click(); await page.getByRole("tab", { name: "Movies" }).click(); await page.getByRole("button", { name: "Select" }).click(); await page.getByRole("checkbox", { name: /select: fixture movie$/i }).check(); await page.getByRole("checkbox", { name: /select: fixture movie two/i }).check(); const trigger = page.getByRole("button", { name: "Review deletion plan", exact: true }); await trigger.click()
  await expect(page.getByRole("alertdialog", { name: /review batch deletion/i })).toBeVisible(); await expect(page.getByRole("heading", { name: /blocked items/i })).toBeVisible(); await expect(page.getByRole("region", { name: /blocked items/i }).getByText("Fixture Movie Two")).toBeVisible(); const count = page.getByRole("textbox", { name: /type the exact selected item count/i }); await count.fill("2"); await page.getByRole("button", { name: /delete selected items/i }).dblclick(); await expect.poll(() => submits).toBe(1)
  await page.getByRole("button", { name: "Close" }).click(); await expect(page.getByRole("button", { name: "Select" })).toBeFocused(); const jobs = page.getByRole("button", { name: "Background tasks" }); await jobs.click(); await expect(page.getByText(/partial/i).last()).toBeVisible(); await expect(page.getByText("Fixture Movie Two").last()).toBeVisible(); await page.getByRole("button", { name: "Close" }).last().click(); await expect(jobs).toBeFocused(); const request = api.last("/api/actions/delete/batches", "POST"); expect(request?.body).toContain("fixture-batch-hash"); expect(request?.body).toContain("library-v1:radarr:fixture:101")
})
