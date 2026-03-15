import { Laptop, Moon, Sun } from "lucide-react"

import { Button } from "@/components/ui/button"
import { useTheme } from "@/components/theme-provider"

const CYCLE = ["light", "dark", "system"] as const
type Theme = (typeof CYCLE)[number]

const ICONS: Record<Theme, typeof Sun> = {
  light: Sun,
  dark: Moon,
  system: Laptop,
}

export function ThemeToggle() {
  const { theme, setTheme } = useTheme()

  const current = (CYCLE.includes(theme as Theme) ? theme : "system") as Theme
  const Icon = ICONS[current]

  function handleClick() {
    const next = CYCLE[(CYCLE.indexOf(current) + 1) % CYCLE.length]
    setTheme(next)
  }

  return (
    <Button
      type="button"
      variant="ghost"
      size="icon"
      className="size-8"
      title={`Theme: ${current}`}
      onClick={handleClick}
    >
      <Icon className="size-4" />
    </Button>
  )
}
