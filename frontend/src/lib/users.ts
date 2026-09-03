export type UserRole = "admin" | "viewer"
export type UserAuthSource = "local" | "sso"

export interface UserAccountPayload {
  username: string
  role: UserRole
  auth_source: UserAuthSource
  created_at: string
  last_seen_at: string | null
}

export interface UserAccountListPayload {
  users: UserAccountPayload[]
}
