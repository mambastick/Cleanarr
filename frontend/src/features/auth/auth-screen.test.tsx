import { render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import { AuthScreen } from "./auth-screen"
import { getUiText } from "@/lib/i18n"

describe("AuthScreen", () => {
  it("renders the API credential requirements on first-run registration", () => {
    render(
      <AuthScreen
        authMode="register"
        authForm={{ username: "", password: "", confirmPassword: "" }}
        text={getUiText("ru")}
        isSubmitting={false}
        isSsoSubmitting={false}
        requiresRegistration
        localAuthEnabled
        ssoMode="password_only"
        ssoConfigured={false}
        hasSsoError={false}
        ssoError={null}
        onFieldChange={vi.fn()}
        onSubmit={vi.fn()}
        onSsoSubmit={vi.fn()}
      />,
    )

    expect(screen.getByText("Имя пользователя должно содержать от 3 до 64 символов.")).toBeVisible()
    expect(screen.getByText("Пароль должен содержать от 8 до 256 символов.")).toBeVisible()
    expect(screen.getByLabelText("Имя пользователя")).toHaveAttribute("minlength", "3")
    expect(screen.getByLabelText("Имя пользователя")).toHaveAttribute("maxlength", "64")
    expect(screen.getByLabelText("Пароль")).toHaveAttribute("minlength", "8")
    expect(screen.getByLabelText("Пароль")).toHaveAttribute("maxlength", "256")
    expect(screen.getByLabelText("Пароль")).toHaveAttribute("autocomplete", "new-password")
  })
})
