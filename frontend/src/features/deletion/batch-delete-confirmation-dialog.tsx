import { useEffect, useMemo, useRef, useState, type RefObject } from "react"
import { ShieldAlert, ShieldCheck, Trash2 } from "lucide-react"
import { AlertDialog, AlertDialogBackdrop, AlertDialogDescription, AlertDialogPopup, AlertDialogPortal, AlertDialogTitle } from "@/components/ui/alert-dialog"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { ScrollArea } from "@/components/ui/scroll-area"
import type { BatchDeletePhase } from "./batch-delete-session"
import { actionGroup, localizedActionLabel, localizedSystemLabel, type DeletionLanguage } from "./deletion-copy"
import type { ManualDeleteBatchPreviewResponse } from "@/lib/library"
import type { BatchSelectionItem } from "@/features/library/library-selection"

const copy = {
  en: { title: "Review batch deletion", preparing: "Preparing a safe batch plan… confirmation is not available yet.", ready: "Review the safe batch plan before confirming.", submitting: "Submitting the confirmed batch. Closing is temporarily unavailable.", submitted: "The batch was accepted. Follow child progress in background tasks.", unavailable: "Confirmation is unavailable until a safe batch plan is ready.", cancel: "Cancel", retry: "Retry preview", close: "Close", simulate: "Simulate batch cleanup", confirm: "Delete selected items", liveGate: "Type the exact selected item count to enable deletion.", dryRun: "Dry-run: this is a simulation and no live deletion will run.", blocked: "Blocked items", systems: "Affected systems", itemTypes: "Selected item types", removing: "Torrent removals", retaining: "Retained or seeding", attention: "Safety blocks", continues: "Safe children may continue when other children are blocked; this batch is not all-or-nothing.", technical: "Technical summary", noSafe: "No selected item has a safe plan to queue.", unknownSize: "Some selected items have an unknown size." },
  ru: { title: "Проверка массового удаления", preparing: "Готовим безопасный пакетный план… подтверждение пока недоступно.", ready: "Проверьте безопасный пакетный план перед подтверждением.", submitting: "Отправляем подтверждённый пакет. Закрытие временно недоступно.", submitted: "Пакет принят. Следите за дочерними задачами в фоновых задачах.", unavailable: "Подтверждение недоступно, пока безопасный пакетный план не готов.", cancel: "Отмена", retry: "Повторить проверку", close: "Закрыть", simulate: "Симулировать очистку", confirm: "Удалить выбранные элементы", liveGate: "Введите точное количество выбранных элементов, чтобы включить удаление.", dryRun: "Режим проверки: это симуляция, live-удаление не будет выполнено.", blocked: "Заблокированные элементы", systems: "Затронутые системы", itemTypes: "Типы выбранных элементов", removing: "Удаления торрентов", retaining: "Сохранено или сидируется", attention: "Блокировки безопасности", continues: "Безопасные дочерние элементы могут продолжить работу, когда другие заблокированы; пакет не является all-or-nothing операцией.", technical: "Техническое резюме", noSafe: "Ни у одного выбранного элемента нет безопасного плана для постановки в очередь.", unknownSize: "Размер некоторых выбранных элементов неизвестен." },
} as const
type BatchCopy = { [Key in keyof typeof copy.en]: string }

