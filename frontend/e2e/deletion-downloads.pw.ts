import { expect, test } from "@playwright/test"
import { boot, clone, downloadItem, fixtureMovie, navButton, runtimeConfig, safePlan } from "./fixtures"

const liveConfig = (() => { const config = clone(runtimeConfig); config.general.dry_run = false; return config })()
const job = { id: "fixture-job", item_type: "Movie", item_name: "Fixture Movie", display_name: "Fixture Movie", status: "queued", phase: "queued", progress_percent: 0, message: "Queued", created_at: "2026-01-01T00:00:00Z", started_at: null, completed_at: null, next_retry_at: null, attempt_count: 0, max_attempts: 3, preflight: safePlan, result: null, error: null }

test("single deletion retries the exact serialized request and prevents rapid duplicate submission", async ({ page }) => {
  let submits = 0
  const api = await boot(page, { config: liveConfig, movies: [fixtureMovie], handlers: [
    (request) => request.pathname === "/api/actions/delete/preview" ? { body: { generated_at: "2026-01-01T00:00:00Z", plan_hash: "fixture-plan", plan: safePlan } } : undefined,
    (request) => { if (request.pathname !== "/api/actions/delete/jobs" || request.method !== "POST") return undefined; submits += 1; return submits === 1 ? { status: 503, body: { detail: { code: "uncertain", message: "Fixture transport uncertainty" } } } : { body: job } },
  ] })
  await navButton(page, "Library").click(); await page.getByRole("tab", { name: "Movies" }).click(); await page.getByRole("button", { name: "Review deletion plan: Fixture Movie" }).click()
  const dialog = page.getByRole("dialog", { name: /fixture movie/i }); await expect(dialog).toBeVisible(); await expect(page.getByRole("button", { name: "Delete" })).toBeEnabled()
  await page.getByRole("button", { name: "Delete" }).dblclick(); await expect(page.getByRole("button", { name: /retry/i })).toBeVisible(); expect(api.count("/api/actions/delete/jobs", "POST")).toBe(1)
  await page.getByRole("button", { name: /retry/i }).click(); await expect(page.getByRole("button", { name: /close/i })).toBeVisible(); expect(api.count("/api/actions/delete/jobs", "POST")).toBe(2)
  const bodies = api.requests.filter((request) => request.pathname === "/api/actions/delete/jobs" && request.method === "POST").map((request) => request.body); expect(bodies[0]).toBe(bodies[1]); const requests = bodies.map((body) => JSON.parse(body ?? "{}")); expect(requests[0].confirmed_plan_hash).toBe("fixture-plan"); expect(requests[0].library_resource_id).toBe("library-v1:radarr:fixture:101"); expect(typeof requests[0].idempotency_key).toBe("string"); expect(requests[0].idempotency_key).not.toBe(""); expect(requests[0].idempotency_key).toBe(requests[1].idempotency_key)
})

test("single deletion exposes preparing, preview retry, accepted-job identity, and portal focus restoration", async ({ page }) => {
  let previews = 0
  const acceptedJobs: unknown[] = []
  const api = await boot(page, { config: liveConfig, movies: [fixtureMovie], jobs: acceptedJobs, handlers: [
    async (request) => { if (request.pathname !== "/api/actions/delete/preview") return undefined; previews += 1; if (previews === 1) { await new Promise((resolve) => setTimeout(resolve, 250)); return { status: 422, body: { detail: { code: "plan_unavailable", message: "Fixture preview failed" } } } } return { body: { generated_at: "2026-01-01T00:00:00Z", plan_hash: "fixture-plan", plan: safePlan } } },
    (request) => { if (request.pathname !== "/api/actions/delete/jobs" || request.method !== "POST") return undefined; acceptedJobs.push(job); return { body: job } },
  ] })
  await navButton(page, "Library").click(); await page.getByRole("tab", { name: "Movies" }).click(); const trigger = page.getByRole("button", { name: "Review deletion plan: Fixture Movie" }); await trigger.click()
  const dialog = page.getByRole("dialog", { name: /fixture movie/i }); await expect(dialog.getByRole("status")).toContainText(/preparing/i); await expect(dialog.getByRole("button", { name: "Delete" })).toBeDisabled(); await expect(dialog.getByRole("alert")).toContainText(/could not be completed safely/i)
  await dialog.getByRole("button", { name: "Retry" }).click(); await expect(dialog.getByRole("button", { name: "Delete" })).toBeEnabled(); await dialog.getByRole("button", { name: "Delete" }).click(); await expect(dialog.getByRole("button", { name: "Close" })).toBeVisible(); await dialog.getByRole("button", { name: "Close" }).click(); await expect(dialog).toBeHidden(); await expect(trigger).toBeFocused()
  const jobs = page.getByRole("button", { name: "Background tasks" }); await expect(jobs).toBeVisible(); await jobs.click(); await expect(page.getByText("Fixture Movie").last()).toBeVisible(); await expect(page.getByText(/queued/i).last()).toBeVisible(); await page.getByRole("button", { name: "Close" }).last().click(); await expect(jobs).toBeFocused(); expect(api.count("/api/actions/delete/jobs", "POST")).toBe(1)
})

