import AxeBuilder from "@axe-core/playwright"
import { expect, test } from "@playwright/test"
import { boot, clone, fixtureMovie, navButton, runtimeConfig } from "./fixtures"

for (const state of [
  { language: "en", width: 1440, scheme: "light", theme: "light" },
  { language: "ru", width: 1440, scheme: "dark", theme: "system" },
  { language: "ru", width: 390, scheme: "light", theme: "system" },
  { language: "en", width: 390, scheme: "dark", theme: "dark" },
] as const) {
  test(`unknown sibling and closed rTorrent block confirmation: ${state.language} ${state.width} ${state.theme}`, async ({ page }, testInfo) => {
    const ru = state.language === "ru"
    await page.setViewportSize({ width: state.width, height: 1000 })
    await page.emulateMedia({ colorScheme: state.scheme })
    await page.addInitScript((theme) => localStorage.setItem("cleanarr-theme", theme), state.theme)
    const config = clone(runtimeConfig); config.general.ui_language = state.language; config.general.dry_run = false
    const plan = { item_type: "Movie", item_id: "synthetic", name: "Fixture Movie", display_name: "Fixture Movie", correlation_id: "synthetic", status: "partial_failure", fingerprint: {}, season_number: null, episode_number: null, episode_end_number: null, actions: [
      { system: "qbittorrent", action: "delete_hash", status: "skipped", reason: "sibling_scope_unknown", message: "PRIVATE", details: { torrent_name: "Fixture target", hash: "A".repeat(40), blocking_torrents: [{ downloader_id: "fixture-client", hash: "B".repeat(40), torrent_name: "Fixture unverified sibling", url: "PRIVATE" }] } },
      { system: "rtorrent", action: "delete_hash", status: "skipped", reason: "torrent_closed", message: "PRIVATE", details: { torrent_name: "Fixture closed torrent", hash: "C".repeat(40) } },
    ] }
    const api = await boot(page, { config, movies: [fixtureMovie], handlers: [(request) => request.pathname === "/api/actions/delete/preview" ? { body: { generated_at: "2026-10-14T00:00:00Z", plan_hash: "synthetic-blocked", plan } } : undefined] })
    await page.emulateMedia({ reducedMotion: "reduce" })
    await navButton(page, ru ? "Библиотека" : "Library").click()
    const trigger = page.getByRole("button", { name: "Review deletion plan: Fixture Movie".replace("Review deletion plan", ru ? "Проверить план удаления" : "Review deletion plan") })
    await trigger.click()
    const dialog = page.getByRole("dialog")
    await expect(dialog.getByRole("button", { name: ru ? "Отмена" : "Cancel", exact: true })).toBeFocused()
    await expect(dialog.getByText(ru ? /неполные сведения о файлах/ : /incomplete file metadata/)).toBeVisible()
    await expect(dialog.getByText(`Fixture unverified sibling · ${ru ? "Клиент" : "Client"} fixture-client`, { exact: true })).toBeVisible()
    await expect(dialog.getByText(ru ? /Откройте или возобновите/ : /Open or resume it in rTorrent/)).toBeVisible()
    await expect(dialog.getByRole("button", { name: ru ? "Удалить" : "Delete", exact: true })).toBeDisabled()
    expect(await page.locator("html").evaluate((node) => node.classList.contains("dark"))).toBe(state.scheme === "dark")
    const screenshot = testInfo.outputPath(`scope-blockers-${state.language}-${state.width}-${state.scheme}.png`)
    await page.screenshot({ path: screenshot }); await testInfo.attach("Scope blockers", { path: screenshot, contentType: "image/png" })
    await dialog.locator("summary").focus(); await page.keyboard.press("Enter")
    await expect(dialog.getByText(new RegExp("B".repeat(40)))).toBeVisible()
    expect(await dialog.evaluate((node) => [node, ...node.querySelectorAll('[data-slot="scroll-area-viewport"]')].some((element) => element.scrollWidth > element.clientWidth + 1))).toBe(false)
    await expect(dialog.getByText(/PRIVATE|synthetic-blocked/)).toHaveCount(0)
    expect((await new AxeBuilder({ page }).include('[role="dialog"]').withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze()).violations).toEqual([])
    await page.keyboard.press("Escape"); await expect(dialog).toBeHidden(); await expect(trigger).toBeFocused()
    expect(api.count("/api/actions/delete/jobs", "POST")).toBe(0)
  })
}
