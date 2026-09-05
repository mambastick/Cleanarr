import { expect, test } from "@playwright/test"

import { ApiController, navButton } from "./fixtures"

const pending = new Promise<never>(() => {})

test("keeps the runtime mode unknown and deletion planning unavailable while config and dashboard are delayed at desktop, tablet, and mobile widths", async ({ page }, testInfo) => {
  const api = new ApiController({
    movies: [{ radarr_id: 101, title: "Fixture Movie", jellyfin_movie_title: "Fixture Movie", size_bytes: 1_000_000, has_file: true, jellyfin_movie_id: "fixture-movie", has_seerr_request: false }],
    handlers: [
      (request) => request.pathname === "/api/config" || request.pathname === "/api/dashboard" ? pending : undefined,
    ],
  })
  await api.install(page)

  for (const viewport of [{ width: 1280, height: 720 }, { width: 768, height: 900 }, { width: 390, height: 844 }]) {
    await page.setViewportSize(viewport)
    await page.goto("/")
    await expect(page.getByText("Checking deletion mode")).toBeVisible()
    await expect(page.getByRole("status", { name: "Runtime status: Checking mode…" }).first()).toBeVisible()
    await expect(page.getByRole("tab", { name: "Dry run" })).toHaveAttribute("aria-disabled", "true")
    await expect(page.getByRole("tab", { name: "Real deletion" })).toHaveAttribute("aria-disabled", "true")
    await testInfo.attach(`runtime-mode-unknown-${viewport.width}`, { body: await page.screenshot(), contentType: "image/png" })

    await navButton(page, "Library").click()
    await expect(page.getByRole("button", { name: "Review deletion plan: Fixture Movie" })).toBeDisabled()
    await expect(page.getByRole("button", { name: "Select" })).toBeDisabled()
    await expect(page.locator("#library-delete-planning-reason")).toContainText("Deletion controls stay unavailable")

    await navButton(page, "Downloads").click()
    await expect(page.getByRole("button", { name: "Refresh" })).toBeDisabled()
    await expect(page.locator("#downloads-mutation-unavailable")).toContainText("Deletion controls stay unavailable")
    await expect(page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth && document.body.scrollWidth <= document.documentElement.clientWidth)).resolves.toBe(true)
  }
})