export function BatchDeleteConfirmationDialog({ open, phase, preview, items, error, isDryRun, language, returnFocusRef, onConfirm, onRetry, onClose }: { open: boolean; phase: BatchDeletePhase; preview: ManualDeleteBatchPreviewResponse | null; items: BatchSelectionItem[]; error: string | null; isDryRun: boolean; language: DeletionLanguage; returnFocusRef?: RefObject<HTMLElement | null>; onConfirm: () => void; onRetry: () => void; onClose: () => void }) {
  const text = copy[language]
  const cancelRef = useRef<HTMLButtonElement>(null)
  const confirmLock = useRef(false)
  const [typedCount, setTypedCount] = useState("")
  const previousOpen = useRef(open)
  useEffect(() => { if (!open) setTypedCount("") }, [open])
  useEffect(() => { if (phase !== "submitting") confirmLock.current = false }, [phase])
  useEffect(() => { const wasOpen = previousOpen.current; previousOpen.current = open; if (wasOpen && !open) returnFocusRef?.current?.focus() }, [open, returnFocusRef])
  const busy = phase === "preparing" || phase === "submitting"
  const readyChildren = preview?.children.filter((child) => child.status === "ready") ?? []
  const needsCount = !isDryRun && typedCount !== String(items.length)
  const canConfirm = phase === "ready" && preview != null && readyChildren.length > 0 && !needsCount
  const reason = phase === "preparing" ? text.preparing : phase === "submitting" ? text.submitting : phase === "submitted" ? text.submitted : readyChildren.length === 0 && preview ? text.noSafe : needsCount ? text.liveGate : phase === "ready" ? text.ready : text.unavailable
  return <AlertDialog open={open} onOpenChange={(next) => { if (!next && phase !== "submitting") onClose() }}><AlertDialogPortal><AlertDialogBackdrop data-testid="batch-delete-backdrop" className="fixed inset-0 z-50 bg-foreground/25 backdrop-blur-[1px]" /><AlertDialogPopup initialFocus={cancelRef} finalFocus={returnFocusRef} aria-busy={busy} className="fixed inset-x-3 top-1/2 z-50 mx-auto flex max-h-[calc(100dvh-1.5rem)] w-auto max-w-2xl -translate-y-1/2 flex-col overflow-hidden rounded-xl border border-border bg-background shadow-2xl sm:inset-x-6"><div className="border-b border-border px-4 py-4 sm:px-5"><AlertDialogTitle className="text-base font-semibold">{text.title}</AlertDialogTitle><AlertDialogDescription role="status" aria-live="polite" className="mt-1 text-sm text-muted-foreground">{reason}</AlertDialogDescription></div><ScrollArea className="max-h-[min(34rem,calc(100dvh-11rem))] overflow-hidden" viewportClassName="h-auto max-h-[min(34rem,calc(100dvh-11rem))]"><div className="px-4 py-4 pr-6 sm:pl-5 sm:pr-7"><BatchSummary preview={preview} items={items} language={language} isDryRun={isDryRun} text={text} />{!isDryRun && phase === "ready" && preview ? <label className="mt-4 block rounded-lg border border-border bg-muted/30 p-3 text-sm font-medium">{text.liveGate}<Input className="mt-2" inputMode="numeric" aria-label={text.liveGate} value={typedCount} onChange={(event) => setTypedCount(event.target.value.replace(/\D/g, ""))} /></label> : null}{error ? <p role="alert" className="mt-4 rounded-lg border border-status-danger-border bg-status-danger-bg px-3 py-2 text-sm text-status-danger">{error}</p> : null}</div></ScrollArea><div className="flex flex-wrap-reverse justify-end gap-2 border-t border-border bg-muted/30 px-4 py-3 sm:px-5"><Button ref={cancelRef} variant="outline" onClick={onClose} disabled={phase === "submitting"}>{text.cancel}</Button>{(phase === "preparation_failed" || phase === "submission_failed") ? <Button variant="outline" onClick={onRetry}>{text.retry}</Button> : null}{phase !== "submitted" ? <Button variant="destructive" onClick={() => { if (confirmLock.current) return; confirmLock.current = true; onConfirm() }} disabled={!canConfirm} aria-describedby={!canConfirm ? "batch-confirmation-reason" : undefined}><Trash2 className="size-4" />{isDryRun ? text.simulate : text.confirm}</Button> : <Button onClick={onClose}>{text.close}</Button>}</div>{!canConfirm && phase !== "submitted" ? <p id="batch-confirmation-reason" className="sr-only">{reason}</p> : null}</AlertDialogPopup></AlertDialogPortal></AlertDialog>
}

