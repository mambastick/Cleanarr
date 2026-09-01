import type { ManualDeleteBatch, ManualDeleteBatchStatus } from "@/lib/library"
import type { DeletionLanguage } from "@/features/deletion/deletion-copy"

export function isTerminalBatchStatus(status: ManualDeleteBatchStatus): boolean { return status === "completed" || status === "partial" || status === "failed" || status === "cancelled" }

export function batchTransitionAnnouncement(batch: ManualDeleteBatch, language: DeletionLanguage): { message: string; tone: "polite" | "assertive" } {
  const messages = language === "ru" ? { completed: "Пакетная задача завершена.", partial: "Пакетная задача завершена частично и требует внимания.", failed: "Пакетная задача завершилась с ошибкой.", cancelled: "Пакетная задача отменена." } : { completed: "Batch job completed.", partial: "Batch job completed partially and needs attention.", failed: "Batch job failed.", cancelled: "Batch job was cancelled." }
  const tone = batch.status === "completed" ? "polite" : "assertive"
  return { message: messages[batch.status as keyof typeof messages] ?? messages.failed, tone }
}
