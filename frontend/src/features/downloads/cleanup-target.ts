import type { CleanupCandidate } from "@/lib/downloads"
import type { LibraryDeleteTarget } from "@/features/library/library-selection"

export function cleanupTarget(candidate: CleanupCandidate): LibraryDeleteTarget | null {
  const link = candidate.deletion_link
  if (!link) return null
  if (link.item_type === "Movie" && link.radarr_movie_id != null) return { kind: "movie", radarr_movie_id: link.radarr_movie_id, movie_title: link.display_name, jellyfin_movie_id: link.jellyfin_item_id }
  if (link.item_type === "Series" && link.sonarr_series_id != null) return { kind: "series", sonarr_series_id: link.sonarr_series_id, series_title: link.display_name, item_type: "Series", jellyfin_item_id: link.jellyfin_item_id }
  return null
}
