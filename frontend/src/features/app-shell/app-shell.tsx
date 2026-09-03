import {
  Activity,
  BookOpen,
  Download,
  Home,
  Languages,
  Laptop,
  LogOut,
  MoreHorizontal,
  Moon,
  Plug,
  SlidersHorizontal,
  Zap,
  Settings,
  Star,
  Sun,
  UserRound,
  X,
  HardDrive,
  type LucideIcon,
} from "lucide-react"
import { useRef, useState, type ReactNode } from "react"

import type { ThemeMode } from "@/components/theme-provider"
import { Button } from "@/components/ui/button"
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

export type AppShellPage = "overview" | "library" | "downloads" | "activity" | "settings"
export type ShellLanguage = "en" | "ru"
export type SettingsSection = "general" | "services"
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
  storagePartial: string
  storageUnavailable: string
  account: string
  settings: string
  settingsGeneral: string
  settingsServices: string
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
    storagePartial: "Partial data",
    storageUnavailable: "Storage unavailable",
  account: "Account",
  settings: "Settings",
  settingsGeneral: "General",
  settingsServices: "Connected services",
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

const NAV_ITEMS: NavItem[] = [
  { page: "overview", icon: Home },
  { page: "library", icon: BookOpen },
  { page: "downloads", icon: Download },
  { page: "activity", icon: Activity },
  { page: "settings", icon: Settings },
]

const MOBILE_ITEMS: NavItem[] = NAV_ITEMS.filter(({ page }) => page !== "settings")

function mergeLabels(labels?: AppShellProps["labels"]): AppShellLabels {
  return {
    ...DEFAULT_LABELS,
    ...labels,
    nav: { ...DEFAULT_LABELS.nav, ...labels?.nav },
    storageStatus: { ...DEFAULT_LABELS.storageStatus, ...labels?.storageStatus },
  }
}

function Brand({ labels }: { labels: AppShellLabels }) {
  return (
    <div className="app-shell__brand" aria-label={labels.logo}>
      <Zap className="app-shell__brand-mark" aria-hidden="true" />
      <span className="app-shell__brand-name"><span>Clean</span><strong>Arr</strong></span>
      <a
        className="app-shell__brand-github"
        href="https://github.com/mambastick/Cleanarr"
        target="_blank"
        rel="noreferrer noopener"
        aria-label={`GitHub: ${labels.githubStars}`}
        title={`GitHub: ${labels.githubStars}`}
      >
        <Star aria-hidden="true" />
        <span>15</span>
      </a>
    </div>
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
      {percent != null ? <div className="app-shell__storage-meter" role="progressbar" aria-valuenow={percent} aria-valuemin={0} aria-valuemax={100} aria-label={`${storage.headline}: ${percent}%`}><span style={{ transform: `scaleX(${percent / 100})` }} /></div> : null}
      {storage.partial || storage.freshness ? <p className="app-shell__storage-meta">{storage.partial ? labels.storagePartial : null}{storage.partial && storage.freshness ? " · " : null}{storage.freshness}</p> : null}
    </section>
  )
}

function NavigationItems({ items, activePage, labels, onNavigate, mobile = false }: { items: NavItem[]; activePage: AppShellPage; labels: AppShellLabels; onNavigate: (page: AppShellPage) => void; mobile?: boolean }) {
  return (
    <div className={cn("app-shell__nav-list", mobile && "app-shell__nav-list--mobile")}>
      {items.map(({ page, icon: Icon }) => {
        const active = activePage === page
        return (
          <button key={page} type="button" className={cn("app-shell__nav-item", active && "app-shell__nav-item--active")} aria-current={active ? "page" : undefined} aria-label={labels.nav[page]} title={labels.nav[page]} onClick={() => onNavigate(page)}>
            <Icon aria-hidden="true" />
            <span>{labels.nav[page]}</span>
          </button>
        )
      })}
    </div>
  )
}

