import { CheckCircle2, Copy, Eye, EyeOff, LibraryBig, LoaderCircle, Plus, RefreshCw, Server, Settings2, ShieldCheck, Trash2 } from "lucide-react"
import { useEffect, useState } from "react"
import { toast } from "sonner"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Skeleton } from "@/components/ui/skeleton"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { SeedingStopPolicyFields } from "@/features/downloads/seeding-stop-policy-fields"
import type { SettingsSection } from "@/features/app-shell/app-shell"
import { FieldHint, FormField, SelectControl } from "@/features/settings/form-presentation"
import { EmptyState, StatusPill } from "@/features/settings/service-presentation"
import { SsoConfigSection } from "@/features/settings/sso-config-section"
import { stopPolicyIsValid } from "@/lib/downloads"
import type { UiLanguage, UiTextMap } from "@/lib/i18n"
import type { GeneralConfig, RuntimeConfigPayload } from "@/lib/runtime-config"
import { generateWebhookToken, getDownloaderLabel, getServiceDescription, getServices, JELLYFIN_LANGUAGE_OPTIONS, LOG_LEVEL_OPTIONS, SERVICE_FAMILIES, SERVICE_META, UI_LANGUAGE_OPTIONS, type DownloaderKind, type ServiceFamily, type ServiceRecord } from "@/lib/service-config"
import { normalizeError } from "@/lib/status-format"
import { STORAGE_THRESHOLD_COPY, validateStorageThresholds } from "./storage-thresholds"

export { GeneralSettingsModal, ServiceModal } from "@/features/settings/settings-modals"
export { SsoConfigSection } from "@/features/settings/sso-config-section"

type SettingsPanelProps = {
  config: RuntimeConfigPayload | null
  isConfigLoading: boolean
  onSaveGeneral: (payload: GeneralConfig) => Promise<void>
  onAddService: (family: ServiceFamily, trigger: HTMLButtonElement) => void
  onEditService: (family: ServiceFamily, service: ServiceRecord, trigger: HTMLButtonElement) => void
  text: UiTextMap
  language: UiLanguage
  settingsSection?: SettingsSection
  onSettingsSectionChange?: (section: SettingsSection) => void
}

const SECTION_COPY = {
  en: {
    cleanarr: ["CleanArr", "Application behaviour, interface, logging, and activity history."],
    library: ["Media library", "Metadata language and storage capacity thresholds."],
    security: ["Security", "Webhook secret and authentication policy."],
    cleanup: ["Cleanup rules", "Conservative seeding and removal automation."],
    services: ["Connected services", "Manage the services participating in the cleanup chain."],
  },
  ru: {
    cleanarr: ["CleanArr", "Поведение приложения, интерфейс, журналирование и история активности."],
    library: ["Медиатека", "Язык метаданных и пороги свободного места."],
    security: ["Безопасность", "Секрет webhook и политика аутентификации."],
    cleanup: ["Правила очистки", "Консервативная автоматизация раздач и удаления."],
    services: ["Подключённые сервисы", "Управление сервисами в цепочке очистки."],
  },
} as const

const SECTION_ICON = { cleanarr: Settings2, library: LibraryBig, security: ShieldCheck, cleanup: Trash2, services: Server }

