import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { useRef, useState } from "react"
import { expect, it } from "vitest"
import { selectionItem } from "@/features/library/library-selection"
import { BatchDeleteConfirmationDialog } from "./batch-delete-confirmation-dialog"

const item = selectionItem({ kind: "movie", radarr_movie_id: 1, movie_title: "Library title", jellyfin_movie_id: "jf-1" }, "Library title", 1024)
const secondItem = selectionItem({ kind: "movie", radarr_movie_id: 2, movie_title: "Second title", jellyfin_movie_id: "jf-2" }, "Second title", 2048)
const preview = { generated_at: "2026-09-01T00:00:00Z", batch_hash: "private-batch-hash", ready_count: 1, blocked_count: 1, children: [{ mutation_identity: "private-id", display_name: "Library title", status: "ready" as const, plan_hash: "private-plan", blocked_code: null, blocked_message: null, plan: { item_type: "Movie" as const, correlation_id: "private", item_id: "private", name: "Canonical", display_name: "Library title", status: "success" as const, fingerprint: { tmdb_id: null, tvdb_id: null, imdb_id: null, path: "/private/path" }, season_number: null, episode_number: null, episode_end_number: null, actions: [{ system: "downloader", action: "delete", status: "deleted" as const, message: "PRIVATE", reason: null, details: { hash: "PRIVATE-HASH", client_name: "Client A" } }] } }, { mutation_identity: "private-block", display_name: "Blocked title", status: "blocked" as const, plan_hash: null, plan: null, blocked_code: "unsafe_plan", blocked_message: "PRIVATE BLOCK" }] }

function Fixture({ dryRun = false, phase = "ready" as const, language = "en" as const, items = [item] }: { dryRun?: boolean; phase?: "ready" | "submitting"; language?: "en" | "ru"; items?: typeof item[] }) { const [open, setOpen] = useState(true); const triggerRef = useRef<HTMLButtonElement>(null); const [calls, setCalls] = useState(0); return <><button ref={triggerRef} type="button">Trigger</button><span data-testid="calls">{calls}</span><BatchDeleteConfirmationDialog open={open} phase={phase} preview={preview} items={items} error={null} isDryRun={dryRun} language={language} returnFocusRef={triggerRef} onConfirm={() => setCalls((count) => count + 1)} onRetry={() => {}} onClose={() => setOpen(false)} /></> }

it("requires the exact live count, supports dry-run simulation, protects private details, and closes accessibly", async () => {
  const user = userEvent.setup()
  const { rerender } = render(<Fixture />)
  const destructive = screen.getByRole("button", { name: "Delete selected items" })
  await waitFor(() => expect(screen.getByRole("button", { name: "Cancel" })).toHaveFocus())
  expect(destructive).toBeDisabled()
  await user.type(screen.getByRole("textbox", { name: /type the exact/i }), "1")
  expect(destructive).toBeEnabled()
  await user.dblClick(destructive)
  expect(screen.getByTestId("calls")).toHaveTextContent("1")
  expect(screen.getByText("Selected item types")).toBeInTheDocument()
  expect(screen.getByText("1 movie")).toBeInTheDocument()
  expect(screen.getByText(/not all-or-nothing/i)).toBeInTheDocument()
  expect(screen.queryByText(/PRIVATE|private-batch|private-plan|private\/path/i)).not.toBeInTheDocument()
  await user.click(screen.getByRole("button", { name: "Cancel" }))
  expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument()
  expect(screen.getByRole("button", { name: "Trigger" })).toHaveFocus()
  rerender(<Fixture key="dry-run" dryRun />)
  expect(screen.getByRole("button", { name: "Simulate batch cleanup" })).toBeEnabled()
})

it("does not dismiss while submitting", async () => { const user = userEvent.setup(); render(<Fixture phase="submitting" />); await user.keyboard("{Escape}"); await user.click(screen.getByTestId("batch-delete-backdrop")); expect(screen.getByRole("alertdialog")).toHaveAttribute("aria-busy", "true") })
it("uses coherent Russian count, item-type, and continuation copy", () => { render(<Fixture language="ru" items={[item, secondItem]} />); expect(screen.getByText("2 элемента выбрано")).toBeInTheDocument(); expect(screen.getByText("Типы выбранных элементов")).toBeInTheDocument(); expect(screen.getByText("2 фильма")).toBeInTheDocument(); expect(screen.getByText(/не является all-or-nothing/i)).toBeInTheDocument() })
