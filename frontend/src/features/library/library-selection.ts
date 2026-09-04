import type { ItemType } from "@/lib/dashboard"
import type { LibraryItem, ManualDeleteRequest } from "@/lib/library"

export type LibraryDeleteTarget =
  | { kind: "movie"; radarr_movie_id: number; movie_title: string; jellyfin_movie_id?: string | null; library_resource_id?: string | null }
  | { kind: "series"; sonarr_series_id: number; series_title: string; item_type: "Series" | "Season"; season_number?: number; jellyfin_item_id?: string | null; library_resource_id?: string | null }
  | { kind: "jellyfin_movie"; jellyfin_item_id: string; movie_title: string }

export interface BatchSelectionItem {
  key: string
  request: ManualDeleteRequest
  displayName: string
  itemType: Extract<ItemType, "Movie" | "Series" | "Season">
  estimatedBytes: number | null
}

export interface BatchSelection {
  order: string[]
  items: Record<string, BatchSelectionItem>
}

export const emptyBatchSelection = (): BatchSelection => ({ order: [], items: {} })

export function buildManualDeleteRequest(target: LibraryDeleteTarget, displayName: string): ManualDeleteRequest {
  if (target.kind === "jellyfin_movie") return { item_type: "Movie", jellyfin_item_id: target.jellyfin_item_id, jellyfin_only: true, display_name: displayName }
  if (target.kind === "movie") return { item_type: "Movie", radarr_movie_id: target.radarr_movie_id, jellyfin_item_id: target.jellyfin_movie_id ?? null, ...(target.library_resource_id ? { library_resource_id: target.library_resource_id } : {}), display_name: displayName }
  return { item_type: target.item_type, sonarr_series_id: target.sonarr_series_id, season_number: target.season_number ?? null, jellyfin_item_id: target.jellyfin_item_id ?? null, ...(target.library_resource_id ? { library_resource_id: target.library_resource_id } : {}), display_name: displayName }
}

export function selectionKey(request: ManualDeleteRequest): string {
  if (request.library_resource_id) return `resource:${request.library_resource_id}`
  if (request.radarr_movie_id != null) return `movie:${request.radarr_movie_id}`
  if (request.sonarr_series_id != null && request.item_type === "Series") return `series:${request.sonarr_series_id}`
  if (request.sonarr_series_id != null && request.item_type === "Season" && request.season_number != null) return `season:${request.sonarr_series_id}:${request.season_number}`
  return `unsupported:${request.item_type}:${request.jellyfin_item_id ?? "unknown"}`
}

export function selectionItem(target: LibraryDeleteTarget, displayName: string, estimatedBytes: number | null): BatchSelectionItem {
  const request = buildManualDeleteRequest(target, displayName)
  return { key: selectionKey(request), request, displayName, itemType: request.item_type as BatchSelectionItem["itemType"], estimatedBytes }
}

/**
 * Convert the untrusted Library API delete target into the existing manual
 * deletion contract. The v2 UI requires both a stable resource id and the
 * current Arr id so topology changes fail closed during backend preflight.
 */
export function libraryDeleteTargetFromItem(item: LibraryItem): LibraryDeleteTarget | null {
  if (!item.resource_id.trim()) return null
  const target = item.delete_target
  if (!target || typeof target !== "object") return null
  const jellyfinItemId = typeof target.jellyfin_item_id === "string" && target.jellyfin_item_id.length > 0
    ? target.jellyfin_item_id
    : null

  if (item.media_type === "movie") {
    const radarrMovieId = routedOrLegacyInteger(target.radarr_movie_id)
    if (radarrMovieId == null) return null
    return {
      kind: "movie",
      radarr_movie_id: radarrMovieId,
      movie_title: item.display_name,
      jellyfin_movie_id: jellyfinItemId,
      library_resource_id: item.resource_id,
    }
  }

  const sonarrSeriesId = routedOrLegacyInteger(target.sonarr_series_id)
  if (sonarrSeriesId == null) return null
  return {
    kind: "series",
    sonarr_series_id: sonarrSeriesId,
    series_title: item.display_name,
    item_type: "Series",
    jellyfin_item_id: jellyfinItemId,
    library_resource_id: item.resource_id,
  }
}

