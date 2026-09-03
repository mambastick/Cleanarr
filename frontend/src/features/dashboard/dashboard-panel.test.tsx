import { render, screen } from "@testing-library/react"
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
  expect(screen.getByText(/Storage is read from each configured Radarr and Sonarr root folder/)).toBeInTheDocument()
  expect(screen.getByText("Movie cleanup target used to resolve and delete movies.")).toBeInTheDocument()
  expect(screen.getAllByText("Technical details")[0]?.closest("details")).not.toHaveAttribute("open")
  await user.dblClick(screen.getByRole("tab", { name: "Live" }))
  expect(onToggleDryRun).toHaveBeenCalledTimes(1)
  resolveToggle?.()
})