function BatchSummary({ preview, items, language, isDryRun, text }: { preview: ManualDeleteBatchPreviewResponse | null; items: BatchSelectionItem[]; language: DeletionLanguage; isDryRun: boolean; text: BatchCopy }) {
  const totals = useMemo(() => items.reduce((value, item) => ({ bytes: item.estimatedBytes == null ? value.bytes : value.bytes + item.estimatedBytes, unknown: value.unknown + Number(item.estimatedBytes == null) }), { bytes: 0, unknown: 0 }), [items])
  const plans = preview?.children.flatMap((child) => child.plan ? [child.plan] : []) ?? []
  const actions = plans.flatMap((plan) => plan.actions)
  const systems = [...new Set(actions.map((action) => localizedSystemLabel(action.system, language)))]
  const torrent = actions.filter((action) => ["downloader", "qbittorrent", "transmission", "deluge", "rtorrent"].includes(action.system.toLowerCase()))
  const removal = torrent.filter((action) => actionGroup(action) === "remove").length
  const retained = torrent.filter((action) => actionGroup(action) === "retain").length
  const blocked = preview?.children.filter((child) => child.status === "blocked") ?? []
  const types = items.reduce<Record<string, number>>((result, item) => ({ ...result, [item.itemType]: (result[item.itemType] ?? 0) + 1 }), {})
  const typeSummary = Object.entries(types).map(([type, count]) => `${count} ${localizedItemType(type, count, language)}`).join(" · ")
  return <div className="space-y-4"><div className="rounded-lg border border-border bg-card p-3"><div className="flex items-start gap-2">{preview?.ready_count ? <ShieldCheck className="mt-0.5 size-4 shrink-0 text-status-success" /> : <ShieldAlert className="mt-0.5 size-4 shrink-0 text-status-warning" />}<div className="min-w-0"><p className="text-sm font-medium">{selectedCountLabel(items.length, language)}</p><p className="text-xs text-muted-foreground">{formatBytes(totals.bytes)}{totals.unknown ? ` · ${text.unknownSize}` : ""}</p></div></div></div>{isDryRun ? <p className="rounded-lg border border-status-warning-border bg-status-warning-bg px-3 py-2 text-sm text-status-warning">{text.dryRun}</p> : null}<SummaryRow label={text.itemTypes} value={typeSummary} /><SummaryRow label={text.systems} value={systems.length ? systems.join(" · ") : "—"} /><SummaryRow label={text.removing} value={String(removal)} /><SummaryRow label={text.retaining} value={String(retained)} /><SummaryRow label={text.attention} value={String(blocked.length)} /><p className="rounded-lg border border-status-warning-border bg-status-warning-bg/50 px-3 py-2 text-sm text-status-warning">{text.continues}</p>{blocked.length ? <section aria-label={text.blocked} className="rounded-lg border border-status-warning-border bg-status-warning-bg/50 p-3"><h3 className="text-sm font-medium">{text.blocked}</h3><ul className="mt-2 space-y-1 text-sm">{blocked.map((child) => <li key={child.mutation_identity}>{child.display_name}</li>)}</ul></section> : null}{preview ? <details className="rounded-lg border border-border bg-muted/20 p-3 text-xs text-muted-foreground"><summary className="cursor-pointer font-medium text-foreground">{text.technical}</summary><div className="mt-3 space-y-2">{preview.children.map((child) => <div key={child.mutation_identity}><span className="font-medium text-foreground">{child.display_name}</span><span> · {child.status === "blocked" ? text.attention : text.ready}</span>{child.plan?.actions.map((action, index) => <Badge key={`${action.system}-${index}`} variant="outline" className="ml-1 text-[10px]">{localizedSystemLabel(action.system, language)}: {localizedActionLabel(action, language)}</Badge>)}</div>)}</div></details> : null}</div>
}
function SummaryRow({ label, value }: { label: string; value: string }) { return <div className="flex justify-between gap-4 rounded-lg border border-border bg-card px-3 py-2 text-sm"><span className="text-muted-foreground">{label}</span><span className="text-right font-medium">{value}</span></div> }
function formatBytes(bytes: number) { if (bytes === 0) return "0 B"; const index = Math.floor(Math.log(bytes) / Math.log(1024)); return `${(bytes / 1024 ** index).toFixed(1)} ${["B", "KB", "MB", "GB", "TB"][index]}` }
function selectedCountLabel(count: number, language: DeletionLanguage) {
  if (language === "en") return `${count} ${count === 1 ? "item" : "items"} selected`
  return `${count} ${russianPlural(count, "элемент", "элемента", "элементов")} ${count === 1 ? "выбран" : "выбрано"}`
}

function localizedItemType(itemType: string, count: number, language: DeletionLanguage) {
  if (language === "en") {
    const names = { Movie: count === 1 ? "movie" : "movies", Series: "series", Season: count === 1 ? "season" : "seasons" }
    return names[itemType as keyof typeof names] ?? (count === 1 ? "item" : "items")
  }
  const names = { Movie: ["фильм", "фильма", "фильмов"], Series: ["сериал", "сериала", "сериалов"], Season: ["сезон", "сезона", "сезонов"] } as const
  const forms: readonly [string, string, string] = names[itemType as keyof typeof names] ?? ["элемент", "элемента", "элементов"]
  return russianPlural(count, forms[0], forms[1], forms[2])
}

function russianPlural(count: number, one: string, few: string, many: string) {
  const mod100 = Math.abs(count) % 100
  const mod10 = mod100 % 10
  if (mod100 >= 11 && mod100 <= 14) return many
  if (mod10 === 1) return one
  if (mod10 >= 2 && mod10 <= 4) return few
  return many
}
