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
  ...props
}: TabsPrimitive.List.Props & VariantProps<typeof tabsListVariants>) {
  return (
    <TabsPrimitive.List
      data-slot="tabs-list"
      data-variant={variant}
      className={cn(tabsListVariants({ variant }), className)}
      {...props}
    />
  )
}

function TabsTrigger({ className, children, ...props }: TabsPrimitive.Tab.Props) {
  const scope = useContext(TabsScopeContext)
  const reducedMotion = useReducedMotionPreference()
  return (
    <TabsPrimitive.Tab
      data-slot="tabs-trigger"
      className={cn(
        "group/tab relative inline-flex h-[calc(100%-1px)] flex-1 items-center justify-center gap-1.5 rounded-md border border-transparent px-1.5 py-0.5 text-sm font-medium whitespace-nowrap text-muted-foreground transition-all group-data-vertical/tabs:w-full group-data-vertical/tabs:justify-start hover:text-foreground focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-1 focus-visible:outline-ring disabled:pointer-events-none disabled:opacity-50 aria-disabled:pointer-events-none aria-disabled:opacity-50 dark:hover:text-foreground group-data-[variant=default]/tabs-list:data-active:shadow-sm group-data-[variant=line]/tabs-list:data-active:shadow-none [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
        "group-data-[variant=line]/tabs-list:bg-transparent group-data-[variant=line]/tabs-list:data-active:bg-transparent dark:group-data-[variant=line]/tabs-list:data-active:border-transparent dark:group-data-[variant=line]/tabs-list:data-active:bg-transparent",
        "data-active:bg-background data-active:text-foreground dark:data-active:border-input dark:data-active:bg-input/30 dark:data-active:text-foreground",
        "after:absolute after:bg-foreground after:opacity-0 after:transition-opacity group-data-horizontal/tabs:after:inset-x-0 group-data-horizontal/tabs:after:bottom-[-5px] group-data-horizontal/tabs:after:h-0.5 group-data-vertical/tabs:after:inset-y-0 group-data-vertical/tabs:after:-right-1 group-data-vertical/tabs:after:w-0.5 group-data-[variant=line]/tabs-list:data-active:after:opacity-100",
        className
      )}
      {...props}
    >
      {children}
      <motion.span aria-hidden data-indicator-id={`cleanarr-tab-indicator-${scope}`} className="pointer-events-none absolute inset-x-1 bottom-0 hidden h-0.5 rounded-full bg-primary group-data-[active]/tab:block" layoutId={`cleanarr-tab-indicator-${scope}`} transition={reducedMotion ? { duration: 0 } : { type: "spring", stiffness: 500, damping: 38 }} />
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
