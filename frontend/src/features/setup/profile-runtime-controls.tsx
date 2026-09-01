import { Switch } from "@/components/ui/switch"
import { Checkbox } from "@/components/ui/checkbox"

type ProfileRuntimeControlsProps = {
  enabled: boolean
  isDefault: boolean
  enabledLabel: string
  defaultLabel: string
  onEnabledChange: (enabled: boolean) => void
  onDefaultChange: (isDefault: boolean) => void
}

export function ProfileRuntimeControls({ enabled, isDefault, enabledLabel, defaultLabel, onEnabledChange, onDefaultChange }: ProfileRuntimeControlsProps) {
  return <div className="grid gap-2 sm:grid-cols-2">
    <div className="flex items-center justify-between gap-3 rounded-lg border px-3 py-2 text-sm"><span>{enabledLabel}</span><Switch aria-label={enabledLabel} checked={enabled} onCheckedChange={onEnabledChange} /></div>
    <div className="flex items-center justify-between gap-3 rounded-lg border px-3 py-2 text-sm"><span>{defaultLabel}</span><Switch aria-label={defaultLabel} checked={isDefault} onCheckedChange={onDefaultChange} /></div>
  </div>
}

export function KeepDryRunControl({ label, checked, onCheckedChange }: { label: string; checked: boolean; onCheckedChange: (checked: boolean) => void }) {
  return <div className="flex items-center justify-between gap-3 text-sm"><span>{label}</span><Checkbox aria-label={label} checked={checked} onCheckedChange={onCheckedChange} /></div>
}
