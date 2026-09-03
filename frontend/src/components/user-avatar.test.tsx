import { render, screen } from "@testing-library/react"
import { expect, it } from "vitest"

import { UserAvatar } from "./user-avatar"
import { userAvatarTone, userInitials } from "@/lib/user-avatar"

it("builds initials from the first and last name segments", () => {
  expect(userInitials("Anna Maria Smith")).toBe("AS")
  expect(userInitials("anna.smith")).toBe("AS")
  expect(userInitials("admin")).toBe("A")
  expect(userInitials("  ")).toBe("?")
})

it("keeps avatar colors deterministic for the same user", () => {
  expect(userAvatarTone("Anna Smith")).toBe(userAvatarTone("Anna Smith"))
  expect(userAvatarTone("Anna Smith")).toBeGreaterThanOrEqual(0)
  expect(userAvatarTone("Anna Smith")).toBeLessThan(5)
})

it("renders the generated initials without duplicating the accessible name", () => {
  render(<><span>Anna Smith</span><UserAvatar name="Anna Smith" /></>)
  expect(screen.getByText("AS")).toHaveAttribute("aria-hidden", "true")
})
