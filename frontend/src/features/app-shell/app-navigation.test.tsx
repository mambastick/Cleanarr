import { render, screen } from "@testing-library/react"
import { afterEach, vi } from "vitest"

import { ThemeProvider } from "@/components/theme-provider"
import { Tabs } from "@/components/ui/tabs"
import { AppNavigation } from "@/features/app-shell/app-navigation"

afterEach(() => vi.unstubAllGlobals())

it("keeps theme and localized logout controls in the mobile-independent accessibility tree", () => {
  vi.stubGlobal("matchMedia", vi.fn().mockReturnValue({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() }))
  render(<ThemeProvider><Tabs defaultValue="dashboard"><AppNavigation labels={{ dashboard: "Панель", settings: "Настройки", activity: "Активность", library: "Библиотека", downloads: "Загрузки", downloadsActive: "активно", live: "Рабочий", dryRun: "Тест", logOut: "Выйти", navigation: "Основная навигация" }} live={false} username="admin" showRuntime downloadsActiveCount={3} onLogout={() => {}} /></Tabs></ThemeProvider>)
  expect(screen.getByRole("button", { name: /Theme:/ })).toBeInTheDocument()
  expect(screen.getByRole("button", { name: "Выйти" })).toBeInTheDocument()
  expect(screen.getByRole("tab", { name: "Загрузки: 3 активно" })).toHaveTextContent("3")
  for (const tab of screen.getAllByRole("tab")) {
    expect(tab.querySelector('[tabindex="0"]')).toBeNull()
  }
})