test("Downloads stays cold until active, refreshes, and sends one safe pause request", async ({ page }) => {
  const torrent = downloadItem()
  const api = await boot(page, { downloads: [torrent], handlers: [(request) => request.pathname === "/api/downloads/actions" ? { body: { action_id: "fixture-action", status: "succeeded", code: null } } : request.pathname === "/api/downloads/refresh" ? { body: { items: [torrent], next_cursor: null, source_status: "complete", failures: [], failure_details: [], active_count: 1, refreshed: true } } : undefined] })
  expect(api.count("/api/downloads")).toBe(0); await navButton(page, /downloads/i).click(); await expect.poll(() => api.count("/api/downloads")).toBeGreaterThan(0)
  await expect(page.getByText("Fixture torrent")).toBeVisible(); await page.getByRole("button", { name: "Pause" }).dblclick(); expect(api.count("/api/downloads/actions", "POST")).toBe(1)
  const action = api.last("/api/downloads/actions", "POST"); expect(action?.body).toContain('"action":"pause"'); expect(action?.body).not.toContain("delete")
  await page.getByRole("button", { name: "Refresh" }).click(); await expect.poll(() => api.count("/api/downloads/refresh", "POST")).toBe(1)
})

test("Downloads retries a structured first-load failure, renders unknown evidence, and resumes exactly once", async ({ page }) => {
  let reads = 0
  const unknown = downloadItem({ client_id: "unknown-client", info_hash: "unknown-hash", display_name: "Unknown fixture", state: "unknown", freshness: "unknown", ownership: "unknown", progress: null, total_bytes: null, downloaded_bytes: null, uploaded_bytes: null, ratio: null, seeding_time_seconds: null, download_speed_bytes_per_second: null, upload_speed_bytes_per_second: null, unavailable_reason: "ownership_unknown" })
  const stopped = downloadItem({ client_id: "resume-client", info_hash: "resume-hash", display_name: "Stopped fixture", state: "stopped" })
  const api = await boot(page, { handlers: [(request) => { if (request.pathname === "/api/downloads") { reads += 1; return reads <= 2 ? { status: 503, body: { detail: { code: "source_failed", message: "Fixture source failed" } } } : { body: { items: [unknown, stopped], next_cursor: null, source_status: "complete", failures: [], failure_details: [], active_count: 1 } } } if (request.pathname === "/api/downloads/actions") return { body: { action_id: "resume-action", status: "succeeded", code: null } }; return undefined }] })
  expect(api.count("/api/downloads")).toBe(0); await navButton(page, /downloads/i).click(); await expect(page.getByRole("button", { name: "Retry" })).toBeVisible(); await page.getByRole("button", { name: "Retry" }).click(); await expect(page.getByText("Unknown fixture")).toBeVisible(); await expect(page.getByText("Unknown").first()).toBeVisible(); await expect(page.getByRole("button", { name: "Controls" }).first()).toBeDisabled()
  await page.getByRole("button", { name: "Resume" }).dblclick(); await expect.poll(() => api.count("/api/downloads/actions", "POST")).toBe(1); const body = JSON.parse(api.last("/api/downloads/actions", "POST")?.body ?? "{}"); expect(Object.keys(body).sort()).toEqual(["action", "client_id", "idempotency_key", "info_hash"]); expect(body).toMatchObject({ action: "resume", client_id: "resume-client", info_hash: "resume-hash" }); expect(body).not.toHaveProperty("delete"); await expect.poll(() => api.count("/api/downloads")).toBeGreaterThanOrEqual(4)
})

