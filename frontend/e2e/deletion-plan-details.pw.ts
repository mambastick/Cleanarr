import AxeBuilder from "@axe-core/playwright"
import { expect, test } from "@playwright/test"
import { boot, clone, fixtureSeries, navButton, runtimeConfig } from "./fixtures"
import { detailedPlan, inspectionProfiles } from "./deletion-plan-fixture"

for (const state of [
  { name: "desktop light EN", language: "en", width: 1440, height: 1000, scheme: "light" as const },
  { name: "desktop dark RU", language: "ru", width: 1440, height: 1000, scheme: "dark" as const },
  { name: "mobile light RU", language: "ru", width: 375, height: 812, scheme: "light" as const },
  { name: "mobile dark EN", language: "en", width: 375, height: 812, scheme: "dark" as const },
]) {
  test(`reviews concrete deletion targets with keyboard and no overflow: ${state.name}`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width: state.width, height: state.height })
    await page.emulateMedia({ colorScheme: state.scheme })
    const config = { ...clone(runtimeConfig), ...inspectionProfiles }
    config.general.ui_language = state.language
    config.general.dry_run = false
    const ru = state.language === "ru"
    const api = await boot(page, { config, series: [{ ...fixtureSeries, jellyfin_series_title: "Пример сериала" }], handlers: [(request) => request.pathname === "/api/actions/delete/preview" ? { body: { generated_at: "2026-09-07T00:00:00Z", plan_hash: "fixture-plan", plan: detailedPlan } } : undefined] })
    await page.emulateMedia({ reducedMotion: "reduce" })
    await navButton(page, ru ? "Библиотека" : "Library").click()
    await page.getByRole("tab", { name: ru ? "Сериалы" : "Series", exact: true }).click()
    const trigger = page.getByRole("button", { name: /(?:Review deletion plan|Проверить план удаления): Пример сериала/ })
    await trigger.click()
    const dialog = page.getByRole("dialog")
    const cancel = dialog.getByRole("button", { name: ru ? "Отмена" : "Cancel", exact: true })
    await expect(cancel).toBeFocused()
    await expect(dialog.getByText(ru ? "Сериал целиком · все сезоны" : "Entire series · all seasons")).toBeVisible()
    await expect(dialog.getByText("Example.Series.S01.1080p.WEB-DL", { exact: true })).toBeVisible()
    await expect(dialog.getByText(ru ? "Удалить торрент из клиента и его скачанные файлы." : "Remove the torrent entry and its downloaded files.").first()).toBeVisible()
    const links = dialog.getByRole("link")
    for (const link of await links.all()) { await expect(link).toHaveAttribute("target", "_blank"); await expect(link).toHaveAttribute("rel", "noopener noreferrer") }
    await expect(dialog.getByRole("link", { name: /(?:Открыть карточку|View item): Seerr/ }).first()).toHaveAttribute("href", "https://seerr.example/tv/42")
    await expect(dialog.getByRole("link", { name: /(?:Открыть сервис|Open service): qBittorrent/ }).first()).toHaveAttribute("href", "https://torrent.example/")
    await testInfo.attach(`plan-${state.name}`, { body: await page.screenshot(), contentType: "image/png" })
    const details = dialog.locator("summary")
    await details.focus(); await page.keyboard.press("Enter")
    await expect(dialog.getByText("1".repeat(40), { exact: true })).toBeVisible()
    await expect(dialog.getByText("71", { exact: true })).toBeVisible()
    await expect(dialog.getByText(/PRIVATE|fixture-only/)).toHaveCount(0)
    const overflow = await dialog.evaluate((node) => [...node.querySelectorAll('[data-slot="scroll-area-viewport"]'), node].some((element) => element.scrollWidth > element.clientWidth + 1))
    expect(overflow).toBe(false)
    expect((await new AxeBuilder({ page }).include('[role="dialog"]').withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze()).violations).toEqual([])
    await page.keyboard.press("Escape")
    await expect(dialog).toBeHidden(); await expect(trigger).toBeFocused()
    expect(api.count("/api/actions/delete/jobs", "POST")).toBe(0)
  })
}

test("retained torrents and failed target resolution remain explicit and prevent confirmation", async ({ page }) => {
  const plan = clone(detailedPlan)
  plan.actions[0].status = "skipped"; plan.actions[0].reason = "seeding_policy"
  plan.actions[1].status = "skipped"; plan.actions[1].reason = "ambiguous_match"
  const api = await boot(page, { series: [fixtureSeries], handlers: [(request) => request.pathname === "/api/actions/delete/preview" ? { body: { generated_at: "2026-09-07T00:00:00Z", plan_hash: "fixture-blocked", plan } } : undefined] })
  await navButton(page, "Library").click()
  await page.getByRole("tab", { name: "Series", exact: true }).click()
  await page.getByRole("button", { name: "Review deletion plan: Fixture Series" }).click()
  const dialog = page.getByRole("dialog")
  await expect(dialog.getByText(/The seeding policy keeps this torrent/)).toBeVisible()
  await expect(dialog.getByText("Several targets could match. Deletion is blocked.")).toBeVisible()
  await expect(dialog.getByRole("button", { name: /Simulate/ })).toBeDisabled()
  expect(api.count("/api/actions/delete/jobs", "POST")).toBe(0)
})
