import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { Settings } from "lucide-react"
import { afterEach, vi } from "vitest"

import { AnimateIcon, AnimatedIcon } from "@/components/animate-ui/animated-icon"

afterEach(() => vi.unstubAllGlobals())

function Fixture() {
  return (
    <AnimateIcon>
      <button type="button">
        <AnimatedIcon animation="wiggle"><Settings /></AnimatedIcon>
        Settings
      </button>
    </AnimateIcon>
  )
}

it("animates an action icon on hover and keyboard focus", async () => {
  const user = userEvent.setup()
  render(<Fixture />)
  const action = screen.getByRole("button", { name: "Settings" })
  const icon = action.querySelector("[data-slot=animated-icon]")
  expect(icon).toHaveAttribute("data-animation-state", "rest")
  await user.hover(action)
  expect(icon).toHaveAttribute("data-animation-state", "active")
  await user.unhover(action)
  await user.tab()
  await waitFor(() => expect(icon).toHaveAttribute("data-animation-state", "active"))
})

it("keeps icon motion still when reduced motion is requested", async () => {
  vi.stubGlobal("matchMedia", vi.fn().mockReturnValue({ matches: true, addEventListener: vi.fn(), removeEventListener: vi.fn() }))
  const user = userEvent.setup()
  render(<Fixture />)
  const action = screen.getByRole("button", { name: "Settings" })
  await user.hover(action)
  expect(action.querySelector("[data-slot=animated-icon]")).toHaveAttribute("data-animation-state", "rest")
})
