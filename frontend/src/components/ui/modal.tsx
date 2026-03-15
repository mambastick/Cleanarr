import { X } from "lucide-react"
import type { ReactNode } from "react"

import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

export function Modal({
  title,
  description,
  children,
  open,
  onClose,
  footer,
  className,
}: {
  title: string
  description?: string
  children: ReactNode
  open: boolean
  onClose: () => void
  footer?: ReactNode
  className?: string
}) {
  if (!open) {
    return null
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={onClose}
      role="presentation"
    >
      <div
        className={cn(
          "w-full max-w-2xl rounded-2xl border bg-background shadow-2xl",
          className,
        )}
        onClick={(event) => {
          event.stopPropagation()
        }}
        role="dialog"
        aria-modal="true"
        aria-label={title}
      >
        <div className="flex items-start justify-between gap-4 border-b px-6 py-5">
          <div className="space-y-1">
            <h2 className="text-xl font-semibold tracking-tight">{title}</h2>
            {description ? (
              <p className="text-sm text-muted-foreground">{description}</p>
            ) : null}
          </div>
          <Button variant="ghost" size="icon-sm" onClick={onClose}>
            <X className="size-4" />
          </Button>
        </div>
        <div className="max-h-[70vh] overflow-y-auto px-6 py-5">{children}</div>
        {footer ? <div className="border-t px-6 py-4">{footer}</div> : null}
      </div>
    </div>
  )
}
