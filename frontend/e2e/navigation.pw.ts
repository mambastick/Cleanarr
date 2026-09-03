import { expect, test, type Page } from "@playwright/test"
import AxeBuilder from "@axe-core/playwright"
import { boot, fixtureMovie, navButton } from "./fixtures"

const WCAG_AA_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]
const mobileJob = { id: "mobile-job", item_type: "Movie", item_name: "Mobile fixture", display_name: "Mobile fixture", status: "queued", phase: "queued", progress_percent: 0, message: "Queued", created_at: "2026-01-01T00:00:00Z", started_at: null, completed_at: null, next_retry_at: null, attempt_count: 0, max_attempts: 3, preflight: null, result: null, error: null }
async function expectNoWcagViolations(page: Page) { const result = await new AxeBuilder({ page }).withTags(WCAG_AA_TAGS).analyze(); expect(result.violations).toEqual([]) }
async function expectViewportWidth(page: Page) { expect(await page.evaluate(() => ({ html: document.documentElement.scrollWidth <= document.documentElement.clientWidth, body: document.body.scrollWidth <= document.documentElement.clientWidth }))).toEqual({ html: true, body: true }) }

test("uses isolated startup mocks, keyboard tabs, theme modes, and accessible desktop/mobile shells", async ({ page }, testInfo) => {
  const api = await boot(page, { jobs: [mobileJob] })
  const overview = navButton(page, "Overview")
  await overview.focus(); await page.keyboard.press("Tab")
  await expect(navButton(page, "Library")).toBeFocused()
  expect(api.count("/api/auth/status")).toBeGreaterThan(0); expect(api.count("/api/config")).toBeGreaterThan(0)
  const account = page.getByRole("button", { name: "Account: fixture-admin" }); await expect(account).toBeVisible(); await expect(account).toHaveText("F"); await account.click()
  const accountPopover = page.getByRole("dialog", { name: "fixture-admin" }); await expect(accountPopover).toBeVisible()
  const theme = accountPopover.getByRole("button", { name: /Theme.*System/i }); await theme.click(); await expect(accountPopover.getByRole("button", { name: /Theme.*Light/i })).toBeVisible(); await expect(page.locator("html")).not.toHaveClass(/dark/); await page.waitForTimeout(250); await expectNoWcagViolations(page)
  await accountPopover.getByRole("button", { name: /Theme.*Light/i }).click(); await expect(accountPopover.getByRole("button", { name: /Theme.*Dark/i })).toBeVisible(); await expect(page.locator("html")).toHaveClass(/dark/); await page.waitForTimeout(250); await expectNoWcagViolations(page); await testInfo.attach("desktop-account-popover-dark-followup", { body: await page.screenshot(), contentType: "image/png" })
  await accountPopover.getByRole("button", { name: /Theme.*Dark/i }).click(); await expect(accountPopover.getByRole("button", { name: /Theme.*System/i })).toBeVisible(); await expect(accountPopover.getByRole("button", { name: /Theme.*System/i })).toBeFocused(); await page.keyboard.press("Escape"); await expect(accountPopover).toBeHidden(); await expect(account).toBeFocused()
  await page.emulateMedia({ reducedMotion: "reduce", colorScheme: "dark" }); await navButton(page, "Library").click(); await expect(page.locator('[data-reduced-motion="true"]:visible')).toHaveCount(1); await expect(page.locator("html")).toHaveClass(/dark/); await expectNoWcagViolations(page)
  await page.setViewportSize({ width: 375, height: 812 }); await expect(page.getByRole("navigation", { name: "Main navigation" })).toBeVisible(); const more = navButton(page, "More"); await expect(more).toBeVisible(); await more.click(); const moreDialog = page.getByRole("dialog", { name: "More" }); await expect(moreDialog.getByRole("button", { name: "Settings" })).toBeVisible(); await expect(moreDialog.getByRole("region", { name: "Storage" })).toBeVisible(); await expect(moreDialog.getByText("fixture-admin")).toBeVisible(); await expect(moreDialog.getByRole("button", { name: /Theme/ })).toBeVisible(); await expect(moreDialog.getByRole("button", { name: /Language/ })).toBeVisible(); await expect(moreDialog.getByRole("button", { name: "Log out" })).toBeVisible(); await moreDialog.getByRole("button", { name: "Close" }).click(); await expect(more).toBeFocused()
  const jobs = page.getByRole("button", { name: "Background tasks" }); await expect(jobs).toBeVisible(); await jobs.click(); const jobsDialog = page.getByRole("dialog", { name: "Background tasks" }); await expect(jobsDialog.getByText("Mobile fixture")).toBeVisible(); const bounds = await jobsDialog.boundingBox(); expect(bounds?.width).toBe(375); await jobsDialog.getByRole("button", { name: "Close" }).click(); await expect(jobs).toBeFocused(); await expectViewportWidth(page); await expectNoWcagViolations(page)
})

