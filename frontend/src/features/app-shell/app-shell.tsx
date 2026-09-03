import {
  Activity,
  BookOpen,
  Download,
  FlaskConical,
  HardDrive,
  Home,
  Languages,
  LibraryBig,
  LogOut,
  Menu,
  MoreHorizontal,
  Plug,
  RadioTower,
  ShieldCheck,
  SlidersHorizontal,
  Settings,
  Trash2,
  Users,
  X,
  Zap,
  type LucideIcon,
} from "lucide-react"
import {
  Laptop as LaptopData,
  Moon as MoonData,
  Sun as SunData,
} from "lucide"
import { MorphIcon } from "morphicons/react"
import { AnimatePresence, motion } from "motion/react"
import { useEffect, useRef, useState, type ReactNode } from "react"

import { AnimateIcon, AnimatedIcon, type IconAnimation } from "@/components/animate-ui/animated-icon"
import { GitHubStarsButton } from "@/components/animate-ui/components/buttons/github-stars"
import { Highlight, HighlightItem } from "@/components/animate-ui/primitives/effects/highlight"
import type { ThemeMode } from "@/components/theme-provider"
import { Button } from "@/components/ui/button"
import { Popover, PopoverClose, PopoverContent, PopoverDescription, PopoverTitle, PopoverTrigger } from "@/components/ui/popover"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { UserAvatar } from "@/components/user-avatar"
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
import { useReducedMotionPreference } from "@/hooks/use-reduced-motion-preference"
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
  library: "pulse",
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
      <span className="app-shell__brand-mark-slot"><AnimatedIcon animation="wiggle"><Zap className="app-shell__brand-mark" /></AnimatedIcon></span>
      <span className="app-shell__brand-name"><span>Clean</span><strong>Arr</strong></span>
      <GitHubStarsButton
        className="app-shell__brand-github"
        username="mambastick"
        repo="Cleanarr"
        value={15}
        variant="ghost"
        size="sm"
        aria-label={`GitHub: ${labels.githubStars}`}
      />
      {onToggle ? <Tooltip><TooltipTrigger render={<button type="button" className="app-shell__collapse" onClick={onToggle} aria-label={collapsed ? labels.expandSidebar : labels.collapseSidebar}><Menu aria-hidden="true" /></button>} /><TooltipContent side="right">{collapsed ? labels.expandSidebar : labels.collapseSidebar}</TooltipContent></Tooltip> : null}
    </div></AnimateIcon>
  )
}

function RuntimeStatus({ dryRun, labels }: { dryRun: boolean; labels: AppShellLabels }) {
  const statusLabel = `${labels.status}: ${dryRun ? labels.dryRun : labels.live}`
  return (
    <Tooltip>
      <TooltipTrigger render={<div className={cn("app-shell__runtime-status", dryRun ? "app-shell__runtime-status--dry" : "app-shell__runtime-status--live")} role="status" tabIndex={0} aria-label={statusLabel} />}>
        {dryRun ? <FlaskConical className="app-shell__status-icon" aria-hidden="true" /> : <RadioTower className="app-shell__status-icon" aria-hidden="true" />}
        <span>{dryRun ? labels.dryRun : labels.live}</span>
      </TooltipTrigger>
      <TooltipContent side="right">{statusLabel}</TooltipContent>
    </Tooltip>
  )
}