export function SettingsPanel({ config, isConfigLoading, onSaveGeneral, onAddService, onEditService, text, language, settingsSection = "cleanarr" }: SettingsPanelProps) {
  const general = config?.general ?? null
  const [draft, setDraft] = useState<GeneralConfig | null>(null)
  const [isSaving, setIsSaving] = useState(false)
  const [tokenCopied, setTokenCopied] = useState(false)
  const [isTokenVisible, setIsTokenVisible] = useState(false)
  const [isSSOSecretVisible, setIsSSOSecretVisible] = useState(false)

  useEffect(() => { setDraft(general ? structuredClone(general) : null) }, [general])

  const isDirty = Boolean(draft && general && JSON.stringify(draft) !== JSON.stringify(general))
  const warningThreshold = draft?.storage_warning_free_percent ?? 15
  const criticalThreshold = draft?.storage_critical_free_percent ?? 5
  const thresholdsValid = validateStorageThresholds(warningThreshold, criticalThreshold)
  const canSave = Boolean(isDirty && draft && stopPolicyIsValid(draft.seeding_stop_policy) && thresholdsValid)
  const thresholdCopy = STORAGE_THRESHOLD_COPY[language === "ru" ? "ru" : "en"]
  const sectionCopy = SECTION_COPY[language === "ru" ? "ru" : "en"][settingsSection]
  const SectionIcon = SECTION_ICON[settingsSection]

  const handleSave = async () => {
    if (!draft) return
    setIsSaving(true)
    try { await onSaveGeneral(draft) }
    catch (error) { toast.error(normalizeError(error)) }
    finally { setIsSaving(false) }
  }

  const saveFooter = <div className="flex flex-wrap items-center justify-between gap-3 border-t pt-4">
    <p className="text-xs text-muted-foreground">{isDirty ? text.unsavedChanges : text.allSettingsSaved}</p>
    <Button onClick={handleSave} disabled={!canSave || isSaving}>
      {isSaving ? <LoaderCircle className="size-4 animate-spin" /> : <CheckCircle2 className="size-4" />}
      {text.saveChanges}
    </Button>
  </div>

  const unavailable = isConfigLoading && !config
    ? <div className="space-y-3"><Skeleton className="h-9 w-full" /><Skeleton className="h-9 w-full" /></div>
    : <EmptyState title={text.settingsUnavailable} description={text.tryAgain} />

  return <section className="space-y-5">
    <header>
      <h1 className="flex items-center gap-2 text-xl font-semibold"><SectionIcon className="size-5 text-primary" />{sectionCopy[0]}</h1>
      <p className="mt-1 text-sm text-muted-foreground">{sectionCopy[1]}</p>
    </header>

    {settingsSection === "cleanarr" ? <Card><CardHeader className="pb-3"><CardTitle className="text-base">{sectionCopy[0]}</CardTitle><CardDescription>{text.appBehaviour}</CardDescription></CardHeader><CardContent className="space-y-5">{draft ? <>
      <div className="grid gap-4 sm:grid-cols-3">
        <FormField label={text.logLevel} htmlFor="settings-log-level"><SelectControl id="settings-log-level" value={draft.log_level} onValueChange={(value) => setDraft({ ...draft, log_level: value })} options={LOG_LEVEL_OPTIONS.map((value) => ({ value, label: value }))} /></FormField>
        <FormField label={text.httpTimeoutSeconds} htmlFor="settings-timeout"><Input id="settings-timeout" type="number" min={1} step={1} value={String(draft.http_timeout_seconds)} onChange={(event) => setDraft({ ...draft, http_timeout_seconds: Number(event.target.value) })} /></FormField>
        <FormField label={text.activityRetention} htmlFor="settings-retention"><SelectControl id="settings-retention" value={String(draft.activity_retention_days)} onValueChange={(value) => setDraft({ ...draft, activity_retention_days: Number(value) })} options={[{ value: "1", label: text.oneDay }, { value: "7", label: text.sevenDays }, { value: "30", label: text.thirtyDays }, { value: "90", label: text.ninetyDays }, { value: "365", label: text.oneYear }]} /></FormField>
      </div>
      <FormField label={text.uiLanguage} htmlFor="settings-ui-language"><SelectControl id="settings-ui-language" value={draft.ui_language} onValueChange={(value) => setDraft({ ...draft, ui_language: value })} options={UI_LANGUAGE_OPTIONS} /><FieldHint text={text.uiLanguageHint} /></FormField>
      {saveFooter}
    </> : unavailable}</CardContent></Card> : null}

    {settingsSection === "library" ? <Card><CardHeader className="pb-3"><CardTitle className="text-base">{sectionCopy[0]}</CardTitle><CardDescription>{sectionCopy[1]}</CardDescription></CardHeader><CardContent className="space-y-5">{draft ? <>
      <FormField label={text.jellyfinMetadataLanguage} htmlFor="settings-jellyfin-language"><SelectControl id="settings-jellyfin-language" value={draft.jellyfin_language} onValueChange={(value) => setDraft({ ...draft, jellyfin_language: value })} options={JELLYFIN_LANGUAGE_OPTIONS} /><FieldHint text={text.jellyfinLanguageHint} /></FormField>
      <div className="space-y-2 rounded-lg border border-border p-3"><div className="grid gap-4 sm:grid-cols-2">
        <FormField label={thresholdCopy.warning} htmlFor="settings-storage-warning"><Input id="settings-storage-warning" type="number" min={0} max={100} step={1} value={String(warningThreshold)} aria-invalid={!thresholdsValid} onChange={(event) => setDraft({ ...draft, storage_warning_free_percent: Number(event.target.value) })} /></FormField>
        <FormField label={thresholdCopy.critical} htmlFor="settings-storage-critical"><Input id="settings-storage-critical" type="number" min={0} max={100} step={1} value={String(criticalThreshold)} aria-invalid={!thresholdsValid} onChange={(event) => setDraft({ ...draft, storage_critical_free_percent: Number(event.target.value) })} /></FormField>
      </div><FieldHint text={thresholdCopy.hint} />{!thresholdsValid ? <p role="alert" className="text-xs text-status-danger">{thresholdCopy.invalid}</p> : null}</div>
      {saveFooter}
    </> : unavailable}</CardContent></Card> : null}

    {settingsSection === "security" ? <Card><CardHeader className="pb-3"><CardTitle className="text-base">{sectionCopy[0]}</CardTitle><CardDescription>{sectionCopy[1]}</CardDescription></CardHeader><CardContent className="space-y-5">{draft ? <>
      <FormField label={text.webhookToken} htmlFor="settings-webhook-token"><div className="flex items-center gap-2"><code id="settings-webhook-token" className="min-w-0 flex-1 rounded-md border border-input bg-muted px-3 py-2 font-mono text-xs break-all select-all">{isTokenVisible ? (draft.webhook_shared_token ?? "—") : "•".repeat(32)}</code>
        <Tooltip><TooltipTrigger render={<Button type="button" variant="outline" size="icon" aria-label={isTokenVisible ? text.hideToken : text.showToken} onClick={() => setIsTokenVisible((value) => !value)}>{isTokenVisible ? <EyeOff /> : <Eye />}</Button>} /><TooltipContent>{isTokenVisible ? text.hideToken : text.showToken}</TooltipContent></Tooltip>
        <Tooltip><TooltipTrigger render={<Button type="button" variant="outline" size="icon" aria-label={text.regenerateToken} onClick={() => setDraft({ ...draft, webhook_shared_token: generateWebhookToken() })}><RefreshCw /></Button>} /><TooltipContent>{text.regenerateToken}</TooltipContent></Tooltip>
        <Tooltip><TooltipTrigger render={<Button type="button" variant="outline" size="icon" disabled={!draft.webhook_shared_token} aria-label={text.copyToken} onClick={async () => { await navigator.clipboard.writeText(draft.webhook_shared_token ?? ""); setTokenCopied(true); setTimeout(() => setTokenCopied(false), 2000) }}>{tokenCopied ? <CheckCircle2 className="text-status-success" /> : <Copy />}</Button>} /><TooltipContent>{text.copyToken}</TooltipContent></Tooltip>
      </div><FieldHint text={text.tokenHint} /></FormField>
      <SsoConfigSection text={text} namespace="settings" draft={draft} onDraftChange={setDraft} isSecretVisible={isSSOSecretVisible} onToggleSecretVisibility={() => setIsSSOSecretVisible((value) => !value)} />
      {saveFooter}
    </> : unavailable}</CardContent></Card> : null}

    {settingsSection === "cleanup" ? <Card><CardHeader className="pb-3"><CardTitle className="text-base">{sectionCopy[0]}</CardTitle><CardDescription>{sectionCopy[1]}</CardDescription></CardHeader><CardContent className="space-y-5">{draft ? <><SeedingStopPolicyFields draft={draft} onDraftChange={setDraft} language={language === "ru" ? "ru" : "en"} />{saveFooter}</> : unavailable}</CardContent></Card> : null}

    {settingsSection === "services" ? <Card><CardHeader className="pb-3"><CardTitle className="flex items-center gap-2 text-base"><Server className="size-4 text-status-success" />{text.connectedServices}</CardTitle><CardDescription>{text.allEnabledRouting}</CardDescription></CardHeader><CardContent className="grid gap-3">
      {SERVICE_FAMILIES.map((family) => {
        const services = getServices(config, family)
        const familyTitle = family === "downloaders" ? text.torrentClient : SERVICE_META[family].title
        const headingId = `service-family-${family}`
        return <section key={family} aria-labelledby={headingId} className="rounded-xl border bg-background/55 p-4">
          <div className="flex flex-wrap items-start justify-between gap-3"><div className="min-w-0"><h2 id={headingId} className="text-sm font-semibold">{familyTitle}</h2><p className="mt-1 text-xs text-muted-foreground">{getServiceDescription(family, text)}</p></div><Button variant="outline" size="sm" onClick={(event) => onAddService(family, event.currentTarget)}><Plus className="size-4" />{text.add}</Button></div>
          {services.length ? <div className="mt-3 grid gap-2 sm:grid-cols-2">{services.map((service) => <article key={service.id} className="flex min-w-0 flex-col gap-3 rounded-lg bg-muted/45 p-3"><div className="min-w-0"><p className="truncate text-sm font-medium">{service.name}</p><p className="mt-1 truncate text-xs text-muted-foreground">{family === "downloaders" ? getDownloaderLabel(service.kind as DownloaderKind) : familyTitle} · {service.url}</p></div><div className="flex flex-wrap items-center gap-2">{service.is_default ? <Badge variant="outline">{text.defaultLabel}</Badge> : null}<StatusPill tone={service.enabled ? "green" : "blue"} label={service.enabled ? text.enabled : text.disabled} /><Button className="ml-auto" variant="ghost" size="sm" onClick={(event) => onEditService(family, service, event.currentTarget)}>{text.edit}</Button></div></article>)}</div> : <p className="mt-3 rounded-lg bg-muted/35 px-3 py-2 text-xs text-muted-foreground">{text.notConfigured}</p>}
        </section>
      })}
    </CardContent></Card> : null}
  </section>
}
