import { CheckCircle2 } from "lucide-react"
import type { ReactNode } from "react"

import { Input } from "@/components/ui/input"
import { FieldHint, FormField, SelectControl } from "@/features/settings/form-presentation"
import type { HealthStatus } from "@/lib/dashboard"
import type { UiTextMap } from "@/lib/i18n"
import { TORRENT_REMOVAL_POLICIES, type ServiceDraft, type TorrentRemovalPolicy } from "@/lib/service-config"
import { cn } from "@/lib/utils"

export function GuideCard({
  tone,
  title,
  description,
  children,
}: {
  tone: "blue" | "green" | "red"
  title: string
  description: string
  children: ReactNode
}) {
  return (
    <div
      className={cn(
        "rounded-lg border p-4",
        tone === "blue" &&
          "border-primary/30 bg-primary/10",
        tone === "green" &&
          "border-status-success-border bg-status-success-bg",
        tone === "red" &&
          "border-status-danger-border bg-status-danger-bg",
      )}
    >
      <div className="space-y-0.5">
        <p className="text-sm font-medium">{title}</p>
        <p className="text-xs text-muted-foreground">{description}</p>
      </div>
      <div className="mt-3">{children}</div>
    </div>
  )
}

export function DownloaderPolicyFields({
  idPrefix,
  draft,
  setDraft,
  text,
}: {
  idPrefix: string
  draft: ServiceDraft
  setDraft: (draft: ServiceDraft) => void
  text: UiTextMap
}) {
  const policyLabels: Record<TorrentRemovalPolicy, string> = {
    immediate: text.seedingImmediate,
    keep: text.seedingKeep,
    defer: text.seedingDefer,
  }

  return (
    <div className="space-y-4 rounded-lg border p-3">
      <FormField label={text.seedingPolicy} htmlFor={`${idPrefix}-seeding-policy`}>
        <SelectControl id={`${idPrefix}-seeding-policy`} value={draft.seeding_policy} onValueChange={(value) => setDraft({ ...draft, seeding_policy: value as TorrentRemovalPolicy })} options={TORRENT_REMOVAL_POLICIES.map((value) => ({ value, label: policyLabels[value] }))} />
        <FieldHint text={text.seedingPolicyHint} />
      </FormField>

      {draft.seeding_policy === "defer" && (
        <div className="space-y-2">
          <div className="grid gap-3 sm:grid-cols-2">
            <FormField label={text.minSeedRatio} htmlFor={`${idPrefix}-min-seed-ratio`}>
              <Input
                id={`${idPrefix}-min-seed-ratio`}
                type="number"
                min={0}
                step={0.1}
                value={draft.min_seed_ratio}
                onChange={(event) => setDraft({ ...draft, min_seed_ratio: event.target.value })}
              />
            </FormField>
            <FormField label={text.minSeedTime} htmlFor={`${idPrefix}-min-seed-time`}>
              <Input
                id={`${idPrefix}-min-seed-time`}
                type="number"
                min={1}
                step={1}
                value={draft.min_seed_time_minutes}
                onChange={(event) => setDraft({ ...draft, min_seed_time_minutes: event.target.value })}
              />
            </FormField>
          </div>
          <FieldHint text={text.seedingThresholdHint} />
        </div>
      )}
    </div>
  )
}

export function ReadOnlyDetail({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border px-3 py-2.5">
      <p className="text-xs uppercase tracking-wide text-muted-foreground">{label}</p>
      <code className="mt-1 block break-all text-sm">{value}</code>
    </div>
  )
}

export function InstructionList({ items }: { items: string[] }) {
  return (
    <ul className="space-y-1.5 text-xs text-muted-foreground">
      {items.map((item) => (
        <li key={item} className="flex items-start gap-2">
          <CheckCircle2 className="mt-0.5 size-3.5 shrink-0 text-status-success" />
          <span>{item}</span>
        </li>
      ))}
    </ul>
  )
}



export function EmptyState({ title, description }: { title: string; description: string }) {
  return (
    <div className="rounded-lg border border-dashed p-4 text-sm text-muted-foreground">
      <p className="font-medium text-foreground">{title}</p>
      <p className="mt-1 text-xs">{description}</p>
    </div>
  )
}

export function StatusPill({
  tone,
  label,
}: {
  tone: "blue" | "green" | "red" | "neutral"
  label: string
}) {
  return (
    <div
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs font-medium",
        tone === "blue" &&
          "border-primary/30 bg-primary/10 text-primary",
        tone === "green" &&
          "border-status-success-border bg-status-success-bg text-status-success",
        tone === "red" &&
          "border-status-danger-border bg-status-danger-bg text-status-danger",
        tone === "neutral" && "border-border bg-background text-foreground",
      )}
    >
      <span
        className={cn(
          "size-1.5 rounded-full",
          tone === "blue" && "bg-primary",
          tone === "green" && "bg-status-success",
          tone === "red" && "bg-status-danger",
          tone === "neutral" && "bg-muted-foreground",
        )}
      />
      {label}
    </div>
  )
}

export function StatusDot({ healthStatus, text }: { healthStatus: HealthStatus; text: UiTextMap }) {
  if (healthStatus === "healthy") {
    return <span className="inline-flex size-2 rounded-full bg-status-success" title={text.healthy} />
  }
  if (healthStatus === "unreachable") {
    return <span className="inline-flex size-2 rounded-full bg-status-danger" title={text.unreachable} />
  }
  return <span className="inline-flex size-2 rounded-full bg-muted" title={text.notConfigured} />
}
