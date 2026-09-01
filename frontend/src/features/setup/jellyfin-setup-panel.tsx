import { CheckCircle2, ChevronDown, ChevronRight, CircleAlert, Copy, Info, RefreshCw, Sparkles, TestTubeDiagonal, Webhook } from "lucide-react"
import { useState } from "react"

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Textarea } from "@/components/ui/textarea"
import { GuideCard, InstructionList, ReadOnlyDetail, StatusPill } from "@/features/settings/service-presentation"
import type { DashboardPayload } from "@/lib/dashboard"
import type { UiTextMap } from "@/lib/i18n"
import { getItemTypeLabel, getStatusLabel } from "@/lib/service-config"
import { formatMediaTitle, getWebhookStatusLabel, getWebhookStatusTone } from "@/lib/status-format"

type SetupState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "success"; message: string }
  | { status: "not_found"; message: string }
  | { status: "error"; message: string }

export function JellyfinSetupPanel({
  text,
  dashboard,
  origin,
  curlPreview,
  tokenConfigured,
  jellyfinConfigured,
  onOpenGeneral,
  onSetupWebhook,
}: {
  text: UiTextMap
  dashboard: DashboardPayload | null
  origin: string
  curlPreview: string
  tokenConfigured: boolean
  jellyfinConfigured: boolean
  onOpenGeneral: () => void
  onSetupWebhook: (webhookUrl: string) => Promise<{ found: boolean; configured: boolean; message: string }>
}) {
  const webhookUrl = `${origin}/webhook/jellyfin`
  const [setupState, setSetupState] = useState<SetupState>({ status: "idle" })
  const [curlOpen, setCurlOpen] = useState(false)

  const webhookStatus = dashboard?.webhook_status
  const webhookTone = getWebhookStatusTone(webhookStatus?.outcome ?? "waiting")
  const lastAttemptAt = webhookStatus?.attempted_at
    ? new Date(webhookStatus.attempted_at).toLocaleString()
    : text.notReceivedYet
  const statusLabel = getWebhookStatusLabel(webhookStatus?.outcome ?? "waiting", text)

  async function handleSetup() {
    setSetupState({ status: "loading" })
    try {
      const result = await onSetupWebhook(webhookUrl)
      if (result.configured) {
        setSetupState({ status: "success", message: result.message })
      } else if (!result.found) {
        setSetupState({ status: "not_found", message: result.message })
      } else {
        setSetupState({ status: "error", message: result.message })
      }
    } catch (err) {
      setSetupState({
        status: "error",
        message: err instanceof Error ? err.message : text.unknownError,
      })
    }
  }

  return (
    <div className="space-y-5">
      {/* Auto-configure */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <Webhook className="size-4 text-primary" />
            {text.autoConfigureWebhook}
          </CardTitle>
          <CardDescription>
            {text.autoConfigureWebhookDescription}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {!jellyfinConfigured && (
            <Alert>
              <Info className="size-4 text-primary" />
              <AlertDescription>
                {text.connectJellyfinFirst}
              </AlertDescription>
            </Alert>
          )}
          {jellyfinConfigured && !tokenConfigured && (
            <Alert>
              <CircleAlert className="size-4" />
              <AlertDescription>
                <button
                  type="button"
                  className="underline underline-offset-2"
                  onClick={onOpenGeneral}
                >
                  {text.setWebhookTokenFirst}
                </button>
              </AlertDescription>
            </Alert>
          )}

          <div className="flex items-center gap-3">
            <Button
              disabled={!jellyfinConfigured || setupState.status === "loading"}
              onClick={() => void handleSetup()}
            >
              {setupState.status === "loading" ? (
                <RefreshCw className="size-4 animate-spin" />
              ) : setupState.status === "success" ? (
                <CheckCircle2 className="size-4" />
              ) : (
                <Webhook className="size-4" />
              )}
              {setupState.status === "loading"
                ? text.configuring
                : setupState.status === "success"
                  ? text.configured
                  : text.autoConfigureWebhook}
            </Button>
            {setupState.status === "success" && <StatusPill tone="green" label={text.done} />}
          </div>

          {setupState.status === "success" && (
            <Alert>
              <CheckCircle2 className="size-4 text-status-success" />
              <AlertDescription>{setupState.message}</AlertDescription>
            </Alert>
          )}
          {setupState.status === "error" && (
            <Alert variant="destructive">
              <CircleAlert className="size-4" />
              <AlertDescription>{setupState.message}</AlertDescription>
            </Alert>
          )}
          {setupState.status === "not_found" && (
            <div className="space-y-3">
              <Alert variant="destructive">
                <CircleAlert className="size-4" />
                <AlertDescription>{setupState.message}</AlertDescription>
              </Alert>
              <GuideCard
                tone="blue"
                title={text.installJellyfinWebhook}
                description={text.installJellyfinWebhookDescription}
              >
                <InstructionList items={[
                  text.jellyfinInstallStep1,
                  text.jellyfinInstallStep2,
                  text.jellyfinInstallStep3,
                  text.jellyfinInstallStep4,
                ]} />
              </GuideCard>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Verify delivery */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <TestTubeDiagonal className="size-4 text-status-success" />
            {text.verifyDelivery}
          </CardTitle>
          <CardDescription>
            {text.verifyDeliveryDescription}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
            <ReadOnlyDetail label={text.deliveryStatus} value={statusLabel} />
            <ReadOnlyDetail label={text.lastAttempt} value={lastAttemptAt} />
            <ReadOnlyDetail
              label={text.httpStatus}
              value={webhookStatus?.http_status ? String(webhookStatus.http_status) : text.none}
            />
            <ReadOnlyDetail
              label={text.lastItem}
              value={
                webhookStatus?.item_name
                  ? formatMediaTitle(getItemTypeLabel(webhookStatus.item_type ?? "Item", text), webhookStatus.item_name)
                  : text.noItemReceived
              }
            />
          </div>

          <div className="flex flex-wrap gap-2">
            <StatusPill tone={webhookTone} label={statusLabel} />
            {webhookStatus?.result_status && (
              <StatusPill
                tone={webhookStatus.result_status === "partial_failure" ? "red" : "green"}
                label={`${text.processing}: ${getStatusLabel(webhookStatus.result_status, text)}`}
              />
            )}
            {webhookStatus?.notification_type && (
              <StatusPill
                tone="blue"
                label={`${webhookStatus.notification_type}${webhookStatus.item_type ? ` / ${webhookStatus.item_type}` : ""}`}
              />
            )}
          </div>

          <Alert
            variant={
              webhookStatus?.outcome === "rejected_auth" ||
              webhookStatus?.outcome === "invalid_payload"
                ? "destructive"
                : "default"
            }
          >
            {webhookTone === "green" ? (
              <CheckCircle2 className="size-4 text-status-success" />
            ) : webhookTone === "red" ? (
              <CircleAlert className="size-4" />
            ) : (
              <Info className="size-4 text-primary" />
            )}
            <AlertTitle>{text.latestWebhookAttempt}</AlertTitle>
            <AlertDescription>
              {webhookStatus?.message ?? text.noJellyfinWebhook}
            </AlertDescription>
          </Alert>

          {/* Collapsible smoke-test cURL */}
          <Card className="border-dashed">
            <button
              type="button"
              className="flex w-full items-center gap-2 px-4 py-3 text-left text-sm"
              onClick={() => setCurlOpen((v) => !v)}
            >
              {curlOpen ? (
                <ChevronDown className="size-4 shrink-0 text-muted-foreground" />
              ) : (
                <ChevronRight className="size-4 shrink-0 text-muted-foreground" />
              )}
              <Sparkles className="size-4 shrink-0 text-status-success" />
              <span className="font-medium">{text.smokeTestCurl}</span>
              <span className="ml-auto text-xs text-muted-foreground">
                {tokenConfigured ? text.tokenPrefilled : text.configureTokenFirst}
              </span>
            </button>
            {curlOpen && (
              <CardContent className="space-y-3 border-t pt-3">
                <p className="text-xs text-muted-foreground">
                  {text.smokeTestDescription}
                </p>
                <Textarea
                  readOnly
                  value={curlPreview}
                  className="min-h-[180px] font-mono text-xs"
                />
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => void navigator.clipboard.writeText(curlPreview)}
                >
                  <Copy className="size-4 text-primary" />
                  {text.copyCurl}
                </Button>
              </CardContent>
            )}
          </Card>
        </CardContent>
      </Card>
    </div>
  )
}



// ─── General settings modal ───────────────────────────────────────────────────
