import { ChevronDown, Film, Search, Tv, Webhook } from "lucide-react"
import { useMemo } from "react"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { EmptyState, StatusPill } from "@/features/settings/service-presentation"
import type { DashboardAction, DashboardActivity, DashboardUnifiedActivityItem, DashboardWebhookAttempt } from "@/lib/dashboard"
import type { UiTextMap } from "@/lib/i18n"
import { getStatusLabel } from "@/lib/service-config"
import { getWebhookStatusLabel, getWebhookStatusTone } from "@/lib/status-format"

type ActivityItem = DashboardUnifiedActivityItem

export function ActivityPanel({ text, filteredActivity, webhookAttempts, activityFilter, onFilterChange }: { text: UiTextMap; filteredActivity: DashboardActivity[]; webhookAttempts: DashboardWebhookAttempt[]; activityFilter: string; onFilterChange: (value: string) => void }) {
  const activityItems = useMemo(() => mergeActivity(filteredActivity, webhookAttempts), [filteredActivity, webhookAttempts])
  return <section className="space-y-5">
    <header><h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">{text.activity}</h1><p className="mt-1 text-sm text-muted-foreground">{text.activityPageDescription}</p></header>
    <Card className="overflow-hidden">
      <CardHeader className="gap-4 border-b sm:flex-row sm:items-center sm:justify-between"><div><CardTitle className="text-base">{text.activityTimeline}</CardTitle><CardDescription>{text.activityTimelineDescription}</CardDescription></div><div className="flex w-full items-center gap-2 sm:max-w-sm"><div className="relative min-w-0 flex-1"><Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" /><Input className="pl-9" value={activityFilter} onChange={(event) => onFilterChange(event.target.value)} placeholder={text.filter} aria-label={text.filter} /></div>{activityFilter ? <Button variant="ghost" size="sm" onClick={() => onFilterChange("")}>{text.clear}</Button> : null}</div></CardHeader>
      <CardContent className="p-0">{activityItems.length === 0 ? <div className="p-5"><EmptyState title={text.noActivity} description={activityFilter ? text.noActivityFiltered : text.sendWebhookToSeeActivity} /></div> : <div role="list" aria-label={text.activityTimeline} className="divide-y">{activityItems.map((item) => <ActivityEventRow key={activityKey(item)} item={item} text={text} />)}</div>}</CardContent>
    </Card>
  </section>
}

function mergeActivity(activity: DashboardActivity[], webhookAttempts: DashboardWebhookAttempt[]): ActivityItem[] {
  return [...activity.map((entry) => ({ kind: "processed_activity" as const, ...entry, sort_at: Date.parse(entry.processed_at) })), ...webhookAttempts.map((attempt) => ({ kind: "webhook_attempt" as const, ...attempt, sort_at: Date.parse(attempt.attempted_at) }))].map((item) => ({ ...item, sort_at: Number.isNaN(item.sort_at) ? 0 : item.sort_at })).sort((left, right) => right.sort_at - left.sort_at) as ActivityItem[]
}

function activityKey(item: ActivityItem) { return item.kind === "processed_activity" ? `processed-${item.processed_at}-${item.result.item_id}` : `webhook-${item.attempted_at}-${item.message}` }

function ActivityEventRow({ item, text }: { item: ActivityItem; text: UiTextMap }) {
  const processed = item.kind === "processed_activity"
  const Icon = processed ? (item.result.item_type === "Movie" ? Film : Tv) : Webhook
  const title = processed ? item.result.name : item.item_name ?? text.item
  const outcome = processed ? friendlyOutcome(item.result.status, text) : getWebhookStatusLabel(item.outcome, text)
  const tone = processed ? item.result.status === "partial_failure" ? "red" : "green" : getWebhookStatusTone(item.outcome)
  const timestamp = processed ? item.processed_at : item.attempted_at
  return <details role="listitem" className="group open:bg-muted/20">
    <summary className="grid min-h-20 cursor-pointer list-none items-center gap-3 px-4 py-3 focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-inset focus-visible:ring-ring/50 sm:grid-cols-[auto_minmax(0,1fr)_auto_auto] [&::-webkit-details-marker]:hidden">
      <span className="grid size-10 place-items-center rounded-xl bg-primary/10 text-primary"><Icon className="size-4" /></span>
      <span className="min-w-0"><span className="block truncate text-sm font-semibold">{title}</span><span className="mt-1 block text-xs text-muted-foreground">{processed ? text.recentActivityProcessed.replace("{{item}}", title) : text.recentActivityWebhook.replace("{{item}}", title)}</span></span>
      <span className="flex items-center gap-3"><StatusPill tone={tone} label={outcome} /><time className="hidden whitespace-nowrap text-xs text-muted-foreground md:inline">{new Date(timestamp).toLocaleString()}</time></span>
      <ChevronDown className="size-4 text-muted-foreground transition-transform duration-200 group-open:rotate-180" aria-hidden="true" />
    </summary>
    <div className="border-t bg-background/60 px-4 py-4 sm:pl-[4.25rem]"><p className="mb-3 text-xs text-muted-foreground md:hidden">{new Date(timestamp).toLocaleString()}</p>{processed ? <ProcessedDetails entry={item} text={text} /> : <WebhookDetails attempt={item} text={text} />}</div>
  </details>
}

function ProcessedDetails({ entry, text }: { entry: DashboardActivity; text: UiTextMap }) {
  return <div className="space-y-2">{entry.result.actions.length ? entry.result.actions.map((action, index) => <ActionDetail key={`${action.system}-${action.action}-${index}`} action={action} text={text} />) : <p className="text-sm text-muted-foreground">{text.noItemsYet}</p>}</div>
}

function WebhookDetails({ attempt, text }: { attempt: DashboardWebhookAttempt; text: UiTextMap }) {
  return <dl className="grid gap-2 text-sm sm:grid-cols-2"><div><dt className="text-xs text-muted-foreground">{text.webhookMessageLabel}</dt><dd className="mt-1">{attempt.message}</dd></div><div><dt className="text-xs text-muted-foreground">{text.httpStatus}</dt><dd className="mt-1">{attempt.http_status ?? text.noStatus}</dd></div>{attempt.notification_type ? <div><dt className="text-xs text-muted-foreground">{text.webhookNotificationLabel}</dt><dd className="mt-1"><code>{attempt.notification_type}</code></dd></div> : null}{attempt.result_status ? <div><dt className="text-xs text-muted-foreground">{text.webhookResultStatusLabel}</dt><dd className="mt-1">{getStatusLabel(attempt.result_status, text)}</dd></div> : null}</dl>
}

function ActionDetail({ action, text }: { action: DashboardAction; text: UiTextMap }) {
  return <div className="rounded-lg border bg-card p-3 text-xs text-muted-foreground"><div className="flex items-center justify-between gap-2"><code>{action.system}/{action.action}</code><StatusPill tone={action.status === "failed" ? "red" : action.status === "deleted" ? "green" : "blue"} label={getStatusLabel(action.status, text)} /></div><p className="mt-2">{action.message}</p>{action.reason ? <p className="mt-1">{text.reasonLabel} <code>{action.reason}</code></p> : null}</div>
}

function friendlyOutcome(status: string, text: UiTextMap) { if (status === "dry_run") return text.dryRun; if (status === "ignored") return text.skipped; if (status === "already_absent") return text.deleted; const label = getStatusLabel(status, text); return label === status ? text.unknown : label }
