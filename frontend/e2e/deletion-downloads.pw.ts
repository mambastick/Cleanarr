import { expect, test } from "@playwright/test"
import { boot, clone, downloadItem, fixtureMovie, navButton, runtimeConfig, safePlan } from "./fixtures"

const liveConfig = (() => { const config = clone(runtimeConfig); config.general.dry_run = false; return config })()
const job = { id: "fixture-job", item_type: "Movie", item_name: "Fixture Movie", display_name: "Fixture Movie", status: "queued", phase: "queued", progress_percent: 0, message: "Queued", created_at: "2026-01-01T00:00:00Z", started_at: null, completed_at: null, next_retry_at: null, attempt_count: 0, max_attempts: 3, preflight: safePlan, result: null, error: null }

test("a completed real deletion refreshes the library from source and removes the stale card", async ({ page }) => {
  const activeJobs: Record<string, unknown>[] = [{ ...job }]
  const api = await boot(page, {
    jobs: activeJobs,
    movies: [fixtureMovie],
    handlers: [
      (request) => request.pathname === "/api/library/items" && request.query.get("refresh") === "true"
        ? { body: { items: [], next_cursor: null, source_status: "complete", source_failures: [], catalog_revision: "fixture-after-delete" } }
        : undefined,
    ],
  })
  await navButton(page, "Library").click()
  await page.getByRole("tab", { name: "Movies" }).click()
  await expect(page.getByText("Fixture Movie", { exact: true }).first()).toBeVisible()

  activeJobs.splice(0, 1, {
    ...job,
    status: "completed",
    phase: "completed",
    progress_percent: 100,
    completed_at: "2026-01-01T00:00:02Z",
    result: { ...safePlan, actions: [{ ...safePlan.actions[0], status: "deleted" }] },
  })

  await expect.poll(() => api.requests.filter((request) => request.pathname === "/api/library/items" && request.query.get("refresh") === "true").length).toBe(1)
  await expect(page.getByText("Fixture Movie", { exact: true })).toHaveCount(0)
  await expect(page.getByText("No library items found.")).toBeVisible()
})

test("a completed dry-run batch refreshes from source and keeps the simulated item", async ({ page }) => {
  const simulatedResult = { ...safePlan, actions: [{ ...safePlan.actions[0], status: "dry_run" }] }
  const activeBatches: Record<string, unknown>[] = [{
    id: "fixture-batch",
    status: "running",
    message: "Running",
    created_at: "2026-01-01T00:00:00Z",
    started_at: "2026-01-01T00:00:01Z",
    completed_at: null,
    error_code: null,
    error_message: null,
    total_count: 1,
    queued_count: 0,
    running_count: 1,
    completed_count: 0,
    blocked_count: 0,
    failed_count: 0,
    cancelled_count: 0,
    children: [{ id: "fixture-child", mutation_identity: "fixture-child", display_name: "Fixture Movie", status: "running", message: "Running", blocked_code: null, error_code: null, error_message: null, preflight: safePlan, result: null, started_at: "2026-01-01T00:00:01Z", completed_at: null }],
  }]
  const api = await boot(page, { batches: activeBatches, movies: [fixtureMovie] })
  await navButton(page, "Library").click()
  await page.getByRole("tab", { name: "Movies" }).click()
  await expect(page.getByText("Fixture Movie", { exact: true }).first()).toBeVisible()

  activeBatches.splice(0, 1, {
    ...activeBatches[0],
    status: "completed",
    completed_at: "2026-01-01T00:00:02Z",
    running_count: 0,
    completed_count: 1,
    children: [{ ...(activeBatches[0].children as Record<string, unknown>[])[0], status: "completed", result: simulatedResult, completed_at: "2026-01-01T00:00:02Z" }],
  })

  await expect.poll(() => api.requests.filter((request) => request.pathname === "/api/library/items" && request.query.get("refresh") === "true").length).toBe(1)
  await expect(page.getByText("Fixture Movie", { exact: true }).first()).toBeVisible()
})

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
  let allowDownloads = false
  const unknown = downloadItem({ client_id: "unknown-client", info_hash: "unknown-hash", display_name: "Unknown fixture", state: "unknown", freshness: "unknown", ownership: "unknown", progress: null, total_bytes: null, downloaded_bytes: null, uploaded_bytes: null, ratio: null, seeding_time_seconds: null, download_speed_bytes_per_second: null, upload_speed_bytes_per_second: null, unavailable_reason: "ownership_unknown" })
  const stopped = downloadItem({ client_id: "resume-client", info_hash: "resume-hash", display_name: "Stopped fixture", state: "stopped" })
  const api = await boot(page, { handlers: [(request) => { if (request.pathname === "/api/downloads") return allowDownloads ? { body: { items: [unknown, stopped], next_cursor: null, source_status: "complete", failures: [], failure_details: [], active_count: 1 } } : { status: 503, body: { detail: { code: "source_failed", message: "Fixture source failed" } } }; if (request.pathname === "/api/downloads/actions") return { body: { action_id: "resume-action", status: "succeeded", code: null } }; return undefined }] })
  expect(api.count("/api/downloads")).toBe(0); await navButton(page, /downloads/i).click(); await expect(page.getByRole("button", { name: "Retry" })).toBeVisible(); allowDownloads = true; await page.getByRole("button", { name: "Retry" }).click(); await expect(page.getByText("Unknown fixture")).toBeVisible(); await expect(page.getByText("Unknown").first()).toBeVisible(); await expect(page.getByRole("button", { name: "Controls" }).first()).toBeDisabled()
  const readsBeforeResume = api.count("/api/downloads")
  await page.getByRole("button", { name: "Resume" }).dblclick(); await expect.poll(() => api.count("/api/downloads/actions", "POST")).toBe(1); const body = JSON.parse(api.last("/api/downloads/actions", "POST")?.body ?? "{}"); expect(Object.keys(body).sort()).toEqual(["action", "client_id", "idempotency_key", "info_hash"]); expect(body).toMatchObject({ action: "resume", client_id: "resume-client", info_hash: "resume-hash" }); expect(body).not.toHaveProperty("delete"); await expect.poll(() => api.count("/api/downloads")).toBeGreaterThan(readsBeforeResume)
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
  await navButton(page, /downloads/i).click()
  const downloadsTabs = page.getByRole("tablist", { name: "Downloads" })
  await expect(downloadsTabs.locator("[data-slot=tabs-highlight]")).toHaveCount(1)
  expect(await downloadsTabs.evaluate((node) => node.scrollWidth <= node.clientWidth)).toBe(true)
  await page.getByRole("tab", { name: "Cleanup candidates" }).click()
  await expect(page.getByRole("combobox", { name: "Sort" })).toContainText("Recently added")
  await expect(page.getByRole("combobox", { name: "Order" })).toContainText("Descending")
  await expect(page.getByText("Safe linked title")).toBeVisible(); await expect(page.getByText("Missing link fixture")).toBeVisible(); await expect(page.getByText("Playback unknown").first()).toBeVisible(); await expect(page.getByText(/could not verify one safe deletion target/i)).toBeVisible(); await expect(page.getByRole("checkbox", { name: /missing link fixture/i })).toHaveCount(0)
  const review = page.getByRole("button", { name: "Review deletion plan: Safe linked title" }); await review.click(); const single = page.getByRole("dialog", { name: /safe linked title/i }); await expect(single).toBeVisible(); await expect(single.getByText("Safe linked title").first()).toBeVisible(); await single.getByRole("button", { name: "Cancel" }).click(); await expect(review).toBeFocused()
  await page.getByRole("checkbox", { name: "Select: Safe linked title" }).check(); const batchTrigger = page.getByRole("button", { name: "Review selected cleanup" }); await batchTrigger.click(); await expect(page.getByRole("alertdialog", { name: /review batch deletion/i })).toBeVisible(); const batchRequest = api.last("/api/actions/delete/batches/preview", "POST"); expect(batchRequest?.body).toContain("Safe linked title")
})

