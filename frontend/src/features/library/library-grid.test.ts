import { describe, expect, it } from "vitest"
import { libraryGridBreakpoint, libraryGridColumns, libraryPageSizeOptions, type LibraryCardSize } from "./library-grid"

describe("Library poster grid", () => {
  it("mirrors every responsive grid breakpoint", () => {
    expect([639, 640, 1023, 1024, 1279, 1280, 1535, 1536].map(libraryGridBreakpoint)).toEqual([0, 640, 640, 1024, 1024, 1280, 1280, 1536])
    expect(libraryGridColumns("small", 639)).toBe(3)
    expect(libraryGridColumns("small", 640)).toBe(4)
    expect(libraryGridColumns("small", 1024)).toBe(6)
    expect(libraryGridColumns("small", 1536)).toBe(7)
    expect(libraryGridColumns("medium", 639)).toBe(2)
    expect(libraryGridColumns("medium", 640)).toBe(3)
    expect(libraryGridColumns("medium", 1024)).toBe(4)
    expect(libraryGridColumns("medium", 1280)).toBe(5)
    expect(libraryGridColumns("large", 639)).toBe(1)
    expect(libraryGridColumns("large", 640)).toBe(2)
    expect(libraryGridColumns("large", 1024)).toBe(3)
    expect(libraryGridColumns("large", 1280)).toBe(4)
  })

  it("returns full-row page sizes without exceeding the API limit", () => {
    expect(libraryPageSizeOptions("medium", 1600)).toEqual([15, 25, 50])
    expect(libraryPageSizeOptions("small", 1600)).toEqual([14, 28, 49])
    expect(libraryPageSizeOptions("large", 1600)).toEqual([12, 24, 48])

    for (const size of ["small", "medium", "large"] satisfies LibraryCardSize[]) {
      for (const width of [375, 640, 1024, 1280, 1536, 2560]) {
        const columns = libraryGridColumns(size, width)
        for (const pageSize of libraryPageSizeOptions(size, width)) {
          expect(pageSize).toBeLessThanOrEqual(50)
          expect(pageSize % columns).toBe(0)
        }
      }
    }
  })
})
