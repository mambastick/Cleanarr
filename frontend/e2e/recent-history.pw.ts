import { expect, test } from "@playwright/test"
import { boot, clone, dashboard, navButton, runtimeConfig } from "./fixtures"
import { detailedPlan } from "./deletion-plan-fixture"

for (const language of ["en", "ru"] as const) {
  test(`completed history is available in Activity without a Recent control: ${language}`, async ({ page }) => {
    const config = clone(runtimeConfig); config.general.ui_language = language
    const result = { ...detailedPlan, name: "Example history item", display_name: "Example history item" }
    const activityDashboard = clone(dashboard)
    Object.assign(activityDashboard, { recent_activity: [{ processed_at: "2026-09-07T00:00:00Z", action_summary: { dry_run: 8 }, result }] })
    await boot(page, { config, dashboard: activityDashboard, jobs: [{ id: "finished-fixture", item_type: "Series", item_name: "Example history item", display_name: "Example history item", status: "completed", phase: "completed", progress_percent: 100, message: "Complete", created_at: "2026-09-07T00:00:00Z", started_at: null, completed_at: "2026-09-07T00:00:01Z", next_retry_at: null, attempt_count: 1, max_attempts: 3, preflight: detailedPlan, result, error: null }] })
    await expect(page.getByRole("button", { name: language === "ru" ? "Фоновые задачи" : "Background tasks" })).toHaveCount(0)
    await expect(page.locator(".app-shell__desktop-status")).toHaveCSS("min-height", "0px")
    await navButton(page, language === "ru" ? "Активность" : "Activity").click()
    await expect(page.getByRole("heading", { name: language === "ru" ? "Активность" : "Activity", exact: true })).toBeVisible()
    await expect(page.getByText("Example history item", { exact: true })).toBeVisible()
  })
}
