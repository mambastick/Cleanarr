import { Film, Tv, Webhook } from "lucide-react"
import { useMemo, useState } from "react"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { EmptyState, StatusPill } from "@/features/settings/service-presentation"
import type { DashboardAction, DashboardActivity, DashboardUnifiedActivityItem, DashboardWebhookAttempt } from "@/lib/dashboard"
import type { UiTextMap } from "@/lib/i18n"
import { getStatusLabel } from "@/lib/service-config"
import { getWebhookStatusLabel, getWebhookStatusTone } from "@/lib/status-format"
import { cn } from "@/lib/utils"

type ActivityItem = DashboardUnifiedActivityItem

export function ActivityPanel({ text, filteredActivity, webhookAttempts, activityFilter, onFilterChange }: {
  text: UiTextMap
  filteredActivity: DashboardActivity[]
  webhookAttempts: DashboardWebhookAttempt[]
  activityFilter: string
  onFilterChange: (v: string) => void
}) {
  const activityItems = useMemo(() => mergeActivity(filteredActivity, webhookAttempts), [filteredActivity, webhookAttempts])
  const [selectedKey, setSelectedKey] = useState<string | null>(null)
  const activeKey = selectedKey && activityItems.some((item) => activityKey(item) === selectedKey) ? selectedKey : activityItems[0] ? activityKey(activityItems[0]) : null
  const selected = activityItems.find((item) => activityKey(item) === activeKey) ?? null

  return <section className="space-y-5">
    <header>
      <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">{text.activity}</h1>
      <p className="mt-1 text-sm text-muted-foreground">{text.activityPageDescription}</p>
    </header>
    <div className="flex flex-wrap items-center gap-3">
      <Input value={activityFilter} onChange={(event) => onFilterChange(event.target.value)} placeholder={text.filter} aria-label={text.filter} className="max-w-sm" />
      {activityFilter ? <Button variant="ghost" size="sm" onClick={() => onFilterChange("")}>{text.clear}</Button> : null}
      <span className="ml-auto text-sm text-muted-foreground">{activityItems.length} {text.eventCount}</span>
    </div>
    {activityItems.length === 0 ? <EmptyState title={text.noActivity} description={activityFilter ? text.noActivityFiltered : text.sendWebhookToSeeActivity} /> : <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_22rem]">
      <div className="grid gap-3 sm:grid-cols-2 2xl:grid-cols-3" role="list" aria-label={text.activityTimeline}>
        {activityItems.map((item) => <ActivityEventCard key={activityKey(item)} item={item} text={text} selected={activityKey(item) === activeKey} onSelect={() => setSelectedKey(activityKey(item))} />)}
      </div>
      <ActivityInspector item={selected} text={text} />
    </div>}
  </section>
}

function mergeActivity(activity: DashboardActivity[], webhookAttempts: DashboardWebhookAttempt[]): ActivityItem[] {
  return [
    ...activity.map((entry) => ({ kind: "processed_activity" as const, ...entry, sort_at: Date.parse(entry.processed_at) })),
    ...webhookAttempts.map((attempt) => ({ kind: "webhook_attempt" as const, ...attempt, sort_at: Date.parse(attempt.attempted_at) })),
  ].map((item) => ({ ...item, sort_at: Number.isNaN(item.sort_at) ? 0 : item.sort_at })).sort((left, right) => right.sort_at - left.sort_at) as ActivityItem[]
}

function activityKey(item: ActivityItem) {
  return item.kind === "processed_activity" ? `processed-${item.processed_at}-${item.result.item_id}` : `webhook-${item.attempted_at}-${item.message}`
}

