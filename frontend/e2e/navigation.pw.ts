import { expect, test, type Page } from "@playwright/test"
import AxeBuilder from "@axe-core/playwright"
import { boot } from "./fixtures"

const WCAG_AA_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]
async function expectNoWcagViolations(page: Page) { const result = await new AxeBuilder({ page }).withTags(WCAG_AA_TAGS).analyze(); expect(result.violations).toEqual([]) }
async function expectViewportWidth(page: Page) { expect(await page.evaluate(() => ({ html: document.documentElement.scrollWidth <= document.documentElement.clientWidth, body: document.body.scrollWidth <= document.documentElement.clientWidth }))).toEqual({ html: true, body: true }) }

test("uses isolated startup mocks, keyboard tabs, theme modes, and accessible desktop/mobile shells", async ({ page }) => {
  const api = await boot(page)
  await page.getByRole("tab", { name: "Settings" }).focus(); await page.keyboard.press("ArrowRight")
  await expect(page.getByRole("tab", { name: "Activity" })).toBeFocused()
  expect(api.count("/api/auth/status")).toBeGreaterThan(0); expect(api.count("/api/config")).toBeGreaterThan(0)
  const theme = page.getByRole("button", { name: /Theme: (light|dark|system)/ }); await theme.click(); await expect(page.getByRole("button", { name: "Theme: light" })).toBeVisible(); await expect(page.locator("html")).not.toHaveClass(/dark/); await page.waitForTimeout(250); await expectNoWcagViolations(page)
  await theme.click(); await expect(page.getByRole("button", { name: "Theme: dark" })).toBeVisible(); await expect(page.locator("html")).toHaveClass(/dark/); await page.waitForTimeout(250); await expectNoWcagViolations(page)
  await theme.click(); await expect(page.getByRole("button", { name: "Theme: system" })).toBeVisible()
  await page.emulateMedia({ reducedMotion: "reduce", colorScheme: "dark" }); await expect(page.locator("[data-reduced-motion=true]")).toHaveCount(1); await expect(page.locator("html")).toHaveClass(/dark/); await expectNoWcagViolations(page)
  await page.setViewportSize({ width: 375, height: 812 }); await expect(page.getByRole("tablist", { name: "Main navigation" })).toBeVisible(); await expectViewportWidth(page); await expectNoWcagViolations(page)
})
