import type { ManualDeleteJobRequest, ManualDeletePreviewResponse, ManualDeleteRequest } from "@/lib/library"

export type DeleteSessionPhase = "closed" | "preparing" | "ready" | "submitting" | "submitted" | "preparation_failed" | "submission_failed"
export type SubmissionRecovery = "refresh_preflight" | "rotate_session" | "resend_exact" | null

export interface DeleteSessionState<T> {
  phase: DeleteSessionPhase
  sessionId: number
  attempt: number
  target: T | null
  displayName: string | null
  idempotencyKey: string | null
  preview: ManualDeletePreviewResponse | null
  submittedRequest: ManualDeleteJobRequest | null
  serializedRequest: string | null
  recovery: SubmissionRecovery
  errorCode: string | null
  errorMessage: string | null
  submittedJobId: string | null
}

export const initialDeleteSession = <T,>(): DeleteSessionState<T> => ({ phase: "closed", sessionId: 0, attempt: 0, target: null, displayName: null, idempotencyKey: null, preview: null, submittedRequest: null, serializedRequest: null, recovery: null, errorCode: null, errorMessage: null, submittedJobId: null })

export type DeleteSessionAction<T> =
  | { type: "open"; target: T; displayName: string; idempotencyKey: string }
  | { type: "preflight_ready"; sessionId: number; attempt: number; preview: ManualDeletePreviewResponse }
  | { type: "preflight_failed"; sessionId: number; attempt: number; code: string | null; message: string }
  | { type: "retry_preflight" }
  | { type: "submit"; request: ManualDeleteJobRequest; serializedRequest: string }
  | { type: "resend_exact" }
  | { type: "submitted"; jobId: string }
  | { type: "submission_failed"; code: string | null; message: string; recovery: SubmissionRecovery }
  | { type: "close" }

export function deleteSessionReducer<T>(state: DeleteSessionState<T>, action: DeleteSessionAction<T>): DeleteSessionState<T> {
  switch (action.type) {
    case "open": return { ...initialDeleteSession<T>(), phase: "preparing", sessionId: state.sessionId + 1, attempt: 1, target: action.target, displayName: action.displayName, idempotencyKey: action.idempotencyKey }
    case "preflight_ready": return isCurrentAttempt(state, action) ? { ...state, phase: "ready", preview: action.preview, errorCode: null, errorMessage: null, recovery: null } : state
    case "preflight_failed": return isCurrentAttempt(state, action) ? { ...state, phase: "preparation_failed", errorCode: action.code, errorMessage: action.message } : state
    case "retry_preflight": return state.target && state.phase !== "submitting" ? { ...state, phase: "preparing", attempt: state.attempt + 1, preview: null, submittedRequest: null, serializedRequest: null, recovery: null, errorCode: null, errorMessage: null } : state
    case "submit": return state.phase === "ready" ? { ...state, phase: "submitting", submittedRequest: action.request, serializedRequest: action.serializedRequest, recovery: null, errorCode: null, errorMessage: null } : state
    case "resend_exact": return state.phase === "submission_failed" && state.recovery === "resend_exact" && state.submittedRequest && state.serializedRequest ? { ...state, phase: "submitting", errorCode: null, errorMessage: null } : state
    case "submitted": return state.phase === "submitting" ? { ...state, phase: "submitted", submittedJobId: action.jobId } : state
    case "submission_failed": return state.phase === "submitting" ? { ...state, phase: "submission_failed", errorCode: action.code, errorMessage: action.message, recovery: action.recovery } : state
    case "close": return state.phase === "submitting" ? state : { ...initialDeleteSession<T>(), sessionId: state.sessionId }
  }
}

function isCurrentAttempt<T>(state: DeleteSessionState<T>, action: { sessionId: number; attempt: number }) { return state.phase === "preparing" && state.sessionId === action.sessionId && state.attempt === action.attempt }

export function buildConfirmedDeleteRequest<T>(state: DeleteSessionState<T>, buildRequest: (target: T, displayName: string) => ManualDeleteRequest): ManualDeleteJobRequest | null {
  if (!state.target || !state.preview || !state.idempotencyKey || !state.displayName) return null
  return { ...buildRequest(state.target, state.displayName), display_name: state.displayName, confirmed_plan_hash: state.preview.plan_hash, idempotency_key: state.idempotencyKey }
}
