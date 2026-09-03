import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"
import { LibraryPanelV2 } from "./library-v2-panel"
import { LIBRARY_COPY } from "./library-copy"
import type { LibraryItem, LibraryItemDetail, LibraryItemsResponse } from "@/lib/library"

const item: LibraryItem = { resource_id: "movie-1", media_type: "movie", display_name: "Dune: Part Two", title: "Dune: Part Two", year: 2024, size: 38_400_000_000, has_file: true, counts: null, added_at: "2026-01-01", artwork: { status: "missing", url: null }, delete_target: { item_type: "Movie", radarr_movie_id: 1 }, fetched_at: "2026-01-01", catalog_revision: "rev-1" }
const detail: LibraryItemDetail = { ...item, playback: { watched: "never_watched", play_count: 0, last_played_at: null, freshness: "fresh" }, library_dates: { added_at: item.added_at, updated_at: null }, seeding: { state: "seeding", readiness: "ready", ratio: 2.4, seeded_seconds: 86400, reason: null }, seasons: null, safety: { status: "safe", reason: null } }
const api = (page: LibraryItemsResponse = { items: [item], next_cursor: null, source_status: "complete", source_failures: [], catalog_revision: "rev-1" }) => vi.fn((url: string) => Promise.resolve(url.includes("/items/movie-1") ? detail : page)) as unknown as Parameters<typeof LibraryPanelV2>[0]["fetchJson"]

