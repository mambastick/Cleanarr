import { describe, expect, it } from "vitest"
import type { LibraryItem } from "@/lib/library"
import { addToSelection, emptyBatchSelection, hiddenSelectionCount, libraryDeleteTargetFromItem, librarySelectionItemFromItem, selectVisible, selectionItem, toggleSelection } from "./library-selection"

const movie = (id: number) => selectionItem({ kind: "movie", radarr_movie_id: id, movie_title: `Movie ${id}`, jellyfin_movie_id: `jellyfin-${id}` }, `Movie ${id}`, id * 10)
const series = () => selectionItem({ kind: "series", sonarr_series_id: 9, series_title: "Series", item_type: "Series", jellyfin_item_id: "series-jf" }, "Series", 100)
const season = (number: number) => selectionItem({ kind: "series", sonarr_series_id: 9, series_title: "Series", item_type: "Season", season_number: number, jellyfin_item_id: `season-${number}` }, `Season ${number} · Series`, 20)

describe("batch library selection", () => {
  it("requires stable resource and valid Arr identities for v2 deletion", () => {
    const item: LibraryItem = {
      resource_id: "library-v1:radarr:profile-a:42",
      media_type: "movie",
      display_name: "Arrival",
      title: "Arrival",
      year: 2016,
      size: 1024,
      has_file: true,
      counts: null,
      added_at: null,
      artwork: { status: "available", url: "/api/library/artwork/library-v1%3Aradarr%3Aprofile-a%3A42" },
      delete_target: { radarr_movie_id: 42, jellyfin_item_id: "jf-42" },
      fetched_at: null,
      catalog_revision: "revision-1",
    }

    expect(libraryDeleteTargetFromItem(item)).toMatchObject({
      kind: "movie",
      radarr_movie_id: 42,
      library_resource_id: item.resource_id,
    })
    expect(librarySelectionItemFromItem(item)?.request).toMatchObject({
      item_type: "Movie",
      radarr_movie_id: 42,
      library_resource_id: item.resource_id,
    })
    expect(librarySelectionItemFromItem(item)?.key).toBe(`resource:${item.resource_id}`)
    expect(libraryDeleteTargetFromItem({ ...item, resource_id: "" })).toBeNull()
    expect(libraryDeleteTargetFromItem({ ...item, delete_target: { radarr_movie_id: 0 } })).toBeNull()
    expect(libraryDeleteTargetFromItem({ ...item, delete_target: { sonarr_series_id: 42 } })).toBeNull()
    expect(libraryDeleteTargetFromItem({ ...item, delete_target: { radarr_movie_id: -42 } })).toMatchObject({
      radarr_movie_id: -42,
      library_resource_id: item.resource_id,
    })
  })

  it("uses stable semantic IDs across filters and records hidden selections", () => {
    const selected = addToSelection(emptyBatchSelection(), movie(1)).selection
    expect(selected.order).toEqual(["movie:1"])
    expect(hiddenSelectionCount(selected, [movie(2)])).toBe(1)
    expect(hiddenSelectionCount(selected, [movie(1)])).toBe(0)
  })

  it("rejects duplicate Arr targets and whole-series/season overlap without replacing selection", () => {
    const selected = addToSelection(emptyBatchSelection(), season(1)).selection
    expect(addToSelection(selected, series()).error).toBe("overlapping_mutation_scope")
    expect(addToSelection(emptyBatchSelection(), movie(1)).error).toBeNull()
    const movieSelected = addToSelection(emptyBatchSelection(), movie(1)).selection
    expect(toggleSelection(movieSelected, movie(1)).selection.order).toHaveLength(0)
    expect(addToSelection(movieSelected, movie(1)).error).toBe("duplicate_mutation_identity")
  })

  it("selects 50 visible items and visibly blocks the 51st", () => {
    const fifty = Array.from({ length: 50 }, (_, index) => movie(index + 1))
    const selected = selectVisible(emptyBatchSelection(), fifty)
    expect(selected.error).toBeNull()
    expect(selected.selection.order).toHaveLength(50)
    expect(addToSelection(selected.selection, movie(51)).error).toBe("batch_limit_exceeded")
  })

  it("continues past preselected and overlapping visible entries to select independent targets", () => {
    const preselected = addToSelection(emptyBatchSelection(), movie(1)).selection
    const result = selectVisible(preselected, [movie(1), season(1), series(), movie(2)])
    expect(result.error).toBe("overlapping_mutation_scope")
    expect(result.selection.order).toEqual(["movie:1", "season:9:1", "movie:2"])
  })

  it("honours the 50-item cap after prior hidden selection while continuing over duplicates", () => {
    const hidden = addToSelection(emptyBatchSelection(), movie(1)).selection
    const visible = [movie(1), ...Array.from({ length: 50 }, (_, index) => movie(index + 2))]
    const result = selectVisible(hidden, visible)
    expect(result.selection.order).toHaveLength(50)
    expect(result.selection.order).toContain("movie:50")
    expect(result.selection.order).not.toContain("movie:51")
    expect(result.error).toBe("batch_limit_exceeded")
  })
})
