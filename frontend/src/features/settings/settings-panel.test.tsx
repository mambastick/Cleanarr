import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { expect, it, vi } from "vitest"

import { getUiText } from "@/lib/i18n"
import { SettingsPanel } from "./settings-panel"

it("supports controlled settings section switching without changing the default API", async () => {
  const user = userEvent.setup()
  const onSettingsSectionChange = vi.fn()
  const props = { config: null, isConfigLoading: false, onSaveGeneral: async () => {}, onAddService: () => {}, onEditService: () => {}, text: getUiText("en"), language: "en", onSettingsSectionChange }
  const view = render(<SettingsPanel {...props} settingsSection="general" />)
  expect(screen.getByRole("tab", { name: "General" })).toHaveAttribute("aria-selected", "true")
  await user.click(screen.getByRole("tab", { name: "Connected services" }))
  expect(onSettingsSectionChange).toHaveBeenCalledWith("services")
  view.rerender(<SettingsPanel {...props} settingsSection="services" />)
  expect(screen.getByRole("tab", { name: "Connected services" })).toHaveAttribute("aria-selected", "true")
  expect(screen.getByText("All enabled Radarr, Sonarr, and torrent-client instances participate in routing.")).toBeInTheDocument()
})
