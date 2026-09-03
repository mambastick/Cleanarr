import { CircleAlert, KeyRound, LoaderCircle, ShieldCheck, UserRoundPlus, Zap } from "lucide-react"

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Skeleton } from "@/components/ui/skeleton"
import {
  AUTH_PASSWORD_MAX_LENGTH,
  AUTH_PASSWORD_MIN_LENGTH,
  AUTH_USERNAME_MAX_LENGTH,
  AUTH_USERNAME_MIN_LENGTH,
} from "@/features/auth/auth-validation"
import { FieldHint, FormField } from "@/features/settings/form-presentation"
import type { SsoAuthMode } from "@/lib/auth"
import type { UiTextMap } from "@/lib/i18n"

type AuthMode = "register" | "login"

export function AuthScreen({
  authMode,
  authForm,
  text,
  isSubmitting,
  isSsoSubmitting,
  requiresRegistration,
  localAuthEnabled,
  ssoMode,
  ssoConfigured,
  hasSsoError,
  ssoError,
  onFieldChange,
  onSubmit,
  onSsoSubmit,
}: {
  authMode: AuthMode
  authForm: { username: string; password: string; confirmPassword: string }
  text: UiTextMap
  isSubmitting: boolean
  isSsoSubmitting: boolean
  requiresRegistration: boolean
  localAuthEnabled: boolean
  ssoMode: SsoAuthMode
  ssoConfigured: boolean
  hasSsoError: boolean
  ssoError: string | null
  onFieldChange: (field: "username" | "password" | "confirmPassword", value: string) => void
  onSubmit: () => void
  onSsoSubmit: () => void
}) {
  const showLocalAuth = requiresRegistration || localAuthEnabled
  const showSsoAuth = ssoMode !== "password_only"
  const authDescription = requiresRegistration
    ? text.firstLaunchCreateAdmin
    : showLocalAuth && showSsoAuth
      ? text.signInWithLocalOrSso
      : showLocalAuth
        ? text.signInWithLocalOnly
        : text.signInWithSso

  return (
    <main className="flex min-h-screen items-center justify-center bg-background px-4 py-8 sm:px-6">
      <div className="w-full max-w-md space-y-6">
        <div className="flex justify-center" aria-label="CleanArr">
          <div className="flex min-h-11 items-center gap-2 text-3xl tracking-tight">
            <Zap aria-hidden="true" className="size-8 rotate-12 text-primary" strokeWidth={1.8} />
            <span><span className="font-light text-foreground">Clean</span><span className="font-bold text-primary">Arr</span></span>
          </div>
        </div>
      <Card className="w-full border-border bg-card shadow-sm">
        <CardHeader className="space-y-1.5">
          <CardTitle className="flex items-center gap-2 text-xl">
            {requiresRegistration ? (
              <UserRoundPlus className="size-5 text-primary" />
            ) : (
              <KeyRound className="size-5 text-primary" />
            )}
            {requiresRegistration ? text.authTitleCreateAdmin : text.authTitleSignIn}
          </CardTitle>
          <CardDescription>
            {authDescription}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {hasSsoError && (
            <Alert variant="destructive">
              <CircleAlert className="size-4" />
              <AlertTitle>{text.ssoSignInError}</AlertTitle>
              <AlertDescription>{ssoError}</AlertDescription>
            </Alert>
          )}

          {showLocalAuth && (
            <>
              <FormField label={text.username} htmlFor="auth-username">
                <Input
                  id="auth-username"
                  value={authForm.username}
                  autoComplete="username"
                  minLength={AUTH_USERNAME_MIN_LENGTH}
                  maxLength={AUTH_USERNAME_MAX_LENGTH}
                  aria-describedby="auth-username-hint"
                  onChange={(e) => onFieldChange("username", e.target.value)}
                />
                <div id="auth-username-hint">
                  <FieldHint text={text.usernameLengthRequirement} />
                </div>
              </FormField>

              <FormField label={text.password} htmlFor="auth-password">
                <Input
                  id="auth-password"
                  type="password"
                  value={authForm.password}
                  autoComplete={requiresRegistration ? "new-password" : "current-password"}
                  minLength={AUTH_PASSWORD_MIN_LENGTH}
                  maxLength={AUTH_PASSWORD_MAX_LENGTH}
                  aria-describedby="auth-password-hint"
                  onChange={(e) => onFieldChange("password", e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !requiresRegistration) onSubmit()
                  }}
                />
                <div id="auth-password-hint">
                  <FieldHint text={text.passwordLengthRequirement} />
                </div>
              </FormField>

              {requiresRegistration && (
                <FormField label={text.confirmPassword} htmlFor="auth-confirm">
                  <Input
                    id="auth-confirm"
                    type="password"
                    value={authForm.confirmPassword}
                    autoComplete="new-password"
                    minLength={AUTH_PASSWORD_MIN_LENGTH}
                    maxLength={AUTH_PASSWORD_MAX_LENGTH}
                    onChange={(e) => onFieldChange("confirmPassword", e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") onSubmit()
                    }}
                  />
                </FormField>
              )}

              <Button className="min-h-11 w-full" disabled={isSubmitting} onClick={onSubmit}>
                {isSubmitting ? (
                  <LoaderCircle className="size-4 animate-spin" />
                ) : authMode === "register" ? (
                  <UserRoundPlus className="size-4" />
                ) : (
                  <KeyRound className="size-4" />
                )}
                {authMode === "register" ? text.authTitleCreateAdmin : text.signInWithCredentials}
              </Button>
            </>
          )}

          {showSsoAuth && !requiresRegistration && (
            <div className="space-y-2">
              {showLocalAuth && (
                <div className="flex items-center gap-3 text-xs text-muted-foreground">
                  <div className="h-px flex-1 bg-border" />
                  <span>{text.orDivider}</span>
                  <div className="h-px flex-1 bg-border" />
                </div>
              )}
              <Button
                className="min-h-11 w-full"
                variant="outline"
                disabled={isSsoSubmitting || !ssoConfigured}
                onClick={onSsoSubmit}
                title={ssoConfigured ? text.continueWithSso : text.ssoNotConfigured}
              >
                {isSsoSubmitting ? (
                  <LoaderCircle className="size-4 animate-spin" />
                ) : (
                  <ShieldCheck className="size-4" />
                )}
                {isSsoSubmitting ? text.connecting : text.signInWithSso}
              </Button>
              {!ssoConfigured && (
                <p className="text-xs text-muted-foreground">
                  {text.configureSsoBefore}
                </p>
              )}
            </div>
          )}
          {!showLocalAuth && !showSsoAuth ? (
            <p className="rounded-md border border-dashed p-2 text-xs text-muted-foreground">
              {text.noAuthConfigured}
            </p>
          ) : null}
        </CardContent>
      </Card>
      </div>
    </main>
  )
}

export function AuthScreenSkeleton() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4 py-8">
      <div className="w-full max-w-sm space-y-4 rounded-xl border p-6">
        <Skeleton className="h-7 w-32" />
        <Skeleton className="h-4 w-48" />
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-10 w-full" />
      </div>
    </div>
  )
}

// ─── Dashboard ────────────────────────────────────────────────────────────────
