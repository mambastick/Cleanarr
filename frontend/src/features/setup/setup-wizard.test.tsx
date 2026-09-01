import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { useRef, useState } from "react"
import { describe, expect, it, vi } from "vitest"

import { Button } from "@/components/ui/button"
import { SetupWizard } from "@/features/setup/setup-wizard"
import { getUiText } from "@/lib/i18n"

Object.defineProperty(window, "scrollTo", { value: () => {}, writable: true })

function Fixture() {
  const [open, setOpen] = useState(false)
  const triggerRef = useRef<HTMLButtonElement>(null)
  return (
    <>
      <Button ref={triggerRef} onClick={() => setOpen(true)}>Open wizard</Button>
      {open ? (
        <SetupWizard
          config={null}
          dashboard={null}
          origin="http://localhost"
          curlPreview="curl example"
          text={getUiText("en")}
          onSaveGeneral={vi.fn()}
          onSaveService={vi.fn()}
          onTestService={vi.fn().mockResolvedValue({ ok: true, message: "Connected" })}
          onSetupWebhook={vi.fn().mockResolvedValue({ found: false, configured: false, message: "Missing" })}
          onClose={() => setOpen(false)}
          returnFocusRef={triggerRef}
          testedDownloaderFingerprints={new Set()}
        />
      ) : null}
    </>
  )
}

describe("SetupWizard dialog", () => {
  it("traps focus, closes by Escape and backdrop, and restores its trigger", async () => {
    const user = userEvent.setup()
    render(<Fixture />)
    const trigger = screen.getByRole("button", { name: "Open wizard" })

    await user.click(trigger)
    const dialog = screen.getByRole("dialog", { name: /first-time setup/i })
    expect(screen.getByRole("button", { name: "Skip for now" })).toHaveFocus()
    await user.tab({ shift: true })
    expect(trigger).not.toHaveFocus()
    expect(document.activeElement).not.toBe(document.body)
    expect(
      dialog.contains(document.activeElement) ||
        (document.activeElement as HTMLElement).hasAttribute("data-base-ui-focus-guard"),
    ).toBe(true)
    await user.keyboard("{Escape}")
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
    expect(trigger).toHaveFocus()

    await user.click(trigger)
    await user.click(screen.getByTestId("setup-wizard-backdrop"))
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
    expect(trigger).toHaveFocus()
  })
})
