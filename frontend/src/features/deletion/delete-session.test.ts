import { describe, expect, it } from "vitest"
import { buildConfirmedDeleteRequest, deleteSessionReducer, initialDeleteSession } from "./delete-session"

const preview = { generated_at: "2026-09-01T00:00:00Z", plan_hash: "confirmed-hash", plan: { item_type: "Movie" as const, correlation_id: null, item_id: "movie-1", name: "Canonical", display_name: "Selected library title", status: "success" as const, fingerprint: { tmdb_id: 1, tvdb_id: null, imdb_id: null, path: null }, season_number: null, episode_number: null, episode_end_number: null, actions: [] } }
const build = (target: { id: number }, displayName: string) => ({ item_type: "Movie" as const, radarr_movie_id: target.id, display_name: displayName })

describe("delete session reducer", () => {
  it("ignores stale preflight completions and keeps one selected display name", () => {
    const first = deleteSessionReducer(initialDeleteSession<{ id: number }>(), { type: "open", target: { id: 1 }, displayName: "Season 1 of Series", idempotencyKey: "key-first" })
    const second = deleteSessionReducer(first, { type: "open", target: { id: 2 }, displayName: "Сезон 2 сериала", idempotencyKey: "key-second" })
    const stale = deleteSessionReducer(second, { type: "preflight_ready", sessionId: first.sessionId, attempt: first.attempt, preview })
    const ready = deleteSessionReducer(stale, { type: "preflight_ready", sessionId: second.sessionId, attempt: second.attempt, preview })
    expect(stale).toBe(second)
    expect(buildConfirmedDeleteRequest(ready, build)?.display_name).toBe("Сезон 2 сериала")
  })

  it("refreshes preflight without rotating a key for changed plans", () => {
    const opened = deleteSessionReducer(initialDeleteSession<{ id: number }>(), { type: "open", target: { id: 7 }, displayName: "Library", idempotencyKey: "same-key" })
    const ready = deleteSessionReducer(opened, { type: "preflight_ready", sessionId: opened.sessionId, attempt: opened.attempt, preview })
    const request = buildConfirmedDeleteRequest(ready, build)!
    const failed = deleteSessionReducer(deleteSessionReducer(ready, { type: "submit", request, serializedRequest: JSON.stringify(request) }), { type: "submission_failed", code: "plan_changed", message: "safe", recovery: "refresh_preflight" })
    const refreshing = deleteSessionReducer(failed, { type: "retry_preflight" })
    expect(refreshing.phase).toBe("preparing")
    expect(refreshing.idempotencyKey).toBe("same-key")
    expect(refreshing.serializedRequest).toBeNull()
  })

  it("only resends an ambiguous response with byte-equivalent stored data and rotates conflicts", () => {
    const opened = deleteSessionReducer(initialDeleteSession<{ id: number }>(), { type: "open", target: { id: 7 }, displayName: "Library", idempotencyKey: "same-key" })
    const ready = deleteSessionReducer(opened, { type: "preflight_ready", sessionId: opened.sessionId, attempt: opened.attempt, preview })
    const request = buildConfirmedDeleteRequest(ready, build)!
    const serialized = JSON.stringify(request)
    const ambiguous = deleteSessionReducer(deleteSessionReducer(ready, { type: "submit", request, serializedRequest: serialized }), { type: "submission_failed", code: null, message: "safe", recovery: "resend_exact" })
    const resent = deleteSessionReducer(ambiguous, { type: "resend_exact" })
    const conflict = deleteSessionReducer(resent, { type: "submission_failed", code: "idempotency_key_conflict", message: "safe", recovery: "rotate_session" })
    const fresh = deleteSessionReducer(conflict, { type: "open", target: { id: 7 }, displayName: "Library", idempotencyKey: "fresh-key" })
    expect(resent.serializedRequest).toBe(serialized)
    expect(resent.submittedRequest).toEqual(request)
    expect(conflict.recovery).toBe("rotate_session")
    expect(fresh.idempotencyKey).toBe("fresh-key")
  })
})
