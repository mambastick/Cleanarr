import { CheckCircle2, Copy, Eye, EyeOff, LoaderCircle, Plus, RefreshCw, TestTubeDiagonal } from "lucide-react"
import { useCallback, useEffect, useState } from "react"
import { motion, useReducedMotion } from "motion/react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { ProfileRuntimeControls } from "@/features/setup/profile-runtime-controls"
import { SsoConfigSection } from "@/features/settings/sso-config-section"
import { FieldHint, FormField, SelectControl } from "@/features/settings/form-presentation"
import { DownloaderPolicyFields, EmptyState, GuideCard, InstructionList, StatusPill } from "@/features/settings/service-presentation"
import { hasCurrentConnectionEvidence } from "@/lib/downloader-profile"
import type { DashboardPayload } from "@/lib/dashboard"
import type { UiTextMap } from "@/lib/i18n"
import { DOWNLOADER_KIND_OPTIONS, EMPTY_DRAFTS, generateWebhookToken, getDownloaderLabel, getServiceDescription, getServiceExample, getServiceFieldHint, getServiceFieldLabel, getServiceFields, getServiceHelp, getServiceTitle, getServices, JELLYFIN_LANGUAGE_OPTIONS, LOG_LEVEL_OPTIONS, resolveActiveService, SERVICE_META, toDraft, UI_LANGUAGE_OPTIONS, type DownloaderKind, type ServiceDraft, type ServiceFamily } from "@/lib/service-config"
import type { ConnectionTestResponse, GeneralConfig, RuntimeConfigPayload } from "@/lib/runtime-config"
import { normalizeError } from "@/lib/status-format"
import { cn } from "@/lib/utils"
import { JellyfinSetupPanel } from "@/features/setup/jellyfin-setup-panel"

