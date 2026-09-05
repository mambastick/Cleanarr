export type LibraryCardSize = "small" | "medium" | "large"

const PAGE_SIZE_TARGETS = [12, 24, 48] as const
const MAX_PAGE_SIZE = 50

const CARD_GRID_CLASSES: Record<LibraryCardSize, string> = {
  small: "grid-cols-3 sm:grid-cols-4 lg:grid-cols-6 2xl:grid-cols-7",
  medium: "grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5",
  large: "grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4",
}

export function cardGridClass(size: LibraryCardSize) {
  return CARD_GRID_CLASSES[size]
}

export function libraryGridBreakpoint(viewportWidth: number) {
  if (viewportWidth >= 1536) return 1536
  if (viewportWidth >= 1280) return 1280
  if (viewportWidth >= 1024) return 1024
  if (viewportWidth >= 640) return 640
  return 0
}

/** Mirrors the Tailwind breakpoints in CARD_GRID_CLASSES. */
export function libraryGridColumns(size: LibraryCardSize, viewportWidth: number) {
  const breakpoint = libraryGridBreakpoint(viewportWidth)
  if (size === "small") {
    if (breakpoint >= 1536) return 7
    if (breakpoint >= 1024) return 6
    if (breakpoint >= 640) return 4
    return 3
  }
  if (size === "large") {
    if (breakpoint >= 1280) return 4
    if (breakpoint >= 1024) return 3
    if (breakpoint >= 640) return 2
    return 1
  }
  if (breakpoint >= 1280) return 5
  if (breakpoint >= 1024) return 4
  if (breakpoint >= 640) return 3
  return 2
}

export function libraryPageSizeOptions(size: LibraryCardSize, viewportWidth: number) {
  const columns = libraryGridColumns(size, viewportWidth)
  const maximumFullPage = Math.floor(MAX_PAGE_SIZE / columns) * columns
  return PAGE_SIZE_TARGETS.map((target) => Math.min(Math.ceil(target / columns) * columns, maximumFullPage))
}
