import { Tooltip as TooltipPrimitive } from "@base-ui/react/tooltip"
import { AnimatePresence, motion } from "motion/react"
import { createContext, useContext, useState } from "react"

import { cn } from "@/lib/utils"
import { useReducedMotionPreference } from "@/hooks/use-reduced-motion-preference"

const TooltipOpenContext = createContext(false)

function TooltipProvider({ delay = 150, ...props }: TooltipPrimitive.Provider.Props) {
  return <TooltipPrimitive.Provider data-slot="tooltip-provider" delay={delay} {...props} />
}

function Tooltip({ open: controlledOpen, defaultOpen, onOpenChange, ...props }: TooltipPrimitive.Root.Props) {
  const [uncontrolledOpen, setUncontrolledOpen] = useState(defaultOpen ?? false)
  const open = controlledOpen ?? uncontrolledOpen

  return (
    <TooltipOpenContext.Provider value={open}>
      <TooltipPrimitive.Root
        data-slot="tooltip"
        open={open}
        onOpenChange={(nextOpen, eventDetails) => {
          if (controlledOpen === undefined) setUncontrolledOpen(nextOpen)
          onOpenChange?.(nextOpen, eventDetails)
        }}
        {...props}
      />
    </TooltipOpenContext.Provider>
  )
}

function TooltipTrigger(props: TooltipPrimitive.Trigger.Props) {
  return <TooltipPrimitive.Trigger data-slot="tooltip-trigger" {...props} />
}

function TooltipContent({
  className,
  side = "top",
  sideOffset = 8,
  align = "center",
  alignOffset = 0,
  children,
  ...props
}: Omit<TooltipPrimitive.Popup.Props, "render"> & Pick<TooltipPrimitive.Positioner.Props, "align" | "alignOffset" | "side" | "sideOffset">) {
  const open = useContext(TooltipOpenContext)
  const reducedMotion = useReducedMotionPreference()

  return (
    <AnimatePresence>
      {open ? (
        <TooltipPrimitive.Portal keepMounted>
          <TooltipPrimitive.Positioner side={side} sideOffset={sideOffset} align={align} alignOffset={alignOffset} className="isolate z-[80]">
            <TooltipPrimitive.Popup
              data-slot="tooltip-content"
              className={cn(
                "max-w-64 origin-(--transform-origin) rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground shadow-lg text-balance",
                className,
              )}
              render={<motion.div initial={reducedMotion ? false : { opacity: 0, scale: 0.55 }} animate={{ opacity: 1, scale: 1 }} exit={reducedMotion ? { opacity: 0 } : { opacity: 0, scale: 0.55 }} transition={reducedMotion ? { duration: 0 } : { type: "spring", stiffness: 300, damping: 25 }} />}
              {...props}
            >
              {children}
              <TooltipPrimitive.Arrow className="size-2.5 rotate-45 rounded-[2px] bg-primary fill-primary" />
            </TooltipPrimitive.Popup>
          </TooltipPrimitive.Positioner>
        </TooltipPrimitive.Portal>
      ) : null}
    </AnimatePresence>
  )
}

export { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger }
