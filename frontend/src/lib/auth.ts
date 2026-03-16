export interface AuthStatusPayload {
  admin_configured: boolean
  requires_registration: boolean
  authenticated: boolean
  username: string | null
}

export interface AuthSessionPayload {
  username: string
  token: string
}
