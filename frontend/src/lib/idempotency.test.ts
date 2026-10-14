import { expect, it, vi } from "vitest"

import { ClientIdempotencyKeyError, createClientIdempotencyKey } from "./idempotency"

it("uses randomUUID when the browser exposes it", () => {
  expect(createClientIdempotencyKey({ randomUUID: () => "fixture-uuid" })).toBe("fixture-uuid")
})

it("builds an RFC 4122 version-4 UUID from getRandomValues", () => {
  const bytes = new Uint8Array(16)
  bytes.fill(0xab)
  const getRandomValues = vi.fn((values: Uint8Array) => {
    values.set(bytes)
    return values
  })

  const key = createClientIdempotencyKey({ getRandomValues })

  expect(key).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/)
  expect(getRandomValues).toHaveBeenCalledWith(expect.any(Uint8Array))
})

it("fails closed when no cryptographically secure random source is available", () => {
  expect(() => createClientIdempotencyKey({})).toThrow(ClientIdempotencyKeyError)
})
