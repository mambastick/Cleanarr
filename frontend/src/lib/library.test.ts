import { afterEach, describe, expect, it, vi } from "vitest"

import { buildLibraryItemsUrl, fetchLibraryArtwork, fetchLibraryItem, fetchLibraryItems, type LibraryFetchJson } from "./library"

afterEach(() => {
  vi.unstubAllGlobals()
})

describe("library API adapter", () => {
  it("normalizes the additive backend wire shape without exposing service URLs", async () => {
    const fetchJson = vi.fn(async () => ({
      state: "partial",
      revision: "catalog-7",
      next_cursor: "opaque.next",
      failures: [{ source: "sonarr", code: "service_timeout" }],
      items: [{
        resource_id: "library-v1:sonarr:profile-a:7",
        media_type: "series",
        title: "Severance",
        display_title: "Severance",
        year: 2022,
        size_bytes: 12_345,
        episode_count: 19,
        episode_file_count: 18,
        artwork_status: "available",
        artwork_url: "/api/library/artwork/library-v1%3Asonarr%3Aprofile-a%3A7",
        delete_target: { sonarr_series_id: 7 },
      }],
    })) as unknown as LibraryFetchJson

    const result = await fetchLibraryItems(fetchJson, { media_type: "series", q: " severance ", limit: 500 })

    expect(result).toMatchObject({
      source_status: "partial",
      catalog_revision: "catalog-7",
      next_cursor: "opaque.next",
      source_failures: [{ source: "sonarr", code: "service_timeout" }],
    })
    expect(result.items[0]).toMatchObject({
      display_name: "Severance",
      size: 12_345,
      counts: { episodes: 19, files: 18 },
      artwork: { status: "available" },
    })
    expect(fetchJson).toHaveBeenCalledWith(expect.stringContaining("limit=50"), expect.anything())
    expect(buildLibraryItemsUrl({ media_type: "movie", q: " dune " })).toContain("q=dune")
  })

  it("normalizes bounded detail and defaults absent safety evidence to unknown", async () => {
    const fetchJson = vi.fn(async () => ({
      catalog_revision: "catalog-8",
      error_code: "playback_unavailable",
      item: {
        resource_id: "library-v1:radarr:profile-a:42",
        media_type: "movie",
        title: "Arrival",
        display_title: "Arrival",
        size_bytes: 2048,
        artwork_status: "missing",
        delete_target: { radarr_movie_id: 42 },
        playback_status: "unknown",
        seeding_state: "unknown",
        unknown_reasons: ["watch_data_stale"],
        series_counts: { seasons: 2, episodes: 18 },
      },
    })) as unknown as LibraryFetchJson

    const result = await fetchLibraryItem(fetchJson, "library-v1:radarr:profile-a:42")

    expect(result.safety).toEqual({ status: "unknown", reason: "playback_unavailable" })
    expect(result.unknown_reasons).toContain("playback_unavailable")
    expect(result.unknown_reasons).toContain("watch_data_stale")
    expect(result.series_counts).toEqual({ seasons: 2, episodes: 18 })
    expect(fetchJson).toHaveBeenCalledWith(
      "/api/library/items/library-v1%3Aradarr%3Aprofile-a%3A42",
      expect.anything(),
    )
  })

  it("rejects malformed list envelopes instead of showing a false empty-success state", async () => {
    const fetchJson = vi.fn(async () => ({ items: [] })) as unknown as LibraryFetchJson
    await expect(fetchLibraryItems(fetchJson, { media_type: "movie" })).rejects.toThrow("Invalid library list response")
  })

  it("preserves exact season bindings and never turns malformed numbers into specials", async () => {
    const fetchJson = vi.fn(async () => ({
      resource_id: "series-1", media_type: "series", title: "Example series",
      delete_target: { sonarr_series_id: -3, jellyfin_item_id: "parent" },
      seasons: [
        {}, { season_number: null }, { season_number: -1 }, { season_number: 1.5 },
        { season_number: 0, jellyfin_item_id: "specials" },
        { season_number: 2, jellyfin_item_id: "season-2" },
        { season_number: 3 },
      ],
    })) as unknown as LibraryFetchJson
    const detail = await fetchLibraryItem(fetchJson, "series-1")
    expect(detail.seasons).toEqual([
      expect.objectContaining({ season_number: 0, jellyfin_item_id: "specials" }),
      expect.objectContaining({ season_number: 2, jellyfin_item_id: "season-2" }),
      expect.objectContaining({ season_number: 3, jellyfin_item_id: null }),
    ])
  })
})

describe("library artwork", () => {
  it("uses authenticated same-origin Blob fetching without service credentials in the URL", async () => {
    const blob = new Blob(["image"], { type: "image/webp" })
    const fetchMock = vi.fn(async () => new Response(blob, { status: 200, headers: { "Content-Type": "image/webp" } }))
    vi.stubGlobal("fetch", fetchMock)

    await expect(fetchLibraryArtwork("library-v1:radarr:profile-a:42")).resolves.toEqual(blob)
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/library/artwork/library-v1%3Aradarr%3Aprofile-a%3A42",
      expect.objectContaining({ credentials: "same-origin", headers: { Accept: "image/*" } }),
    )
    expect(JSON.stringify(fetchMock.mock.calls)).not.toMatch(/api[_-]?key|token|jellyfin/i)
  })

  it("rejects non-success responses", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(null, { status: 404 })))
    await expect(fetchLibraryArtwork("missing")).rejects.toThrow("Artwork request failed (404)")
  })
})
