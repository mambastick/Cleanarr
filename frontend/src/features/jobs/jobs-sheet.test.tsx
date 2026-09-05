import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { expect, it } from "vitest"
import { JobsSheet } from "./jobs-sheet"

const jobs = [{ id: "job-1", item_type: "Movie" as const, item_name: "Canonical", display_name: "Selected library title", status: "running" as const, phase: "cleaning" as const, progress_percent: 40, message: "PRIVATE MESSAGE", created_at: "2026-09-01T00:00:00Z", started_at: null, completed_at: null, next_retry_at: null, attempt_count: 1, max_attempts: 3, preflight: { item_type: "Movie" as const, correlation_id: null, item_id: "movie-1", name: "Canonical", display_name: "Selected library title", status: "success" as const, fingerprint: { tmdb_id: null, tvdb_id: null, imdb_id: null, path: null }, season_number: null, episode_number: null, episode_end_number: null, actions: [] }, result: null, error: null }]
const batches = [{ id: "batch-1", status: "partial" as const, message: "PRIVATE PARENT MESSAGE", created_at: "2026-09-01T00:00:00Z", started_at: null, completed_at: null, error_code: "unsafe_plan", error_message: "PRIVATE ERROR", total_count: 3, queued_count: 0, running_count: 0, completed_count: 1, blocked_count: 1, failed_count: 0, cancelled_count: 1, children: [{ id: "child-1", mutation_identity: "private", display_name: "Completed title", status: "completed" as const, message: "PRIVATE", blocked_code: null, error_code: null, error_message: null, preflight: null, result: null, started_at: null, completed_at: null }, { id: "child-2", mutation_identity: "private", display_name: "Blocked title", status: "blocked" as const, message: "PRIVATE", blocked_code: "unsafe_plan", error_code: null, error_message: null, preflight: null, result: null, started_at: null, completed_at: null }, { id: "child-3", mutation_identity: "private", display_name: "Cancelled title", status: "cancelled" as const, message: "PRIVATE", blocked_code: null, error_code: null, error_message: null, preflight: null, result: null, started_at: null, completed_at: null }] }]

it("uses an inline non-obscuring trigger, localized phases, one-shot live state, and returns focus", async () => { const user = userEvent.setup(); render(<JobsSheet jobs={jobs} title="Background tasks" activeLabel="active" recentLabel="recent" dismissLabel="Dismiss" closeLabel="Close jobs" progressLabel="Progress" language="en" announcement="Selected library title: completed" announcementTone="polite" onDismiss={() => {}} />); const trigger = screen.getByRole("button", { name: "Background tasks" }); expect(trigger).toHaveAttribute("aria-expanded", "false"); expect(trigger.className).not.toContain("fixed"); expect(screen.getByText("Selected library title: completed")).toHaveAttribute("aria-live", "polite"); await user.click(trigger); expect(trigger).toHaveAttribute("aria-expanded", "true"); expect(trigger).toHaveAttribute("aria-controls", "delete-jobs-sheet"); expect(screen.getAllByText("Running").length).toBeGreaterThan(0); expect(screen.queryByText("PRIVATE MESSAGE")).not.toBeInTheDocument(); await user.click(screen.getByRole("button", { name: "Close jobs" })); expect(trigger).toHaveFocus() })

it("renders structured batch parent and child partial, blocked, and cancelled progress without raw errors", async () => { const user = userEvent.setup(); render(<JobsSheet jobs={[]} batches={batches} title="Background tasks" activeLabel="active" recentLabel="recent" dismissLabel="Dismiss" closeLabel="Close jobs" progressLabel="Progress" language="en" announcement={null} announcementTone="polite" onDismiss={() => {}} />); await user.click(screen.getByRole("button", { name: "Background tasks" })); expect(screen.getAllByText("Partial outcome").length).toBeGreaterThan(0); expect(screen.getByText("Blocked")).toBeInTheDocument(); expect(screen.getByText("Cancelled")).toBeInTheDocument(); expect(screen.getByText("Completed title")).toBeInTheDocument(); expect(screen.getByText("3/3")).toBeInTheDocument(); expect(screen.getByText("completed: 1 · blocked: 1 · failed: 0 · cancelled: 1")).toBeInTheDocument(); expect(document.querySelector(".lucide-circle-alert")).toBeInTheDocument(); expect(screen.queryByText(/PRIVATE/)).not.toBeInTheDocument() })

