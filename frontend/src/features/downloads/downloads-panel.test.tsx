import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { expect, it, vi } from "vitest"

import { DownloadsPanel } from "./downloads-panel"

const item = {
  client_id: "client-a", client_name: "Client A", client_kind: "qbittorrent", info_hash: "a".repeat(40), observed_at: "2026-01-01T00:00:00Z", display_name: "Example download", state: "seeding" as const, freshness: "fresh" as const, ownership: "managed" as const,
  progress: null, total_bytes: null, downloaded_bytes: null, uploaded_bytes: null, ratio: null, seeding_time_seconds: null, download_speed_bytes_per_second: null, upload_speed_bytes_per_second: null, eta_seconds: null, added_at: null, completed_at: null, activity_at: null, category: null, tags: null, tracker_summary: null, unavailable_reason: null, policy_decision: null, policy_reason_code: null, policy_facts: null, latest_action: null,
}
const downloads = { items: [item], next_cursor: null, source_status: "complete", failures: [], failure_details: [], active_count: 1 }

type FetchJson = <T>(url: string, init?: RequestInit) => Promise<T>
function renderPanel(fetchJson: FetchJson = async <T,>() => downloads as T, language: "en" | "ru" = "en") {
  return render(<DownloadsPanel active authenticated language={language} isLive={false} fetchJson={fetchJson} onActiveCountChange={() => {}} onDelete={() => {}} onBatchPreview={() => {}} />)
}

it("loads only the active panel and sends one reversible action under rapid clicks", async () => {
  const fetchJson: FetchJson & { mock: ReturnType<typeof vi.fn>["mock"] } = vi.fn((url: string) => url.includes("/actions") ? new Promise<{ action_id: string; status: string; code: null }>(() => {}) : Promise.resolve(downloads)) as unknown as FetchJson & { mock: ReturnType<typeof vi.fn>["mock"] }
  const user = userEvent.setup()
  renderPanel(fetchJson)
  await screen.findByText("Example download")
  const pause = screen.getByRole("button", { name: "Pause" })
  await user.dblClick(pause)
  await waitFor(() => expect(fetchJson.mock.calls.filter(([url]) => url === "/api/downloads/actions")).toHaveLength(1))
  const actionCall = fetchJson.mock.calls.find((call) => call[0] === "/api/downloads/actions") as [string, RequestInit]
  const body = JSON.parse(actionCall[1].body as string)
  expect(body.action).toBe("pause")
  expect(body).not.toHaveProperty("delete")
})

it("shows unknown values rather than zero and keeps an incomplete candidate out of deletion planning", async () => {
  const fetchJson: FetchJson = vi.fn(async (url: string) => (url.includes("cleanup-candidates") ? { items: [{ jellyfin_item_id: "safe-test", display_name: "No link", media_type: "movie", created_at: null, added_at: null, size_bytes: null, playback_status: "unknown", play_count: null, watched_user_count: null, last_played_at: null, playback_unavailable_reason: "missing", data_source: "jellyfin_standard", fetched_at: "2026-01-01T00:00:00Z", unavailable_reason: null, seeding: { torrent_state: "unknown", readiness: "unknown", readiness_reason: null, torrent_count: null, ratio: null, seeding_time_seconds: null, unavailable_reason: null }, deletion_link: null }], next_cursor: null, source_status: "partial", failure_codes: [], truncated: true } : downloads) as never)
  const user = userEvent.setup()
  renderPanel(fetchJson)
  await screen.findByText("Example download")
  expect(screen.getByText(/Progress: Unknown/)).toBeInTheDocument()
  expect(screen.getByText("Download speed: Unknown")).toBeInTheDocument()
  expect(screen.queryByText("Download speed: Unknown/s")).not.toBeInTheDocument()
  expect(screen.getByRole("progressbar", { name: "Progress" }).querySelector("[data-slot=progress-indicator]")).toHaveClass("hidden")
  await user.click(screen.getByRole("tab", { name: "Cleanup candidates" }))
  await screen.findByText("No link")
  expect(screen.getByText(/no safe library link/i)).toBeInTheDocument()
  expect(screen.queryByRole("button", { name: "Review deletion plan" })).not.toBeInTheDocument()
})

it("renders Russian downloads navigation copy", async () => {
  const cleanup = { items: [], next_cursor: null, source_status: "complete", failure_codes: [], truncated: false }
  const fetchJson: FetchJson = async <T,>(url: string) => (url.includes("cleanup-candidates") ? cleanup : downloads) as T
  const user = userEvent.setup()
  renderPanel(fetchJson, "ru")
  expect(await screen.findByRole("tab", { name: "Торренты" })).toBeInTheDocument()
  expect(screen.getByRole("button", { name: "Обновить сейчас" })).toBeInTheDocument()
  await user.click(screen.getByRole("tab", { name: "Кандидаты очистки" }))
  expect(await screen.findByRole("combobox", { name: "Статус источника" })).toHaveTextContent("Все")
  expect(screen.getByRole("combobox", { name: "Медиа" })).toHaveTextContent("Все")
  expect(screen.getByRole("combobox", { name: "Состояние безопасности" })).toHaveTextContent("Все")
  expect(screen.getByRole("combobox", { name: "Сортировка" })).toHaveTextContent("Недавно добавленные")
  expect(screen.getByRole("combobox", { name: "Порядок" })).toHaveTextContent("По убыванию")
  expect(screen.queryByText("library_added")).not.toBeInTheDocument()
})