export function librarySelectionItemFromItem(item: LibraryItem): BatchSelectionItem | null {
  const target = libraryDeleteTargetFromItem(item)
  return target ? selectionItem(target, item.display_name, item.size) : null
}

function routedOrLegacyInteger(value: unknown): number | null {
  // Multi-profile Arr routers intentionally encode the routed legacy ID as a
  // negative safe integer. Zero is never a valid Arr resource identity.
  return typeof value === "number" && Number.isSafeInteger(value) && value !== 0 ? value : null
}

export function selectionConflict(selection: BatchSelection, candidate: BatchSelectionItem): string | null {
  if (selection.items[candidate.key]) return "duplicate_mutation_identity"
  const seriesId = candidate.request.sonarr_series_id
  if (seriesId == null) return null
  const sameSeries = selection.order.flatMap((key) => selection.items[key] ? [selection.items[key]] : []).filter((item) => item.request.sonarr_series_id === seriesId)
  const hasWhole = sameSeries.some((item) => item.itemType === "Series")
  const selectingWhole = candidate.itemType === "Series"
  const hasSeason = sameSeries.some((item) => item.itemType === "Season")
  return (selectingWhole && hasSeason) || (!selectingWhole && hasWhole) ? "overlapping_mutation_scope" : null
}

export function addToSelection(selection: BatchSelection, candidate: BatchSelectionItem, max = 50): { selection: BatchSelection; error: string | null } {
  const conflict = selectionConflict(selection, candidate)
  if (conflict) return { selection, error: conflict }
  if (selection.order.length >= max) return { selection, error: "batch_limit_exceeded" }
  return { selection: { order: [...selection.order, candidate.key], items: { ...selection.items, [candidate.key]: candidate } }, error: null }
}

export function removeFromSelection(selection: BatchSelection, key: string): BatchSelection {
  if (!selection.items[key]) return selection
  const items = { ...selection.items }
  delete items[key]
  return { order: selection.order.filter((value) => value !== key), items }
}

export function toggleSelection(selection: BatchSelection, candidate: BatchSelectionItem, max = 50): { selection: BatchSelection; error: string | null } {
  return selection.items[candidate.key] ? { selection: removeFromSelection(selection, candidate.key), error: null } : addToSelection(selection, candidate, max)
}

export function selectVisible(selection: BatchSelection, visible: BatchSelectionItem[], max = 50): { selection: BatchSelection; error: string | null } {
  let current = selection
  let firstError: string | null = null
  for (const item of visible) {
    if (current.items[item.key]) continue
    if (current.order.length >= max) {
      firstError ??= "batch_limit_exceeded"
      break
    }
    const result = addToSelection(current, item, max)
    current = result.selection
    firstError ??= result.error
  }
  return { selection: current, error: firstError }
}

export function selectedItems(selection: BatchSelection): BatchSelectionItem[] { return selection.order.flatMap((key) => selection.items[key] ? [selection.items[key]] : []) }
export function hiddenSelectionCount(selection: BatchSelection, visible: BatchSelectionItem[]): number { const visibleKeys = new Set(visible.map((item) => item.key)); return selection.order.filter((key) => !visibleKeys.has(key)).length }
export function batchTypeSummary(items: BatchSelectionItem[]): Record<BatchSelectionItem["itemType"], number> { return items.reduce<Record<BatchSelectionItem["itemType"], number>>((result, item) => ({ ...result, [item.itemType]: result[item.itemType] + 1 }), { Movie: 0, Series: 0, Season: 0 }) }
export function totalKnownBytes(items: BatchSelectionItem[]): { knownBytes: number; unknownCount: number } { return items.reduce((result, item) => item.estimatedBytes == null ? { ...result, unknownCount: result.unknownCount + 1 } : { ...result, knownBytes: result.knownBytes + item.estimatedBytes }, { knownBytes: 0, unknownCount: 0 }) }
