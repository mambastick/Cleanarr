import { motion, type Variants } from "motion/react"
import { cloneElement, createContext, useContext, useState, type FocusEvent, type MouseEvent, type PointerEvent, type ReactElement, type ReactNode } from "react"

import { useReducedMotionPreference } from "@/hooks/use-reduced-motion-preference"
import { cn } from "@/lib/utils"

export type IconAnimation = "bounce" | "lift" | "pulse" | "rotate" | "wiggle"

const animations: Record<IconAnimation, Variants> = {
  bounce: { rest: { y: 0 }, active: { y: [0, -3, 0] } },
  lift: { rest: { scale: 1, y: 0 }, active: { scale: 1.08, y: -2 } },
  pulse: { rest: { scale: 1 }, active: { scale: [1, 1.14, 1] } },
  rotate: { rest: { rotate: 0 }, active: { rotate: 180 } },
  wiggle: { rest: { rotate: 0 }, active: { rotate: [0, -12, 12, 0] } },
}

const AnimatedIconContext = createContext(false)

type InteractiveProps = {
  onBlur?: (event: FocusEvent<HTMLElement>) => void
  onFocus?: (event: FocusEvent<HTMLElement>) => void
  onMouseEnter?: (event: MouseEvent<HTMLElement>) => void
  onMouseLeave?: (event: MouseEvent<HTMLElement>) => void
  onPointerDown?: (event: PointerEvent<HTMLElement>) => void
  onPointerUp?: (event: PointerEvent<HTMLElement>) => void
}

function compose<Event>(original: ((event: Event) => void) | undefined, update: (event: Event) => void) {
  return (event: Event) => {
    original?.(event)
    update(event)
  }
}

/** Animate UI-inspired trigger that lets a whole action drive its icon. */
export function AnimateIcon({ children }: { children: ReactElement<InteractiveProps> }) {
  const [hovered, setHovered] = useState(false)
  const [focused, setFocused] = useState(false)
  const [pressed, setPressed] = useState(false)
  const reducedMotion = useReducedMotionPreference()
  const original = children.props
  const active = !reducedMotion && (hovered || focused || pressed)

  return (
    <AnimatedIconContext.Provider value={active}>
      {cloneElement(children, {
        onBlur: compose(original.onBlur, () => setFocused(false)),
        onFocus: compose(original.onFocus, () => setFocused(true)),
        onMouseEnter: compose(original.onMouseEnter, () => setHovered(true)),
        onMouseLeave: compose(original.onMouseLeave, () => { setHovered(false); setPressed(false) }),
        onPointerDown: compose(original.onPointerDown, () => setPressed(true)),
        onPointerUp: compose(original.onPointerUp, () => setPressed(false)),
      })}
    </AnimatedIconContext.Provider>
  )
}

export function AnimatedIcon({ animation = "lift", children, className }: { animation?: IconAnimation; children: ReactNode; className?: string }) {
  const active = useContext(AnimatedIconContext)
  return (
    <motion.span
      aria-hidden="true"
      className={cn("inline-flex shrink-0 items-center justify-center", className)}
      data-animation={animation}
      data-animation-state={active ? "active" : "rest"}
      data-slot="animated-icon"
      initial="rest"
      animate={active ? "active" : "rest"}
      variants={animations[animation]}
      transition={{ duration: 0.2, ease: "easeOut" }}
    >
      {children}
    </motion.span>
  )
}
