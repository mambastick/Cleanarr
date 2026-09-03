import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { expect, it } from "vitest"

import { getUiText } from "@/lib/i18n"
import { ActivityPanel } from "./activity-panel"

const entry = {
  processed_at: "2026-09-03T08:00:00Z", action_summary: { radarr_delete: 1 },
  result: { item_type: "Movie" as const, item_id: "movie-1", name: "Example film", display_name: null, status: "success" as const, fingerprint: { tmdb_id: null, tvdb_id: null, imdb_id: null, path: null }, season_number: null, episode_number: null, episode_end_number: null, actions: [{ system: "radarr", action: "delete", status: "deleted" as const, message: "Removed", reason: null, details: {} }] },
}

it("presents friendly localized activity cards and keeps action codes in the inspector disclosure", async () => {
  const user = userEvent.setup()
  render(<ActivityPanel text={getUiText("ru")} filteredActivity={[entry]} webhookAttempts={[]} activityFilter="" onFilterChange={() => {}} />)
  expect(screen.getByText("Очистка обработана для Фильм")).toBeInTheDocument()
  expect(screen.getByText("Успешно")).toBeInTheDocument()
  await user.click(screen.getByRole("button", { name: "Открыть сведения" }))
  await user.click(screen.getByText("Технические сведения"))
  expect(screen.getByText("radarr/delete")).toBeInTheDocument()
})
