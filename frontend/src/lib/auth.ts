export interface AuthStatusPayload {
  admin_configured: boolean
  requires_registration: boolean
  authenticated: boolean
  username: string | null
  sso_enabled: boolean
  sso_configured: boolean
}

export interface AuthSessionPayload {
  username: string
  token: string
}

export interface SSOLoginPayload {
  authorize_url: string
  state: string
}
