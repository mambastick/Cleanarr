import { expect, test } from "@playwright/test"
import AxeBuilder from "@axe-core/playwright"
import { boot, clone, fixtureSeries, navButton, runtimeConfig, safePlan } from "./fixtures"

for (const scenario of [
  { language: "en", width: 1440, height: 1000, color: "light", dryRun: false },
  { language: "en", width: 1440, height: 1000, color: "dark", dryRun: true },
  { language: "ru", width: 390, height: 844, color: "light", dryRun: true },
  { language: "ru", width: 390, height: 844, color: "dark", dryRun: false },
] as const) {
  test(`season preview, scope, retry and focus: ${scenario.language} ${scenario.width} ${scenario.color}`, async ({ page }) => {
    await page.setViewportSize(scenario)
    await page.emulateMedia({ colorScheme: scenario.color })
    const config = clone(runtimeConfig)
    config.general.ui_language = scenario.language
    config.general.dry_run = scenario.dryRun
    const ru = scenario.language === "ru"
    const series = { ...fixtureSeries, seasons: [fixtureSeries.seasons[0], { ...fixtureSeries.seasons[0], season_number: 2, jellyfin_season_id: "fixture-season-2" }] }
    let submits = 0
    const api = await boot(page, { config, series: [series], handlers: [
      (request) => request.pathname === "/api/actions/delete/preview" ? { body: { generated_at: "2026-01-01T00:00:00Z", plan_hash: "season-plan", plan: { ...safePlan, item_type: "Season", season_number: 2 } } } : undefined,
      (request) => {
        if (request.pathname !== "/api/actions/delete/jobs" || request.method !== "POST") return undefined
        submits += 1
        if (submits === 1) return { status: 503, body: { detail: { code: "uncertain", message: "Fixture uncertainty" } } }
        return { body: { id: "season-job", item_type: "Season", display_name: "Season 2", status: "queued", phase: "queued", progress_percent: 0, message: "Queued", created_at: "2026-01-01T00:00:00Z", attempt_count: 0, max_attempts: 3, preflight: safePlan, result: null, error: null } }
      },
    ] })
    await page.emulateMedia({ reducedMotion: "reduce" })
    await navButton(page, ru ? "Библиотека" : "Library").click()
    await page.getByRole("tab", { name: ru ? "Сериалы" : "Series", exact: true }).click()
    await page.getByRole("button", { name: "Fixture Series 2026", exact: false }).click()
    const trigger = page.getByRole("button", { name: ru ? "Удалить сезон: Сезон 2" : "Delete season: Season 2" })
    await expect(trigger).toBeEnabled()
    await expect(page.locator("html")).toHaveClass(scenario.color === "dark" ? /dark/ : /^(?!.*dark)/)
    await trigger.focus()
    await page.keyboard.press("Enter")
    const dialog = page.getByRole("dialog", { name: ru ? /Сезон 2/ : /Season 2/ })
    await expect(dialog).toBeVisible()
    const cancel = dialog.getByRole("button", { name: ru ? "Отмена" : "Cancel" })
    await expect(cancel).toBeFocused()
    const preview = JSON.parse(api.last("/api/actions/delete/preview")?.body ?? "{}")
    expect(preview).toMatchObject({ item_type: "Season", season_number: 2, sonarr_series_id: 201, jellyfin_item_id: "fixture-season-2", library_resource_id: "library-v1:sonarr:fixture:201" })
    expect(api.count("/api/actions/delete/jobs", "POST")).toBe(0)
    await page.keyboard.press("Escape")
    await expect(dialog).toBeHidden()
    await expect(trigger).toBeFocused()
    await trigger.click()
    await expect(dialog).toBeVisible()
    const confirm = dialog.getByRole("button", { name: scenario.dryRun ? (ru ? "Симулировать" : "Simulate") : (ru ? "Удалить" : "Delete"), exact: true })
    await expect(confirm).toBeEnabled()
    await expect(confirm).toHaveCSS("opacity", "1")
    const axe = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze()
    expect(axe.violations).toEqual([])
    expect(await dialog.evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true)
    await confirm.dblclick()
    const retry = dialog.getByRole("button", { name: ru ? "Повторить" : "Retry", exact: true })
    await expect(retry).toBeVisible()
    expect(api.count("/api/actions/delete/jobs", "POST")).toBe(1)
    await retry.click()
    await expect(dialog.getByRole("button", { name: ru ? "Закрыть" : "Close", exact: true })).toBeVisible()
    const requests = api.requests.filter((request) => request.pathname === "/api/actions/delete/jobs" && request.method === "POST")
    expect(requests).toHaveLength(2)
    expect(requests[1].body).toBe(requests[0].body)
    expect(JSON.parse(requests[0].body ?? "{}")).toMatchObject({ ...preview, confirmed_plan_hash: "season-plan", idempotency_key: expect.any(String) })
  })
}