it("uses coherent singular and Russian batch count copy", async () => {
  const user = userEvent.setup()
  const russianBatch = {
    ...batches[0],
    total_count: 2,
    completed_count: 1,
    blocked_count: 1,
    cancelled_count: 0,
    children: batches[0].children.slice(0, 2),
  }
  render(<JobsSheet jobs={[]} batches={[russianBatch]} title="Фоновые задачи" activeLabel="активных" recentLabel="недавних" dismissLabel="Скрыть" closeLabel="Закрыть" progressLabel="Прогресс" language="ru" announcement={null} announcementTone="polite" onDismiss={() => {}} />)
  expect(screen.getByText("1 недавняя")).toBeInTheDocument()
  await user.click(screen.getByRole("button", { name: "Фоновые задачи" }))
  expect(screen.getByText("2 элемента в пакете")).toBeInTheDocument()
})

it("labels completed dry-run single jobs and batch children as simulations without changing real completions", async () => {
  const user = userEvent.setup()
  const simulatedResult = {
    ...jobs[0].preflight,
    actions: [{ system: "radarr", action: "delete_movie", status: "dry_run" as const, message: "PRIVATE", reason: null, details: {} }],
  }
  const simulatedJob = { ...jobs[0], status: "completed" as const, phase: "completed" as const, progress_percent: 100, result: simulatedResult }
  const simulatedBatch = {
    ...batches[0],
    status: "completed" as const,
    total_count: 1,
    completed_count: 1,
    blocked_count: 0,
    cancelled_count: 0,
    children: [{ ...batches[0].children[0], result: simulatedResult }],
  }
  const realCompletedJob = { ...simulatedJob, id: "job-2", display_name: "Real completed title", result: { ...simulatedResult, actions: [{ ...simulatedResult.actions[0], status: "deleted" as const }] } }
  render(<JobsSheet jobs={[simulatedJob, realCompletedJob]} batches={[simulatedBatch]} title="Background tasks" activeLabel="active" recentLabel="recent" dismissLabel="Dismiss" closeLabel="Close jobs" progressLabel="Progress" language="en" announcement={null} announcementTone="polite" onDismiss={() => {}} />)
  await user.click(screen.getByRole("button", { name: "Background tasks" }))
  expect(screen.getAllByText("Simulation completed — no changes were made.")).toHaveLength(5)
  expect(screen.getAllByText("Completed")).toHaveLength(2)
  expect(screen.queryByText("PRIVATE")).not.toBeInTheDocument()
})

it("localizes the completed dry-run outcome in Russian", async () => {
  const user = userEvent.setup()
  const simulatedResult = {
    ...jobs[0].preflight,
    actions: [{ system: "radarr", action: "delete_movie", status: "dry_run" as const, message: "PRIVATE", reason: null, details: {} }],
  }
  const simulatedJob = { ...jobs[0], status: "completed" as const, phase: "completed" as const, progress_percent: 100, result: simulatedResult }
  render(<JobsSheet jobs={[simulatedJob]} title="Фоновые задачи" activeLabel="активных" recentLabel="недавних" dismissLabel="Скрыть" closeLabel="Закрыть" progressLabel="Прогресс" language="ru" announcement={null} announcementTone="polite" onDismiss={() => {}} />)
  await user.click(screen.getByRole("button", { name: "Фоновые задачи" }))
  expect(screen.getAllByText("Симуляция завершена — изменения не внесены.")).toHaveLength(2)
})
