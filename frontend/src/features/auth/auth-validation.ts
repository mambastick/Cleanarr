export const AUTH_USERNAME_MIN_LENGTH = 3
export const AUTH_USERNAME_MAX_LENGTH = 64
export const AUTH_PASSWORD_MIN_LENGTH = 8
export const AUTH_PASSWORD_MAX_LENGTH = 256

export type AuthMode = "register" | "login"

export type AuthFormValue = {
  username: string
  password: string
  confirmPassword: string
}

export type AuthValidationError =
  | "usernameLengthRequirement"
  | "passwordLengthRequirement"
  | "passwordsDoNotMatch"

export function validateAuthForm(
  mode: AuthMode,
  form: AuthFormValue,
): AuthValidationError | null {
  const usernameLength = form.username.trim().length
  if (usernameLength < AUTH_USERNAME_MIN_LENGTH || usernameLength > AUTH_USERNAME_MAX_LENGTH) {
    return "usernameLengthRequirement"
  }

  if (form.password.length < AUTH_PASSWORD_MIN_LENGTH || form.password.length > AUTH_PASSWORD_MAX_LENGTH) {
    return "passwordLengthRequirement"
  }

  if (mode === "register" && form.password !== form.confirmPassword) {
    return "passwordsDoNotMatch"
  }

  return null
}
