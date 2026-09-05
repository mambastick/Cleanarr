import type {
  ManualDeleteBatch,
  ManualDeleteBatchChild,
  ManualDeleteJob,
  ManualDeleteResponse,
} from "@/lib/library"
import type { DeletionLanguage } from "@/features/deletion/deletion-copy"

const simulationCompletionCopy: Record<DeletionLanguage, string> = {
  en: "Simulation completed — no changes were made.",
  ru: "Симуляция завершена — изменения не внесены.",
}

export function hasDryRunAction(
  result: ManualDeleteResponse | null | undefined,
): boolean {
  return result?.actions.some((action) => action.status === "dry_run") ?? false
}

export function isSimulatedJob(job: ManualDeleteJob): boolean {
  return job.status === "completed" && hasDryRunAction(job.result)
}

export function isSimulatedBatchChild(child: ManualDeleteBatchChild): boolean {
  return child.status === "completed" && hasDryRunAction(child.result)
}

export function isSimulatedBatch(batch: ManualDeleteBatch): boolean {
  return batch.status === "completed" && batch.children.some(isSimulatedBatchChild)
}

export function simulationCompletionLabel(language: DeletionLanguage): string {
  return simulationCompletionCopy[language]
}

export function simulationJobCompletionNotice(
  job: ManualDeleteJob,
  language: DeletionLanguage,
): string | null {
  return isSimulatedJob(job) ? simulationCompletionLabel(language) : null
}

export function simulationBatchCompletionNotice(
  batch: ManualDeleteBatch,
  language: DeletionLanguage,
): string | null {
  return isSimulatedBatch(batch) ? simulationCompletionLabel(language) : null
}
