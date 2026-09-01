import { X } from "lucide-react"
import { useEffect, type ReactNode, type RefObject } from "react"

import { Button } from "@/components/ui/button"
import { Dialog, DialogBackdrop, DialogClose, DialogDescription, DialogPopup, DialogPortal, DialogTitle } from "@/components/ui/dialog"
import { ScrollArea } from "@/components/ui/scroll-area"
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
          <DialogPopup finalFocus={returnFocusRef} className={cn("flex max-h-[calc(100dvh-2rem)] w-full max-w-2xl flex-col rounded-2xl border bg-background shadow-2xl outline-none", className)}>
            <div className="flex items-start justify-between gap-4 border-b px-6 py-5">
              <div className="space-y-1">
                <DialogTitle className="text-xl font-semibold tracking-tight">{title}</DialogTitle>
                {description ? <DialogDescription className="text-sm text-muted-foreground">{description}</DialogDescription> : null}
              </div>
              <DialogClose render={<Button autoFocus variant="ghost" size="icon-sm" aria-label={closeLabel} />}>
                <X />
              </DialogClose>
            </div>
            <ScrollArea className="min-h-0 flex-1" viewportClassName="h-full px-6 py-5">{children}</ScrollArea>
            {footer ? <div className="border-t px-6 py-4">{footer}</div> : null}
          </DialogPopup>
        </div>
      </DialogPortal>
    </Dialog>
  )
}