function SettingsNavigation({ activePage, settingsSection = "general", labels, onNavigate, onSettingsSectionChange }: { activePage: AppShellPage; settingsSection?: SettingsSection; labels: AppShellLabels; onNavigate: (page: AppShellPage) => void; onSettingsSectionChange?: (section: SettingsSection) => void }) {
  const expanded = activePage === "settings"
  const selectSection = (section: SettingsSection) => {
    onSettingsSectionChange?.(section)
    onNavigate("settings")
  }

  return (
    <div className="app-shell__settings-group">
      <button
        type="button"
        className={cn("app-shell__nav-item", expanded && "app-shell__nav-item--active")}
        aria-current={expanded ? "page" : undefined}
        aria-expanded={expanded}
        aria-controls={expanded ? "app-shell-settings-sections" : undefined}
        aria-label={labels.nav.settings}
        title={labels.nav.settings}
        onClick={() => selectSection("general")}
      >
        <Settings aria-hidden="true" />
        <span>{labels.nav.settings}</span>
      </button>
      {expanded ? (
        <div id="app-shell-settings-sections" className="app-shell__settings-sections" role="group" aria-label={labels.settings}>
          <button
            type="button"
            className={cn("app-shell__settings-section", settingsSection === "general" && "app-shell__settings-section--active")}
            aria-current={settingsSection === "general" ? "page" : undefined}
            title={labels.settingsGeneral}
            onClick={() => selectSection("general")}
          >
            <SlidersHorizontal aria-hidden="true" />
            <span>{labels.settingsGeneral}</span>
          </button>
          <button
            type="button"
            className={cn("app-shell__settings-section", settingsSection === "services" && "app-shell__settings-section--active")}
            aria-current={settingsSection === "services" ? "page" : undefined}
            title={labels.settingsServices}
            onClick={() => selectSection("services")}
          >
            <Plug aria-hidden="true" />
            <span>{labels.settingsServices}</span>
          </button>
        </div>
      ) : null}
    </div>
  )
}

function MorePanel({ labels, storageHeadline, username, theme, language, onThemeChange, onLanguageChange, onLogout, onSettings, triggerRef, activePage, desktop = false }: { labels: AppShellLabels; storageHeadline: StorageHeadline; username: string | null | undefined; theme?: ThemeMode; language?: ShellLanguage; onThemeChange?: (theme: ThemeMode) => void; onLanguageChange?: (language: ShellLanguage) => void; onLogout?: () => void; onSettings: () => void; triggerRef: React.RefObject<HTMLButtonElement | null>; activePage: AppShellPage; desktop?: boolean }) {
  const [open, setOpen] = useState(false)
  const currentTheme = theme ?? "system"
  const currentLanguage = language ?? "en"
  const nextTheme: ThemeMode = currentTheme === "light" ? "dark" : currentTheme === "dark" ? "system" : "light"
  const ThemeIcon = currentTheme === "dark" ? Moon : currentTheme === "light" ? Sun : Laptop
  const themeLabel = currentTheme === "dark" ? labels.themeDark : currentTheme === "light" ? labels.themeLight : labels.themeSystem
  return (
    <Sheet open={open} onOpenChange={setOpen}>
      {desktop ? (
        <SheetTrigger render={<button ref={triggerRef} type="button" className="app-shell__account" aria-label={`${labels.account}: ${username || labels.account}`} />}>
          <span className="app-shell__account-avatar" aria-hidden="true">{(username?.trim().charAt(0) || "A").toUpperCase()}</span>
          <span className="app-shell__account-name">{username || labels.account}</span>
        </SheetTrigger>
      ) : (
        <SheetTrigger render={<Button ref={triggerRef} type="button" variant="ghost" className="app-shell__more-trigger" aria-label={labels.more} />}>
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
              <SheetClose render={<Button type="button" variant="ghost" size="icon-lg" className="min-h-11 min-w-11" aria-label={labels.close} />}>
                <X aria-hidden="true" />
              </SheetClose>
            </div>
          )}
          <div className="app-shell__sheet-body">
            {!desktop ? <NavigationItems items={[{ page: "settings", icon: Settings }]} activePage={activePage} labels={labels} onNavigate={(page) => { setOpen(false); if (page === "settings") onSettings() }} /> : null}
            {!desktop ? <StorageCard storage={storageHeadline} labels={labels} /> : null}
            <div className="app-shell__sheet-account"><UserRound aria-hidden="true" /><span>{labels.account}</span><strong>{username || labels.account}</strong></div>
            <button type="button" className={cn("app-shell__sheet-action", desktop && "app-shell__sheet-icon-action")} onClick={() => onThemeChange?.(nextTheme)} aria-label={desktop ? `${labels.theme}: ${themeLabel}` : undefined} title={desktop ? `${labels.theme}: ${themeLabel}` : undefined}><ThemeIcon aria-hidden="true" />{!desktop ? <><span>{labels.theme}</span><strong>{themeLabel}</strong></> : null}</button>
            <button type="button" className={cn("app-shell__sheet-action", desktop && "app-shell__sheet-icon-action")} onClick={() => onLanguageChange?.(currentLanguage === "en" ? "ru" : "en")} aria-label={desktop ? `${labels.language}: ${currentLanguage.toUpperCase()}` : undefined} title={desktop ? `${labels.language}: ${currentLanguage.toUpperCase()}` : undefined}><Languages aria-hidden="true" />{!desktop ? <><span>{labels.language}</span><strong>{currentLanguage.toUpperCase()}</strong></> : null}</button>
            <Button type="button" variant="outline" className="app-shell__logout" onClick={() => { setOpen(false); onLogout?.() }}><LogOut aria-hidden="true" />{labels.logOut}</Button>
          </div>
        </SheetContent>
      </SheetPortal>
    </Sheet>
  )
}

