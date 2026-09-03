import { CheckCircle2, Copy, Eye, EyeOff, LoaderCircle, Plus, RefreshCw, Server, Settings2 } from "lucide-react"
import { useEffect, useState } from "react"
import { toast } from "sonner"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Skeleton } from "@/components/ui/skeleton"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { SeedingStopPolicyFields } from "@/features/downloads/seeding-stop-policy-fields"
import { stopPolicyIsValid } from "@/lib/downloads"
import { FieldHint, FormField, SelectControl } from "@/features/settings/form-presentation"
import { EmptyState, StatusPill } from "@/features/settings/service-presentation"
import type { UiLanguage, UiTextMap } from "@/lib/i18n"
import type { GeneralConfig, RuntimeConfigPayload } from "@/lib/runtime-config"
import { generateWebhookToken, getDownloaderLabel, getServiceDescription, getServices, JELLYFIN_LANGUAGE_OPTIONS, LOG_LEVEL_OPTIONS, SERVICE_FAMILIES, SERVICE_META, UI_LANGUAGE_OPTIONS, type DownloaderKind, type ServiceFamily, type ServiceRecord } from "@/lib/service-config"
import { normalizeError } from "@/lib/status-format"
import { STORAGE_THRESHOLD_COPY, validateStorageThresholds } from "./storage-thresholds"
export { GeneralSettingsModal, ServiceModal } from "@/features/settings/settings-modals"
export { SsoConfigSection } from "@/features/settings/sso-config-section"
import { SsoConfigSection } from "@/features/settings/sso-config-section"

