export interface ApiErrorDetail {
  code?: string
  message?: string
  [key: string]: unknown
}

export class ApiError extends Error {
  readonly status: number
  readonly detail: ApiErrorDetail | null

  constructor(status: number, message: string, detail: ApiErrorDetail | null = null) {
    super(message)
    this.name = "ApiError"
    this.status = status
    this.detail = detail
  }

  get code(): string | null {
    return typeof this.detail?.code === "string" ? this.detail.code : null
  }
}

export function apiErrorFromResponse(status: number, statusText: string, body: unknown): ApiError {
  const fallback = statusText || `HTTP ${status}`
  if (isApiErrorDetail(body)) {
    return new ApiError(status, body.message ?? fallback, body)
  }
  if (isRecord(body) && isApiErrorDetail(body.detail)) {
    return new ApiError(status, body.detail.message ?? fallback, body.detail)
  }
  if (isRecord(body) && typeof body.detail === "string") {
    return new ApiError(status, body.detail)
  }
  if (isRecord(body) && typeof body.message === "string") {
    return new ApiError(status, body.message)
  }
  return new ApiError(status, fallback)
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null
}

function isApiErrorDetail(value: unknown): value is ApiErrorDetail {
  return isRecord(value) && (typeof value.code === "string" || typeof value.message === "string")
}