test("Downloads pauses polling while hidden and reloads immediately when visible", async ({ page }) => {
  await page.clock.install({ time: new Date("2026-01-01T00:00:00Z") })
  const api = await boot(page, { downloads: [downloadItem()] })
  await navButton(page, /downloads/i).click(); await expect.poll(() => api.count("/api/downloads")).toBeGreaterThan(0)
  const beforeHidden = api.count("/api/downloads")
  await page.evaluate(() => { Object.defineProperty(document, "hidden", { configurable: true, get: () => true }); document.dispatchEvent(new Event("visibilitychange")) })
  await page.clock.fastForward(60_000); expect(api.count("/api/downloads")).toBe(beforeHidden)
  await page.evaluate(() => { Object.defineProperty(document, "hidden", { configurable: true, get: () => false }); document.dispatchEvent(new Event("visibilitychange")) })
  await expect.poll(() => api.count("/api/downloads")).toBe(beforeHidden + 1)
})

test("Cleanup candidates preserve unknown evidence and hand safe links into single and batch previews", async ({ page }) => {
  const linkedPlan = { ...safePlan, display_name: "Safe linked title" }
  const safeCandidate = { jellyfin_item_id: "safe-linked", display_name: "Ignored source title", media_type: "movie", created_at: null, added_at: null, size_bytes: null, playback_status: "unknown", play_count: null, watched_user_count: null, last_played_at: null, playback_unavailable_reason: "playback_unknown", data_source: "jellyfin_standard", fetched_at: "2026-01-01T00:00:00Z", unavailable_reason: null, seeding: { torrent_state: "unknown", readiness: "unknown", readiness_reason: "ownership_unknown", torrent_count: null, ratio: null, seeding_time_seconds: null, unavailable_reason: "ownership_unknown" }, deletion_link: { item_type: "Movie", radarr_movie_id: 101, sonarr_series_id: null, jellyfin_item_id: "safe-linked", display_name: "Safe linked title" } }
  const unlinkedCandidate = { ...safeCandidate, jellyfin_item_id: "missing-linked", display_name: "Missing link fixture", deletion_link: null }
  const api = await boot(page, { config: liveConfig, cleanup: [safeCandidate, unlinkedCandidate], handlers: [
    (request) => request.pathname === "/api/actions/delete/preview" ? { body: { generated_at: "2026-01-01T00:00:00Z", plan_hash: "safe-plan", plan: linkedPlan } } : undefined,
    (request) => request.pathname === "/api/actions/delete/batches/preview" ? { body: { generated_at: "2026-01-01T00:00:00Z", batch_hash: "safe-batch", ready_count: 1, blocked_count: 0, children: [{ mutation_identity: "safe-child", display_name: "Safe linked title", status: "ready", plan_hash: "safe-plan", plan: linkedPlan, blocked_code: null, blocked_message: null }] } } : undefined,
  ] })
  await navButton(page, /downloads/i).click(); await page.getByRole("tab", { name: "Cleanup candidates" }).click(); await expect(page.getByText("Safe linked title")).toBeVisible(); await expect(page.getByText("Missing link fixture")).toBeVisible(); await expect(page.getByText("Playback unknown").first()).toBeVisible(); await expect(page.getByText(/no safe library link/i)).toBeVisible(); await expect(page.getByRole("checkbox", { name: /missing link fixture/i })).toHaveCount(0)
  const review = page.getByRole("button", { name: "Review deletion plan: Safe linked title" }); await review.click(); const single = page.getByRole("dialog", { name: /safe linked title/i }); await expect(single).toBeVisible(); await expect(single.getByText("Safe linked title").first()).toBeVisible(); await single.getByRole("button", { name: "Cancel" }).click(); await expect(review).toBeFocused()
  await page.getByRole("checkbox", { name: "Select: Safe linked title" }).check(); const batchTrigger = page.getByRole("button", { name: "Review selected cleanup" }); await batchTrigger.click(); await expect(page.getByRole("alertdialog", { name: /review batch deletion/i })).toBeVisible(); const batchRequest = api.last("/api/actions/delete/batches/preview", "POST"); expect(batchRequest?.body).toContain("Safe linked title")
})
