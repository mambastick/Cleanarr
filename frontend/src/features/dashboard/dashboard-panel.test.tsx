import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { expect, it, vi } from "vitest"

import { getUiText } from "@/lib/i18n"
import { DashboardPanel } from "./dashboard-panel"

const dashboard = {
  service: { name: "CleanArr", version: "1.0", dry_run: true, log_level: "INFO", downloader_kind: "qbittorrent", webhook_token_configured: true, activity_retention_days: 30 },
  endpoints: [], rules: [], jellyfin_template: "", sample_payload: {}, recent_activity: [], webhook_attempts: [],
  downstream: [{ name: "Radarr", role: "Movies", url: "https://radarr.private.example", configured: true, health_status: "healthy" as const }],
  webhook_status: { attempted_at: null, outcome: "unknown", http_status: null, message: "", notification_type: null, item_type: null, item_name: null, result_status: null },
}

it("uses controlled runtime tabs once and keeps service URLs behind disclosure", async () => {
  const user = userEvent.setup()
  let resolveToggle: (() => void) | undefined
  const onToggleDryRun = vi.fn(() => new Promise<void>((resolve) => { resolveToggle = resolve }))
  render(<DashboardPanel text={getUiText("en")} dashboard={dashboard} isDashboardLoading={false} setupCompletionCount={5} deletedActions={2} latestActivity={null} allServicesConfigured isLive={false} onToggleDryRun={onToggleDryRun} onOpenWizard={() => {}} onEditService={() => {}} storage={null} />)
  expect(screen.getByRole("tab", { name: "Dry run" })).toHaveAttribute("aria-selected", "true")
  expect(screen.getByText(/CleanArr reads free space for each media folder/)).toBeInTheDocument()
  expect(screen.getByText("Movies")).toBeInTheDocument()
  expect(screen.getAllByText("Technical details")[0]?.closest("details")).not.toHaveAttribute("open")
  await user.dblClick(screen.getByRole("tab", { name: "Real deletion" }))
  expect(onToggleDryRun).toHaveBeenCalledTimes(1)
  resolveToggle?.()
  await waitFor(() => expect(screen.getByRole("tab", { name: "Real deletion" })).not.toBeDisabled())
})

it("explains recent skipped actions without exposing raw status keys", async () => {
  const latestActivity = {
    processed_at: "2026-01-01T00:00:00Z",
    action_summary: { skipped: 2 },
    result: {
      item_type: "Movie" as const,
      item_id: "item",
      name: "Example",
      status: "success" as const,
      fingerprint: { tmdb_id: null, tvdb_id: null, imdb_id: null, path: null },
      season_number: null,
      episode_number: null,
      episode_end_number: null,
      actions: [],
    },
  }
  render(<DashboardPanel text={getUiText("ru")} dashboard={dashboard} isDashboardLoading={false} setupCompletionCount={5} deletedActions={2} latestActivity={latestActivity} allServicesConfigured isLive={false} onToggleDryRun={async () => {}} onOpenWizard={() => {}} onEditService={() => {}} storage={null} storageLanguage="ru" />)

  await userEvent.click(screen.getByText("Что произошло"))
  expect(screen.getByText("2 безопасно пропущено")).toBeInTheDocument()
  expect(screen.queryByText(/skipped:/)).not.toBeInTheDocument()
})
