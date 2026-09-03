import { render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, vi } from "vitest"

import { AppShell } from "@/features/app-shell/app-shell"

afterEach(() => vi.restoreAllMocks())

const labels = {
  nav: { overview: "Overview", library: "Library", downloads: "Downloads", activity: "Activity", settings: "Settings" },
  more: "More",
  close: "Close",
  storage: "Storage",
  account: "Account",
  navigation: "Main navigation",
}

function renderShell(overrides: Partial<React.ComponentProps<typeof AppShell>> = {}) {
  return render(
    <AppShell
      activePage="library"
      onPageChange={vi.fn()}
      dryRun
      username="admin"
      storageHeadline={{ status: "warning", headline: "18% free", percent: 82 }}
      labels={labels}
      {...overrides}
    >
      <h1>Library content</h1>
    </AppShell>,
  )
}

it("marks the active page and exposes every desktop destination as a keyboard target", async () => {
  const user = userEvent.setup()
  const onPageChange = vi.fn()
  renderShell({ onPageChange })

  expect(screen.getAllByRole("button", { name: "Library" })[0]).toHaveAttribute("aria-current", "page")
  const overview = screen.getAllByRole("button", { name: "Overview" })[0]
  expect(overview).toBeEnabled()
  await user.click(overview)
  expect(onPageChange).toHaveBeenCalledWith("overview")
})

it("opens More and returns focus to its trigger after closing", async () => {
  const user = userEvent.setup()
  renderShell()

  const trigger = screen.getByRole("button", { name: "More" })
  await user.click(trigger)
  expect(screen.getByRole("dialog")).toBeInTheDocument()
  expect(screen.getByRole("button", { name: "Settings" })).toBeInTheDocument()

  await user.click(screen.getByRole("button", { name: "Close" }))
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
  expect(trigger).toHaveFocus()
})

it("closes More from the backdrop and Escape, returning focus to its trigger", async () => {
  const user = userEvent.setup()
  renderShell()

  const trigger = screen.getByRole("button", { name: "More" })
  await user.click(trigger)
  await user.click(document.querySelector(".app-shell__sheet-backdrop")!)
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
  await waitFor(() => expect(trigger).toHaveFocus())

  await user.click(trigger)
  await user.keyboard("{Escape}")
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
  await waitFor(() => expect(trigger).toHaveFocus())
})

it("navigates to Settings from More before closing the sheet", async () => {
  const user = userEvent.setup()
  const onPageChange = vi.fn()
  renderShell({ onPageChange })

  await user.click(screen.getByRole("button", { name: "More" }))
  const settings = screen.getAllByRole("button", { name: "Settings" }).at(-1)
  expect(settings).toBeDefined()
  await user.click(settings!)

  expect(onPageChange).toHaveBeenCalledWith("settings")
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
})

it("reveals the active Settings sections and reports the selected section", async () => {
  const user = userEvent.setup()
  const onPageChange = vi.fn()
  const onSettingsSectionChange = vi.fn()
  renderShell({ activePage: "settings", onPageChange, onSettingsSectionChange })

  const settings = screen.getByRole("button", { name: "Settings" })
  expect(settings).toHaveAttribute("aria-expanded", "true")
  expect(screen.getByRole("button", { name: "General" })).toHaveAttribute("aria-current", "page")

  await user.click(screen.getByRole("button", { name: "Connected services" }))
  expect(onSettingsSectionChange).toHaveBeenCalledWith("services")
  expect(onPageChange).toHaveBeenCalledWith("settings")
})

it("keeps Settings and Storage in mobile More but removes their desktop-sheet duplicates", async () => {
  const user = userEvent.setup()
  renderShell()

  await user.click(screen.getByRole("button", { name: "More" }))
  const mobileDialog = screen.getByRole("dialog")
  expect(within(mobileDialog).getByRole("button", { name: "Settings" })).toBeInTheDocument()
  expect(within(mobileDialog).getByRole("region", { name: "Storage" })).toBeInTheDocument()
  await user.keyboard("{Escape}")

  await user.click(screen.getByRole("button", { name: "Account: admin" }))
  const desktopDialog = screen.getByRole("dialog")
  expect(desktopDialog).toHaveAccessibleName("Account")
  expect(within(desktopDialog).queryByRole("button", { name: "Settings" })).not.toBeInTheDocument()
  expect(within(desktopDialog).queryByRole("region", { name: "Storage" })).not.toBeInTheDocument()
  expect(within(desktopDialog).getByRole("button", { name: "Theme: System" })).toBeInTheDocument()
  expect(within(desktopDialog).getByRole("button", { name: "Language: EN" })).toBeInTheDocument()
})

it("links the brand to the static GitHub star count without a runtime fetch", () => {
  renderShell()

  for (const link of screen.getAllByRole("link", { name: "GitHub: 15 stars" })) {
    expect(link).toHaveAttribute("href", "https://github.com/mambastick/Cleanarr")
    expect(link).toHaveAttribute("target", "_blank")
    expect(link).toHaveAttribute("rel", "noreferrer noopener")
    expect(link).toHaveTextContent("15")
  }
})

it("renders semantic runtime and storage status with an accessible meter", () => {
  renderShell({
    dryRun: false,
    storageHeadline: { status: "critical", headline: "2% free", detail: "Clear space soon", percent: 98, partial: true, freshness: "Updated recently" },
  })

  expect(screen.getAllByText("Live").length).toBeGreaterThan(0)
  expect(screen.getByRole("progressbar", { name: "Used: 98%" })).toHaveAttribute("aria-valuenow", "98")
  expect(screen.getByText("Clear space soon")).toBeInTheDocument()
})
