type BrowserCrypto = {
  randomUUID?: () => string
  getRandomValues?: (values: Uint8Array) => Uint8Array
}

export class ClientIdempotencyKeyError extends Error {
  constructor() {
    super("A cryptographically secure random source is required to create an idempotency key.")
    this.name = "ClientIdempotencyKeyError"
  }
}

/**
 * Build a per-action RFC 4122 version-4 idempotency key even on HTTP/LAN
 * origins where `crypto.randomUUID()` is unavailable. A collision remains
 * fail-closed on the backend as an idempotency conflict; the value is not used
 * as a secret.
 */
export function createClientIdempotencyKey(source: BrowserCrypto | undefined = globalThis.crypto): string {
  if (typeof source?.randomUUID === "function") return source.randomUUID()
  if (typeof source?.getRandomValues !== "function") throw new ClientIdempotencyKeyError()

  let bytes: Uint8Array
  try {
    bytes = source.getRandomValues(new Uint8Array(16))
  } catch {
    throw new ClientIdempotencyKeyError()
  }
  bytes[6] = (bytes[6] & 0x0f) | 0x40
  bytes[8] = (bytes[8] & 0x3f) | 0x80
  const hex = Array.from(bytes, (value) => value.toString(16).padStart(2, "0")).join("")
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`
}
