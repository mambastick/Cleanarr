export type SsoAuthMode = "password_only" | "sso_only" | "both"

export interface AuthStatusPayload {
  admin_configured: boolean
  requires_registration: boolean
  authenticated: boolean
  username: string | null
  role: "admin" | "viewer" | null
  csrf_token: string | null
  sso_enabled: boolean
  sso_mode: SsoAuthMode
  sso_configured: boolean
  ui_language: string
}

export interface AuthSessionPayload {
  username: string
  role: "admin" | "viewer"
  csrf_token: string
}

export interface SSOLoginPayload {
  authorize_url: string
}