function StorageCard({ storage, labels }: { storage: StorageHeadline; labels: AppShellLabels }) {
  const percent = storage.percent == null ? null : Math.max(0, Math.min(100, storage.percent))
  const tooltipLabel = `${labels.storage}: ${labels.storageStatus[storage.status]} — ${storage.headline}`
  return (
    <Tooltip>
      <TooltipTrigger render={<section className={cn("app-shell__storage", `app-shell__storage--${storage.status}`)} aria-label={labels.storage} tabIndex={0} />}>
        <div className="app-shell__storage-heading">
          <HardDrive aria-hidden="true" />
          <span>{labels.storage}</span>
          <span className="app-shell__storage-state">{labels.storageStatus[storage.status]}</span>
        </div>
        <p className="app-shell__storage-headline">{storage.headline}</p>
        {storage.detail ? <p className="app-shell__storage-detail">{storage.detail}</p> : null}
        {percent != null ? <div className="app-shell__storage-meter" role="progressbar" aria-valuenow={percent} aria-valuemin={0} aria-valuemax={100} aria-label={`${labels.storageUsed}: ${percent}%`}><span style={{ transform: `scaleX(${percent / 100})` }} /></div> : null}
        {storage.partial || storage.freshness ? <p className="app-shell__storage-meta">{storage.partial ? labels.storagePartial : null}{storage.partial && storage.freshness ? " · " : null}{storage.freshness}</p> : null}
      </TooltipTrigger>
      <TooltipContent side="right">{tooltipLabel}</TooltipContent>
    </Tooltip>
  )
}

