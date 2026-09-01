import { CheckCircle2, CircleAlert, Copy, Eye, EyeOff, LoaderCircle, RefreshCw, TestTubeDiagonal } from "lucide-react"
import { useEffect, useState, type RefObject } from "react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Modal } from "@/components/ui/modal"
import { KeepDryRunControl, ProfileRuntimeControls } from "@/features/setup/profile-runtime-controls"
import { JellyfinSetupPanel } from "@/features/setup/jellyfin-setup-panel"
import { FieldHint, FormField, SelectControl } from "@/features/settings/form-presentation"
import { DownloaderPolicyFields, EmptyState, GuideCard, InstructionList } from "@/features/settings/service-presentation"
import { SsoConfigSection } from "@/features/settings/sso-config-section"
import type { DashboardPayload } from "@/lib/dashboard"
import type { UiTextMap } from "@/lib/i18n"
import type { ConnectionTestResponse, GeneralConfig } from "@/lib/runtime-config"
import { DOWNLOADER_KIND_OPTIONS, generateWebhookToken, getDownloaderLabel, getServiceDescription, getServiceExample, getServiceFieldHint, getServiceFieldLabel, getServiceFields, getServiceHelp, getServiceTitle, JELLYFIN_LANGUAGE_OPTIONS, LOG_LEVEL_OPTIONS, SERVICE_META, UI_LANGUAGE_OPTIONS, type DownloaderKind, type ServiceDraft, type ServiceFamily, type ServiceModalState } from "@/lib/service-config"
import { normalizeError } from "@/lib/status-format"

export function GeneralSettingsModal({
  open,
  config,
  text,
  onClose,
  onSave,
  returnFocusRef,
}: {
  open: boolean
  config: GeneralConfig | null
  text: UiTextMap
  onClose: () => void
  onSave: (payload: GeneralConfig) => Promise<void>
  returnFocusRef?: RefObject<HTMLElement | null>
  }) {
  const [draft, setDraft] = useState<GeneralConfig | null>(config)
  const [isSaving, setIsSaving] = useState(false)
  const [tokenCopied, setTokenCopied] = useState(false)
  const [isTokenVisible, setIsTokenVisible] = useState(false)
  const [isSSOSecretVisible, setIsSSOSecretVisible] = useState(false)

  useEffect(() => {
    setDraft(config ? structuredClone(config) : null)
    setTokenCopied(false)
  }, [config, open])

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={text.runtimeSettings}
      description={text.runtimeSettingsDescription}
      closeLabel={text.cancel}
      returnFocusRef={returnFocusRef}
      footer={
        <div className="flex justify-end">
          <Button
            disabled={!draft || isSaving}
            onClick={async () => {
              if (!draft) return
              setIsSaving(true)
              try {
                await onSave(draft)
              } catch (e) {
                toast.error(normalizeError(e))
              } finally {
                setIsSaving(false)
              }
            }}
          >
            {isSaving ? (
              <LoaderCircle className="size-4 animate-spin" />
            ) : (
              <CheckCircle2 className="size-4 text-status-success" />
            )}
            {text.saveSettings}
          </Button>
        </div>
      }
    >
      {draft ? (
        <div className="space-y-5">
          <GuideCard
            tone="blue"
            title={text.recommendedFirstRun}
            description={text.recommendedDryRun}
          >
            <InstructionList items={[
              text.generalSetupStep1,
              text.generalSetupStep2,
              text.generalSetupStep3,
            ]} />
          </GuideCard>

          <div className="grid gap-4 sm:grid-cols-2">
            <FormField label={text.logLevel} htmlFor="general-log-level">
              <SelectControl id="general-log-level" value={draft.log_level} onValueChange={(value) => setDraft({ ...draft, log_level: value })} options={LOG_LEVEL_OPTIONS.map((value) => ({ value, label: value }))} />
            </FormField>

            <FormField label={text.httpTimeoutSeconds} htmlFor="general-timeout">
              <Input
                id="general-timeout"
                type="number"
                min={1}
                step={1}
                value={String(draft.http_timeout_seconds)}
                onChange={(e) =>
                  setDraft({ ...draft, http_timeout_seconds: Number(e.target.value) })
                }
              />
              <FieldHint text={text.httpTimeoutHint} />
            </FormField>

            <FormField label={text.activityRetention} htmlFor="general-retention">
              <SelectControl id="general-retention" value={String(draft.activity_retention_days)} onValueChange={(value) => setDraft({ ...draft, activity_retention_days: Number(value) })} options={[{ value: "1", label: text.oneDay }, { value: "7", label: text.sevenDays }, { value: "30", label: text.thirtyDays }, { value: "90", label: text.ninetyDays }, { value: "365", label: text.oneYear }]} />
              <FieldHint text={text.retentionHint} />
            </FormField>
          </div>

          <FormField label={text.webhookToken} htmlFor="general-webhook-token">
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
                onClick={() => {
                  setDraft({ ...draft, webhook_shared_token: generateWebhookToken() })
                }}
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
                {tokenCopied ? (
                  <CheckCircle2 className="size-4 text-status-success" />
                ) : (
                  <Copy className="size-4" />
                )}
              </Button>
            </div>
            <FieldHint text={text.tokenHint} />
          </FormField>

          <FormField label={text.jellyfinMetadataLanguage} htmlFor="general-jellyfin-language">
            <SelectControl id="general-jellyfin-language" value={draft.jellyfin_language} onValueChange={(value) => setDraft({ ...draft, jellyfin_language: value })} options={JELLYFIN_LANGUAGE_OPTIONS} />
            <FieldHint text={text.jellyfinLanguageHint} />
          </FormField>

          <FormField label={text.uiLanguage} htmlFor="general-ui-language">
            <SelectControl id="general-ui-language" value={draft.ui_language} onValueChange={(value) => setDraft({ ...draft, ui_language: value })} options={UI_LANGUAGE_OPTIONS} />
            <FieldHint text={text.uiLanguageHint} />
          </FormField>

          <SsoConfigSection
            text={text}
            draft={draft}
            onDraftChange={setDraft}
            namespace="general"
            isSecretVisible={isSSOSecretVisible}
            onToggleSecretVisibility={() => setIsSSOSecretVisible((v: boolean) => !v)}
          />

          <KeepDryRunControl label={text.keepDryRun} checked={draft.dry_run} onCheckedChange={(dry_run) => setDraft({ ...draft, dry_run })} />
        </div>
      ) : (
        <EmptyState
          title={text.settingsUnavailable}
          description={text.closeAndRefresh}
        />
      )}
    </Modal>
  )
}

