import { ApiError } from "@/lib/api-client"
import type { DashboardAction } from "@/lib/dashboard"
import type { SubmissionRecovery } from "./delete-session"

export type DeletionLanguage = "en" | "ru"
export const SAFE_RETAINED_SKIP_REASONS = new Set(["pack_torrent", "shared_file", "seeding_policy", "partial_request_retained", "no_partial_request_cleanup"])
export const DELETION_NOTICES: Record<DeletionLanguage, { jobNeedsAttention: string; jobCompleted: string; batchAccepted: string }> = {
  en: { jobNeedsAttention: "job needs attention.", jobCompleted: "job completed.", batchAccepted: "Batch job accepted." },
  ru: { jobNeedsAttention: "задача требует внимания.", jobCompleted: "задача завершена.", batchAccepted: "Пакетная задача принята." },
}

const copy = {
  en: {
    plan_changed: "The safe plan changed. Review the current plan before confirming again.", confirmation_required: "Review the safe plan before confirming deletion.", confirmation_invalid: "The confirmation no longer matches the reviewed plan. Review it again.", unsafe_plan: "This plan needs attention and cannot be queued for deletion.", idempotency_key_conflict: "This confirmation session is no longer valid. Open a new confirmation.", idempotency_key_required: "The confirmation session is incomplete. Open a new confirmation.", active_job: "An active deletion job cannot be dismissed.", default: "The deletion request could not be completed safely.",
    remove: "Removal is planned", retain: "Kept safely", attention: "Needs attention", action: "Planned action", jobQueued: "Queued", jobRunning: "Running", jobRetrying: "Retry scheduled", jobCompleted: "Completed", jobFailed: "Needs attention", batch_plan_changed: "The batch plan changed. Review the current batch plan before confirming again.", batch_queue_full: "The batch queue is full. Wait for an active batch to finish.", duplicate_mutation_identity: "The same deletion target cannot be included more than once.", overlapping_mutation_scope: "A whole series and one of its seasons cannot be deleted together.", invalid_batch_size: "Select between 1 and 50 items for a batch.", batchPartial: "Partial outcome", batchCancelled: "Cancelled", batchBlocked: "Blocked",
  },
  ru: {
    plan_changed: "Безопасный план изменился. Проверьте текущий план перед повторным подтверждением.", confirmation_required: "Проверьте безопасный план перед подтверждением удаления.", confirmation_invalid: "Подтверждение больше не соответствует просмотренному плану. Проверьте его снова.", unsafe_plan: "Этот план требует внимания и не может быть поставлен в очередь на удаление.", idempotency_key_conflict: "Сеанс подтверждения больше недействителен. Откройте новое подтверждение.", idempotency_key_required: "Сеанс подтверждения неполный. Откройте новое подтверждение.", active_job: "Активную задачу удаления нельзя скрыть.", default: "Запрос на удаление не удалось безопасно завершить.",
    remove: "Удаление запланировано", retain: "Безопасно сохранено", attention: "Требует внимания", action: "Запланированное действие", jobQueued: "В очереди", jobRunning: "Выполняется", jobRetrying: "Повтор запланирован", jobCompleted: "Завершено", jobFailed: "Требует внимания", batch_plan_changed: "Пакетный план изменился. Проверьте текущий пакетный план перед повторным подтверждением.", batch_queue_full: "Очередь пакетных задач заполнена. Дождитесь завершения активного пакета.", duplicate_mutation_identity: "Один и тот же целевой элемент нельзя включить больше одного раза.", overlapping_mutation_scope: "Нельзя удалить сериал целиком вместе с одним из его сезонов.", invalid_batch_size: "Выберите от 1 до 50 элементов для пакета.", batchPartial: "Частичный результат", batchCancelled: "Отменено", batchBlocked: "Заблокировано",
  },
} as const

export function localizedDeletionError(error: unknown, language: DeletionLanguage): { code: string | null; message: string } {
  const code = error instanceof ApiError ? error.code : null
  const messages = copy[language]
  return code && code in messages ? { code, message: messages[code as keyof typeof messages] } : { code, message: messages.default }
}

export function submissionRecovery(error: unknown): SubmissionRecovery {
  if (!(error instanceof ApiError)) return "resend_exact"
  if (error.status >= 500) return "resend_exact"
  if (error.code === "idempotency_key_conflict") return "rotate_session"
  return "refresh_preflight"
}

export function actionGroup(action: DashboardAction): "remove" | "retain" | "attention" {
  if (action.status === "skipped") return action.reason && SAFE_RETAINED_SKIP_REASONS.has(action.reason) ? "retain" : "attention"
  if (action.status === "ignored" || action.status === "failed") return "attention"
  return action.status === "already_absent" ? "retain" : "remove"
}

export function localizedActionLabel(action: DashboardAction, language: DeletionLanguage): string {
  const labels = copy[language]
  return labels[actionGroup(action)]
}

export function localizedSystemLabel(system: string, language: DeletionLanguage): string {
  const known: Record<string, readonly [string, string]> = {
    downloader: ["Torrent client", "Торрент-клиент"],
    qbittorrent: ["qBittorrent", "qBittorrent"],
    transmission: ["Transmission", "Transmission"],
    deluge: ["Deluge", "Deluge"],
    rtorrent: ["rTorrent", "rTorrent"],
    radarr: ["Radarr", "Radarr"],
    sonarr: ["Sonarr", "Sonarr"],
    seerr: ["Seerr", "Seerr"],
    jellyfin: ["Jellyfin", "Jellyfin"],
  }
  return known[system.toLowerCase()]?.[language === "ru" ? 1 : 0]
    ?? (language === "ru" ? "Настроенный сервис" : "Configured service")
}

export function localizedJobPhase(phase: string, failed: boolean, language: DeletionLanguage): string {
  const labels = copy[language]
  if (failed || phase === "failed") return labels.jobFailed
  if (phase === "completed") return labels.jobCompleted
  if (phase === "retrying" || phase === "retry_wait") return labels.jobRetrying
  if (phase === "queued") return labels.jobQueued
  return labels.jobRunning
}

export function localizedBatchStatus(status: string, language: DeletionLanguage): string {
  const labels = copy[language]
  if (status === "partial") return labels.batchPartial
  if (status === "cancelled") return labels.batchCancelled
  if (status === "blocked") return labels.batchBlocked
  if (status === "failed") return labels.jobFailed
  if (status === "completed") return labels.jobCompleted
  if (status === "queued") return labels.jobQueued
  return labels.jobRunning
}
