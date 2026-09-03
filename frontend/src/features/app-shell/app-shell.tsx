import {
  Activity,
  BookOpen,
  Download,
  HardDrive,
  Home,
  Languages,
  LibraryBig,
  LogOut,
  Menu,
  MoreHorizontal,
  Plug,
  ShieldCheck,
  SlidersHorizontal,
  Settings,
  Star,
  Trash2,
  Users,
  X,
  Zap,
  type LucideIcon,
} from "lucide-react"
import { Laptop as LaptopData, Moon as MoonData, Sun as SunData } from "lucide"
import { MorphIcon } from "morphicons/react"
import { LayoutGroup, motion } from "motion/react"
import { useEffect, useRef, useState, type ReactNode } from "react"

import { AnimateIcon, AnimatedIcon, type IconAnimation } from "@/components/animate-ui/animated-icon"
import type { ThemeMode } from "@/components/theme-provider"
import { Button } from "@/components/ui/button"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import {
  Sheet,
  SheetBackdrop,
  SheetClose,
  SheetContent,
  SheetDescription,
  SheetPortal,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet"
import { cn } from "@/lib/utils"

export type AppShellPage = "overview" | "library" | "downloads" | "activity" | "users" | "settings"
export type ShellLanguage = "en" | "ru"
export type SettingsSection = "cleanarr" | "library" | "security" | "cleanup" | "services"
export type StorageHealth = "healthy" | "warning" | "critical" | "unknown"

export type StorageHeadline = {
  status: StorageHealth
  headline: string
  detail?: string
  percent?: number
  partial?: boolean
  freshness?: string | null
}

export type AppShellLabels = {
  logo: string
  navigation: string
  more: string
  close: string
  status: string
  live: string
  dryRun: string
  storage: string
  storageUsed: string
  storagePartial: string
  storageUnavailable: string
  account: string
  settings: string
  settingsCleanarr: string
  settingsLibrary: string
  settingsSecurity: string
  settingsCleanup: string
  settingsServices: string
  collapseSidebar: string
  expandSidebar: string
  theme: string
  themeLight: string
  themeDark: string
  themeSystem: string
  language: string
  logOut: string
  githubStars: string
  nav: Record<AppShellPage, string>
  storageStatus: Record<StorageHealth, string>
}

const DEFAULT_LABELS: AppShellLabels = {
  logo: "CleanArr",
  navigation: "Main navigation",
  more: "More",
  close: "Close",
  status: "Runtime status",
  live: "Live",
  dryRun: "Dry-run",
  storage: "Storage",
  storageUsed: "Used",
  storagePartial: "Partial data",
  storageUnavailable: "Storage unavailable",
  account: "Account",
  settings: "Settings",
  settingsCleanarr: "CleanArr",
  settingsLibrary: "Media library",
  settingsSecurity: "Security",
  settingsCleanup: "Cleanup",
  settingsServices: "Connected services",
  collapseSidebar: "Collapse sidebar",
  expandSidebar: "Expand sidebar",
  theme: "Theme",
  themeLight: "Light",
  themeDark: "Dark",
  themeSystem: "System",
  language: "Language",
  logOut: "Log out",
  githubStars: "15 stars",
  nav: {
    overview: "Overview",
    library: "Library",
    downloads: "Downloads",
    activity: "Activity",
    users: "Users",
    settings: "Settings",
  },
  storageStatus: {
    healthy: "Healthy",
    warning: "Limited space",
    critical: "Low space",
    unknown: "Unknown",
  },
}

type AppShellProps = {
  activePage: AppShellPage
  onPageChange?: (page: AppShellPage) => void
  onNavigate?: (page: AppShellPage) => void
  settingsSection?: SettingsSection
  onSettingsSectionChange?: (section: SettingsSection) => void
  username?: string | null
  canAdmin?: boolean
  theme?: ThemeMode
  onThemeChange?: (theme: ThemeMode) => void
  language?: ShellLanguage
  onLanguageChange?: (language: ShellLanguage) => void
  onLogout?: () => void
  dryRun: boolean
  storageHeadline?: StorageHeadline
  /** Alias kept intentionally concise for shell consumers. */
  storage?: StorageHeadline
  jobsSlot?: ReactNode
  jobs?: ReactNode
  jobsCount?: number | null
  labels?: Partial<Omit<AppShellLabels, "nav" | "storageStatus">> & {
    nav?: Partial<Record<AppShellPage, string>>
    storageStatus?: Partial<Record<StorageHealth, string>>
  }
  children?: ReactNode
}

type NavItem = { page: AppShellPage; icon: LucideIcon }

const NAV_ICON_ANIMATION: Record<AppShellPage, IconAnimation> = {
  overview: "pulse",
  library: "lift",
  downloads: "bounce",
  activity: "pulse",
  users: "lift",
  settings: "wiggle",
}

const NAV_ITEMS: NavItem[] = [
  { page: "overview", icon: Home },
  { page: "library", icon: BookOpen },
  { page: "downloads", icon: Download },
  { page: "activity", icon: Activity },
  { page: "users", icon: Users },
  { page: "settings", icon: Settings },
]

const MOBILE_ITEMS: NavItem[] = NAV_ITEMS.filter(({ page }) => page !== "settings" && page !== "users")

function mergeLabels(labels?: AppShellProps["labels"]): AppShellLabels {
  return {
    ...DEFAULT_LABELS,
    ...labels,
    nav: { ...DEFAULT_LABELS.nav, ...labels?.nav },
    storageStatus: { ...DEFAULT_LABELS.storageStatus, ...labels?.storageStatus },
  }
}

function Brand({ labels, collapsed, onToggle }: { labels: AppShellLabels; collapsed?: boolean; onToggle?: () => void }) {
  return (
    <AnimateIcon><div className="app-shell__brand" aria-label={labels.logo}>
      <AnimatedIcon animation="wiggle"><Zap className="app-shell__brand-mark" /></AnimatedIcon>
      <span className="app-shell__brand-name"><span>Clean</span><strong>Arr</strong></span>
      {onToggle ? <Tooltip><TooltipTrigger render={<button type="button" className="app-shell__collapse" onClick={onToggle} aria-label={collapsed ? labels.expandSidebar : labels.collapseSidebar}><Menu /></button>} /><TooltipContent side="right">{collapsed ? labels.expandSidebar : labels.collapseSidebar}</TooltipContent></Tooltip> : null}
      {!onToggle ? <AnimateIcon><a
          className="app-shell__brand-github"
          href="https://github.com/mambastick/Cleanarr"
          target="_blank"
          rel="noreferrer noopener"
          aria-label={`GitHub: ${labels.githubStars}`}
          title={`GitHub: ${labels.githubStars}`}
        >
          <AnimatedIcon animation="pulse"><Star /></AnimatedIcon>
          <span>15</span>
        </a></AnimateIcon> : null}
    </div></AnimateIcon>
  )
}

function RuntimeStatus({ dryRun, labels }: { dryRun: boolean; labels: AppShellLabels }) {
  return (
    <div className={cn("app-shell__runtime-status", dryRun ? "app-shell__runtime-status--dry" : "app-shell__runtime-status--live")} aria-label={`${labels.status}: ${dryRun ? labels.dryRun : labels.live}`}>
      <span className="app-shell__status-dot" aria-hidden="true" />
      <span>{dryRun ? labels.dryRun : labels.live}</span>
    </div>
  )
}

function StorageCard({ storage, labels }: { storage: StorageHeadline; labels: AppShellLabels }) {
  const percent = storage.percent == null ? null : Math.max(0, Math.min(100, storage.percent))
  return (
    <section className={cn("app-shell__storage", `app-shell__storage--${storage.status}`)} aria-label={labels.storage}>
      <div className="app-shell__storage-heading">
        <HardDrive aria-hidden="true" />
        <span>{labels.storage}</span>
        <span className="app-shell__storage-state">{labels.storageStatus[storage.status]}</span>
      </div>
      <p className="app-shell__storage-headline">{storage.headline}</p>
      {storage.detail ? <p className="app-shell__storage-detail">{storage.detail}</p> : null}
      {percent != null ? <div className="app-shell__storage-meter" role="progressbar" aria-valuenow={percent} aria-valuemin={0} aria-valuemax={100} aria-label={`${labels.storageUsed}: ${percent}%`}><span style={{ transform: `scaleX(${percent / 100})` }} /></div> : null}
      {storage.partial || storage.freshness ? <p className="app-shell__storage-meta">{storage.partial ? labels.storagePartial : null}{storage.partial && storage.freshness ? " · " : null}{storage.freshness}</p> : null}
    </section>
  )
}

function NavigationItems({ items, activePage, labels, onNavigate, mobile = false, collapsed = false }: { items: NavItem[]; activePage: AppShellPage; labels: AppShellLabels; onNavigate: (page: AppShellPage) => void; mobile?: boolean; collapsed?: boolean }) {
  return (
    <div className={cn("app-shell__nav-list", mobile && "app-shell__nav-list--mobile")}>
      {items.map(({ page, icon: Icon }) => {
        const active = activePage === page
        return (
          <Tooltip key={page}>
            <AnimateIcon><TooltipTrigger render={<button type="button" className={cn("app-shell__nav-item", active && "app-shell__nav-item--active")} aria-current={active ? "page" : undefined} aria-label={labels.nav[page]} onClick={() => onNavigate(page)}>
              {active ? <motion.span layoutId={mobile ? "mobile-active-navigation" : "sidebar-active-navigation"} initial={false} transition={{ type: "spring", stiffness: 310, damping: 30 }} className="app-shell__nav-active-indicator" /> : null}
              <AnimatedIcon animation={NAV_ICON_ANIMATION[page]}><Icon /></AnimatedIcon>
              <span>{labels.nav[page]}</span>
            </button>} /></AnimateIcon>
            {collapsed && !mobile ? <TooltipContent side="right">{labels.nav[page]}</TooltipContent> : null}
          </Tooltip>
        )
      })}
    </div>
  )
}

const SETTINGS_ITEMS: Array<{ section: SettingsSection; label: keyof Pick<AppShellLabels, "settingsCleanarr" | "settingsLibrary" | "settingsSecurity" | "settingsCleanup" | "settingsServices">; icon: LucideIcon; animation: IconAnimation }> = [
  { section: "cleanarr", label: "settingsCleanarr", icon: SlidersHorizontal, animation: "rotate" },
  { section: "library", label: "settingsLibrary", icon: LibraryBig, animation: "lift" },
  { section: "security", label: "settingsSecurity", icon: ShieldCheck, animation: "pulse" },
  { section: "cleanup", label: "settingsCleanup", icon: Trash2, animation: "wiggle" },
  { section: "services", label: "settingsServices", icon: Plug, animation: "bounce" },
]

function SettingsNavigation({ activePage, settingsSection = "cleanarr", labels, onNavigate, onSettingsSectionChange, collapsed = false }: { activePage: AppShellPage; settingsSection?: SettingsSection; labels: AppShellLabels; onNavigate: (page: AppShellPage) => void; onSettingsSectionChange?: (section: SettingsSection) => void; collapsed?: boolean }) {
  const expanded = activePage === "settings"
  const selectSection = (section: SettingsSection) => {
    onSettingsSectionChange?.(section)
    onNavigate("settings")
  }

  return (
    <div className="app-shell__settings-group">
      <Tooltip><AnimateIcon><TooltipTrigger render={<button
          type="button"
          className={cn("app-shell__nav-item", expanded && "app-shell__nav-item--active")}
          aria-current={expanded ? "page" : undefined}
          aria-expanded={expanded && !collapsed}
          aria-controls={expanded && !collapsed ? "app-shell-settings-sections" : undefined}
          aria-label={labels.nav.settings}
          onClick={() => selectSection(settingsSection)}
        >
          {expanded ? <motion.span layoutId="sidebar-active-navigation" initial={false} transition={{ type: "spring", stiffness: 310, damping: 30 }} className="app-shell__nav-active-indicator" /> : null}
          <AnimatedIcon animation="wiggle"><Settings /></AnimatedIcon>
          <span>{labels.nav.settings}</span>
        </button>} /></AnimateIcon>{collapsed ? <TooltipContent side="right">{labels.nav.settings}</TooltipContent> : null}</Tooltip>
      {expanded ? (
        <div id="app-shell-settings-sections" className="app-shell__settings-sections" role="group" aria-label={labels.settings}>
          {SETTINGS_ITEMS.map(({ section, label, icon: Icon, animation }) => <Tooltip key={section}><AnimateIcon><TooltipTrigger render={<button
              type="button"
              className={cn("app-shell__settings-section", settingsSection === section && "app-shell__settings-section--active")}
              aria-current={settingsSection === section ? "page" : undefined}
              aria-label={labels[label]}
              onClick={() => selectSection(section)}
            >
              <AnimatedIcon animation={animation}><Icon /></AnimatedIcon>
              <span>{labels[label]}</span>
            </button>} /></AnimateIcon>{collapsed ? <TooltipContent side="right">{labels[label]}</TooltipContent> : null}</Tooltip>)}
        </div>
      ) : null}
    </div>
  )
}

function MorePanel({ labels, storageHeadline, username, theme, language, onThemeChange, onLanguageChange, onLogout, onNavigate, settingsSection = "cleanarr", onSettingsSectionChange, triggerRef, activePage, canAdmin = true, desktop = false }: { labels: AppShellLabels; storageHeadline: StorageHeadline; username: string | null | undefined; theme?: ThemeMode; language?: ShellLanguage; onThemeChange?: (theme: ThemeMode) => void; onLanguageChange?: (language: ShellLanguage) => void; onLogout?: () => void; onNavigate: (page: AppShellPage) => void; settingsSection?: SettingsSection; onSettingsSectionChange?: (section: SettingsSection) => void; triggerRef: React.RefObject<HTMLButtonElement | null>; activePage: AppShellPage; canAdmin?: boolean; desktop?: boolean }) {
  const [open, setOpen] = useState(false)
  const currentTheme = theme ?? "system"
  const currentLanguage = language ?? "en"
  const moreActive = activePage === "users" || activePage === "settings"
  const nextTheme: ThemeMode = currentTheme === "light" ? "dark" : currentTheme === "dark" ? "system" : "light"
  const themeIcon = currentTheme === "dark" ? MoonData : currentTheme === "light" ? SunData : LaptopData
  const themeLabel = currentTheme === "dark" ? labels.themeDark : currentTheme === "light" ? labels.themeLight : labels.themeSystem
  const setPanelOpen = (nextOpen: boolean) => {
    setOpen(nextOpen)
    if (!nextOpen) window.setTimeout(() => triggerRef.current?.focus(), 0)
  }
  return (
    <Sheet open={open} onOpenChange={setPanelOpen}>
      {desktop ? (
        <SheetTrigger render={<button ref={triggerRef} type="button" className="app-shell__account" aria-label={`${labels.account}: ${username || labels.account}`} />}>
          <span className="app-shell__account-avatar" aria-hidden="true">{(username?.trim().charAt(0) || "A").toUpperCase()}</span>
          <span className="app-shell__account-name">{username || labels.account}</span>
        </SheetTrigger>
      ) : (
        <SheetTrigger render={<Button ref={triggerRef} type="button" variant="ghost" className={cn("app-shell__more-trigger", moreActive && "app-shell__more-trigger--active")} aria-current={moreActive ? "page" : undefined} aria-label={labels.more} />}>
          {moreActive ? <motion.span layoutId="mobile-active-navigation" initial={false} transition={{ type: "spring", stiffness: 310, damping: 30 }} className="app-shell__nav-active-indicator" /> : null}
          <MoreHorizontal aria-hidden="true" />
          <span>{labels.more}</span>
        </SheetTrigger>
      )}
      <SheetPortal>
        <SheetBackdrop className="app-shell__sheet-backdrop" />
        <SheetContent finalFocus={triggerRef} className={cn("app-shell__sheet-content", desktop && "app-shell__sheet-content--desktop")}>
          {desktop ? (
            <>
              <SheetTitle className="sr-only">{labels.account}</SheetTitle>
              <SheetDescription className="sr-only">{labels.navigation}</SheetDescription>
            </>
          ) : (
            <div className="app-shell__sheet-header">
              <div>
                <SheetTitle>{labels.more}</SheetTitle>
                <SheetDescription>{labels.navigation}</SheetDescription>
              </div>
              <SheetClose render={<Button type="button" variant="ghost" size="icon-lg" className="min-h-11 min-w-11" aria-label={labels.close} title={labels.close} />}>
                <X aria-hidden="true" />
              </SheetClose>
            </div>
          )}
          <div className="app-shell__sheet-body">
            {!desktop && canAdmin ? <NavigationItems items={[{ page: "users", icon: Users }, { page: "settings", icon: Settings }]} activePage={activePage} labels={labels} onNavigate={(page) => { setOpen(false); onNavigate(page) }} /> : null}
            {!desktop && canAdmin && activePage === "settings" ? <div className="app-shell__sheet-settings" role="group" aria-label={labels.settings}>
              <p className="app-shell__sheet-section-label">{labels.settings}</p>
              {SETTINGS_ITEMS.map(({ section, label, icon: Icon, animation }) => <AnimateIcon key={section}><button type="button" className={cn("app-shell__sheet-action", settingsSection === section && "app-shell__sheet-action--active")} aria-current={settingsSection === section ? "page" : undefined} onClick={() => { onSettingsSectionChange?.(section); setOpen(false); onNavigate("settings") }}><AnimatedIcon animation={animation}><Icon /></AnimatedIcon><span>{labels[label]}</span></button></AnimateIcon>)}
            </div> : null}
            {!desktop ? <StorageCard storage={storageHeadline} labels={labels} /> : null}
            <div className={cn(desktop && "app-shell__sheet-icon-actions")}>
              <AnimateIcon><button type="button" className={cn("app-shell__sheet-action", desktop && "app-shell__sheet-icon-action")} onClick={() => onThemeChange?.(nextTheme)} aria-label={desktop ? `${labels.theme}: ${themeLabel}` : undefined} title={desktop ? `${labels.theme}: ${themeLabel}` : undefined}><AnimatedIcon animation="pulse"><MorphIcon icon={themeIcon} reducedMotion="user" size={18} /></AnimatedIcon>{!desktop ? <><span>{labels.theme}</span><strong>{themeLabel}</strong></> : null}</button></AnimateIcon>
              <AnimateIcon><button type="button" className={cn("app-shell__sheet-action", desktop && "app-shell__sheet-icon-action")} onClick={() => onLanguageChange?.(currentLanguage === "en" ? "ru" : "en")} aria-label={desktop ? `${labels.language}: ${currentLanguage.toUpperCase()}` : undefined} title={desktop ? `${labels.language}: ${currentLanguage.toUpperCase()}` : undefined}><AnimatedIcon animation="wiggle"><Languages /></AnimatedIcon>{!desktop ? <><span>{labels.language}</span><strong>{currentLanguage.toUpperCase()}</strong></> : null}</button></AnimateIcon>
            </div>
            <AnimateIcon><Button type="button" variant="outline" className="app-shell__logout" onClick={() => { setOpen(false); onLogout?.() }}><AnimatedIcon animation="bounce"><LogOut /></AnimatedIcon>{labels.logOut}</Button></AnimateIcon>
            <div className="app-shell__sheet-account"><span className="app-shell__account-avatar" aria-hidden="true">{(username?.trim().charAt(0) || "A").toUpperCase()}</span><strong>{username || labels.account}</strong></div>
          </div>
        </SheetContent>
      </SheetPortal>
    </Sheet>
  )
}

function DesktopAccountControls({ labels, username, theme = "system", language = "en", onThemeChange, onLanguageChange, onLogout }: Pick<AppShellProps, "username" | "theme" | "language" | "onThemeChange" | "onLanguageChange" | "onLogout"> & { labels: AppShellLabels }) {
  const nextTheme: ThemeMode = theme === "light" ? "dark" : theme === "dark" ? "system" : "light"
  const themeIcon = theme === "dark" ? MoonData : theme === "light" ? SunData : LaptopData
  const themeLabel = theme === "dark" ? labels.themeDark : theme === "light" ? labels.themeLight : labels.themeSystem
  return <div className="app-shell__account-panel">
    <div className="app-shell__account-summary" aria-label={`${labels.account}: ${username || labels.account}`}>
      <span className="app-shell__account-avatar" aria-hidden="true">{(username?.trim().charAt(0) || "A").toUpperCase()}</span>
      <span className="app-shell__account-name">{username || labels.account}</span>
    </div>
    <div className="app-shell__account-actions">
      <Tooltip><AnimateIcon><TooltipTrigger render={<button type="button" className="app-shell__account-action" onClick={() => onThemeChange?.(nextTheme)} aria-label={`${labels.theme}: ${themeLabel}`}><AnimatedIcon animation="pulse"><MorphIcon icon={themeIcon} reducedMotion="user" size={18} /></AnimatedIcon></button>} /></AnimateIcon><TooltipContent side="top">{labels.theme}: {themeLabel}</TooltipContent></Tooltip>
      <Tooltip><AnimateIcon><TooltipTrigger render={<button type="button" className="app-shell__account-action" onClick={() => onLanguageChange?.(language === "en" ? "ru" : "en")} aria-label={`${labels.language}: ${language.toUpperCase()}`}><AnimatedIcon animation="wiggle"><Languages /></AnimatedIcon></button>} /></AnimateIcon><TooltipContent side="top">{labels.language}: {language.toUpperCase()}</TooltipContent></Tooltip>
      <Tooltip><AnimateIcon><TooltipTrigger render={<button type="button" className="app-shell__account-action app-shell__account-action--logout" onClick={onLogout} aria-label={labels.logOut}><AnimatedIcon animation="bounce"><LogOut /></AnimatedIcon></button>} /></AnimateIcon><TooltipContent side="top">{labels.logOut}</TooltipContent></Tooltip>
    </div>
  </div>
}

export function AppShell({ activePage, onPageChange, onNavigate, settingsSection, onSettingsSectionChange, username, canAdmin = true, theme, onThemeChange, language, onLanguageChange, onLogout, dryRun, storageHeadline, storage, jobsSlot, jobs, jobsCount, labels: labelOverrides, children }: AppShellProps) {
  const labels = mergeLabels(labelOverrides)
  const [collapsed, setCollapsed] = useState(() => typeof window !== "undefined" && window.localStorage.getItem("cleanarr.sidebar.collapsed") === "true")
  const resolvedStorage = storageHeadline ?? storage ?? { status: "unknown" as const, headline: labels.storageUnavailable }
  const resolvedJobs = jobsSlot ?? jobs
  const mobileMoreTriggerRef = useRef<HTMLButtonElement>(null)
  useEffect(() => {
    window.localStorage.setItem("cleanarr.sidebar.collapsed", String(collapsed))
  }, [collapsed])
  useEffect(() => {
    const toggle = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "b") {
        event.preventDefault()
        setCollapsed((value) => !value)
      }
    }
    window.addEventListener("keydown", toggle)
    return () => window.removeEventListener("keydown", toggle)
  }, [])
  const navigate = (page: AppShellPage) => {
    onPageChange?.(page)
    onNavigate?.(page)
  }
  return (
    <div className={cn("app-shell", collapsed && "app-shell--sidebar-collapsed")}>
      <aside className="app-shell__sidebar" aria-label={labels.navigation}>
        <Brand labels={labels} collapsed={collapsed} onToggle={() => setCollapsed((value) => !value)} />
        <div className="app-shell__navigation-scroll" role="region" aria-label={labels.navigation} tabIndex={0}>
          <LayoutGroup id="desktop-sidebar-navigation">
            <NavigationItems items={NAV_ITEMS.filter(({ page }) => page !== "settings" && (canAdmin || page !== "users"))} activePage={activePage} labels={labels} onNavigate={navigate} collapsed={collapsed} />
            {canAdmin ? <SettingsNavigation activePage={activePage} settingsSection={settingsSection} labels={labels} onNavigate={navigate} onSettingsSectionChange={onSettingsSectionChange} collapsed={collapsed} /> : null}
          </LayoutGroup>
        </div>
        <div className="app-shell__sidebar-bottom">
          <RuntimeStatus dryRun={dryRun} labels={labels} />
          <StorageCard storage={resolvedStorage} labels={labels} />
          <DesktopAccountControls labels={labels} username={username} theme={theme} language={language} onThemeChange={onThemeChange} onLanguageChange={onLanguageChange} onLogout={onLogout} />
        </div>
      </aside>
      <header className="app-shell__mobile-topbar">
        <Brand labels={labels} />
        <RuntimeStatus dryRun={dryRun} labels={labels} />
      </header>
      <div className="app-shell__desktop-status">{jobsCount != null ? <span className="app-shell__jobs-count">{jobsCount}</span> : null}{resolvedJobs}</div>
      <main className="app-shell__main">{children}</main>
      <nav className="app-shell__bottom-nav" aria-label={labels.navigation}>
        <NavigationItems items={MOBILE_ITEMS} activePage={activePage} labels={labels} onNavigate={navigate} mobile />
        <MorePanel labels={labels} storageHeadline={resolvedStorage} username={username} theme={theme} language={language} onThemeChange={onThemeChange} onLanguageChange={onLanguageChange} onLogout={onLogout} onNavigate={navigate} settingsSection={settingsSection} onSettingsSectionChange={onSettingsSectionChange} triggerRef={mobileMoreTriggerRef} activePage={activePage} canAdmin={canAdmin} />
      </nav>
    </div>
  )
}

export type { AppShellProps }
