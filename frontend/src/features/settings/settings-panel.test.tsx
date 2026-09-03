import { render, screen } from "@testing-library/react"
import { expect, it, vi } from "vitest"

import { getUiText } from "@/lib/i18n"
import type { RuntimeConfigPayload } from "@/lib/runtime-config"
import { SettingsPanel } from "./settings-panel"

it("renders the selected settings tree section without duplicate top tabs", () => {
  const props = { config: null, isConfigLoading: false, onSaveGeneral: async () => {}, onAddService: vi.fn(), onEditService: vi.fn(), text: getUiText("en"), language: "en" as const }
  const view = render(<SettingsPanel {...props} settingsSection="cleanarr" />)
  expect(screen.getByRole("heading", { name: "CleanArr" })).toBeInTheDocument()
  expect(screen.queryByRole("tablist")).not.toBeInTheDocument()
  view.rerender(<SettingsPanel {...props} settingsSection="services" />)
  expect(screen.getByRole("heading", { name: "Connected services" })).toBeInTheDocument()
  expect(screen.getByText("All enabled Radarr, Sonarr, and torrent-client instances participate in routing.")).toBeInTheDocument()
})

it("presents each service family as a separate labelled section", () => {
  const config = {
    radarr: [{ id: "radarr-one", kind: "radarr", name: "Movies", url: "https://radarr.example", api_key: "secret", enabled: true, is_default: true }],
    sonarr: [], seerr: [], downloaders: [], jellyfin: [],
  } as unknown as RuntimeConfigPayload
  render(<SettingsPanel config={config} isConfigLoading={false} onSaveGeneral={async () => {}} onAddService={vi.fn()} onEditService={vi.fn()} text={getUiText("en")} language="en" settingsSection="services" />)

  expect(screen.getByRole("region", { name: "Radarr" })).toContainElement(screen.getByText("Movies"))
  expect(screen.getByRole("region", { name: "Sonarr" })).toHaveTextContent("Not configured")
  expect(screen.getByRole("region", { name: "Torrent client" })).toHaveTextContent("Not configured")
})
