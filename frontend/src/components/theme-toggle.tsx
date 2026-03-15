import { Laptop, Moon, Sun } from "lucide-react"

import { Button } from "@/components/ui/button"
import { useTheme } from "@/components/theme-provider"

const OPTIONS = [
  { value: "light", label: "Light", icon: Sun },
  { value: "dark", label: "Dark", icon: Moon },
  { value: "system", label: "System", icon: Laptop },
] as const

export function ThemeToggle() {
  const { theme, setTheme } = useTheme()

  return (
    <div className="inline-flex items-center rounded-lg border bg-background p-1">
      {OPTIONS.map((option) => {
        const Icon = option.icon
        const active = theme === option.value
        return (
          <Button
            key={option.value}
            type="button"
            variant={active ? "secondary" : "ghost"}
            size="sm"
            className="gap-2"
            onClick={() => {
              setTheme(option.value)
            }}
          >
            <Icon className="size-4" />
            {option.label}
          </Button>
        )
      })}
    </div>
  )
}
