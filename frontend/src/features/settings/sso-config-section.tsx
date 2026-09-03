import { Eye, EyeOff } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { FieldHint, FormField, SelectControl } from "@/features/settings/form-presentation"
import type { SsoAuthMode } from "@/lib/auth"
import type { UiTextMap } from "@/lib/i18n"
import type { GeneralConfig } from "@/lib/runtime-config"

const SSO_MODE_OPTIONS: Array<{
  value: SsoAuthMode
  labelKey: "ssoModePasswordOnly" | "ssoModeSsoOnly" | "ssoModeBoth"
  hintKey: "ssoModePasswordOnlyHint" | "ssoModeSsoOnlyHint" | "ssoModeBothHint"
}> = [
  { value: "password_only", labelKey: "ssoModePasswordOnly", hintKey: "ssoModePasswordOnlyHint" },
  { value: "sso_only", labelKey: "ssoModeSsoOnly", hintKey: "ssoModeSsoOnlyHint" },
  { value: "both", labelKey: "ssoModeBoth", hintKey: "ssoModeBothHint" },
]


export function SsoConfigSection({
  draft,
  onDraftChange,
  namespace,
  isSecretVisible,
  onToggleSecretVisibility,
  text,
  compact = false,
}: {
  draft: GeneralConfig
  namespace: "settings" | "wizard" | "general"
  onDraftChange: (next: GeneralConfig) => void
  isSecretVisible: boolean
  onToggleSecretVisibility: () => void
  text: UiTextMap
  compact?: boolean
}) {
  const ssoEnabled = draft.sso_mode !== "password_only"

  const handleModeChange = (nextMode: SsoAuthMode) => {
    onDraftChange({
      ...draft,
      sso_mode: nextMode,
      sso_enabled: nextMode !== "password_only",
    })
  }

  const providerFields = (
    <div className="grid gap-4 sm:grid-cols-2">
      <FormField label={text.ssoIssuer} htmlFor={`${namespace}-sso-issuer`}>
        <Input
          id={`${namespace}-sso-issuer`}
          type="url"
          value={draft.sso_issuer_url ?? ""}
          disabled={!ssoEnabled}
          onChange={(e) => onDraftChange({ ...draft, sso_issuer_url: e.target.value || null })}
          placeholder="https://id.example.com/realms/cleanarr"
        />
        <FieldHint text={text.ssoIssuerHint} />
      </FormField>

      <FormField label={text.ssoClientId} htmlFor={`${namespace}-sso-client-id`}>
        <Input
          id={`${namespace}-sso-client-id`}
          value={draft.sso_client_id ?? ""}
          disabled={!ssoEnabled}
          onChange={(e) => onDraftChange({ ...draft, sso_client_id: e.target.value || null })}
        />
        <FieldHint text={text.ssoClientIdHint} />
      </FormField>

      <FormField label={text.ssoClientSecret} htmlFor={`${namespace}-sso-client-secret`}>
        <div className="flex items-center gap-2">
          <Input
            id={`${namespace}-sso-client-secret`}
            type={isSecretVisible ? "text" : "password"}
            value={draft.sso_client_secret ?? ""}
            disabled={!ssoEnabled}
            onChange={(e) => onDraftChange({ ...draft, sso_client_secret: e.target.value || null })}
          />
          <Tooltip>
            <TooltipTrigger render={<span className="inline-flex shrink-0" />}>
              <Button
                type="button"
                variant="outline"
                size="sm"
                aria-label={`${isSecretVisible ? text.hideToken : text.showToken}: ${text.ssoClientSecret}`}
                onClick={onToggleSecretVisibility}
                disabled={!ssoEnabled}
              >
                {isSecretVisible ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
              </Button>
            </TooltipTrigger>
            <TooltipContent>{isSecretVisible ? text.hideToken : text.showToken}: {text.ssoClientSecret}</TooltipContent>
          </Tooltip>
        </div>
        <FieldHint text={text.ssoClientSecretHint} />
      </FormField>

      <FormField label={text.ssoRedirectUri} htmlFor={`${namespace}-sso-redirect-uri`}>
        <Input
          id={`${namespace}-sso-redirect-uri`}
          value={draft.sso_redirect_uri ?? ""}
          disabled={!ssoEnabled}
          onChange={(e) => onDraftChange({ ...draft, sso_redirect_uri: e.target.value || null })}
        />
        <FieldHint text={text.ssoRedirectHint} />
      </FormField>

      <FormField label={text.ssoScopes} htmlFor={`${namespace}-sso-scopes`}>
        <Input
          id={`${namespace}-sso-scopes`}
          value={draft.sso_scopes}
          disabled={!ssoEnabled}
          onChange={(e) => onDraftChange({ ...draft, sso_scopes: e.target.value })}
          placeholder="openid profile email"
        />
        <FieldHint text={text.ssoScopesHint} />
      </FormField>
    </div>
  )

  const accessFields = (
    <div className="grid gap-4 sm:grid-cols-2">
      <FormField label={text.ssoAllowedUsers} htmlFor={`${namespace}-sso-allowed-users`}>
        <Input
          id={`${namespace}-sso-allowed-users`}
          value={draft.sso_allowed_users.join(", ")}
          disabled={!ssoEnabled}
          onChange={(e) => onDraftChange({
            ...draft,
            sso_allowed_users: e.target.value.split(",").map((value) => value.trim()).filter(Boolean),
          })}
          placeholder="admin@example.com, cleanarr-admin"
        />
      </FormField>

      <FormField label={text.ssoAllowedGroups} htmlFor={`${namespace}-sso-allowed-groups`}>
        <Input
          id={`${namespace}-sso-allowed-groups`}
          value={draft.sso_allowed_groups.join(", ")}
          disabled={!ssoEnabled}
          onChange={(e) => onDraftChange({
            ...draft,
            sso_allowed_groups: e.target.value.split(",").map((value) => value.trim()).filter(Boolean),
          })}
          placeholder="cleanarr-admins"
        />
      </FormField>

      <FormField label={text.ssoGroupClaim} htmlFor={`${namespace}-sso-group-claim`}>
        <Input id={`${namespace}-sso-group-claim`} value={draft.sso_group_claim} disabled={!ssoEnabled} onChange={(e) => onDraftChange({ ...draft, sso_group_claim: e.target.value })} placeholder="groups" />
      </FormField>

      <FormField label={text.ssoRequiredClaim} htmlFor={`${namespace}-sso-required-claim`}>
        <Input id={`${namespace}-sso-required-claim`} value={draft.sso_required_claim ?? ""} disabled={!ssoEnabled} onChange={(e) => onDraftChange({ ...draft, sso_required_claim: e.target.value || null })} placeholder="cleanarr_role" />
      </FormField>

      <FormField label={text.ssoRequiredValue} htmlFor={`${namespace}-sso-required-value`}>
        <Input id={`${namespace}-sso-required-value`} value={draft.sso_required_value ?? ""} disabled={!ssoEnabled} onChange={(e) => onDraftChange({ ...draft, sso_required_value: e.target.value || null })} placeholder="administrator" />
      </FormField>
      <div className="sm:col-span-2"><FieldHint text={text.ssoAccessPolicyHint} /></div>
    </div>
  )

  return (
    <div className={compact ? "space-y-4 rounded-xl border border-border bg-background p-4" : "space-y-3 border-t pt-4"}>
      <FormField label={text.ssoAuthMode} htmlFor={`${namespace}-sso-mode`}>
        <SelectControl id={`${namespace}-sso-mode`} value={draft.sso_mode} onValueChange={(value) => handleModeChange(value as SsoAuthMode)} options={SSO_MODE_OPTIONS.map((mode) => ({ value: mode.value, label: text[mode.labelKey] }))} />
        <FieldHint text={text[SSO_MODE_OPTIONS.find((mode) => mode.value === draft.sso_mode)?.hintKey ?? "ssoModeBothHint"]} />
      </FormField>

      {!ssoEnabled ? (
        <p className="text-xs text-muted-foreground">
          {text.ssoFieldDisabledHint}
        </p>
      ) : compact ? (
        <Tabs defaultValue="provider" className="gap-4">
          <TabsList className="w-full sm:w-fit" aria-label={text.ssoSettings}>
            <TabsTrigger value="provider">{text.ssoProvider}</TabsTrigger>
            <TabsTrigger value="access">{text.ssoAccessPolicy}</TabsTrigger>
          </TabsList>
          <TabsContent value="provider">{providerFields}</TabsContent>
          <TabsContent value="access">{accessFields}</TabsContent>
        </Tabs>
      ) : (
        <div className="space-y-4">
          {providerFields}
          {accessFields}
        </div>
      )}
    </div>
  )
}
