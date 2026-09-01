import { Activity, Download, LayoutDashboard, Library, LogOut, Settings2, UserRound } from "lucide-react"
import { motion, useReducedMotion } from "motion/react"

import { ThemeToggle } from "@/components/theme-toggle"
import { Button } from "@/components/ui/button"
import { TabsList, TabsTrigger } from "@/components/ui/tabs"

type AppNavigationProps = {
  labels: { dashboard: string; settings: string; activity: string; library: string; downloads: string; downloadsActive: string; live: string; dryRun: string; logOut: string; navigation: string }
  live: boolean
  username: string | null
  showRuntime: boolean
  downloadsActiveCount?: number | null
  onLogout: () => void
}

export function AppNavigation({ labels, live, username, showRuntime, downloadsActiveCount, onLogout }: AppNavigationProps) {
  const reducedMotion = useReducedMotion()
  const feedback = reducedMotion ? {} : { whileHover: { scale: 1.12 }, whileTap: { scale: 0.94 }, transition: { duration: 0.18 } }
  return <header className="sticky top-0 z-50 border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
    <div className="mx-auto flex max-w-6xl items-center gap-3 overflow-hidden px-4 py-2.5 sm:px-6">
      <div className="flex shrink-0 items-center gap-2"><svg width="18" height="18" viewBox="0 0 48 48" fill="none" aria-hidden><path d="M28,6 L8,28 L24,28 L22,42 L40,20 L24,20 Z" fill="currentColor" className="text-primary" /></svg><span className="hidden text-base sm:inline"><span className="font-light">Clean</span><span className="font-bold text-primary">Arr</span></span></div>
      <div className="h-5 w-px bg-border" />
      <TabsList aria-label={labels.navigation} className="min-w-0 max-w-[calc(100vw-8.5rem)] shrink-0 overflow-x-auto overflow-y-hidden [scrollbar-width:none] [&::-webkit-scrollbar]:hidden sm:max-w-none sm:overflow-visible"><TabsTrigger value="dashboard" aria-label={labels.dashboard}><motion.span aria-hidden tabIndex={-1} {...feedback}><LayoutDashboard /></motion.span><span className="hidden sm:inline">{labels.dashboard}</span></TabsTrigger><TabsTrigger value="settings" aria-label={labels.settings}><motion.span aria-hidden tabIndex={-1} {...feedback}><Settings2 /></motion.span><span className="hidden sm:inline">{labels.settings}</span></TabsTrigger><TabsTrigger value="activity" aria-label={labels.activity}><motion.span aria-hidden tabIndex={-1} {...feedback}><Activity /></motion.span><span className="hidden sm:inline">{labels.activity}</span></TabsTrigger><TabsTrigger value="library" aria-label={labels.library}><motion.span aria-hidden tabIndex={-1} {...feedback}><Library /></motion.span><span className="hidden sm:inline">{labels.library}</span></TabsTrigger><TabsTrigger value="downloads" aria-label={downloadsActiveCount != null ? `${labels.downloads}: ${downloadsActiveCount} ${labels.downloadsActive}` : labels.downloads}><motion.span aria-hidden tabIndex={-1} {...feedback}><Download /></motion.span><span className="hidden sm:inline">{labels.downloads}</span>{downloadsActiveCount != null ? <span aria-hidden className="rounded-full bg-primary/15 px-1.5 text-xs text-primary">{downloadsActiveCount}</span> : null}</TabsTrigger></TabsList>
      <div className="ml-auto flex shrink-0 items-center gap-1 sm:gap-2">
        {showRuntime && <div className={live ? "hidden items-center gap-1.5 rounded-full border border-status-success-border bg-status-success-bg px-2.5 py-1 text-xs font-medium text-status-success lg:flex" : "hidden items-center gap-1.5 rounded-full border border-status-warning-border bg-status-warning-bg px-2.5 py-1 text-xs font-medium text-status-warning lg:flex"}><span className={live ? "size-1.5 rounded-full bg-status-success" : "size-1.5 rounded-full bg-status-warning"} />{live ? labels.live : labels.dryRun}</div>}
        <ThemeToggle />
        <div className="hidden items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs text-muted-foreground md:flex"><UserRound className="size-3.5" />{username}</div>
        <Button variant="ghost" size="icon" className="size-8" onClick={onLogout} title={labels.logOut} aria-label={labels.logOut}><LogOut className="size-4 text-status-danger" /></Button>
      </div>
    </div>
  </header>
}
