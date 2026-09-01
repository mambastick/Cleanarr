import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { expect, it, vi } from "vitest"

import { SeedingStopPolicyFields } from "./seeding-stop-policy-fields"
import type { GeneralConfig } from "@/lib/runtime-config"

const draft = {
  seeding_stop_policy: { enabled: false, mode: "all", min_ratio: null, min_seeding_minutes: null, include_categories: [], exclude_categories: [], include_tags: [], exclude_tags: [], interval_seconds: 30, max_attempts: 1 },
} as unknown as GeneralConfig

it("preserves disabled values and normalizes changed scope fields", async () => {
  const onDraftChange = vi.fn()
  const user = userEvent.setup()
  render(<SeedingStopPolicyFields draft={draft} onDraftChange={onDraftChange} language="en" />)
  await user.click(screen.getByRole("switch", { name: "Enable stop policy" }))
  expect(onDraftChange).toHaveBeenLastCalledWith(expect.objectContaining({ seeding_stop_policy: expect.objectContaining({ enabled: true, interval_seconds: 30, max_attempts: 1 }) }))
  expect(screen.getByLabelText("Include tags")).toBeDisabled()
})
