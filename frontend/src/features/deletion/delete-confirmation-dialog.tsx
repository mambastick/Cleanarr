import { type RefObject, useEffect, useRef } from "react"
import { Trash2 } from "lucide-react"
import { Dialog, DialogBackdrop, DialogDescription, DialogPopup, DialogPortal, DialogTitle } from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { ScrollArea } from "@/components/ui/scroll-area"
import type { ManualDeletePreviewResponse } from "@/lib/library"
import { isExecutablePlan, type DeletionLanguage } from "./deletion-copy"
import { DeletionPlanSummary } from "./deletion-plan-summary"
import type { InspectionService } from "./plan-presentation"
import type { DeleteSessionPhase } from "./delete-session"

export interface DeleteDialogCopy { cancel: string; delete: string; simulateAction: string; dryRunNotice: string; retry: string; technicalDetails: string; remove: string; retain: string; attention: string; unknownSize: string; preparing: string; ready: string; submitting: string; submitted: string; unavailable: string; close: string }
export function DeleteConfirmationDialog({ open, title, phase, preview, error, isDryRun, language, copy, services, returnFocusRef, onConfirm, onRetry, onClose }: { open: boolean; title: string; phase: DeleteSessionPhase; preview: ManualDeletePreviewResponse | null; error: string | null; isDryRun: boolean; language: DeletionLanguage; copy: DeleteDialogCopy; services?: InspectionService[]; returnFocusRef?: RefObject<HTMLElement | null>; onConfirm: () => void; onRetry: () => void; onClose: () => void }) {
  const cancelRef = useRef<HTMLButtonElement>(null)
  const confirmLock = useRef(false)
  const wasOpenRef = useRef(open)
  useEffect(() => {
    if (phase !== "submitting") confirmLock.current = false
  }, [phase])
  useEffect(() => {
    const wasOpen = wasOpenRef.current
    wasOpenRef.current = open
    if (wasOpen && !open) returnFocusRef?.current?.focus()
  }, [open, returnFocusRef])
  const busy = phase === "preparing" || phase === "submitting"
  const canConfirm = phase === "ready" && preview != null && isExecutablePlan(preview)
  const phaseCopy = phase === "preparing" ? copy.preparing : phase === "submitting" ? copy.submitting : phase === "submitted" ? copy.submitted : canConfirm ? copy.ready : copy.unavailable
  const handleConfirm = () => {
    if (!canConfirm || confirmLock.current) return
    confirmLock.current = true
    onConfirm()
  }
  return <Dialog open={open} onOpenChange={(nextOpen) => { if (!nextOpen && phase !== "submitting") onClose() }}><DialogPortal><DialogBackdrop data-testid="delete-backdrop" className="fixed inset-0 z-[60] bg-foreground/25 backdrop-blur-[1px]" /><DialogPopup initialFocus={cancelRef} finalFocus={returnFocusRef} aria-busy={busy} className="fixed inset-x-3 top-1/2 z-[60] mx-auto flex max-h-[calc(100dvh-1.5rem)] w-auto max-w-2xl -translate-y-1/2 flex-col overflow-hidden rounded-2xl border border-border bg-background shadow-2xl sm:inset-x-6"><div className="border-b border-border bg-card px-4 py-4 sm:px-5"><DialogTitle className="text-base font-semibold">{title}</DialogTitle><DialogDescription role="status" aria-live="polite" className="mt-1 text-sm text-muted-foreground">{phaseCopy}</DialogDescription></div><ScrollArea className="max-h-[min(34rem,calc(100dvh-11rem))] overflow-hidden" viewportClassName="h-auto max-h-[min(34rem,calc(100dvh-11rem))]"><div className="space-y-4 px-4 py-4 pr-6 sm:pl-5 sm:pr-7">{isDryRun ? <p className="rounded-lg border border-status-warning-border bg-status-warning-bg px-3 py-2 text-sm text-status-warning">{copy.dryRunNotice}</p> : null}{preview ? <DeletionPlanSummary preview={preview} language={language} copy={copy} services={services} /> : phase === "preparing" ? <div className="rounded-lg border border-border bg-muted/30 p-3 text-sm text-muted-foreground">{copy.preparing}</div> : null}{error ? <p role="alert" className="rounded-lg border border-status-danger-border bg-status-danger-bg px-3 py-2 text-sm text-status-danger">{error}</p> : null}</div></ScrollArea><div className="flex flex-wrap-reverse justify-end gap-2 border-t border-border bg-muted/30 px-4 py-3 sm:px-5"><Button ref={cancelRef} variant="outline" className="min-h-11" onClick={onClose} disabled={phase === "submitting"}>{copy.cancel}</Button>{(phase === "preparation_failed" || phase === "submission_failed") ? <Button variant="outline" className="min-h-11" onClick={onRetry}>{copy.retry}</Button> : null}{phase !== "submitted" ? <Button variant="destructive" className="min-h-11 bg-status-danger-bg text-status-danger hover:bg-status-danger-bg dark:bg-status-danger-bg dark:hover:bg-status-danger-bg" onClick={handleConfirm} disabled={!canConfirm} aria-describedby={!canConfirm ? "delete-confirmation-reason" : undefined}><Trash2 className="size-4" />{isDryRun ? copy.simulateAction : copy.delete}</Button> : null}{phase === "submitted" ? <Button className="min-h-11" onClick={onClose}>{copy.close}</Button> : null}</div>{!canConfirm && phase !== "submitted" ? <p id="delete-confirmation-reason" className="sr-only">{phaseCopy}</p> : null}</DialogPopup></DialogPortal></Dialog>
}