test("a Jellyfin-only movie stays out of batches and sends a narrow single-item preview", async ({ page }) => {
  const directCandidate = { jellyfin_item_id: "jf-direct", display_name: "Direct movie", media_type: "movie", created_at: null, added_at: null, size_bytes: 1_000_000, playback_status: "never_watched", play_count: 0, watched_user_count: 0, last_played_at: null, playback_unavailable_reason: null, data_source: "jellyfin_standard", fetched_at: "2026-01-01T00:00:00Z", unavailable_reason: null, seeding: { torrent_state: "unknown", readiness: "unknown", readiness_reason: "arr_mapping_unknown", torrent_count: null, ratio: null, seeding_time_seconds: null, unavailable_reason: "arr_mapping_unknown" }, deletion_link: { item_type: "Movie", radarr_movie_id: null, sonarr_series_id: null, jellyfin_item_id: "jf-direct", display_name: "Direct movie", jellyfin_only: true } }
  const api = await boot(page, { cleanup: [directCandidate], handlers: [
    (request) => request.pathname === "/api/actions/delete/preview" ? {
      body: {
        generated_at: "2026-01-01T00:00:00Z",
        plan_hash: "direct-plan",
        plan: { ...safePlan, display_name: "Direct movie", actions: [{ system: "jellyfin", action: "delete_item", status: "dry_run", message: "Fixture", reason: null, details: {} }] },
      },
    } : undefined,
  ] })
  await navButton(page, /downloads/i).click(); await page.getByRole("tab", { name: "Cleanup candidates" }).click()
  await expect(page.getByText("Only in Jellyfin").first()).toBeVisible(); await expect(page.getByRole("checkbox", { name: /Direct movie/ })).toHaveCount(0)
  await page.getByRole("button", { name: "Review deletion plan: Direct movie" }).click()

  const body = JSON.parse(api.last("/api/actions/delete/preview", "POST")?.body ?? "{}")
  expect(body).toMatchObject({ item_type: "Movie", jellyfin_item_id: "jf-direct", jellyfin_only: true })
  expect(body).not.toHaveProperty("radarr_movie_id")
})
