import { expect, it } from "vitest"

import { normalizeStopPolicyScope, stopPolicyValidationIssues } from "@/lib/downloads"
import type { SeedingStopPolicyConfig } from "@/lib/runtime-config"

const valid: SeedingStopPolicyConfig = {
  enabled: true, mode: "all", min_ratio: 1, min_seeding_minutes: null,
  include_categories: [], exclude_categories: [], include_tags: [], exclude_tags: [],
  interval_seconds: 30, max_attempts: 1,
}

it("validates every persisted stop-policy boundary without changing disabled values", () => {
  expect(stopPolicyValidationIssues(valid)).toEqual([])
  expect(stopPolicyValidationIssues({ ...valid, min_ratio: -0.01 })).toContain("ratio_invalid")
  expect(stopPolicyValidationIssues({ ...valid, min_seeding_minutes: 1.5 })).toContain("minutes_invalid")
  expect(stopPolicyValidationIssues({ ...valid, interval_seconds: 29 })).toContain("interval_invalid")
  expect(stopPolicyValidationIssues({ ...valid, interval_seconds: 86_401 })).toContain("interval_invalid")
  expect(stopPolicyValidationIssues({ ...valid, max_attempts: 0 })).toContain("attempts_invalid")
  expect(stopPolicyValidationIssues({ ...valid, include_tags: ["A", " a "] })).toContain("scope_invalid")
  expect(stopPolicyValidationIssues({ ...valid, include_tags: Array.from({ length: 101 }, (_, index) => `${index}`) })).toContain("scope_invalid")
  expect(stopPolicyValidationIssues({ ...valid, enabled: false, min_ratio: null, min_seeding_minutes: null })).toEqual([])
})

it("normalizes scopes with trimmed case-insensitive de-duplication and a 100 item cap", () => {
  expect(normalizeStopPolicyScope(" Movies, movies ,  TV ")).toEqual(["Movies", "TV"])
  expect(normalizeStopPolicyScope(Array.from({ length: 102 }, (_, index) => `tag-${index}`).join(",")).length).toBe(100)
})