export function SettingsPanel({
  config,
  isConfigLoading,
  onSaveGeneral,
  onAddService,
  onEditService,
  text,
  language,
  settingsSection,
  onSettingsSectionChange,
}: {
  config: RuntimeConfigPayload | null
  isConfigLoading: boolean
  onSaveGeneral: (payload: GeneralConfig) => Promise<void>
  onAddService: (family: ServiceFamily, trigger: HTMLButtonElement) => void
  onEditService: (family: ServiceFamily, service: ServiceRecord, trigger: HTMLButtonElement) => void
  text: UiTextMap
  language: UiLanguage
  settingsSection?: "general" | "services"
  onSettingsSectionChange?: (section: "general" | "services") => void
}) {
  const general = config?.general ?? null
  const [draft, setDraft] = useState<GeneralConfig | null>(null)
  const [isSaving, setIsSaving] = useState(false)
  const [tokenCopied, setTokenCopied] = useState(false)
  const [isTokenVisible, setIsTokenVisible] = useState(false)
  const [isSSOSecretVisible, setIsSSOSecretVisible] = useState(false)
  const [uncontrolledSection, setUncontrolledSection] = useState<"general" | "services">("general")
  const activeSection = settingsSection ?? uncontrolledSection
  const setActiveSection = (value: string | null) => {
    if (value !== "general" && value !== "services") return
    if (settingsSection === undefined) setUncontrolledSection(value)
    onSettingsSectionChange?.(value)
  }

  useEffect(() => {
    setDraft(general ? structuredClone(general) : null)
  }, [general])

  const isDirty = draft && general && JSON.stringify(draft) !== JSON.stringify(general)
  const warningThreshold = draft?.storage_warning_free_percent ?? 15
  const criticalThreshold = draft?.storage_critical_free_percent ?? 5
  const thresholdsValid = validateStorageThresholds(warningThreshold, criticalThreshold)
  const canSave = Boolean(isDirty && draft && stopPolicyIsValid(draft.seeding_stop_policy) && thresholdsValid)
  const thresholdCopy = STORAGE_THRESHOLD_COPY[language === "ru" ? "ru" : "en"]

  const handleSave = async () => {
    if (!draft) return
    setIsSaving(true)
    try {
      await onSaveGeneral(draft)
    } catch (e) {
      toast.error(normalizeError(e))
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <section className="space-y-5">
      <div><h1 className="text-xl font-semibold">{text.settings}</h1><p className="text-sm text-muted-foreground">{text.runtimeSettingsDescription}</p></div>
      <Tabs value={activeSection} onValueChange={setActiveSection}>
        <TabsList aria-label={text.settings}>
          <TabsTrigger value="general">{text.general}</TabsTrigger>
          <TabsTrigger value="services">{text.connectedServices}</TabsTrigger>
        </TabsList>
        <TabsContent value="general">
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <Settings2 className="size-4 text-primary" />
            {text.general}
          </CardTitle>
          <CardDescription>{text.appBehaviour}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          {isConfigLoading && !config ? (
            <div className="space-y-3">
              <Skeleton className="h-9 w-full" />
              <Skeleton className="h-9 w-full" />
            </div>
          ) : draft ? (
            <>
              <div className="grid gap-4 sm:grid-cols-3">
                <FormField label={text.logLevel} htmlFor="settings-log-level">
                  <SelectControl id="settings-log-level" value={draft.log_level} onValueChange={(value) => setDraft({ ...draft, log_level: value })} options={LOG_LEVEL_OPTIONS.map((value) => ({ value, label: value }))} />
                </FormField>

                <FormField label={text.httpTimeoutSeconds} htmlFor="settings-timeout">
                  <Input
                    id="settings-timeout"
                    type="number"
                    min={1}
                    step={1}
                    value={String(draft.http_timeout_seconds)}
                    onChange={(e) => setDraft({ ...draft, http_timeout_seconds: Number(e.target.value) })}
                  />
                </FormField>

                <FormField label={text.activityRetention} htmlFor="settings-retention">
                  <SelectControl id="settings-retention" value={String(draft.activity_retention_days)} onValueChange={(value) => setDraft({ ...draft, activity_retention_days: Number(value) })} options={[{ value: "1", label: text.oneDay }, { value: "7", label: text.sevenDays }, { value: "30", label: text.thirtyDays }, { value: "90", label: text.ninetyDays }, { value: "365", label: text.oneYear }]} />
                </FormField>
              </div>

              <FormField label={text.jellyfinMetadataLanguage} htmlFor="settings-jellyfin-language">
                <SelectControl id="settings-jellyfin-language" value={draft.jellyfin_language} onValueChange={(value) => setDraft({ ...draft, jellyfin_language: value })} options={JELLYFIN_LANGUAGE_OPTIONS} />
                <FieldHint text={text.jellyfinLanguageHint} />
              </FormField>

              <FormField label={text.uiLanguage} htmlFor="settings-ui-language">
                <SelectControl id="settings-ui-language" value={draft.ui_language} onValueChange={(value) => setDraft({ ...draft, ui_language: value })} options={UI_LANGUAGE_OPTIONS} />
                <FieldHint text={text.uiLanguageHint} />
              </FormField>

              <div className="space-y-2 rounded-lg border border-border p-3">
                <div className="grid gap-4 sm:grid-cols-2">
                  <FormField label={thresholdCopy.warning} htmlFor="settings-storage-warning">
                    <Input id="settings-storage-warning" type="number" min={0} max={100} step={1} value={String(warningThreshold)} aria-invalid={!thresholdsValid} onChange={(event) => setDraft({ ...draft, storage_warning_free_percent: Number(event.target.value) })} />
                  </FormField>
                  <FormField label={thresholdCopy.critical} htmlFor="settings-storage-critical">
                    <Input id="settings-storage-critical" type="number" min={0} max={100} step={1} value={String(criticalThreshold)} aria-invalid={!thresholdsValid} onChange={(event) => setDraft({ ...draft, storage_critical_free_percent: Number(event.target.value) })} />
                  </FormField>
                </div>
                <FieldHint text={thresholdCopy.hint} />
                {!thresholdsValid ? <p role="alert" className="text-xs text-status-danger">{thresholdCopy.invalid}</p> : null}
              </div>

              <FormField label={text.webhookToken} htmlFor="settings-webhook-token">
                <div className="flex items-center gap-2">
                  <code className="flex-1 rounded-md border border-input bg-muted px-3 py-2 font-mono text-xs break-all select-all">
                    {isTokenVisible ? (draft.webhook_shared_token ?? "—") : "•".repeat(32)}
                  </code>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    title={isTokenVisible ? text.hideToken : text.showToken}
                    onClick={() => setIsTokenVisible((v) => !v)}
                  >
                    {isTokenVisible ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    title={text.regenerateToken}
                    onClick={() => setDraft({ ...draft, webhook_shared_token: generateWebhookToken() })}
                  >
                    <RefreshCw className="size-4" />
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={!draft.webhook_shared_token}
                    title={text.copyToken}
                    onClick={async () => {
                      await navigator.clipboard.writeText(draft.webhook_shared_token ?? "")
                      setTokenCopied(true)
                      setTimeout(() => setTokenCopied(false), 2000)
                    }}
                  >
                    {tokenCopied
                      ? <CheckCircle2 className="size-4 text-status-success" />
                      : <Copy className="size-4" />}
                  </Button>
                </div>
                <FieldHint text={text.tokenHint} />
              </FormField>

              <SsoConfigSection
                text={text}
                namespace="settings"
                draft={draft}
                onDraftChange={setDraft}
                isSecretVisible={isSSOSecretVisible}
                onToggleSecretVisibility={() => setIsSSOSecretVisible((v) => !v)}
              />

              <SeedingStopPolicyFields draft={draft} onDraftChange={setDraft} language={language === "ru" ? "ru" : "en"} />

              <div className="flex items-center justify-between border-t pt-4">
                <p className="text-xs text-muted-foreground">
                  {isDirty ? text.unsavedChanges : text.allSettingsSaved}
                </p>
                <Button onClick={handleSave} disabled={!canSave || isSaving}>
                  {isSaving
                    ? <LoaderCircle className="size-4 animate-spin" />
                    : <CheckCircle2 className="size-4 text-status-success" />}
                  {text.saveChanges}
                </Button>
              </div>
            </>
          ) : (
            <EmptyState
              title={text.settingsUnavailable}
              description={text.tryAgain}
            />
          )}
        </CardContent>
      </Card>

        </TabsContent>
        <TabsContent value="services">
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <Server className="size-4 text-status-success" />
            {text.connectedServices}
          </CardTitle>
          <CardDescription>
            {text.allEnabledRouting}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {SERVICE_FAMILIES.map((family) => {
            const services = getServices(config, family)
            return (
              <div key={family} className="rounded-lg border p-3">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="text-sm font-medium">
                      {family === "downloaders" ? text.torrentClient : SERVICE_META[family].title}
                    </p>
                    <p className="text-xs text-muted-foreground">{getServiceDescription(family, text)}</p>
                  </div>
                  <Button variant="outline" size="sm" onClick={(event) => onAddService(family, event.currentTarget)}>
                    <Plus className="size-4" />
                    {text.add}
                  </Button>
                </div>
                {services.length > 0 ? (
                  <div className="mt-3 space-y-2">
                    {services.map((service) => <div key={service.id} className="rounded-lg border bg-card p-3"><div className="flex flex-wrap items-center justify-between gap-3"><div className="min-w-0"><p className="truncate text-sm font-medium">{service.name}</p><p className="mt-0.5 text-xs text-muted-foreground">{family === "downloaders" ? getDownloaderLabel(service.kind as DownloaderKind) : SERVICE_META[family].title}</p></div><div className="flex items-center gap-2">{service.is_default && <Badge variant="outline">{text.defaultLabel}</Badge>}<StatusPill tone={service.enabled ? "green" : "blue"} label={service.enabled ? text.enabled : text.disabled} /><Button variant="ghost" size="sm" onClick={(event) => onEditService(family, service, event.currentTarget)}>{text.edit}</Button></div></div><details className="mt-2 text-xs text-muted-foreground"><summary className="cursor-pointer select-none hover:text-foreground">{text.serviceDetails}</summary><code className="mt-2 block break-all rounded-md bg-muted/60 p-2">{service.url}</code></details></div>)}
                  </div>
                ) : (
                  <p className="mt-3 text-xs text-muted-foreground">{text.notConfigured}</p>
                )}
              </div>
            )
          })}
        </CardContent>
      </Card>
        </TabsContent>
      </Tabs>
    </section>
  )
}
