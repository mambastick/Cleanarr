import { Tabs as TabsPrimitive } from "@base-ui/react/tabs"
import { cva, type VariantProps } from "class-variance-authority"
import { motion, useReducedMotion } from "motion/react"
import { createContext, useContext, useEffect, useId, useState } from "react"

import { cn } from "@/lib/utils"

const TabsScopeContext = createContext("tabs")

function useReducedMotionPreference() {
  const motionPreference = useReducedMotion()
  const [mediaPreference, setMediaPreference] = useState(() => typeof window !== "undefined" && typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches)
  useEffect(() => {
    if (typeof window.matchMedia !== "function") return
    const media = window.matchMedia("(prefers-reduced-motion: reduce)")
    const update = () => setMediaPreference(media.matches)
    update()
    media.addEventListener("change", update)
    return () => media.removeEventListener("change", update)
  }, [])
  return Boolean(motionPreference || mediaPreference)
}

function Tabs({
  className,
  orientation = "horizontal",
  ...props
}: TabsPrimitive.Root.Props) {
  const scope = useId()
  return (
    <TabsScopeContext.Provider value={scope}><TabsPrimitive.Root
      data-slot="tabs"
      data-tabs-scope={scope}
      data-orientation={orientation}
      className={cn(
        "group/tabs flex gap-2 data-horizontal:flex-col",
        className
      )}
      {...props}
    /></TabsScopeContext.Provider>
  )
}

const tabsListVariants = cva(
  "group/tabs-list inline-flex w-fit items-center justify-center rounded-lg p-[3px] text-muted-foreground group-data-horizontal/tabs:h-11 group-data-vertical/tabs:h-fit group-data-vertical/tabs:flex-col data-[variant=line]:rounded-none",
  {
    variants: {
      variant: {
        default: "bg-muted",
        line: "gap-1 bg-transparent",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
)

function TabsList({
  className,
  variant = "default",
  children,
  ...props
}: TabsPrimitive.List.Props & VariantProps<typeof tabsListVariants>) {
  const scope = useContext(TabsScopeContext)
  const reducedMotion = useReducedMotionPreference()
  return (
    <TabsPrimitive.List
      data-slot="tabs-list"
      data-variant={variant}
      className={cn("relative isolate overflow-visible", tabsListVariants({ variant }), className)}
      {...props}
    >
      {children}
      <TabsPrimitive.Indicator
        className="pointer-events-none absolute inset-0 z-0"
        aria-hidden="true"
        render={(indicatorProps, state) => (
          <span {...indicatorProps}>
            <motion.span
              className="absolute left-0 top-0 rounded-md border border-border bg-background shadow-sm"
              data-indicator-id={`cleanarr-tab-indicator-${scope}`}
              data-slot="tabs-highlight"
              initial={false}
              animate={state.activeTabPosition && state.activeTabSize ? {
                x: state.activeTabPosition.left,
                y: state.activeTabPosition.top,
                width: state.activeTabSize.width,
                height: state.activeTabSize.height,
                opacity: 1,
              } : { opacity: 0 }}
              transition={reducedMotion ? { duration: 0 } : { type: "spring", stiffness: 200, damping: 25 }}
            />
          </span>
        )}
      />
    </TabsPrimitive.List>
  )
}

function TabsTrigger({ className, children, ...props }: TabsPrimitive.Tab.Props) {
  return (
    <TabsPrimitive.Tab
      data-slot="tabs-trigger"
      className={cn(
        "relative z-[1] inline-flex h-[calc(100%-1px)] flex-1 items-center justify-center gap-1.5 rounded-md border border-transparent px-2 py-1 text-sm font-medium whitespace-nowrap text-muted-foreground transition-colors duration-200 group-data-vertical/tabs:w-full group-data-vertical/tabs:justify-start hover:text-foreground focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-1 focus-visible:outline-ring disabled:pointer-events-none disabled:opacity-50 aria-disabled:pointer-events-none aria-disabled:opacity-50 data-active:text-foreground [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
        className
      )}
      {...props}
    >
      {children}
    </TabsPrimitive.Tab>
  )
}

function TabsContent({ className, children, ...props }: TabsPrimitive.Panel.Props) {
  const reducedMotion = useReducedMotionPreference()
  return (
    <TabsPrimitive.Panel
      data-slot="tabs-content"
      data-reduced-motion={reducedMotion ? "true" : "false"}
      className={cn("flex-1 text-sm outline-none", className)}
      {...props}
    >
      <motion.div initial={reducedMotion ? false : { opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={reducedMotion ? { duration: 0 } : { duration: 0.2, ease: "easeOut" }}>
        {children}
      </motion.div>
    </TabsPrimitive.Panel>
  )
}

export { Tabs, TabsList, TabsTrigger, TabsContent, tabsListVariants }
