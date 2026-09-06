import { Trash2 } from "lucide-react"

import { Button } from "@/components/ui/button"
import type { LibraryItemDetail } from "@/lib/library"
import type { LibraryLanguage, LibraryV2Copy } from "./library-copy"
import { librarySeasonDeleteTarget, type LibraryDeleteTarget } from "./library-selection"

export function LibrarySeasons({ detail, text, language, onPreview, unavailableReason }: {
  detail: LibraryItemDetail
  text: LibraryV2Copy
  language: LibraryLanguage
  onPreview?: (target: LibraryDeleteTarget, trigger: HTMLElement) => void
  unavailableReason?: string
}) {
  const count = detail.seasons?.length ?? detail.series_counts?.seasons ?? detail.counts?.seasons
  if (detail.media_type !== "series" || count == null) return null
  const episodes = detail.seasons?.every((season) => season.episode_count != null)
    ? detail.seasons.reduce((sum, season) => sum + (season.episode_count ?? 0), 0)
    : detail.series_counts?.episodes ?? detail.counts?.episodes

  return <section className="rounded-xl border border-border p-3 text-sm" aria-label={text.seasonBreakdown}>
    <h3 className="font-medium">{text.seasonBreakdown}</h3>
    <p className="mt-1 text-muted-foreground">{count} {mediaUnitLabel(count, "season", language)} · {episodes == null ? `${text.unknown} ${text.episodes.toLowerCase()}` : `${episodes} ${mediaUnitLabel(episodes, "episode", language)}`}</p>
    {detail.seasons?.length ? <>
      <p className="mt-2 text-xs text-muted-foreground">{text.seasonDeleteHint}</p>
      <ul className="mt-3 divide-y divide-border rounded-lg border border-border">
        {detail.seasons.map((season) => {
          const target = librarySeasonDeleteTarget(detail, season.season_number)
          const reason = unavailableReason ?? (!onPreview || !target ? text.deleteUnavailable : undefined)
          const name = `${text.season} ${season.season_number}`
          return <li key={season.season_number} className="space-y-2 px-3 py-3">
            <div className="min-w-0"><p className="break-words font-medium">{season.title || name}</p><p className="mt-1 text-xs text-muted-foreground">{season.episode_file_count ?? text.unknown}/{season.episode_count ?? text.unknown} {mediaUnitLabel(season.episode_count, "episode", language)}{season.size != null ? ` · ${formatSize(season.size)}` : ""}</p></div>
            <Button variant="outline" className="min-h-11 w-full text-status-danger" disabled={Boolean(reason)} aria-label={`${text.seasonDelete}: ${name}`} onClick={(event) => { if (target && !reason) onPreview?.(target, event.currentTarget) }}><Trash2 aria-hidden="true" />{text.seasonDelete}</Button>
            {target?.kind === "series" && !target.jellyfin_item_id ? <p className="text-xs text-muted-foreground">{text.seasonJellyfinRetained}</p> : null}
            {reason ? <p className="text-xs text-muted-foreground">{reason}</p> : null}
          </li>
        })}
      </ul>
    </> : null}
  </section>
}

function mediaUnitLabel(value: number | null | undefined, unit: "season" | "episode", language: LibraryLanguage) {
  if (language === "en") return value === 1 ? unit : `${unit}s`
  const forms = unit === "season" ? ["сезон", "сезона", "сезонов"] : ["эпизод", "эпизода", "эпизодов"]
  if (value == null) return forms[2]
  const lastTwo = value % 100
  if (lastTwo >= 11 && lastTwo <= 14) return forms[2]
  const last = value % 10
  return last === 1 ? forms[0] : last >= 2 && last <= 4 ? forms[1] : forms[2]
}

function formatSize(size: number) {
  if (!size) return "0 B"
  const index = Math.min(4, Math.floor(Math.log(size) / Math.log(1024)))
  return `${(size / 1024 ** index).toFixed(1)} ${["B", "KB", "MB", "GB", "TB"][index]}`
}
