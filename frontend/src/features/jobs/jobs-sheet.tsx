import { useEffect, useRef, useState, type RefObject } from "react"
import { CheckCircle2, CircleAlert, FlaskConical, ListChecks, X } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Progress } from "@/components/ui/progress"
import { Sheet, SheetBackdrop, SheetContent, SheetDescription, SheetPortal, SheetTitle } from "@/components/ui/sheet"
import type { ManualDeleteBatch, ManualDeleteJob } from "@/lib/library"
import { localizedBatchStatus, localizedJobPhase, type DeletionLanguage } from "@/features/deletion/deletion-copy"
import { isSimulatedBatch, isSimulatedBatchChild, isSimulatedJob, simulationCompletionLabel } from "@/features/jobs/simulation-outcome"

type JobsSheetProps = { jobs: ManualDeleteJob[]; batches?: ManualDeleteBatch[]; title: string; activeLabel: string; dismissLabel: string; closeLabel: string; progressLabel: string; language: DeletionLanguage; announcement: string | null; announcementTone: "polite" | "assertive"; canDismiss?: boolean; returnFocusRef?: RefObject<HTMLElement | null>; onDismiss: (id: string) => void }

export function JobsSheet({ jobs, batches = [], title, activeLabel, dismissLabel, closeLabel, progressLabel, language, announcement, announcementTone, canDismiss = true, returnFocusRef, onDismiss }: JobsSheetProps) {
  const [open, setOpen] = useState(false)
  const [followedJobIds, setFollowedJobIds] = useState<Set<string>>(new Set())
  const [followedBatchIds, setFollowedBatchIds] = useState<Set<string>>(new Set())
  const triggerRef = useRef<HTMLButtonElement>(null)
  const sheetId = "delete-jobs-sheet"
  const activeCount = jobs.filter(isActive).length + batches.filter(isBatchActive).length
  const summary = activeCount ? taskCountLabel(activeCount, language, activeLabel) : completionSummaryLabel(language)
  const showTrigger = activeCount > 0 || open
  useEffect(() => {
    if (!open) return
    const activeJobIds = jobs.filter(isActive).map((job) => job.id)
    const activeBatchIds = batches.filter(isBatchActive).map((batch) => batch.id)
    if (activeJobIds.length) setFollowedJobIds((current) => addMissingIds(current, activeJobIds))
    if (activeBatchIds.length) setFollowedBatchIds((current) => addMissingIds(current, activeBatchIds))
  }, [batches, jobs, open])
  const visibleJobs = jobs.filter((job) => isActive(job) || followedJobIds.has(job.id))
  const visibleBatches = batches.filter((batch) => isBatchActive(batch) || followedBatchIds.has(batch.id))
  const openSheet = () => {
    setFollowedJobIds(new Set(jobs.filter(isActive).map((job) => job.id)))
    setFollowedBatchIds(new Set(batches.filter(isBatchActive).map((batch) => batch.id)))
    setOpen(true)
  }
  const handleOpenChange = (nextOpen: boolean) => {
    setOpen(nextOpen)
    if (!nextOpen) {
      setFollowedJobIds(new Set())
      setFollowedBatchIds(new Set())
    }
  }
  const finalFocus = activeCount > 0 ? triggerRef : returnFocusRef
  return <><div aria-live={announcementTone} aria-atomic="true" className="jobs-announcement sr-only">{announcement}</div>{showTrigger ? <div className="jobs-sheet-trigger"><Button ref={triggerRef} variant="outline" size="sm" className="min-h-11 bg-card/95 shadow-sm" onClick={openSheet} aria-expanded={open} aria-controls={sheetId} aria-label={title}><ListChecks className="size-4" /><span>{summary}</span></Button></div> : null}<Sheet open={open} onOpenChange={handleOpenChange}><SheetPortal><SheetBackdrop className="fixed inset-0 z-50 bg-foreground/20" /><SheetContent id={sheetId} finalFocus={finalFocus} className="fixed inset-y-0 right-0 z-50 flex w-full flex-col border-border bg-background shadow-2xl sm:w-[min(100%,26rem)] sm:border-l"><div className="relative min-h-16 border-b border-border bg-card p-4 pl-16 sm:p-5 sm:pl-16"><Button variant="ghost" size="icon-sm" className="absolute left-1 top-3 min-h-11 min-w-11 sm:top-4" onClick={() => handleOpenChange(false)} aria-label={closeLabel} title={closeLabel}><X className="size-4" /></Button><div><SheetTitle className="font-semibold">{title}</SheetTitle><SheetDescription className="text-sm text-muted-foreground">{summary}</SheetDescription></div></div><div role="region" aria-label={title} tabIndex={0} className="min-h-0 flex-1 overflow-y-auto outline-none focus-visible:ring-3 focus-visible:ring-inset focus-visible:ring-ring/50"><div className="space-y-3 p-4 pr-5 pb-[calc(1rem+env(safe-area-inset-bottom))] sm:p-5 sm:pr-6">{visibleBatches.map((batch) => <BatchCard key={batch.id} batch={batch} language={language} progressLabel={progressLabel} />)}{visibleJobs.map((job) => <JobCard key={job.id} job={job} language={language} dismissLabel={dismissLabel} progressLabel={progressLabel} canDismiss={canDismiss} onDismiss={onDismiss} />)}</div></div></SheetContent></SheetPortal></Sheet></>
}

