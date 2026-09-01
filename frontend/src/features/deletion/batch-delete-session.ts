import type { ManualDeleteBatch, ManualDeleteBatchPreviewResponse, ManualDeleteBatchRequest, ManualDeleteRequest } from "@/lib/library"
import type { BatchSelectionItem } from "@/features/library/library-selection"

export type BatchDeletePhase = "closed" | "preparing" | "ready" | "submitting" | "submitted" | "preparation_failed" | "submission_failed"
export type BatchSubmissionRecovery = "refresh_preflight" | "rotate_session" | "resend_exact" | null
export interface BatchDeleteSession {
  phase: BatchDeletePhase
  sessionId: number
  attempt: number
  items: BatchSelectionItem[]
  idempotencyKey: string | null
  preview: ManualDeleteBatchPreviewResponse | null
  submittedRequest: ManualDeleteBatchRequest | null
  serializedRequest: string | null
  recovery: BatchSubmissionRecovery
  errorCode: string | null
  errorMessage: string | null
  submittedBatch: ManualDeleteBatch | null
}
export const initialBatchDeleteSession = (): BatchDeleteSession => ({ phase: "closed", sessionId: 0, attempt: 0, items: [], idempotencyKey: null, preview: null, submittedRequest: null, serializedRequest: null, recovery: null, errorCode: null, errorMessage: null, submittedBatch: null })
export type BatchDeleteAction =
  | { type: "open"; items: BatchSelectionItem[]; idempotencyKey: string }
  | { type: "preflight_ready"; sessionId: number; attempt: number; preview: ManualDeleteBatchPreviewResponse }
  | { type: "preflight_failed"; sessionId: number; attempt: number; code: string | null; message: string }
  | { type: "retry_preflight" }
  | { type: "submit"; request: ManualDeleteBatchRequest; serializedRequest: string }
  | { type: "resend_exact" }
  | { type: "submitted"; batch: ManualDeleteBatch }
  | { type: "submission_failed"; code: string | null; message: string; recovery: BatchSubmissionRecovery }
  | { type: "close" }
export function batchDeleteSessionReducer(state: BatchDeleteSession, action: BatchDeleteAction): BatchDeleteSession {
  switch (action.type) {
    case "open": return { ...initialBatchDeleteSession(), phase: "preparing", sessionId: state.sessionId + 1, attempt: 1, items: action.items, idempotencyKey: action.idempotencyKey }
    case "preflight_ready": return current(state, action) ? { ...state, phase: "ready", preview: action.preview, errorCode: null, errorMessage: null, recovery: null } : state
    case "preflight_failed": return current(state, action) ? { ...state, phase: "preparation_failed", errorCode: action.code, errorMessage: action.message } : state
    case "retry_preflight": return state.items.length && state.phase !== "submitting" ? { ...state, phase: "preparing", attempt: state.attempt + 1, preview: null, submittedRequest: null, serializedRequest: null, recovery: null, errorCode: null, errorMessage: null } : state
    case "submit": return state.phase === "ready" ? { ...state, phase: "submitting", submittedRequest: action.request, serializedRequest: action.serializedRequest, errorCode: null, errorMessage: null, recovery: null } : state
    case "resend_exact": return state.phase === "submission_failed" && state.recovery === "resend_exact" && state.submittedRequest && state.serializedRequest ? { ...state, phase: "submitting", errorCode: null, errorMessage: null } : state
    case "submitted": return state.phase === "submitting" ? { ...state, phase: "submitted", submittedBatch: action.batch } : state
    case "submission_failed": return state.phase === "submitting" ? { ...state, phase: "submission_failed", errorCode: action.code, errorMessage: action.message, recovery: action.recovery } : state
    case "close": return state.phase === "submitting" ? state : { ...initialBatchDeleteSession(), sessionId: state.sessionId }
  }
}
function current(state: BatchDeleteSession, action: { sessionId: number; attempt: number }) { return state.phase === "preparing" && state.sessionId === action.sessionId && state.attempt === action.attempt }
export function batchChildRequests(items: BatchSelectionItem[]): ManualDeleteRequest[] { return items.map((item) => { const request = { ...item.request }; delete request.confirmed_plan_hash; delete request.idempotency_key; return request }) }
export function buildBatchRequest(state: BatchDeleteSession): ManualDeleteBatchRequest | null { if (!state.preview || !state.idempotencyKey || !state.items.length) return null; return { children: batchChildRequests(state.items), idempotency_key: state.idempotencyKey, confirmed_batch_hash: state.preview.batch_hash, confirmed_item_count: state.items.length } }