test("matches the annotated sidebar and library-card interactions", async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 1280, height: 720 })
  await boot(page, { movies: [fixtureMovie] })

  const stars = page.getByRole("link", { name: "GitHub: 15 stars" }).filter({ visible: true })
  await expect(stars).toBeVisible()

  await navButton(page, "Settings").click()
  const navigation = page.locator(".app-shell__navigation-scroll")
  await expect(navigation).toBeVisible()
  await expect(page.getByRole("group", { name: "Settings" })).toHaveAttribute("data-motion-tree", "true")
  expect(await navigation.evaluate((element) => ({
    overflows: element.scrollHeight > element.clientHeight,
    firefox: getComputedStyle(element).scrollbarWidth,
    webkit: getComputedStyle(element, "::-webkit-scrollbar").display,
  }))).toEqual({ overflows: true, firefox: "none", webkit: "none" })
  await expect(page.locator('[data-slot="motion-highlight-item-container"][data-value="settings"]')).toHaveAttribute("data-active", "true")
  const settingsIndicator = page.locator(".app-shell__settings-highlight > .app-shell__settings-active-indicator")
  const settingsStart = await settingsIndicator.evaluate((element) => Number.parseFloat((element as HTMLElement).style.top))
  await page.getByRole("button", { name: "Media library" }).click()
  await page.waitForTimeout(300)
  const settingsEnd = await settingsIndicator.evaluate((element) => Number.parseFloat((element as HTMLElement).style.top))
  expect(Number.isFinite(settingsStart)).toBe(true)
  expect(Number.isFinite(settingsEnd)).toBe(true)
  expect(settingsEnd).toBeGreaterThan(settingsStart)
  await testInfo.attach("desktop-settings-tree-followup", { body: await page.screenshot(), contentType: "image/png" })

  await page.getByRole("button", { name: "Collapse sidebar" }).click()
  await expect(page.getByRole("button", { name: "Expand sidebar" })).toBeVisible()
  await expect(page.getByRole("status", { name: /Runtime status/ }).first()).toBeVisible()
  await expect(page.getByRole("region", { name: "Storage" }).first()).toBeVisible()
  const desktopFocus = await page.locator(".app-shell__navigation-highlight > .app-shell__nav-active-indicator").boundingBox()
  expect(desktopFocus).not.toBeNull()
  expect(Math.abs(desktopFocus!.width - desktopFocus!.height)).toBeLessThan(1)
  expect(desktopFocus!.width).toBe(40)
  await testInfo.attach("desktop-collapsed-focus-followup", { body: await page.screenshot(), contentType: "image/png" })

  const activity = navButton(page, "Activity")
  const activityIcon = activity.locator('[data-slot="animated-icon"]')
  await activity.hover()
  await expect(activityIcon).not.toHaveCSS("background-color", "rgba(0, 0, 0, 0)")

  await activity.click()
  await page.getByRole("button", { name: "Expand sidebar" }).click()
  const account = page.getByRole("button", { name: "Account: fixture-admin" })
  await expect(account).toHaveText("F")
  await account.click()
  const accountPopover = page.getByRole("dialog", { name: "fixture-admin" })
  await expect(accountPopover.getByRole("button", { name: "Language: EN" })).toBeVisible()
  await testInfo.attach("desktop-account-popover-followup", { body: await page.screenshot(), contentType: "image/png" })
  await page.keyboard.press("Escape")
  await expect(account).toBeFocused()
  await navButton(page, "Library").click()
  const card = page.getByRole("listitem").filter({ hasText: "Fixture Movie" })
  const deleteButton = card.getByRole("button", { name: "Review deletion plan: Fixture Movie" })
  await expect(deleteButton).toHaveCSS("opacity", "0")
  await card.hover()
  await expect(deleteButton).toHaveCSS("opacity", "1")

  const poster = await card.locator("div").first().boundingBox()
  const button = await deleteButton.boundingBox()
  expect(poster).not.toBeNull()
  expect(button).not.toBeNull()
  expect(Math.abs((button!.x + button!.width / 2) - (poster!.x + poster!.width / 2))).toBeLessThan(2)
  expect(Math.abs((button!.y + button!.height / 2) - (poster!.y + poster!.height / 2))).toBeLessThan(2)
})

test("animates one active surface across the mobile bottom bar", async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 375, height: 812 })
  await boot(page)

  const indicator = page.locator(".app-shell__bottom-highlight > .app-shell__nav-active-indicator--mobile")
  const start = await indicator.boundingBox()
  await navButton(page, "Library").click()
  await page.waitForTimeout(350)
  const end = await indicator.boundingBox()

  expect(start).not.toBeNull()
  expect(end).not.toBeNull()
  expect(end!.x).toBeGreaterThan(start!.x)
  expect(await page.locator(".app-shell__bottom-highlight [data-slot=motion-highlight]").count()).toBe(1)
  await testInfo.attach("mobile-bottom-navigation-followup", { body: await page.screenshot(), contentType: "image/png" })
})
