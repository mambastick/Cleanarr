import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { useState } from "react"
import { afterEach, vi } from "vitest"

import { Checkbox } from "@/components/ui/checkbox"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Switch } from "@/components/ui/switch"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"

afterEach(() => vi.unstubAllGlobals())

function ControlFixture() {
  const [choice, setChoice] = useState("one")
  const [checked, setChecked] = useState(false)
  return <><Select items={{ one: "One", two: "Two" }} value={choice} onValueChange={(value) => value && setChoice(value)}><SelectTrigger aria-label="Client"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="one">One</SelectItem><SelectItem value="two">Two</SelectItem></SelectContent></Select><Checkbox aria-label="Enabled" checked={checked} onCheckedChange={setChecked} /><Switch aria-label="Default" checked={checked} onCheckedChange={setChecked} /></>
}

describe("design-system controls", () => {
  it("supports select, checkbox, and switch interaction", async () => {
    const user = userEvent.setup()
    render(<ControlFixture />)
    const select = screen.getByRole("combobox", { name: "Client" })
    select.focus()
    await user.keyboard("{ArrowDown}{ArrowDown}{Enter}")
    expect(select).toHaveTextContent("Two")
    await user.click(screen.getByRole("checkbox", { name: "Enabled" }))
    expect(screen.getByRole("checkbox", { name: "Enabled" })).toBeChecked()
    await user.click(screen.getByRole("switch", { name: "Default" }))
    expect(screen.getByRole("switch", { name: "Default" })).not.toBeChecked()
  })

  it("uses Base UI keyboard tabs and exposes reduced-motion state", async () => {
    const user = userEvent.setup()
    render(<Tabs defaultValue="one"><TabsList><TabsTrigger value="one">One</TabsTrigger><TabsTrigger value="two">Two</TabsTrigger></TabsList><TabsContent value="one">First</TabsContent><TabsContent value="two">Second</TabsContent></Tabs>)
    const first = screen.getByRole("tab", { name: "One" })
    first.focus()
    await user.keyboard("{ArrowRight}{Enter}")
    expect(screen.getByRole("tab", { name: "Two" })).toHaveAttribute("aria-selected", "true")
    expect(screen.getByText("Second").closest("div[data-reduced-motion]")).toBeTruthy()
  })

  it("uses the matchMedia reduced-motion branch and scopes tab indicators", () => {
    vi.stubGlobal("matchMedia", vi.fn().mockReturnValue({ matches: true, addEventListener: vi.fn(), removeEventListener: vi.fn() }))
    const { container } = render(<><Tabs defaultValue="one"><TabsList><TabsTrigger value="one">One</TabsTrigger><TabsTrigger value="two">Two</TabsTrigger></TabsList><TabsContent value="one">First</TabsContent><TabsContent value="two">Second</TabsContent></Tabs><Tabs defaultValue="three"><TabsList><TabsTrigger value="three">Three</TabsTrigger><TabsTrigger value="four">Four</TabsTrigger></TabsList><TabsContent value="three">Third</TabsContent><TabsContent value="four">Fourth</TabsContent></Tabs></>)
    expect(screen.getByText("First").closest("div[data-reduced-motion]")).toHaveAttribute("data-reduced-motion", "true")
    const ids = new Set(Array.from(container.querySelectorAll("[data-indicator-id]")).map((item) => item.getAttribute("data-indicator-id")))
    expect(ids).toHaveLength(2)
    for (const highlight of container.querySelectorAll("[data-slot=tabs-highlight]")) {
      expect(highlight).toHaveClass("rounded-md", "border")
      expect(highlight).not.toHaveClass("h-0.5")
    }
  })
})