export function AppShell({ activePage, onPageChange, onNavigate, settingsSection, onSettingsSectionChange, username, theme, onThemeChange, language, onLanguageChange, onLogout, dryRun, storageHeadline, storage, jobsSlot, jobs, jobsCount, labels: labelOverrides, children }: AppShellProps) {
  const labels = mergeLabels(labelOverrides)
  const resolvedStorage = storageHeadline ?? storage ?? { status: "unknown" as const, headline: labels.storageUnavailable }
  const resolvedJobs = jobsSlot ?? jobs
  const mobileMoreTriggerRef = useRef<HTMLButtonElement>(null)
  const desktopAccountTriggerRef = useRef<HTMLButtonElement>(null)
  const navigate = (page: AppShellPage) => {
    onPageChange?.(page)
    onNavigate?.(page)
  }
  return (
    <div className="app-shell">
      <aside className="app-shell__sidebar" aria-label={labels.navigation}>
        <Brand labels={labels} />
        <NavigationItems items={NAV_ITEMS.filter(({ page }) => page !== "settings")} activePage={activePage} labels={labels} onNavigate={navigate} />
        <SettingsNavigation activePage={activePage} settingsSection={settingsSection} labels={labels} onNavigate={navigate} onSettingsSectionChange={onSettingsSectionChange} />
        <div className="app-shell__sidebar-bottom">
          <RuntimeStatus dryRun={dryRun} labels={labels} />
          <StorageCard storage={resolvedStorage} labels={labels} />
          <MorePanel labels={labels} storageHeadline={resolvedStorage} username={username} theme={theme} language={language} onThemeChange={onThemeChange} onLanguageChange={onLanguageChange} onLogout={onLogout} onSettings={() => navigate("settings")} triggerRef={desktopAccountTriggerRef} activePage={activePage} desktop />
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
        <MorePanel labels={labels} storageHeadline={resolvedStorage} username={username} theme={theme} language={language} onThemeChange={onThemeChange} onLanguageChange={onLanguageChange} onLogout={onLogout} onSettings={() => navigate("settings")} triggerRef={mobileMoreTriggerRef} activePage={activePage} />
      </nav>
    </div>
  )
}

export type { AppShellProps }
