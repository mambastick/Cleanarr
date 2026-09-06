import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { useRef, useState } from "react"
import { describe, expect, it, vi } from "vitest"
import { DeleteConfirmationDialog } from "./delete-confirmation-dialog"

const copy = { cancel: "Cancel", delete: "Delete", simulateAction: "Simulate", dryRunNotice: "Dry-run: no changes", retry: "Retry", technicalDetails: "Technical details", remove: "Will be removed", retain: "Will be retained", attention: "Needs attention", unknownSize: "Size unknown", preparing: "Preparing", ready: "Ready", submitting: "Submitting", submitted: "Submitted", unavailable: "Unavailable", close: "Close" }
const preview = { generated_at: "2026-09-01T00:00:00Z", plan_hash: "private-plan-hash", plan: { item_type: "Movie" as const, correlation_id: "secret-correlation", item_id: "private-item-id", name: "Canonical", display_name: "Library title", status: "success" as const, fingerprint: { tmdb_id: 1, tvdb_id: null, imdb_id: null, path: "/private/media/path" }, season_number: null, episode_number: null, episode_end_number: null, actions: [{ system: "downloader", action: "delete", status: "deleted" as const, message: "PRIVATE BACKEND MESSAGE", reason: null, details: { hash: "PRIVATE-HASH", url: "https://private.example", client_name: "Client A" } }] } }
function Fixture({ phase = "ready" as const, initiallyOpen = false, language = "en" as const, onConfirm = () => {} }: { phase?: "ready" | "submitting"; initiallyOpen?: boolean; language?: "en" | "ru"; onConfirm?: () => void }) { const [open, setOpen] = useState(initiallyOpen); const triggerRef = useRef<HTMLButtonElement>(null); return <><button ref={triggerRef} type="button" onClick={() => setOpen(true)}>Delete trigger</button><DeleteConfirmationDialog open={open} title="Delete Library title" phase={phase} preview={preview} error={null} isDryRun={false} language={language} copy={copy} returnFocusRef={triggerRef} onConfirm={onConfirm} onRetry={() => {}} onClose={() => setOpen(false)} /></> }

describe("DeleteConfirmationDialog", () => {
  it("does not steal focus while the controlled dialog is closed", () => { render(<Fixture />); expect(screen.getByRole("button", { name: "Delete trigger" })).not.toHaveFocus() })
  it("focuses Cancel, closes on Escape and backdrop, and restores the trigger", async () => { const user = userEvent.setup(); render(<Fixture />); const trigger = screen.getByRole("button", { name: "Delete trigger" }); await user.click(trigger); expect(screen.getByRole("button", { name: "Cancel" })).toHaveFocus(); await user.click(screen.getByTestId("delete-backdrop")); expect(screen.queryByRole("dialog")).not.toBeInTheDocument(); expect(trigger).toHaveFocus(); await user.click(trigger); await user.keyboard("{Escape}"); expect(screen.queryByRole("dialog")).not.toBeInTheDocument() })
  it("blocks Escape and backdrop while submitting and exposes busy state", async () => { const user = userEvent.setup(); render(<Fixture phase="submitting" initiallyOpen />); await user.keyboard("{Escape}"); await user.click(screen.getByTestId("delete-backdrop")); expect(screen.getByRole("dialog")).toHaveAttribute("aria-busy", "true"); expect(screen.getByRole("button", { name: "Cancel" })).toBeDisabled() })
  it("shows reviewable identifiers and paths but never dumps messages, URLs or confirmation secrets", async () => {
    const user = userEvent.setup(); render(<Fixture initiallyOpen />)
    expect(screen.getAllByText("Library title")[0]).toBeInTheDocument()
    expect(screen.queryByText("PRIVATE BACKEND MESSAGE")).not.toBeInTheDocument()
    await user.click(screen.getByText("Target identifiers and paths"))
    expect(screen.getByText("PRIVATE-HASH")).toBeVisible()
    expect(screen.getByText("/private/media/path")).toBeVisible()
    expect(screen.queryByText(/private-plan-hash|private-item-id|private\.example|secret-correlation/)).not.toBeInTheDocument()
  })
  it("protects the single destructive confirmation from duplicate activation", async () => { const user = userEvent.setup(); const onConfirm = vi.fn(); render(<Fixture initiallyOpen onConfirm={onConfirm} />); const confirm = screen.getByRole("button", { name: "Delete" }); await user.dblClick(confirm); expect(onConfirm).toHaveBeenCalledTimes(1) })
  it("localizes generic system codes instead of exposing raw mixed-language copy", () => { render(<Fixture initiallyOpen language="ru" />); expect(screen.getByText(/Торрент-клиент · Client A/)).toBeInTheDocument(); expect(screen.queryByText("downloader")).not.toBeInTheDocument() })
})