// ─── Service modal ────────────────────────────────────────────────────────────

export function ServiceModal({
  state,
  text,
  onClose,
  onSave,
  onDelete,
  onTest,
  jellyfinSetupProps,
  returnFocusRef,
}: {
  state: ServiceModalState | null
  text: UiTextMap
  onClose: () => void
  onSave: (family: ServiceFamily, draft: ServiceDraft) => Promise<void>
  onDelete: (family: ServiceFamily, serviceId: string) => Promise<void>
  onTest: (family: ServiceFamily, draft: ServiceDraft) => Promise<ConnectionTestResponse>
  returnFocusRef?: RefObject<HTMLElement | null>
  jellyfinSetupProps?: {
    dashboard: DashboardPayload | null
    origin: string
    curlPreview: string
    tokenConfigured: boolean
    onSetupWebhook: (webhookUrl: string) => Promise<{ found: boolean; configured: boolean; message: string }>
  }
}) {
  const [draft, setDraft] = useState<ServiceDraft | null>(state?.draft ?? null)
  const [isSaving, setIsSaving] = useState(false)
  const [isTesting, setIsTesting] = useState(false)
  const [isDeleting, setIsDeleting] = useState(false)

  useEffect(() => {
    setDraft(state ? structuredClone(state.draft) : null)
  }, [state])

  if (!state) return null

  const meta = SERVICE_META[state.family]

  return (
    <Modal
      open={state !== null}
      onClose={onClose}
      title={`${draft?.id ? text.edit : text.add} ${getServiceTitle(state.family, draft)}`}
      description={getServiceDescription(state.family, text)}
      closeLabel={text.cancel}
      returnFocusRef={returnFocusRef}
      footer={
        <div className="flex flex-wrap justify-between gap-3">
          <div>
            {draft?.id && (
              <Button
                variant="destructive"
                disabled={isDeleting}
                onClick={async () => {
                  if (!draft?.id) return
                  setIsDeleting(true)
                  try {
                    await onDelete(state.family, draft.id)
                  } catch (e) {
                    toast.error(normalizeError(e))
                  } finally {
                    setIsDeleting(false)
                  }
                }}
              >
                {isDeleting ? <LoaderCircle className="size-4 animate-spin" /> : <CircleAlert className="size-4" />}
                {text.delete}
              </Button>
            )}
          </div>

          <div className="flex flex-wrap gap-3">
            <Button
              variant="outline"
              disabled={!draft || isTesting}
              onClick={async () => {
                if (!draft) return
                setIsTesting(true)
                try {
                  const result = await onTest(state.family, draft)
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
              }}
            >
              {isTesting ? (
                <LoaderCircle className="size-4 animate-spin" />
              ) : (
                <TestTubeDiagonal className="size-4 text-primary" />
              )}
              {text.test}
            </Button>
            <Button
              disabled={!draft || isSaving}
              onClick={async () => {
                if (!draft) return
                setIsSaving(true)
                try {
                  await onSave(state.family, draft)
                } catch (e) {
                  toast.error(normalizeError(e))
                } finally {
                  setIsSaving(false)
                }
              }}
            >
              {isSaving ? (
                <LoaderCircle className="size-4 animate-spin" />
              ) : (
                <CheckCircle2 className="size-4 text-status-success" />
              )}
              {text.save}
            </Button>
          </div>
        </div>
      }
    >
      {draft ? (
        <div className="space-y-4">
          <GuideCard
            tone={meta.accent}
            title={text.beforeYouSave}
            description={text.beforeSaveDescription}
          >
            <InstructionList items={getServiceHelp(meta, text, draft)} />
          </GuideCard>

          {state.family === "downloaders" && (
            <FormField label={text.torrentClient} htmlFor="downloader-kind">
              <SelectControl id="downloader-kind" value={draft.downloader_kind ?? "qbittorrent"} disabled={Boolean(draft.id)} onValueChange={(value) => {
                  const kind = value as DownloaderKind
                  setDraft({ ...draft, downloader_kind: kind, name: getDownloaderLabel(kind) })
                }} options={DOWNLOADER_KIND_OPTIONS} />
            </FormField>
          )}

          <FormField label={text.displayName} htmlFor={`${state.family}-name`}>
            <Input
              id={`${state.family}-name`}
              value={draft.name}
              onChange={(e) => setDraft({ ...draft, name: e.target.value })}
            />
          </FormField>

          <FormField label={text.baseUrl} htmlFor={`${state.family}-url`}>
            <Input
              id={`${state.family}-url`}
              type="url"
              value={draft.url}
              onChange={(e) => setDraft({ ...draft, url: e.target.value })}
              placeholder={getServiceExample(meta, draft)}
            />
            <FieldHint
              text={
                state.family === "downloaders" ? text.downloaderUrlHint : text.serviceUrlHint
              }
            />
          </FormField>

          {getServiceFields(meta, draft).map((field) => (
            <FormField
              key={field.key}
              label={getServiceFieldLabel(field.key, text)}
              htmlFor={`${state.family}-${field.key}`}
            >
              <Input
                id={`${state.family}-${field.key}`}
                type={field.type}
                value={draft[field.key]}
                onChange={(e) => setDraft({ ...draft, [field.key]: e.target.value })}
              />
              <FieldHint text={getServiceFieldHint(state.family, field.key, text, draft.downloader_kind)} />
            </FormField>
          ))}

          {state.family === "downloaders" && (
            <DownloaderPolicyFields
              idPrefix="downloader"
              draft={draft}
              setDraft={setDraft}
              text={text}
            />
          )}

          <ProfileRuntimeControls enabled={draft.enabled} isDefault={draft.is_default} enabledLabel={text.enabled} defaultLabel={text.runtimeTarget} onEnabledChange={(enabled) => setDraft({ ...draft, enabled })} onDefaultChange={(is_default) => setDraft({ ...draft, is_default })} />

          {state.family === "jellyfin_server" && jellyfinSetupProps && (
            <div className="mt-6 space-y-5 border-t pt-5">
              <p className="text-sm font-semibold text-muted-foreground uppercase tracking-wider">{text.webhook}</p>
              <JellyfinSetupPanel
                text={text}
                dashboard={jellyfinSetupProps.dashboard}
                origin={jellyfinSetupProps.origin}
                curlPreview={jellyfinSetupProps.curlPreview}
                tokenConfigured={jellyfinSetupProps.tokenConfigured}
                jellyfinConfigured={Boolean(draft?.id)}
                onOpenGeneral={() => {}}
                onSetupWebhook={jellyfinSetupProps.onSetupWebhook}
              />
            </div>
          )}
        </div>
      ) : null}
    </Modal>
  )
}
