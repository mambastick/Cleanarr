import { X } from "lucide-react"
import { useEffect, type ReactNode, type RefObject } from "react"

import { Button } from "@/components/ui/button"
import { Dialog, DialogBackdrop, DialogClose, DialogDescription, DialogPopup, DialogPortal, DialogTitle } from "@/components/ui/dialog"
import { cn } from "@/lib/utils"

export function Modal({
  title,
  description,
  children,
  open,
  onClose,
  footer,
  className,
  closeLabel,
  returnFocusRef,
}: {
  title: string
  description?: string
  children: ReactNode
  open: boolean
  onClose: () => void
  footer?: ReactNode
  className?: string
  closeLabel: string
  returnFocusRef?: RefObject<HTMLElement | null>
}) {
  useEffect(() => {
    if (!open) return
    const returnFocusTarget = returnFocusRef?.current
    return () => returnFocusTarget?.focus()
  }, [open, returnFocusRef])

  return (
    <Dialog open={open} onOpenChange={(nextOpen) => { if (!nextOpen) onClose() }}>
      <DialogPortal>
        <DialogBackdrop data-testid="modal-backdrop" className="fixed inset-0 z-50 bg-black/50" />
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <DialogPopup finalFocus={returnFocusRef} className={cn("flex max-h-[calc(100dvh-2rem)] min-h-0 w-full max-w-2xl flex-col overflow-hidden rounded-2xl border bg-background shadow-2xl outline-none", className)}>
            <div className="flex items-start justify-between gap-4 border-b px-6 py-5">
              <div className="space-y-1">
                <DialogTitle className="text-xl font-semibold tracking-tight">{title}</DialogTitle>
                {description ? <DialogDescription className="text-sm text-muted-foreground">{description}</DialogDescription> : null}
              </div>
              <DialogClose render={<Button autoFocus type="button" variant="ghost" size="icon-sm" aria-label={closeLabel} title={closeLabel} />}><X /></DialogClose>
            </div>
            <div role="region" aria-label={title} tabIndex={0} className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-6 py-5 outline-none focus-visible:ring-3 focus-visible:ring-inset focus-visible:ring-ring/50">{children}</div>
            {footer ? <div className="shrink-0 border-t bg-background px-6 py-4">{footer}</div> : null}
          </DialogPopup>
        </div>
      </DialogPortal>
    </Dialog>
  )
}
