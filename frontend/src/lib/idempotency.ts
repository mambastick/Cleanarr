let fallbackSequence = 0

type BrowserCrypto = {
  randomUUID?: () => string
  getRandomValues?: (values: Uint32Array) => Uint32Array
}

/**
 * Build a per-action idempotency key even on HTTP/LAN origins where
 * `crypto.randomUUID()` is unavailable. A collision remains fail-closed on the
 * backend as an idempotency conflict; the value is not used as a secret.
 */
export function createClientIdempotencyKey(source: BrowserCrypto | undefined = globalThis.crypto): string {
  if (typeof source?.randomUUID === "function") return source.randomUUID()
  if (typeof source?.getRandomValues === "function") {
    const values = source.getRandomValues(new Uint32Array(4))
    return `cleanarr-${Array.from(values, (value) => value.toString(16).padStart(8, "0")).join("")}`
  }
  fallbackSequence += 1
  return `cleanarr-${Date.now().toString(36)}-${fallbackSequence.toString(36)}`
}