describe("LibraryPanelV2", () => {
  it("keeps deletion preview single-shot and opens detail from the card body in normal mode", async () => {
    const user = userEvent.setup()
    const onDeletePreview = vi.fn()
    const fetchJson = api()
    render(<LibraryPanelV2 active authenticated fetchJson={fetchJson} copy={LIBRARY_COPY.en} onDeletePreview={onDeletePreview} />)
    await waitFor(() => expect(screen.getByText("Dune: Part Two")).toBeInTheDocument())
    const trash = screen.getByRole("button", { name: /Review deletion plan: Dune/ })
    expect(trash).toHaveClass("library-card__delete", "bg-destructive!")
    await user.click(trash)
    expect(onDeletePreview).toHaveBeenCalledTimes(1)
    await user.click(screen.getByText("Dune: Part Two").closest("button")!)
    await waitFor(() => expect(screen.getByText("Technical details")).toBeInTheDocument())
    expect(fetchJson).toHaveBeenCalledWith(expect.stringContaining("/api/library/items/movie-1"), expect.anything())
  })

  it("uses poster and card body clicks for selection mode without opening the inspector", async () => {
    const user = userEvent.setup()
    const unlinked = { ...item, resource_id: "movie-unlinked", display_name: "Unlinked movie", title: "Unlinked movie", delete_target: null }
    const fetchJson = api({ items: [item, unlinked], next_cursor: null, source_status: "complete", source_failures: [], catalog_revision: "rev-1" })
    render(<LibraryPanelV2 active authenticated fetchJson={fetchJson} copy={LIBRARY_COPY.en} />)

    await waitFor(() => expect(screen.getByText("Dune: Part Two")).toBeInTheDocument())
    await user.click(screen.getByRole("button", { name: "Select" }))
    await user.click(screen.getByText("Dune: Part Two").closest("button")!)
    expect(screen.getByText(/1 selected/)).toBeInTheDocument()
    expect(screen.queryByText("Technical details")).not.toBeInTheDocument()

    const poster = screen.getAllByRole("button", { name: "Select: Dune: Part Two" })[0]
    await user.click(poster!)
    expect(screen.queryByText(/1 selected/)).not.toBeInTheDocument()
    expect(screen.queryByText("Technical details")).not.toBeInTheDocument()

    expect(screen.getByText(LIBRARY_COPY.en.selectionUnavailable)).toBeInTheDocument()
    expect(screen.getByRole("checkbox", { name: "Select: Unlinked movie" })).toHaveAttribute("aria-disabled", "true")
    expect(screen.getAllByRole("button", { name: "Select: Unlinked movie" })[0]).toBeDisabled()
  })

  it("clears the current selection when leaving selection mode", async () => {
    const user = userEvent.setup()
    render(<LibraryPanelV2 active authenticated fetchJson={api()} copy={LIBRARY_COPY.en} />)
    await waitFor(() => expect(screen.getByText("Dune: Part Two")).toBeInTheDocument())
    await user.click(screen.getByRole("button", { name: "Select" }))
    await user.click(screen.getByRole("checkbox", { name: /Select: Dune/ }))
    expect(screen.getByText(/1 selected/)).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "Done" }))
    expect(screen.queryByText(/1 selected/)).not.toBeInTheDocument()
  })

  it("requests server-sorted pages when the sort select and direction control change", async () => {
    const user = userEvent.setup()
    const alpha = { ...item, resource_id: "movie-alpha", display_name: "Alpha", title: "Alpha" }
    const zeta = { ...item, resource_id: "movie-zeta", display_name: "Zeta", title: "Zeta" }
    const fetchJson = vi.fn((url: string) => {
      if (url.includes("sort=title") && url.includes("direction=asc")) return Promise.resolve({ items: [alpha, zeta], next_cursor: null, source_status: "complete", source_failures: [], catalog_revision: "rev-1" })
      if (url.includes("sort=title") && url.includes("direction=desc")) return Promise.resolve({ items: [zeta, alpha], next_cursor: null, source_status: "complete", source_failures: [], catalog_revision: "rev-1" })
      return Promise.resolve({ items: [zeta, alpha], next_cursor: null, source_status: "complete", source_failures: [], catalog_revision: "rev-1" })
    }) as unknown as Parameters<typeof LibraryPanelV2>[0]["fetchJson"]
    render(<LibraryPanelV2 active authenticated fetchJson={fetchJson} copy={LIBRARY_COPY.en} />)

    await waitFor(() => expect(screen.getByText("Zeta")).toBeInTheDocument())
    const sort = screen.getByRole("combobox", { name: "Sort" })
    await user.click(sort)
    await user.click(screen.getByRole("option", { name: "Title" }))
    await waitFor(() => expect(fetchJson).toHaveBeenCalledWith(expect.stringContaining("sort=title&direction=desc"), expect.anything()))
    await waitFor(() => expect(screen.getAllByRole("listitem").map((card) => card.textContent)).toEqual([expect.stringContaining("Zeta"), expect.stringContaining("Alpha")]))

    await user.click(screen.getByRole("button", { name: "Descending" }))
    await waitFor(() => expect(fetchJson).toHaveBeenCalledWith(expect.stringContaining("sort=title&direction=asc"), expect.anything()))
    await waitFor(() => expect(screen.getAllByRole("listitem").map((card) => card.textContent)).toEqual([expect.stringContaining("Alpha"), expect.stringContaining("Zeta")]))
  })

  it("persists selections across tabs, exposes hidden count, and caps at fifty", async () => {
    const user = userEvent.setup()
    const fetchJson = api()
    render(<LibraryPanelV2 active authenticated fetchJson={fetchJson} copy={LIBRARY_COPY.en} />)
    await waitFor(() => expect(screen.getByText("Dune: Part Two")).toBeInTheDocument())
    await user.click(screen.getByRole("button", { name: "Select" }))
    await user.click(screen.getByRole("checkbox", { name: /Select: Dune/ }))
    expect(screen.getByText(/1 selected/)).toBeInTheDocument()
    await user.click(screen.getByRole("tab", { name: /Series/ }))
    expect(screen.getByText(/1 selected/)).toBeInTheDocument()
  })

  it("visibly refuses a fifty-first selection", async () => {
    const items = Array.from({ length: 51 }, (_, index): LibraryItem => ({
      ...item,
      resource_id: `movie-${index + 1}`,
      display_name: `Movie ${index + 1}`,
      title: `Movie ${index + 1}`,
      delete_target: { radarr_movie_id: index + 1 },
    }))
    const fetchJson = api({ items, next_cursor: null, source_status: "complete", source_failures: [], catalog_revision: "rev-1" })
    render(<LibraryPanelV2 active authenticated fetchJson={fetchJson} copy={LIBRARY_COPY.en} />)
    await waitFor(() => expect(screen.getByText("Movie 51")).toBeInTheDocument())
    fireEvent.click(screen.getByRole("button", { name: "Select" }))
    fireEvent.click(screen.getByRole("button", { name: "Select visible" }))
    expect(screen.getByText(/50 selected/)).toBeInTheDocument()
    expect(screen.getByRole("alert")).toHaveTextContent(LIBRARY_COPY.en.selectionLimit)
  })

  it("keeps stale hidden selections visible but blocks batch review after a catalog revision change", async () => {
    const user = userEvent.setup()
    let call = 0
    const revisedItem: LibraryItem = {
      ...item,
      resource_id: "movie-2",
      display_name: "Revised movie",
      title: "Revised movie",
      catalog_revision: "rev-2",
      delete_target: { item_type: "Movie", radarr_movie_id: 2 },
    }
    const fetchJson = vi.fn(() => {
      call += 1
      return Promise.resolve(
        call === 1
          ? { items: [item], next_cursor: "next", source_status: "complete", source_failures: [], catalog_revision: "rev-1" }
          : { items: [revisedItem], next_cursor: null, source_status: "complete", source_failures: [], catalog_revision: "rev-2" },
      )
    }) as unknown as Parameters<typeof LibraryPanelV2>[0]["fetchJson"]
    render(<LibraryPanelV2 active authenticated fetchJson={fetchJson} copy={LIBRARY_COPY.en} onBatchPreview={vi.fn()} />)
    await waitFor(() => expect(screen.getByText("Dune: Part Two")).toBeInTheDocument())
    await user.click(screen.getByRole("button", { name: "Select" }))
    await user.click(screen.getByRole("checkbox", { name: /Select: Dune/ }))
    await user.click(screen.getByRole("button", { name: "Next" }))

    await waitFor(() => expect(screen.getByText(LIBRARY_COPY.en.selectionNeedsReview)).toBeInTheDocument())
    expect(screen.getByRole("button", { name: "Review deletion plan" })).toBeDisabled()
    expect(screen.getByText(/1 hidden/)).toBeInTheDocument()
  })

  it("keeps a valid selection across movie and series catalogs with independent revisions", async () => {
    const movieItem: LibraryItem = { ...item, catalog_revision: "movie-rev-1" }
    const seriesItem: LibraryItem = {
      ...item,
      resource_id: "series-1",
      media_type: "series",
      display_name: "Severance",
      title: "Severance",
      catalog_revision: "series-rev-1",
      delete_target: { sonarr_series_id: 7 },
    }
    const fetchJson = vi.fn((url: string) => Promise.resolve(
      url.includes("media_type=series")
        ? { items: [seriesItem], next_cursor: null, source_status: "complete", source_failures: [], catalog_revision: "series-rev-1" }
        : { items: [movieItem], next_cursor: null, source_status: "complete", source_failures: [], catalog_revision: "movie-rev-1" },
    )) as unknown as Parameters<typeof LibraryPanelV2>[0]["fetchJson"]
    const onBatchPreview = vi.fn()
    const user = userEvent.setup()
    render(<LibraryPanelV2 active authenticated fetchJson={fetchJson} copy={LIBRARY_COPY.en} onBatchPreview={onBatchPreview} />)

    await waitFor(() => expect(screen.getByText("Dune: Part Two")).toBeInTheDocument())
    await user.click(screen.getByRole("button", { name: "Select" }))
    await user.click(screen.getByRole("checkbox", { name: "Select: Dune: Part Two" }))
    await user.click(screen.getByRole("tab", { name: "Series" }))
    await user.click(await screen.findByRole("checkbox", { name: "Select: Severance" }))

    const review = screen.getByRole("button", { name: "Review deletion plan" })
    expect(review).toBeEnabled()
    await user.click(review)
    expect(onBatchPreview).toHaveBeenCalledWith(
      expect.arrayContaining([
        expect.objectContaining({ resource_id: "movie-1" }),
        expect.objectContaining({ resource_id: "series-1" }),
      ]),
      expect.any(HTMLElement),
    )
  })

  it("ignores late detail responses after a controlled reset", async () => {
    let resolveDetail: ((value: LibraryItemDetail) => void) | undefined
    const fetchJson = vi.fn((url: string) => url.includes("/items/movie-1")
      ? new Promise<LibraryItemDetail>((resolve) => { resolveDetail = resolve })
      : Promise.resolve({ items: [item], next_cursor: null, source_status: "complete", source_failures: [], catalog_revision: "rev-1" })) as unknown as Parameters<typeof LibraryPanelV2>[0]["fetchJson"]
    const { rerender } = render(<LibraryPanelV2 active authenticated fetchJson={fetchJson} copy={LIBRARY_COPY.en} resetKey={0} />)
    await waitFor(() => expect(screen.getByText("Dune: Part Two")).toBeInTheDocument())
    fireEvent.click(screen.getByRole("button", { name: /Dune: Part Two, Movie/ }))
    await waitFor(() => expect(screen.getByText("Loading current safety evidence…")).toBeInTheDocument())
    rerender(<LibraryPanelV2 active authenticated fetchJson={fetchJson} copy={LIBRARY_COPY.en} resetKey={1} />)
    resolveDetail?.(detail)
    await Promise.resolve()
    expect(screen.queryByText("Loading current safety evidence…")).not.toBeInTheDocument()
    expect(screen.queryByText("Technical details")).not.toBeInTheDocument()
  })

  it("renders Russian copy without English technical labels", async () => {
    const fetchJson = api()
    render(<LibraryPanelV2 active authenticated language="ru" fetchJson={fetchJson} />)
    await waitFor(() => expect(screen.getByText("Библиотека")).toBeInTheDocument())
    expect(screen.getByPlaceholderText("Поиск по библиотеке")).toBeInTheDocument()
    expect(screen.queryByText("Search library")).not.toBeInTheDocument()
  })
})
