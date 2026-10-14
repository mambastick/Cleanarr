import { describe, expect, it } from "vitest"
import { localizedJobError } from "./deletion-copy"

describe("durable job error codes", () => {
  it.each(["preflight_failed", "execution_failed", "library_item_changed", "interrupted_before_mutation", "interrupted_unknown", "plan_changed", "partial_result_not_retryable"])("has EN/RU copy for %s", (code) => {
    const english = localizedJobError(code, "en")
    const russian = localizedJobError(code, "ru")
    expect(english).toBeTruthy()
    expect(russian).toMatch(/[А-Яа-я]/)
    expect(russian).not.toBe(english)
  })
})
