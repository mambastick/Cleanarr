import { describe, expect, it } from "vitest"
import { batchDeleteSessionReducer, buildBatchRequest, initialBatchDeleteSession } from "./batch-delete-session"
import { selectionItem } from "@/features/library/library-selection"

const item = selectionItem({ kind: "movie", radarr_movie_id: 1, movie_title: "Selected title", jellyfin_movie_id: "jf-1" }, "Selected title", 1)
const preview = { generated_at: "2026-09-01T00:00:00Z", batch_hash: "batch-hash", ready_count: 1, blocked_count: 0, children: [] }

describe("batch delete session", () => {
  it("ignores stale preview responses and sends children without nested confirmation fields", () => {
    const first = batchDeleteSessionReducer(initialBatchDeleteSession(), { type: "open", items: [item], idempotencyKey: "same-key" })
    const second = batchDeleteSessionReducer(first, { type: "open", items: [item], idempotencyKey: "new-key" })
    expect(batchDeleteSessionReducer(second, { type: "preflight_ready", sessionId: first.sessionId, attempt: first.attempt, preview })).toBe(second)
    const ready = batchDeleteSessionReducer(second, { type: "preflight_ready", sessionId: second.sessionId, attempt: second.attempt, preview })
    expect(buildBatchRequest(ready)).toMatchObject({ idempotency_key: "new-key", confirmed_batch_hash: "batch-hash", confirmed_item_count: 1 })
    expect(buildBatchRequest(ready)?.children[0]).not.toHaveProperty("confirmed_plan_hash")
    expect(buildBatchRequest(ready)?.children[0]).not.toHaveProperty("idempotency_key")
  })

  it("retains an exact serialized retry, refreshes changed plans with the key, and rotates conflicts", () => {
    const opened = batchDeleteSessionReducer(initialBatchDeleteSession(), { type: "open", items: [item], idempotencyKey: "same-key" })
    const ready = batchDeleteSessionReducer(opened, { type: "preflight_ready", sessionId: opened.sessionId, attempt: opened.attempt, preview })
    const request = buildBatchRequest(ready)!
    const serialized = JSON.stringify(request)
    const ambiguous = batchDeleteSessionReducer(batchDeleteSessionReducer(ready, { type: "submit", request, serializedRequest: serialized }), { type: "submission_failed", code: null, message: "safe", recovery: "resend_exact" })
    const resent = batchDeleteSessionReducer(ambiguous, { type: "resend_exact" })
    expect(resent.serializedRequest).toBe(serialized)
    const changed = batchDeleteSessionReducer(resent, { type: "submission_failed", code: "batch_plan_changed", message: "safe", recovery: "refresh_preflight" })
    expect(batchDeleteSessionReducer(changed, { type: "retry_preflight" }).idempotencyKey).toBe("same-key")
    const conflict = batchDeleteSessionReducer(resent, { type: "submission_failed", code: "idempotency_key_conflict", message: "safe", recovery: "rotate_session" })
    expect(batchDeleteSessionReducer(conflict, { type: "open", items: [item], idempotencyKey: "fresh-key" }).idempotencyKey).toBe("fresh-key")
  })
})