export function WizardGeneralStep({
  config,
  onSave,
  text,
  registerSave,
}: {
  config: RuntimeConfigPayload | null
  onSave: (payload: GeneralConfig) => Promise<void>
  text: UiTextMap
  registerSave?: (save: () => Promise<boolean>) => () => void
}) {
  const general = config?.general ?? null
  const [draft, setDraft] = useState<GeneralConfig | null>(() =>
    general ? structuredClone(general) : null,
  )
  const [isSaving, setIsSaving] = useState(false)
  const [tokenCopied, setTokenCopied] = useState(false)
  const [isTokenVisible, setIsTokenVisible] = useState(false)
  const [isSSOSecretVisible, setIsSSOSecretVisible] = useState(false)

  useEffect(() => {
    setDraft(general ? structuredClone(general) : null)
  }, [general])

  const handleSave = useCallback(async () => {
    if (!draft || (general && JSON.stringify(draft) === JSON.stringify(general))) return true
    setIsSaving(true)
    try {
      await onSave(draft)
      return true
    } catch (e) {
      toast.error(normalizeError(e))
      return false
    } finally {
      setIsSaving(false)
    }
  }, [draft, general, onSave])

  useEffect(() => registerSave?.(handleSave), [handleSave, registerSave])

  if (!draft) {
    return (
      <EmptyState
        title={text.settingsUnavailable}
        description={text.tryAgain}
      />
    )
  }

  return (
    <div className="space-y-4 pb-2">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 className="text-lg font-semibold">{text.general}</h2>
          <p className="text-sm text-muted-foreground">{text.runtimeSettingsSummary}</p>
        </div>
        <p className="rounded-md bg-muted px-2.5 py-1 text-xs text-muted-foreground" aria-live="polite">
          {isSaving ? text.savingProgress : text.savedOnContinue}
        </p>
      </div>
      <Tabs defaultValue="basic" className="gap-4">
        <TabsList className="w-full sm:w-fit" aria-label={text.general}>
          <TabsTrigger value="basic" className="min-w-32">{text.basicSettings}</TabsTrigger>
          <TabsTrigger value="sso" className="min-w-32">{text.ssoSettings}</TabsTrigger>
        </TabsList>
        <TabsContent value="basic">
          <div className="space-y-4 rounded-xl border border-border bg-background p-4">
            <div className="grid gap-3 sm:grid-cols-3">
              <FormField label={text.logLevel} htmlFor="wizard-log-level">
                <SelectControl id="wizard-log-level" value={draft.log_level} onValueChange={(value) => setDraft({ ...draft, log_level: value })} options={LOG_LEVEL_OPTIONS.map((value) => ({ value, label: value }))} />
              </FormField>
              <FormField label={text.httpTimeoutSeconds} htmlFor="wizard-timeout">
                <Input id="wizard-timeout" type="number" min={1} step={1} value={String(draft.http_timeout_seconds)} onChange={(e) => setDraft({ ...draft, http_timeout_seconds: Number(e.target.value) })} />
              </FormField>
              <FormField label={text.activityRetention} htmlFor="wizard-retention">
                <SelectControl id="wizard-retention" value={String(draft.activity_retention_days)} onValueChange={(value) => setDraft({ ...draft, activity_retention_days: Number(value) })} options={[{ value: "1", label: text.oneDay }, { value: "7", label: text.sevenDays }, { value: "30", label: text.thirtyDays }, { value: "90", label: text.ninetyDays }, { value: "365", label: text.oneYear }]} />
              </FormField>
              <FormField label={text.jellyfinMetadataLanguage} htmlFor="wizard-jellyfin-language">
                <SelectControl id="wizard-jellyfin-language" value={draft.jellyfin_language} onValueChange={(value) => setDraft({ ...draft, jellyfin_language: value })} options={JELLYFIN_LANGUAGE_OPTIONS} />
              </FormField>
              <FormField label={text.uiLanguage} htmlFor="wizard-ui-language">
                <SelectControl id="wizard-ui-language" value={draft.ui_language} onValueChange={(value) => setDraft({ ...draft, ui_language: value })} options={UI_LANGUAGE_OPTIONS} />
              </FormField>
            </div>
            <FormField label={text.webhookToken} htmlFor="wizard-webhook-token">
              <div className="flex items-center gap-2">
                <code id="wizard-webhook-token" className="min-w-0 flex-1 truncate rounded-md border border-input bg-muted px-3 py-2 font-mono text-xs select-all">
                  {isTokenVisible ? (draft.webhook_shared_token ?? "—") : "•".repeat(32)}
                </code>
                <Button type="button" variant="outline" size="icon" aria-label={isTokenVisible ? text.hideToken : text.showToken} title={isTokenVisible ? text.hideToken : text.showToken} onClick={() => setIsTokenVisible((v) => !v)}>
                  {isTokenVisible ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
                </Button>
                <Button type="button" variant="outline" size="icon" aria-label={text.regenerateToken} title={text.regenerateToken} onClick={() => setDraft({ ...draft, webhook_shared_token: generateWebhookToken() })}>
                  <RefreshCw className="size-4" />
                </Button>
                <Button type="button" variant="outline" size="icon" disabled={!draft.webhook_shared_token} aria-label={text.copyToken} title={text.copyToken} onClick={async () => { await navigator.clipboard.writeText(draft.webhook_shared_token ?? ""); setTokenCopied(true); setTimeout(() => setTokenCopied(false), 2000) }}>
                  {tokenCopied ? <CheckCircle2 className="size-4 text-status-success" /> : <Copy className="size-4" />}
                </Button>
              </div>
              <FieldHint text={text.tokenHint} />
            </FormField>
          </div>
        </TabsContent>
        <TabsContent value="sso">
          <SsoConfigSection text={text} namespace="wizard" draft={draft} onDraftChange={setDraft} isSecretVisible={isSSOSecretVisible} onToggleSecretVisibility={() => setIsSSOSecretVisible((v) => !v)} compact />
        </TabsContent>
      </Tabs>
    </div>
  )
}

export function WizardServiceStep({
  family,
  config,
  text,
  onSave,
  onTest,
  testedDownloaderFingerprints,
  jellyfinSetupProps,
  registerSave,
}: {
  family: ServiceFamily
  config: RuntimeConfigPayload | null
  text: UiTextMap
  onSave: (family: ServiceFamily, draft: ServiceDraft) => Promise<void>
  onTest: (family: ServiceFamily, draft: ServiceDraft) => Promise<ConnectionTestResponse>
  testedDownloaderFingerprints: ReadonlySet<string>
  registerSave?: (save: () => Promise<boolean>) => () => void
  jellyfinSetupProps?: {
    dashboard: DashboardPayload | null
    origin: string
    curlPreview: string
    tokenConfigured: boolean
    onSetupWebhook: (webhookUrl: string) => Promise<{ found: boolean; configured: boolean; message: string }>
  }
}) {
  const meta = SERVICE_META[family]
  const existingServices = getServices(config, family)
  const existingService = resolveActiveService(existingServices) ?? existingServices[0] ?? null

  const [draft, setDraft] = useState<ServiceDraft>(() =>
    existingService ? toDraft(existingService) : structuredClone(EMPTY_DRAFTS[family]),
  )
  const [isSaving, setIsSaving] = useState(false)
  const [isTesting, setIsTesting] = useState(false)
  const reduceMotion = useReducedMotion()

  useEffect(() => {
    const svc = resolveActiveService(getServices(config, family)) ?? getServices(config, family)[0] ?? null
    setDraft(svc ? toDraft(svc) : structuredClone(EMPTY_DRAFTS[family]))
  }, [config, family])

  const alreadyConfigured = Boolean(existingService)
  const hasCurrentEvidence = family === "downloaders" && hasCurrentConnectionEvidence(draft, testedDownloaderFingerprints)

  const handleTest = async () => {
    setIsTesting(true)
    try {
      const result = await onTest(family, draft)
      if (result.ok) {
        toast.success(result.message)
      } else {
        toast.error(result.message)
      }
    } catch (e) {
      toast.error(normalizeError(e))
    } finally {
      setIsTesting(false)
    }
  }

  const baselineDraft = existingService ? toDraft(existingService) : EMPTY_DRAFTS[family]
  const handleSave = useCallback(async () => {
    if (JSON.stringify(draft) === JSON.stringify(baselineDraft)) return true
    setIsSaving(true)
    try {
      await onSave(family, draft)
      return true
    } catch (e) {
      toast.error(normalizeError(e))
      return false
    } finally {
      setIsSaving(false)
    }
  }, [baselineDraft, draft, family, onSave])

  useEffect(() => registerSave?.(handleSave), [handleSave, registerSave])

  const connectionFields = (
    <div className="space-y-5">
      <GuideCard
        tone={meta.accent}
        title={text.beforeYouSave}
        description={text.beforeSaveDescription}
      >
        <InstructionList items={getServiceHelp(meta, text, draft)} />
      </GuideCard>

      {family === "downloaders" && (
        <div className="space-y-3 rounded-lg border border-status-warning-border bg-status-warning-bg/40 p-3">
          <p className="text-sm font-medium">{text.enabledTopology}</p>
          {existingServices.length > 0 ? <div className="space-y-2">{existingServices.map((service) => (
            <motion.button key={service.id} type="button" onClick={() => setDraft(toDraft(service))} initial={reduceMotion ? false : { opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={reduceMotion ? { duration: 0 } : { duration: 0.2 }} className="flex w-full items-center justify-between rounded-md border border-border bg-card px-3 py-2 text-left text-sm hover:bg-muted focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/50">
              <span>{service.name} · {getDownloaderLabel(service.kind as DownloaderKind)}</span>
              <span className={service.enabled ? "text-status-success" : "text-muted-foreground"}>{service.enabled ? text.enabled : text.disabled}{service.is_default ? ` · ${text.defaultLabel}` : ""}</span>
            </motion.button>
          ))}</div> : <p className="text-sm text-muted-foreground">{text.connectionIncomplete}</p>}
          <Button type="button" variant="outline" size="sm" onClick={() => setDraft(structuredClone(EMPTY_DRAFTS.downloaders))}><Plus className="size-3.5" />{text.addAnotherProfile}</Button>
        </div>
      )}

      {family === "downloaders" && (
        <FormField label={text.torrentClient} htmlFor="wizard-downloader-kind">
          <SelectControl id="wizard-downloader-kind" value={draft.downloader_kind ?? "qbittorrent"} disabled={Boolean(draft.id)} onValueChange={(value) => {
              const kind = value as DownloaderKind
              setDraft({ ...draft, downloader_kind: kind, name: getDownloaderLabel(kind) })
            }} options={DOWNLOADER_KIND_OPTIONS} />
        </FormField>
      )}

      <FormField label={text.displayName} htmlFor={`wizard-${family}-name`}>
        <Input id={`wizard-${family}-name`} value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} />
      </FormField>

      <FormField label={text.baseUrl} htmlFor={`wizard-${family}-url`}>
        <Input id={`wizard-${family}-url`} type="url" value={draft.url} onChange={(e) => setDraft({ ...draft, url: e.target.value })} placeholder={getServiceExample(meta, draft)} />
        <FieldHint text={family === "downloaders" ? text.downloaderUrlHint : text.serviceUrlHint} />
      </FormField>

      {getServiceFields(meta, draft).map((field) => (
        <FormField key={field.key} label={getServiceFieldLabel(field.key, text)} htmlFor={`wizard-${family}-${field.key}`}>
          <Input id={`wizard-${family}-${field.key}`} type={field.type} value={draft[field.key]} onChange={(e) => setDraft({ ...draft, [field.key]: e.target.value })} />
          <FieldHint text={getServiceFieldHint(family, field.key, text, draft.downloader_kind)} />
        </FormField>
      ))}

      {family === "downloaders" && <DownloaderPolicyFields idPrefix="wizard-downloader" draft={draft} setDraft={setDraft} text={text} />}

      <ProfileRuntimeControls enabled={draft.enabled} isDefault={draft.is_default} enabledLabel={text.enabled} defaultLabel={text.runtimeTarget} onEnabledChange={(enabled) => setDraft({ ...draft, enabled })} onDefaultChange={(is_default) => setDraft({ ...draft, is_default })} />

      {family === "downloaders" && <p className={cn("rounded-md border px-3 py-2 text-sm", hasCurrentEvidence ? "border-status-success-border bg-status-success-bg text-status-success" : "border-status-warning-border bg-status-warning-bg text-status-warning")}>{hasCurrentEvidence ? text.connectionVerified : text.connectionIncomplete}</p>}

      <div className="flex gap-3 border-t pt-4">
        <Button variant="outline" disabled={isTesting} onClick={() => void handleTest()}>
          {isTesting ? <LoaderCircle className="size-4 animate-spin" /> : <TestTubeDiagonal className="size-4 text-primary" />}
          {family === "downloaders" ? text.testCurrentProfile : text.test}
        </Button>
      </div>
    </div>
  )

  return (
    <div className="space-y-5 pb-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">{family === "downloaders" ? text.downloaderServiceTitle : getServiceTitle(family, draft)}</h2>
          <p className="text-sm text-muted-foreground">{getServiceDescription(family, text)}</p>
        </div>
        <div className="flex items-center gap-2">
          {alreadyConfigured && family !== "downloaders" ? <StatusPill tone="green" label={text.alreadyConfigured} /> : null}
          <span className="rounded-md bg-muted px-2.5 py-1 text-xs text-muted-foreground" aria-live="polite">{isSaving ? text.savingProgress : text.savedOnContinue}</span>
        </div>
      </div>

      {jellyfinSetupProps ? (
        <Tabs defaultValue="connection" className="gap-4">
          <TabsList className="w-full sm:w-fit" aria-label={text.serviceJellyfinDescription}>
            <TabsTrigger value="connection">{text.connectionSettings}</TabsTrigger>
            <TabsTrigger value="webhook">{text.webhook}</TabsTrigger>
          </TabsList>
          <TabsContent value="connection">{connectionFields}</TabsContent>
          <TabsContent value="webhook">
            <JellyfinSetupPanel
              text={text}
              dashboard={jellyfinSetupProps.dashboard}
              origin={jellyfinSetupProps.origin}
              curlPreview={jellyfinSetupProps.curlPreview}
              tokenConfigured={jellyfinSetupProps.tokenConfigured}
              jellyfinConfigured={alreadyConfigured || Boolean(draft.id)}
              onOpenGeneral={() => {}}
              onSetupWebhook={jellyfinSetupProps.onSetupWebhook}
            />
          </TabsContent>
        </Tabs>
      ) : connectionFields}
    </div>
  )
}
