import { describe, expect, it } from "vitest"

import { validateAuthForm } from "./auth-validation"

describe("validateAuthForm", () => {
  it("rejects usernames outside the API contract after trimming", () => {
    expect(validateAuthForm("register", {
      username: " ab ",
      password: "correct-password",
      confirmPassword: "correct-password",
    })).toBe("usernameLengthRequirement")
  })

  it("rejects passwords shorter than the API contract", () => {
    expect(validateAuthForm("register", {
      username: "admin",
      password: "short",
      confirmPassword: "short",
    })).toBe("passwordLengthRequirement")
  })

  it("checks confirmation only during registration", () => {
    expect(validateAuthForm("register", {
      username: "admin",
      password: "correct-password",
      confirmPassword: "different-password",
    })).toBe("passwordsDoNotMatch")
    expect(validateAuthForm("login", {
      username: "admin",
      password: "correct-password",
      confirmPassword: "",
    })).toBeNull()
  })
})
