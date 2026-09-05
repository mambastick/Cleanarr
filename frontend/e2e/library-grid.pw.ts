import { expect, test, type Page } from "@playwright/test"
import { boot, fixtureMovie, navButton } from "./fixtures"

async function gridState(page: Page) {
  return page.getByRole("list").evaluate((element) => ({
    cards: element.children.length,
    columns: getComputedStyle(element).gridTemplateColumns.split(" ").filter(Boolean).length,
  }))
}

test("fills responsive Library poster rows for every page-size tier", async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 1600, height: 900 })
  const movies = Array.from({ length: 60 }, (_, index) => ({
    ...fixtureMovie,
    radarr_id: fixtureMovie.radarr_id + index,
    title: `Fixture Movie ${index + 1}`,
    jellyfin_movie_title: `Fixture Movie ${index + 1}`,
    jellyfin_movie_id: `fixture-movie-${index + 1}`,
  }))
  const api = await boot(page, { movies })
  await navButton(page, "Library").click()

  const pageSize = page.getByRole("combobox", { name: "Items per page" })
  await expect(pageSize).toContainText("15")
  await expect(page.getByRole("listitem")).toHaveCount(15)
  await expect.poll(() => gridState(page)).toEqual({ cards: 15, columns: 5 })

  for (const option of ["25", "50"]) {
    await pageSize.click()
    await page.getByRole("option", { name: option, exact: true }).click()
    await expect(page.getByRole("listitem")).toHaveCount(Number(option))
    const state = await gridState(page)
    expect(state.cards % state.columns).toBe(0)
    expect(api.last("/api/library/items")?.query.get("limit")).toBe(option)
  }

  const cardSize = page.getByRole("combobox", { name: "Card size" })
  await cardSize.click()
  await page.getByRole("option", { name: "Small", exact: true }).click()
  await expect(pageSize).toContainText("49")
  await expect(page.getByRole("listitem")).toHaveCount(49)
  await expect.poll(() => gridState(page)).toEqual({ cards: 49, columns: 7 })
  await testInfo.attach("library-grid-desktop-full-rows", { body: await page.screenshot(), contentType: "image/png" })

  await page.setViewportSize({ width: 375, height: 812 })
  await expect(pageSize).toContainText("48")
  await expect(page.getByRole("listitem")).toHaveCount(48)
  await expect.poll(() => gridState(page)).toEqual({ cards: 48, columns: 3 })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true)
  await testInfo.attach("library-grid-mobile-full-rows", { body: await page.screenshot(), contentType: "image/png" })
})
