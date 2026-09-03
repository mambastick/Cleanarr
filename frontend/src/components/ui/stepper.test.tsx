import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"

import Stepper, { Step } from "@/components/ui/stepper"

const motionPreference = vi.hoisted(() => ({ reduced: false }))

vi.mock("motion/react", async (importOriginal) => {
  const actual = await importOriginal<typeof import("motion/react")>()
  return { ...actual, useReducedMotion: () => motionPreference.reduced }
})

Object.defineProperty(window, "scrollTo", { value: () => {}, writable: true })

describe("Stepper", () => {
  beforeEach(() => {
    motionPreference.reduced = false
  })

  it("supports keyboard step navigation and localized final copy", async () => {
    const user = userEvent.setup()
    render(
      <Stepper backButtonText="Назад" nextButtonText="Далее" completeButtonText="Готово" stepLabel="Шаг">
        <Step><p>Первый шаг</p></Step>
        <Step><p>Второй шаг</p></Step>
      </Stepper>,
    )
    const secondStep = screen.getByRole("button", { name: "Шаг 2" })
    await user.tab()
    await user.tab()
    await user.keyboard("{Enter}")
    expect(screen.getByText("Второй шаг")).toBeInTheDocument()
    expect(secondStep).toHaveAttribute("aria-current", "step")
    expect(screen.getByRole("button", { name: "Готово" })).toBeInTheDocument()
  })

  it("selects the immediate transition branch when reduced motion is requested", async () => {
    motionPreference.reduced = true
    const user = userEvent.setup()
    const { container } = render(
      <Stepper nextButtonText="Next" stepLabel="Step">
        <Step><p>First</p></Step>
        <Step><p>Second</p></Step>
      </Stepper>,
    )
    expect(container.firstElementChild).toHaveAttribute("data-reduced-motion", "true")
    await user.click(screen.getByRole("button", { name: "Step 2" }))
    expect(screen.getByText("Second")).toBeInTheDocument()
  })

  it("waits for the transition guard and stays on the current step when it rejects", async () => {
    const user = userEvent.setup()
    let resolveGuard: ((value: boolean) => void) | undefined
    const guard = vi.fn(() => new Promise<boolean>((resolve) => { resolveGuard = resolve }))
    render(
      <Stepper nextButtonText="Next" stepLabel="Step" onBeforeStepChange={guard}>
        <Step><p>First</p></Step>
        <Step><p>Second</p></Step>
      </Stepper>,
    )

    const next = screen.getByRole("button", { name: "Next" })
    await user.click(next)
    expect(next).toBeDisabled()
    resolveGuard?.(false)
    await vi.waitFor(() => expect(next).toBeEnabled())
    expect(screen.getByText("First")).toBeInTheDocument()
    expect(guard).toHaveBeenCalledWith(1, 2)
  })
})