function JobCard({ job, language, dismissLabel, progressLabel, canDismiss, onDismiss }: { job: ManualDeleteJob; language: DeletionLanguage; dismissLabel: string; progressLabel: string; canDismiss: boolean; onDismiss: (id: string) => void }) { const active = isActive(job); const failed = job.status === "failed" || job.result?.status === "partial_failure"; const simulated = isSimulatedJob(job); const name = job.display_name; const statusLabel = simulated ? simulationCompletionLabel(language) : localizedJobPhase(job.phase, failed, language); return <article className="rounded-lg border border-border bg-card p-3"><div className="flex gap-2"><div className="pt-0.5">{failed ? <CircleAlert className="size-4 text-status-danger" /> : active ? <ListChecks className="size-4 text-primary" /> : simulated ? <FlaskConical className="size-4 text-primary" /> : <CheckCircle2 className="size-4 text-status-success" />}</div><div className="min-w-0 flex-1"><div className="flex gap-2"><h3 className="min-w-0 flex-1 truncate text-sm font-medium" title={name}>{name}</h3>{canDismiss && !active ? <Button variant="ghost" size="icon-xs" className="min-h-11 min-w-11" aria-label={`${dismissLabel}: ${name}`} title={`${dismissLabel}: ${name}`} onClick={() => onDismiss(job.id)}><X className="size-3.5" /></Button> : null}</div><p className="mt-1 text-xs text-muted-foreground">{statusLabel}</p><Progress className="mt-3" value={job.progress_percent} aria-label={`${name}: ${progressLabel}`} /><div className="mt-1.5 flex justify-between gap-2 text-[11px] text-muted-foreground"><Badge variant="outline" className="text-[10px]">{statusLabel}</Badge><span>{job.progress_percent}%</span></div></div></div></article> }
function isActive(job: ManualDeleteJob) { return job.status === "queued" || job.status === "running" || job.status === "retry_wait" }
function isBatchActive(batch: ManualDeleteBatch) { return batch.status === "queued" || batch.status === "running" }
function addMissingIds(current: Set<string>, ids: string[]) { const next = new Set(current); let changed = false; ids.forEach((id) => { if (!next.has(id)) { next.add(id); changed = true } }); return changed ? next : current }
function BatchCard({ batch, language, progressLabel }: { batch: ManualDeleteBatch; language: DeletionLanguage; progressLabel: string }) { const active = isBatchActive(batch); const needsAttention = batch.status === "failed" || batch.status === "partial" || batch.status === "cancelled"; const simulated = isSimulatedBatch(batch); const terminal = batch.completed_count + batch.blocked_count + batch.failed_count + batch.cancelled_count; const progress = batch.total_count ? Math.round((terminal / batch.total_count) * 100) : 0; const counts = batchCounts(batch, language); const statusLabel = simulated ? simulationCompletionLabel(language) : localizedBatchStatus(batch.status, language); return <article className="rounded-lg border border-border bg-card p-3"><div className="flex gap-2"><div className="pt-0.5">{needsAttention ? <CircleAlert className="size-4 text-status-danger" /> : active ? <ListChecks className="size-4 text-primary" /> : simulated ? <FlaskConical className="size-4 text-primary" /> : <CheckCircle2 className="size-4 text-status-success" />}</div><div className="min-w-0 flex-1"><h3 className="text-sm font-medium">{batchItemCountLabel(batch.total_count, language)}</h3><p className="mt-1 text-xs text-muted-foreground">{statusLabel}</p><Progress className="mt-3" value={progress} aria-label={`${progressLabel}: ${progress}%`} /><div className="mt-1.5 flex justify-between gap-2 text-[11px] text-muted-foreground"><Badge variant="outline" className="text-[10px]">{statusLabel}</Badge><span>{terminal}/{batch.total_count}</span></div><p className="mt-1 text-[11px] text-muted-foreground">{counts}</p><ul className="mt-3 space-y-1 border-t border-border pt-2">{batch.children.map((child) => { const childLabel = isSimulatedBatchChild(child) ? simulationCompletionLabel(language) : localizedBatchStatus(child.status, language); return <li key={child.id} className="flex items-center justify-between gap-2 text-xs"><span className="min-w-0 truncate">{child.display_name}</span><Badge variant="outline" className="shrink-0 text-[10px]">{childLabel}</Badge></li> })}</ul></div></div></article> }
function batchCounts(batch: ManualDeleteBatch, language: DeletionLanguage) { const labels = language === "ru" ? { completed: "завершено", blocked: "заблокировано", failed: "ошибка", cancelled: "отменено" } : { completed: "completed", blocked: "blocked", failed: "failed", cancelled: "cancelled" }; return [`${labels.completed}: ${batch.completed_count}`, `${labels.blocked}: ${batch.blocked_count}`, `${labels.failed}: ${batch.failed_count}`, `${labels.cancelled}: ${batch.cancelled_count}`].join(" · ") }
function taskCountLabel(count: number, language: DeletionLanguage, fallback: string) { if (language !== "ru") return `${count} ${fallback}`; if (count === 1) return "1 активная"; return `${count} ${fallback}` }
function completionSummaryLabel(language: DeletionLanguage) { return language === "ru" ? "Завершённые задачи" : "Completed jobs" }
function batchItemCountLabel(count: number, language: DeletionLanguage) { if (language !== "ru") return `${count} ${count === 1 ? "item" : "items"} in batch`; const mod100 = Math.abs(count) % 100; const mod10 = mod100 % 10; const noun = mod100 >= 11 && mod100 <= 14 ? "элементов" : mod10 === 1 ? "элемент" : mod10 >= 2 && mod10 <= 4 ? "элемента" : "элементов"; return `${count} ${noun} в пакете` }
