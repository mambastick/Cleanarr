import { expect, test } from "@playwright/test"
import { boot, clone, runtimeConfig, safePlan } from "./fixtures"

for (const state of [
  { language: "en", theme: "light", width: 1440, tasks: "Background tasks", close: "Close", message: "A connected service could not verify the cleanup plan." },
  { language: "ru", theme: "dark", width: 390, tasks: "Фоновые задачи", close: "Закрыть", message: "Подключённый сервис не смог проверить план очистки." },
] as const) {
  test(`durable preflight error remains localized after a failed retry: ${state.language}`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width: state.width, height: 900 })
    await page.emulateMedia({ colorScheme: state.theme })
    await page.addInitScript((theme) => localStorage.setItem("cleanarr-theme", theme), state.theme)
    const config = clone(runtimeConfig); config.general.ui_language = state.language
    const jobs: Record<string, unknown>[] = [{ id: "fixture-retry-job", item_type: "Movie", item_name: "Fixture Movie", display_name: "Fixture Movie", status: "retry_wait", phase: "retry_wait", progress_percent: 0, message: "Synthetic private message", created_at: "2026-01-01T00:00:00Z", started_at: null, completed_at: null, next_retry_at: "2026-01-01T00:00:02Z", attempt_count: 1, max_attempts: 2, preflight: safePlan, result: null, error: "Synthetic private service error", error_code: "preflight_failed" }]
    const api = await boot(page, { config, jobs })
    await page.emulateMedia({ reducedMotion: "reduce" })
    const trigger = page.getByRole("button", { name: state.tasks })
    await expect(trigger).toBeVisible(); await trigger.click()
    await expect(page.getByText(state.message, { exact: false })).toBeVisible()
    jobs.splice(0, 1, { ...jobs[0], status: "failed", phase: "failed", progress_percent: 100, completed_at: "2026-01-01T00:00:03Z", next_retry_at: null, attempt_count: 2 })
    await expect.poll(() => api.count("/api/actions/delete/jobs", "GET")).toBeGreaterThan(1)
    await expect(page.getByText("100%", { exact: true })).toBeVisible()
    await expect(page.getByText(state.message, { exact: false })).toBeVisible()
    await expect(page.getByText("Synthetic private service error", { exact: true })).toHaveCount(0)
    expect(await page.locator("body").evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true)
    expect(api.count("/api/actions/delete/jobs", "POST")).toBe(0)
    const screenshot = testInfo.outputPath(`preflight-error-${state.language}-${state.theme}.png`)
    await page.screenshot({ path: screenshot })
    await testInfo.attach("Localized durable preflight error", { path: screenshot, contentType: "image/png" })
    await page.getByRole("button", { name: state.close, exact: true }).last().click()
  })
}
