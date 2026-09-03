import { expect, it } from "vitest"

import { createClientIdempotencyKey } from "./idempotency"

it("uses randomUUID when the browser exposes it", () => {
  expect(createClientIdempotencyKey({ randomUUID: () => "fixture-uuid" })).toBe("fixture-uuid")
})

it("keeps deletion actions usable on insecure LAN origins without Web Crypto", () => {
  const first = createClientIdempotencyKey({})
  const second = createClientIdempotencyKey({})
  expect(first).toMatch(/^cleanarr-/)
  expect(second).not.toBe(first)
})
