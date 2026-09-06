import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

import type { LibraryItemDetail } from "@/lib/library"
import { LIBRARY_COPY } from "./library-copy"
import { LibrarySeasons } from "./library-seasons"
import { buildManualDeleteRequest, librarySeasonDeleteTarget } from "./library-selection"

const detail: LibraryItemDetail = {
  resource_id: "series-resource", media_type: "series", title: "Example series", display_name: "Example series", year: 2026, size: 100, has_file: true, counts: null, added_at: null, artwork: { status: "missing", url: null }, fetched_at: null, catalog_revision: "revision",
  delete_target: { sonarr_series_id: -3, jellyfin_item_id: "jf-series" },
  seasons: [0, 1, 2].map((number) => ({ season_number: number, title: null, episode_count: 10, episode_file_count: 8, size: 100, jellyfin_item_id: `jf-season-${number}` })),
}

describe("season deletion", () => {
  it.each(["en", "ru"] as const)("prepares only the chosen season through the keyboard (%s)", async (language) => {
    const user = userEvent.setup()
    const preview = vi.fn()
    const text = LIBRARY_COPY[language]
    render(<LibrarySeasons detail={detail} text={text} language={language} onPreview={preview} />)
    const button = screen.getByRole("button", { name: `${text.seasonDelete}: ${text.season} 2` })
    button.focus()
    await user.keyboard("{Enter}")
    expect(preview).toHaveBeenCalledTimes(1)
    expect(preview).toHaveBeenCalledWith(expect.objectContaining({ item_type: "Season", sonarr_series_id: -3, season_number: 2, jellyfin_item_id: "jf-season-2", library_resource_id: "series-resource" }), button)
    expect(buildManualDeleteRequest(preview.mock.calls[0][0], "Season 2")).toMatchObject({ item_type: "Season", season_number: 2, jellyfin_item_id: "jf-season-2" })
  })

  it("keeps specials distinct from missing or malformed season numbers", () => {
    expect(librarySeasonDeleteTarget(detail, 0)).toMatchObject({ item_type: "Season", season_number: 0, jellyfin_item_id: "jf-season-0" })
    for (const number of [-1, 1.5, NaN, 3]) expect(librarySeasonDeleteTarget(detail, number)).toBeNull()
    expect(librarySeasonDeleteTarget({ ...detail, seasons: null }, 1)).toBeNull()
    expect(librarySeasonDeleteTarget({ ...detail, delete_target: null }, 1)).toBeNull()
    expect(librarySeasonDeleteTarget({ ...detail, seasons: [detail.seasons![1], detail.seasons![1]] }, 1)).toBeNull()
  })

  it("never inherits a parent Jellyfin ID when no season binding exists", () => {
    const withoutBinding = { ...detail, seasons: [{ ...detail.seasons![1], jellyfin_item_id: null }] }
    expect(librarySeasonDeleteTarget(withoutBinding, 1)).toMatchObject({ jellyfin_item_id: null, season_number: 1 })
    render(<LibrarySeasons detail={withoutBinding} text={LIBRARY_COPY.en} language="en" onPreview={vi.fn()} />)
    expect(screen.getByText(LIBRARY_COPY.en.seasonJellyfinRetained)).toBeInTheDocument()
    const parentBinding = { ...detail, seasons: [{ ...detail.seasons![1], jellyfin_item_id: "JF-SERIES" }] }
    expect(librarySeasonDeleteTarget(parentBinding, 1)).toBeNull()
  })

  it.each(["Loading details", "Preview unavailable", "Administrator access required"])("explains disabled actions: %s", async (reason) => {
    const preview = vi.fn()
    render(<LibrarySeasons detail={detail} text={LIBRARY_COPY.en} language="en" onPreview={preview} unavailableReason={reason} />)
    expect(screen.getAllByText(reason)).toHaveLength(3)
    for (const button of screen.getAllByRole("button")) {
      expect(button).toBeDisabled()
      await userEvent.click(button)
    }
    expect(preview).not.toHaveBeenCalled()
  })
})