it("retries an uncertain reversible action with its exact original body", async () => {
  const fetchMock = vi.fn((url: string) => {
    if (url === "/api/downloads/actions") {
      const actionCalls = fetchMock.mock.calls.filter(([calledUrl]) => calledUrl === "/api/downloads/actions")
      return Promise.resolve(actionCalls.length === 1 ? { action_id: "a", status: "uncertain", code: "timeout" } : { action_id: "a", status: "simulated", code: null })
    }
    return Promise.resolve(downloads)
  })
  const fetchJson = fetchMock as unknown as FetchJson
  const user = userEvent.setup()
  renderPanel(fetchJson)
  await screen.findByText("Example download")
  await user.click(screen.getByRole("button", { name: "Pause" }))
  expect(await screen.findByRole("status")).toHaveTextContent("uncertain")
  await user.click(screen.getByRole("button", { name: "Retry the same action" }))
  await waitFor(() => expect(fetchMock.mock.calls.filter(([url]) => url === "/api/downloads/actions")).toHaveLength(2))
  const actionCalls = (fetchMock.mock.calls as unknown as Array<[string, RequestInit]>).filter(([url]) => url === "/api/downloads/actions")
  expect(actionCalls[1]![1].body).toBe(actionCalls[0]![1].body)
})

it("uses the safe deletion-link display name and reports localized partial provenance", async () => {
  const fetchJson: FetchJson = vi.fn(async (url: string) => (url.includes("cleanup-candidates") ? { items: [{ jellyfin_item_id: "safe-test", display_name: "Untrusted candidate title", media_type: "movie", created_at: null, added_at: null, size_bytes: null, playback_status: "unknown", play_count: null, watched_user_count: null, last_played_at: null, playback_unavailable_reason: "playback_observation_incomplete", data_source: "jellyfin_standard", fetched_at: "2026-01-01T00:00:00Z", unavailable_reason: null, seeding: { torrent_state: "not_present", readiness: "blocked", readiness_reason: "no_arr_hashes", torrent_count: 0, ratio: null, seeding_time_seconds: null, unavailable_reason: null }, deletion_link: { item_type: "Movie", radarr_movie_id: 4, sonarr_series_id: null, jellyfin_item_id: "safe-test", display_name: "Safe linked title" } }], next_cursor: null, source_status: "partial", failure_codes: ["jellyfin_catalog_unavailable"], truncated: false } : downloads) as never)
  const user = userEvent.setup()
  const onDelete = vi.fn()
  render(<DownloadsPanel active authenticated language="en" isLive={false} fetchJson={fetchJson} onActiveCountChange={() => {}} onDelete={onDelete} onBatchPreview={() => {}} />)
  await user.click(screen.getByRole("tab", { name: "Cleanup candidates" }))
  await screen.findByText("Safe linked title")
  expect(screen.getByText(/Failure evidence: Jellyfin catalogue unavailable/)).toBeInTheDocument()
  expect(screen.getByText(/Data source: Standard Jellyfin API/)).toBeInTheDocument()
  expect(screen.getByText(/Torrent state: Not present/)).toBeInTheDocument()
  await user.click(screen.getByRole("button", { name: "Review deletion plan" }))
  expect(onDelete).toHaveBeenCalledWith(expect.objectContaining({ movie_title: "Safe linked title" }), expect.any(HTMLElement))
})

it("renders latest action evidence and a visible reason when controls are unavailable", async () => {
  const unavailable = { ...item, state: "unknown" as const, freshness: "stale" as const, ownership: "unknown" as const, latest_action: { action_id: "action", source: "policy", status: "failed" as const, code: "target_not_fresh", attempt_count: 1, max_attempts: 3, created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:01:00Z", result: null } }
  renderPanel(async <T,>() => ({ ...downloads, items: [unavailable] }) as T)
  expect(await screen.findByText("This reversible control is unavailable until CleanArr has fresh, managed ownership evidence and a known torrent state.")).toBeInTheDocument()
  await userEvent.click(screen.getByText(/Latest reversible control: Failed/))
  expect(screen.getByText(/Attempts: 1\/3/)).toBeInTheDocument()
  expect(screen.getByText(/Unavailable reason: Target is not fresh/)).toBeInTheDocument()
})
