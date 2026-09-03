import { render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, vi } from "vitest"

import { AppShell } from "@/features/app-shell/app-shell"
import { TooltipProvider } from "@/components/ui/tooltip"

afterEach(() => {
  vi.restoreAllMocks()
  window.localStorage.removeItem("cleanarr.sidebar.collapsed")
})

const labels = {
  nav: { overview: "Overview", library: "Library", downloads: "Downloads", activity: "Activity", users: "Users", settings: "Settings" },
  more: "More",
  close: "Close",
  storage: "Storage",
  account: "Account",
  navigation: "Main navigation",
}

function renderShell(overrides: Partial<React.ComponentProps<typeof AppShell>> = {}) {
  return render(
    <TooltipProvider delay={0}>
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
      </AppShell>
    </TooltipProvider>,
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

it("keeps every Settings section reachable from the mobile More sheet", async () => {
  const user = userEvent.setup()
  const onSettingsSectionChange = vi.fn()
  renderShell({ activePage: "settings", onSettingsSectionChange })

  const more = screen.getByRole("button", { name: "More" })
  expect(more).toHaveAttribute("aria-current", "page")
  await user.click(more)
  const mobileDialog = screen.getByRole("dialog")
  await user.click(within(mobileDialog).getByRole("button", { name: "Connected services" }))

  expect(onSettingsSectionChange).toHaveBeenCalledWith("services")
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
})

it("reveals the active Settings sections and reports the selected section", async () => {
  const user = userEvent.setup()
  const onPageChange = vi.fn()
  const onSettingsSectionChange = vi.fn()
  const { container } = renderShell({ activePage: "settings", onPageChange, onSettingsSectionChange })

  const settings = screen.getByRole("button", { name: "Settings" })
  expect(settings).toHaveAttribute("aria-expanded", "true")
  expect(screen.getByRole("group", { name: "Settings" })).toHaveAttribute("data-motion-tree", "true")
  expect(screen.getByRole("button", { name: "CleanArr" })).toHaveAttribute("aria-current", "page")
  expect(container.querySelector('.app-shell__settings-highlight [data-slot="motion-highlight-item-container"][data-value="cleanarr"]')).toHaveAttribute("data-active", "true")

  await user.click(screen.getByRole("button", { name: "Connected services" }))
  expect(onSettingsSectionChange).toHaveBeenCalledWith("services")
  expect(onPageChange).toHaveBeenCalledWith("settings")
})

it("keeps Settings and Storage in mobile More while desktop account actions live in the avatar popover", async () => {
  const user = userEvent.setup()
  renderShell()

  await user.click(screen.getByRole("button", { name: "More" }))
  const mobileDialog = screen.getByRole("dialog")
  expect(within(mobileDialog).getByRole("button", { name: "Settings" })).toBeInTheDocument()
  expect(within(mobileDialog).getByRole("region", { name: "Storage" })).toBeInTheDocument()
  await user.keyboard("{Escape}")

  const account = screen.getByRole("button", { name: "Account: admin" })
  expect(account).toHaveClass("app-shell__account-trigger")
  expect(screen.queryByRole("button", { name: "Theme: System" })).not.toBeInTheDocument()

  await user.click(account)
  const accountPopover = screen.getByRole("dialog", { name: "admin" })
  expect(within(accountPopover).getByRole("button", { name: "Theme: System" })).toBeInTheDocument()
  expect(within(accountPopover).getByRole("button", { name: "Language: EN" })).toBeInTheDocument()
  expect(within(accountPopover).getByRole("button", { name: "Log out" })).toBeInTheDocument()
  await user.keyboard("{Escape}")
  await waitFor(() => expect(account).toHaveFocus())
})

it("uses one measured moving highlight for the mobile bottom navigation", () => {
  const { container } = renderShell({ activePage: "library" })
  const mobileHighlight = container.querySelector(".app-shell__bottom-highlight")
  const activeItem = mobileHighlight?.querySelector('[data-slot="motion-highlight-item-container"][data-value="library"]')

  expect(mobileHighlight).toBeInTheDocument()
  expect(activeItem).toHaveAttribute("data-active", "true")
})

it("collapses the desktop sidebar and keeps every destination available by accessible name", async () => {
  const user = userEvent.setup()
  const { container } = renderShell()
  await user.click(screen.getByRole("button", { name: "Collapse sidebar" }))
  expect(container.querySelector(".app-shell")).toHaveClass("app-shell--sidebar-collapsed")
  expect(screen.getAllByRole("button", { name: "Activity" })[0]).toBeEnabled()
  expect(screen.getByRole("button", { name: "Expand sidebar" })).toBeInTheDocument()
})

it("wires tooltip triggers for icon-only destinations in the collapsed sidebar", async () => {
  const user = userEvent.setup()
  renderShell()
  await user.click(screen.getByRole("button", { name: "Collapse sidebar" }))
  expect(screen.getAllByRole("button", { name: "Activity" })[0]).toHaveAttribute("data-base-ui-tooltip-trigger")
})

it("uses the measured Animate UI highlight for the active desktop destination", () => {
  const { container } = renderShell({ activePage: "library" })
  const activeItem = container.querySelector('[data-slot="motion-highlight-item-container"][data-value="library"]')

  expect(container.querySelector('[data-slot="motion-highlight-container"]')).toBeInTheDocument()
  expect(activeItem).toHaveAttribute("data-active", "true")
})

it("keeps administration destinations out of a viewer workspace", async () => {
  const user = userEvent.setup()
  renderShell({ canAdmin: false })
  expect(screen.queryByRole("button", { name: "Users" })).not.toBeInTheDocument()
  expect(screen.queryByRole("button", { name: "Settings" })).not.toBeInTheDocument()
  await user.click(screen.getByRole("button", { name: "More" }))
  expect(within(screen.getByRole("dialog")).queryByRole("button", { name: "Users" })).not.toBeInTheDocument()
  expect(within(screen.getByRole("dialog")).queryByRole("button", { name: "Settings" })).not.toBeInTheDocument()
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
  expect(screen.getAllByRole("status", { name: "Runtime status: Live" })[0]).toHaveAttribute("data-base-ui-tooltip-trigger")
  expect(screen.getAllByRole("region", { name: "Storage" })[0]).toHaveAttribute("data-base-ui-tooltip-trigger")
})
