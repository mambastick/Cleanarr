import { Activity, ChevronDown, ChevronRight, Film, Tv, Webhook } from "lucide-react"
import { useMemo, useState } from "react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { ScrollArea } from "@/components/ui/scroll-area"
import { EmptyState, StatusPill } from "@/features/settings/service-presentation"
import type { DashboardAction, DashboardActivity, DashboardUnifiedActivityItem, DashboardWebhookAttempt } from "@/lib/dashboard"
import type { UiTextMap } from "@/lib/i18n"
import { getItemTypeLabel, getStatusLabel } from "@/lib/service-config"
import { getWebhookStatusLabel, getWebhookStatusTone } from "@/lib/status-format"

export function ActivityPanel({
  text,
  filteredActivity,
  webhookAttempts,
  activityFilter,
  onFilterChange,
}: {
  text: UiTextMap
  filteredActivity: DashboardActivity[]
  webhookAttempts: DashboardWebhookAttempt[]
  activityFilter: string
  onFilterChange: (v: string) => void
}) {
  const activityItems = useMemo(() => {
    const merged = [
      ...filteredActivity.map((entry) => ({
        kind: "processed_activity" as const,
        ...entry,
        sort_at: Date.parse(entry.processed_at),
      })),
      ...webhookAttempts.map((attempt) => ({
        kind: "webhook_attempt" as const,
        ...attempt,
        sort_at: Date.parse(attempt.attempted_at),
      })),
    ]
      .map((item) => ({ ...item, sort_at: Number.isNaN(item.sort_at) ? 0 : item.sort_at }))
      .sort((left, right) => right.sort_at - left.sort_at) as DashboardUnifiedActivityItem[]

    return merged
  }, [filteredActivity, webhookAttempts])

  const activityCount = activityItems.length

  return (
    <section className="space-y-4">
      <div className="flex items-center gap-3">
        <Input
          value={activityFilter}
          onChange={(e) => onFilterChange(e.target.value)}
          placeholder={text.filter}
          className="max-w-sm"
        />
        {activityFilter && (
          <Button variant="ghost" size="sm" onClick={() => onFilterChange("")}>
            {text.clear}
          </Button>
        )}
        <span className="ml-auto text-sm text-muted-foreground">
          {activityCount} {text.eventCount}
        </span>
      </div>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <Activity className="size-4 text-status-success" />
            {text.activityTimeline}
          </CardTitle>
          <CardDescription>{text.activityTimelineDescription}</CardDescription>
        </CardHeader>
        <CardContent>
          <ScrollArea className="h-[480px]">
            {activityItems.length === 0 ? (
              <EmptyState
                title={text.noActivity}
                description={
                  activityFilter
                    ? text.noActivityFiltered
                    : text.sendWebhookToSeeActivity
                }
              />
            ) : (
              <div className="space-y-2 p-px">
                {activityItems.map((item) =>
                  item.kind === "webhook_attempt" ? (
                    <WebhookAttemptEntry
                      key={`${item.kind}-${item.attempted_at}-${item.message}`}
                      attempt={item}
                      text={text}
                    />
                  ) : (
                    <ActivityEntry
                      key={`${item.kind}-${item.processed_at}-${item.result.item_id}`}
                      entry={item}
                      text={text}
                    />
                  ),
                )}
              </div>
            )}
          </ScrollArea>
        </CardContent>
      </Card>
    </section>
  )
}
// ─── Settings panel ───────────────────────────────────────────────────────────