function ActivityEventCard({ item, text, selected, onSelect }: { item: ActivityItem; text: UiTextMap; selected: boolean; onSelect: () => void }) {
  const processed = item.kind === "processed_activity"
  const Icon = processed ? (item.result.item_type === "Movie" ? Film : Tv) : Webhook
  const title = processed ? item.result.name : item.item_name ?? text.item
  const outcome = processed ? friendlyOutcome(item.result.status, text) : getWebhookStatusLabel(item.outcome, text)
  const tone = processed ? item.result.status === "partial_failure" ? "red" : "green" : getWebhookStatusTone(item.outcome)
  const timestamp = processed ? item.processed_at : item.attempted_at

  return <Card role="listitem" className={cn("relative transition-colors", selected && "border-primary/50 bg-primary/5")}>
    <CardContent className="pointer-events-none space-y-4 p-4">
      <div className="flex items-start justify-between gap-3"><div className="flex min-w-0 items-start gap-3"><div className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-muted"><Icon className="size-4 text-primary" /></div><div className="min-w-0"><p className="truncate text-sm font-semibold">{title}</p><p className="mt-1 text-xs text-muted-foreground">{processed ? text.recentActivityProcessed.replace("{{item}}", title) : text.recentActivityWebhook.replace("{{item}}", title)}</p></div></div><StatusPill tone={tone} label={outcome} /></div>
      <div className="flex items-center justify-between gap-3"><time className="text-xs text-muted-foreground">{new Date(timestamp).toLocaleString()}</time><span className="text-xs font-medium text-primary">{text.viewDetails}</span></div>
    </CardContent>
    <button type="button" className="absolute inset-0 rounded-xl focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/50" onClick={onSelect} aria-label={`${text.viewDetails}: ${title}`} aria-pressed={selected} />
  </Card>
}

function ActivityInspector({ item, text }: { item: ActivityItem | null; text: UiTextMap }) {
  if (!item) return null
  const processed = item.kind === "processed_activity"
  const title = processed ? item.result.name : item.item_name ?? text.item
  const outcome = processed ? friendlyOutcome(item.result.status, text) : getWebhookStatusLabel(item.outcome, text)
  const tone = processed ? item.result.status === "partial_failure" ? "red" : "green" : getWebhookStatusTone(item.outcome)
  return <Card className="xl:sticky xl:top-5 xl:h-fit"><CardHeader className="pb-3"><CardTitle className="flex items-center justify-between gap-3 text-base"><span>{text.eventDetails}</span><StatusPill tone={tone} label={outcome} /></CardTitle><CardDescription>{title}</CardDescription></CardHeader><CardContent className="space-y-3"><p className="text-xs text-muted-foreground">{new Date(processed ? item.processed_at : item.attempted_at).toLocaleString()}</p>{processed ? <ProcessedDetails entry={item} text={text} /> : <WebhookDetails attempt={item} text={text} />}</CardContent></Card>
}

function ProcessedDetails({ entry, text }: { entry: DashboardActivity; text: UiTextMap }) {
  return <details className="rounded-lg border p-3 text-xs text-muted-foreground"><summary className="cursor-pointer font-medium text-foreground">{text.technicalDetails}</summary><div className="mt-3 space-y-2">{entry.result.actions.length ? entry.result.actions.map((action, index) => <ActionDetail key={`${action.system}-${action.action}-${index}`} action={action} text={text} />) : <p>{text.noItemsYet}</p>}</div></details>
}

function WebhookDetails({ attempt, text }: { attempt: DashboardWebhookAttempt; text: UiTextMap }) {
  return <details className="rounded-lg border p-3 text-xs text-muted-foreground"><summary className="cursor-pointer font-medium text-foreground">{text.technicalDetails}</summary><div className="mt-3 space-y-1"><p>{text.webhookMessageLabel} {attempt.message}</p><p>{text.httpStatus} {attempt.http_status ?? text.noStatus}</p>{attempt.notification_type ? <p>{text.webhookNotificationLabel} <code>{attempt.notification_type}</code></p> : null}{attempt.result_status ? <p>{text.webhookResultStatusLabel} {getStatusLabel(attempt.result_status, text)}</p> : null}</div></details>
}

function ActionDetail({ action, text }: { action: DashboardAction; text: UiTextMap }) {
  return <div className="rounded-md bg-muted/60 p-2"><div className="flex items-center justify-between gap-2"><code>{action.system}/{action.action}</code><StatusPill tone={action.status === "failed" ? "red" : action.status === "deleted" ? "green" : "blue"} label={getStatusLabel(action.status, text)} /></div><p className="mt-1">{action.message}</p>{action.reason ? <p className="mt-1">{text.reasonLabel} <code>{action.reason}</code></p> : null}</div>
}

function friendlyOutcome(status: string, text: UiTextMap) {
  if (status === "dry_run") return text.dryRun
  if (status === "ignored") return text.skipped
  if (status === "already_absent") return text.deleted
  const label = getStatusLabel(status, text)
  return label === status ? text.unknown : label
}
