import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { useState } from "react"

import { KeepDryRunControl, ProfileRuntimeControls } from "@/features/setup/profile-runtime-controls"

function Fixture() {
  const [enabled, setEnabled] = useState(true)
  const [isDefault, setDefault] = useState(false)
  const [dryRun, setDryRun] = useState(true)
  return <><ProfileRuntimeControls enabled={enabled} isDefault={isDefault} enabledLabel="Enabled" defaultLabel="Mark as preferred/default" onEnabledChange={setEnabled} onDefaultChange={setDefault} /><KeepDryRunControl label="Keep CleanArr in Dry Run" checked={dryRun} onCheckedChange={setDryRun} /></>
}

it("names production downloader switches from their visible labels", async () => {
  const user = userEvent.setup()
  render(<Fixture />)
  await user.click(screen.getByRole("switch", { name: "Enabled" }))
  expect(screen.getByRole("switch", { name: "Enabled" })).not.toBeChecked()
  await user.click(screen.getByRole("switch", { name: "Mark as preferred/default" }))
  expect(screen.getByRole("switch", { name: "Mark as preferred/default" })).toBeChecked()
  await user.click(screen.getByRole("checkbox", { name: "Keep CleanArr in Dry Run" }))
  expect(screen.getByRole("checkbox", { name: "Keep CleanArr in Dry Run" })).not.toBeChecked()
})
