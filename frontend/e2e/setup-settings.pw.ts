import { expect, test } from "@playwright/test"
import AxeBuilder from "@axe-core/playwright"
import { boot, navButton } from "./fixtures"

const WCAG_AA_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]

test("setup dialog traps focus, supports escape/backdrop restoration, and remains scrollable on mobile", async ({ page }) => {
  await boot(page); const trigger = page.getByRole("button", { name: /setup wizard/i }); await trigger.click(); const dialog = page.getByRole("dialog", { name: /first-time setup/i })
  await expect(dialog).toBeVisible(); await expect(page.getByRole("button", { name: /skip for now/i })).toBeFocused(); await page.keyboard.press("Tab"); await expect(dialog.locator(":focus")).toHaveCount(1)
  await page.keyboard.press("Escape"); await expect(dialog).toBeHidden(); await expect(trigger).toBeFocused(); await trigger.click(); await page.getByTestId("setup-wizard-backdrop").click({ position: { x: 2, y: 2 } }); await expect(trigger).toBeFocused()
  await page.setViewportSize({ width: 375, height: 812 }); await trigger.click(); const viewport = dialog.getByRole("region", { name: /first-time setup/i }); await viewport.evaluate((node) => node.scrollTop = node.scrollHeight); await expect(page.getByRole("button", { name: /next/i })).toBeVisible(); expect(await page.evaluate(() => ({ html: document.documentElement.scrollWidth <= document.documentElement.clientWidth, body: document.body.scrollWidth <= document.documentElement.clientWidth }))).toEqual({ html: true, body: true }); const horizontalOverflow = { dialog: await dialog.evaluate((node) => ({ scrollWidth: node.scrollWidth, clientWidth: node.clientWidth })), viewport: await viewport.evaluate((node) => ({ scrollWidth: node.scrollWidth, clientWidth: node.clientWidth })) }; expect(horizontalOverflow.dialog.scrollWidth).toBeLessThanOrEqual(horizontalOverflow.dialog.clientWidth); expect(horizontalOverflow.viewport.scrollWidth).toBeLessThanOrEqual(horizontalOverflow.viewport.clientWidth)
  const axe = await new AxeBuilder({ page }).withTags(WCAG_AA_TAGS).analyze(); expect(axe.violations).toEqual([])
})

test("settings Select is a themed portal and keeps English/Russian copy localized", async ({ page }) => {
  await boot(page)
  const account = page.getByLabel("Account: fixture-admin"); await expect(account).toBeVisible()
  await page.getByRole("button", { name: /Theme.*System/i }).click()
  await expect(page.getByRole("button", { name: /Theme.*Light/i })).toBeFocused()
  await navButton(page, "Settings").click()
  const language = page.locator("#settings-ui-language")
  await language.focus()
  await page.keyboard.press("Enter")
  const russian = page.getByRole("option", { name: "Русский" })
  await expect(russian).toBeVisible()
  const lightPopup = russian.locator("xpath=ancestor::*[contains(@class, 'bg-popover')]").first()
  await expect(lightPopup).toHaveClass(/bg-popover/)
  expect(await lightPopup.evaluate((node) => getComputedStyle(node).backgroundColor)).not.toBe("rgba(0, 0, 0, 0)")
  await page.keyboard.press("Escape")

  await page.getByRole("button", { name: /Theme.*Light/i }).click()
  await expect(page.getByRole("button", { name: /Theme.*Dark/i })).toBeFocused()
  await language.focus()
  await page.keyboard.press("Enter")
  await expect(russian).toBeVisible()
  const darkPopup = russian.locator("xpath=ancestor::*[contains(@class, 'bg-popover')]").first()
  await expect(darkPopup).toHaveClass(/bg-popover/)
  expect(await darkPopup.evaluate((node) => getComputedStyle(node).backgroundColor)).not.toBe("rgba(0, 0, 0, 0)")
  await russian.click()
  await page.getByRole("button", { name: /save changes/i }).click()
  await expect(navButton(page, "Настройки")).toBeVisible()
  await expect(page.getByText("Настройки сохранены.", { exact: true })).toBeVisible()
})