function WebhookAttemptEntry({ attempt, text }: { attempt: DashboardWebhookAttempt; text: UiTextMap }) {
  const [open, setOpen] = useState(false)
  const tone = getWebhookStatusTone(attempt.outcome)

  return (
    <Card>
      <button
        type="button"
        className="flex w-full items-center gap-3 px-4 py-3 text-left"
        onClick={() => setOpen((v) => !v)}
      >
        {open ? (
          <ChevronDown className="size-4 shrink-0 text-muted-foreground" />
        ) : (
          <ChevronRight className="size-4 shrink-0 text-muted-foreground" />
        )}
        <Webhook className="size-4 shrink-0 text-primary" />
        <div className="min-w-0 flex-1 space-y-1">
          <span className="block truncate text-sm font-medium">{attempt.item_name ?? attempt.message}</span>
          <span className="text-xs text-muted-foreground">
            {new Date(attempt.attempted_at).toLocaleString()}
          </span>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <Badge variant="outline" className="text-xs">
            {attempt.http_status != null ? attempt.http_status : text.noStatus}
          </Badge>
          <StatusPill tone={tone} label={getWebhookStatusLabel(attempt.outcome, text)} />
        </div>
      </button>

      {open && (
        <CardContent className="border-t pb-3 pt-3 space-y-3">
          <div className="space-y-1 text-xs text-muted-foreground">
            <p>
              <span className="text-foreground">{text.webhookMessageLabel}</span> {attempt.message}
            </p>
            {attempt.payload_event_count != null ? (
              <p>
                <span className="text-foreground">{text.webhookPayloadEventsLabel}</span> {attempt.payload_event_count}
              </p>
            ) : null}
            <p>
              <span className="text-foreground">{text.webhookNotificationLabel}</span>{" "}
              {attempt.notification_type ?? "—"}
              {attempt.item_type ? ` / ${attempt.item_type}` : ""}
            </p>
            {attempt.result_status && (
              <p>
                <span className="text-foreground">{text.webhookResultStatusLabel}</span> {getStatusLabel(attempt.result_status, text)}
              </p>
            )}
          </div>
        </CardContent>
      )}
    </Card>
  )
}

function ActivityEntry({ entry, text }: { entry: DashboardActivity; text: UiTextMap }) {
  const [open, setOpen] = useState(false)
  const Icon = entry.result.item_type === "Movie" ? Film : Tv
  const hasActions = entry.result.actions.length > 0
  return (
    <Card>
      <button
        type="button"
        className="flex w-full items-center gap-3 px-4 py-3 text-left"
        onClick={() => setOpen((v) => !v)}
      >
        {open ? (
          <ChevronDown className="size-4 shrink-0 text-muted-foreground" />
        ) : (
          <ChevronRight className="size-4 shrink-0 text-muted-foreground" />
        )}
        <Icon className="size-4 shrink-0 text-primary" />
        <span className="flex-1 truncate text-sm font-medium">{entry.result.name}</span>
        <div className="flex shrink-0 items-center gap-2">
          <Badge variant="outline" className="text-xs">{getItemTypeLabel(entry.result.item_type, text)}</Badge>
          <StatusPill
            tone={entry.result.status === "partial_failure" ? "red" : "green"}
            label={getStatusLabel(entry.result.status, text)}
          />
          <span className="hidden text-xs text-muted-foreground sm:block">
            {new Date(entry.processed_at).toLocaleString()}
          </span>
        </div>
      </button>

      {open && (
        <CardContent className="border-t pb-3 pt-3 space-y-3">
          <div className="text-xs text-muted-foreground sm:hidden">
            {new Date(entry.processed_at).toLocaleString()}
          </div>
          <div className="flex flex-wrap gap-1.5">
            {Object.entries(entry.action_summary).map(([k, v]) => (
              <Badge key={k} variant="outline" className="text-xs">
                {k}: {v}
              </Badge>
            ))}
          </div>
          <div className="space-y-1.5">
            {entry.result.actions.map((action, i) => (
              <ActionRow key={`${action.system}-${action.action}-${i}`} action={action} text={text} />
            ))}
          </div>
          {!hasActions && (
            <p className="text-xs text-muted-foreground">{text.noItemsYet}</p>
          )}
        </CardContent>
      )}
    </Card>
  )
}

function ActionRow({ action, text }: { action: DashboardAction; text: UiTextMap }) {
  return (
    <div className="rounded-lg border p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="outline" className="text-xs">{action.system}</Badge>
          <span className="text-sm font-medium">{action.action}</span>
        </div>
        <StatusPill
          tone={action.status === "failed" ? "red" : action.status === "deleted" ? "green" : "blue"}
          label={getStatusLabel(action.status, text)}
        />
      </div>
      <p className="mt-1.5 text-xs text-muted-foreground">{action.message}</p>
      {action.reason && (
      <p className="mt-1 text-xs text-muted-foreground">
          {text.reasonLabel} <span className="font-mono">{action.reason}</span>
        </p>
      )}
    </div>
  )
}
