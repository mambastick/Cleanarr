import { describe, expect, it } from "vitest"

import { apiErrorFromResponse } from "./api-client"
import { localizedDeletionError, submissionRecovery } from "@/features/deletion/deletion-copy"

describe("structured API errors", () => {
  it("preserves a structured code and maps it to localized safe copy", () => {
    const error = apiErrorFromResponse(409, "Conflict", { detail: { code: "plan_changed", message: "Internal message" } })

    expect(error.status).toBe(409)
    expect(error.code).toBe("plan_changed")
    expect(localizedDeletionError(error, "ru").message).toContain("план")
  })

  it("treats transport and server failures as ambiguous but refreshes explicit plan conflicts", () => {
    expect(submissionRecovery(new TypeError("network response lost"))).toBe("resend_exact")
    expect(submissionRecovery(apiErrorFromResponse(502, "Bad Gateway", null))).toBe("resend_exact")
    expect(submissionRecovery(apiErrorFromResponse(409, "Conflict", { detail: { code: "plan_changed" } }))).toBe("refresh_preflight")
    expect(submissionRecovery(apiErrorFromResponse(409, "Conflict", { detail: { code: "idempotency_key_conflict" } }))).toBe("rotate_session")
  })
})