function NavigationItems({ items, activePage, labels, onNavigate, mobile = false, collapsed = false, highlight = false }: { items: NavItem[]; activePage: AppShellPage; labels: AppShellLabels; onNavigate: (page: AppShellPage) => void; mobile?: boolean; collapsed?: boolean; highlight?: boolean }) {
  return (
    <div className={cn("app-shell__nav-list", mobile && "app-shell__nav-list--mobile")}>
      {items.map(({ page, icon: Icon }) => {
        const active = activePage === page
        const button = <button type="button" className={cn("app-shell__nav-item", active && "app-shell__nav-item--active")} aria-current={active ? "page" : undefined} aria-label={labels.nav[page]} onClick={() => onNavigate(page)}>
          <AnimatedIcon animation={NAV_ICON_ANIMATION[page]}><Icon /></AnimatedIcon>
          <span>{labels.nav[page]}</span>
        </button>
        const tooltip = (
          <Tooltip key={page}>
            <AnimateIcon><TooltipTrigger render={button} /></AnimateIcon>
            {collapsed && !mobile ? <TooltipContent side="right">{labels.nav[page]}</TooltipContent> : null}
          </Tooltip>
        )
        return highlight ? <HighlightItem key={page} value={page} className="app-shell__nav-highlight-item">{tooltip}</HighlightItem> : tooltip
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
  const reducedMotion = useReducedMotionPreference()
  const selectSection = (section: SettingsSection) => {
    onSettingsSectionChange?.(section)
    onNavigate("settings")
  }

  return (
    <div className="app-shell__settings-group">
      <HighlightItem value="settings" className="app-shell__nav-highlight-item" activeClassName="app-shell__nav-active-indicator--settings"><Tooltip><AnimateIcon><TooltipTrigger render={<button
          type="button"
          className={cn("app-shell__nav-item", expanded && "app-shell__nav-item--active")}
          aria-current={expanded ? "page" : undefined}
          aria-expanded={expanded && !collapsed}
          aria-controls={expanded && !collapsed ? "app-shell-settings-sections" : undefined}
          aria-label={labels.nav.settings}
          onClick={() => selectSection(settingsSection)}
        >
          <AnimatedIcon animation="wiggle"><Settings /></AnimatedIcon>
          <span>{labels.nav.settings}</span>
        </button>} /></AnimateIcon>{collapsed ? <TooltipContent side="right">{labels.nav.settings}</TooltipContent> : null}</Tooltip></HighlightItem>
      <AnimatePresence initial={false}>
        {expanded && !collapsed ? (
          <motion.div
            id="app-shell-settings-sections"
            className="app-shell__settings-sections"
            role="group"
            aria-label={labels.settings}
            data-motion-tree="true"
            initial={reducedMotion ? false : { height: 0, opacity: 0, y: -6 }}
            animate={{ height: "auto", opacity: 1, y: 0 }}
            exit={reducedMotion ? { opacity: 0 } : { height: 0, opacity: 0, y: -6 }}
            transition={reducedMotion ? { duration: 0 } : { duration: 0.22, ease: [0.2, 0.8, 0.2, 1] }}
          >
            <Highlight
              mode="parent"
              controlledItems
              value={settingsSection}
              hover={false}
              click={false}
              transition={{ type: "spring", stiffness: 350, damping: 35 }}
              className="app-shell__settings-active-indicator"
              containerClassName="app-shell__settings-highlight"
            >
              {SETTINGS_ITEMS.map(({ section, label, icon: Icon, animation }) => (
                <HighlightItem key={section} value={section} className="app-shell__settings-highlight-item">
                  <AnimateIcon><button
                    type="button"
                    className={cn("app-shell__settings-section", settingsSection === section && "app-shell__settings-section--active")}
                    aria-current={settingsSection === section ? "page" : undefined}
                    aria-label={labels[label]}
                    onClick={() => selectSection(section)}
                  >
                    <AnimatedIcon animation={animation}><Icon /></AnimatedIcon>
                    <span>{labels[label]}</span>
                  </button></AnimateIcon>
                </HighlightItem>
              ))}
            </Highlight>
          </motion.div>
        ) : null}
      </AnimatePresence>
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
          <UserAvatar name={username} className="app-shell__account-avatar" />
          <span className="app-shell__account-name">{username || labels.account}</span>
        </SheetTrigger>
      ) : (
        <SheetTrigger render={<Button ref={triggerRef} type="button" variant="ghost" className={cn("app-shell__more-trigger", moreActive && "app-shell__more-trigger--active")} aria-current={moreActive ? "page" : undefined} aria-label={labels.more} />}>
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
            <div className="app-shell__sheet-account"><UserAvatar name={username} className="app-shell__account-avatar" /><strong>{username || labels.account}</strong></div>
          </div>
        </SheetContent>
      </SheetPortal>
    </Sheet>
  )
}

function DesktopAccountPopover({ labels, username, theme = "system", language = "en", onThemeChange, onLanguageChange, onLogout, collapsed = false }: Pick<AppShellProps, "username" | "theme" | "language" | "onThemeChange" | "onLanguageChange" | "onLogout"> & { labels: AppShellLabels; collapsed?: boolean }) {
  const nextTheme: ThemeMode = theme === "light" ? "dark" : theme === "dark" ? "system" : "light"
  const themeIcon = theme === "dark" ? MoonData : theme === "light" ? SunData : LaptopData
  const themeLabel = theme === "dark" ? labels.themeDark : theme === "light" ? labels.themeLight : labels.themeSystem
  const accountLabel = `${labels.account}: ${username || labels.account}`
  const trigger = <PopoverTrigger render={<button type="button" className="app-shell__account-trigger" aria-label={accountLabel} />}>
    <UserAvatar name={username} className="app-shell__account-avatar" />
    <span className="app-shell__account-name">{username || labels.account}</span>
  </PopoverTrigger>

  return (
    <div className="app-shell__account-panel">
      <Popover>
        {collapsed ? <Tooltip><TooltipTrigger render={trigger} /><TooltipContent side="right">{accountLabel}</TooltipContent></Tooltip> : trigger}
        <PopoverContent className="app-shell__account-popover" aria-label={labels.account}>
          <div className="app-shell__account-popover-header">
            <UserAvatar name={username} className="app-shell__account-avatar" />
            <div>
              <PopoverTitle className="app-shell__account-popover-title">{username || labels.account}</PopoverTitle>
              <PopoverDescription className="app-shell__account-popover-description">{labels.account}</PopoverDescription>
            </div>
          </div>
          <div className="app-shell__account-popover-actions">
            <AnimateIcon><button type="button" className="app-shell__account-popover-action" onClick={() => onThemeChange?.(nextTheme)} aria-label={`${labels.theme}: ${themeLabel}`}><AnimatedIcon animation="pulse"><MorphIcon icon={themeIcon} reducedMotion="user" size={18} /></AnimatedIcon><span>{labels.theme}</span><strong>{themeLabel}</strong></button></AnimateIcon>
            <AnimateIcon><button type="button" className="app-shell__account-popover-action" onClick={() => onLanguageChange?.(language === "en" ? "ru" : "en")} aria-label={`${labels.language}: ${language.toUpperCase()}`}><AnimatedIcon animation="wiggle"><Languages /></AnimatedIcon><span>{labels.language}</span><strong>{language.toUpperCase()}</strong></button></AnimateIcon>
            <AnimateIcon><PopoverClose render={<button type="button" className="app-shell__account-popover-action app-shell__account-popover-action--logout" onClick={onLogout} aria-label={labels.logOut} />}><AnimatedIcon animation="bounce"><LogOut /></AnimatedIcon><span>{labels.logOut}</span></PopoverClose></AnimateIcon>
          </div>
        </PopoverContent>
      </Popover>
    </div>
  )
}

export function AppShell({ activePage, onPageChange, onNavigate, settingsSection, onSettingsSectionChange, username, canAdmin = true, theme, onThemeChange, language, onLanguageChange, onLogout, dryRun, storageHeadline, storage, jobsSlot, jobs, jobsCount, labels: labelOverrides, children }: AppShellProps) {
  const labels = mergeLabels(labelOverrides)
  const [collapsed, setCollapsed] = useState(() => typeof window !== "undefined" && window.localStorage.getItem("cleanarr.sidebar.collapsed") === "true")
  const resolvedStorage = storageHeadline ?? storage ?? { status: "unknown" as const, headline: labels.storageUnavailable }
  const resolvedJobs = jobsSlot ?? jobs
  const mobileMoreTriggerRef = useRef<HTMLButtonElement>(null)
  const mobileHighlightValue = MOBILE_ITEMS.some(({ page }) => page === activePage) ? activePage : "more"
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
          <Highlight mode="parent" controlledItems value={activePage} hover={false} click={false} forceUpdateBounds transition={{ type: "spring", stiffness: 350, damping: 35 }} className="app-shell__nav-active-indicator" containerClassName="app-shell__navigation-highlight">
            <NavigationItems items={NAV_ITEMS.filter(({ page }) => page !== "settings" && (canAdmin || page !== "users"))} activePage={activePage} labels={labels} onNavigate={navigate} collapsed={collapsed} highlight />
            {canAdmin ? <SettingsNavigation activePage={activePage} settingsSection={settingsSection} labels={labels} onNavigate={navigate} onSettingsSectionChange={onSettingsSectionChange} collapsed={collapsed} /> : null}
          </Highlight>
        </div>
        <div className="app-shell__sidebar-bottom">
          <RuntimeStatus dryRun={dryRun} labels={labels} />
          {!collapsed ? <StorageCard storage={resolvedStorage} labels={labels} /> : null}
          <DesktopAccountPopover labels={labels} username={username} theme={theme} language={language} onThemeChange={onThemeChange} onLanguageChange={onLanguageChange} onLogout={onLogout} collapsed={collapsed} />
        </div>
      </aside>
      <header className="app-shell__mobile-topbar">
        <Brand labels={labels} />
        <RuntimeStatus dryRun={dryRun} labels={labels} />
      </header>
      <div className="app-shell__desktop-status">{jobsCount != null ? <span className="app-shell__jobs-count">{jobsCount}</span> : null}{resolvedJobs}</div>
      <main className="app-shell__main">{children}</main>
      <nav className="app-shell__bottom-nav" aria-label={labels.navigation}>
        <Highlight mode="parent" controlledItems value={mobileHighlightValue} hover={false} click={false} transition={{ type: "spring", stiffness: 350, damping: 35 }} className="app-shell__nav-active-indicator app-shell__nav-active-indicator--mobile" containerClassName="app-shell__bottom-highlight">
          <NavigationItems items={MOBILE_ITEMS} activePage={activePage} labels={labels} onNavigate={navigate} mobile highlight />
          <HighlightItem value="more" className="app-shell__more-highlight-item">
            <MorePanel labels={labels} storageHeadline={resolvedStorage} username={username} theme={theme} language={language} onThemeChange={onThemeChange} onLanguageChange={onLanguageChange} onLogout={onLogout} onNavigate={navigate} settingsSection={settingsSection} onSettingsSectionChange={onSettingsSectionChange} triggerRef={mobileMoreTriggerRef} activePage={activePage} canAdmin={canAdmin} />
          </HighlightItem>
        </Highlight>
      </nav>
    </div>
  )
}

export type { AppShellProps }
