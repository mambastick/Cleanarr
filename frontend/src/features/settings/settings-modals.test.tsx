import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { useRef, useState } from "react"
import { describe, expect, it } from "vitest"

import { Button } from "@/components/ui/button"
import { Modal } from "@/components/ui/modal"

function Fixture({ title }: { title: string }) {
  const [open, setOpen] = useState(false)
  const triggerRef = useRef<HTMLButtonElement>(null)
  return (
    <>
      <Button ref={triggerRef} onClick={() => setOpen(true)}>Open settings</Button>
      <Modal open={open} onClose={() => setOpen(false)} title={title} description="Dialog description" closeLabel={title === "Настройки выполнения" ? "Закрыть настройки" : "Close settings"} returnFocusRef={triggerRef}>
        <Button>Save</Button>
      </Modal>
    </>
  )
}

describe("settings modal accessibility", () => {
  it("opens with its accessible name, initializes focus, and closes on Escape", async () => {
    const user = userEvent.setup()
    render(<Fixture title="Runtime settings" />)
    await user.click(screen.getByRole("button", { name: "Open settings" }))
    expect(screen.getByRole("dialog", { name: "Runtime settings" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Close settings" })).toHaveFocus()
    await user.keyboard("{Escape}")
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Open settings" })).toHaveFocus()
  })

  it("renders localized Russian dialog copy without an English fallback", async () => {
    const user = userEvent.setup()
    render(<Fixture title="Настройки выполнения" />)
    await user.click(screen.getByRole("button", { name: "Open settings" }))
    expect(screen.getByRole("dialog", { name: "Настройки выполнения" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Закрыть настройки" })).toHaveFocus()
    expect(screen.queryByText("Runtime settings")).not.toBeInTheDocument()
    await user.click(screen.getByTestId("modal-backdrop"))
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Open settings" })).toHaveFocus()
  })
})
