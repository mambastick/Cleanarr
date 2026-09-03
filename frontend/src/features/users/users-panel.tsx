import { Search, ShieldCheck, Users } from "lucide-react"
import { useCallback, useEffect, useMemo, useState } from "react"
import { toast } from "sonner"

import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Skeleton } from "@/components/ui/skeleton"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { UserAvatar } from "@/components/user-avatar"
import { normalizeError } from "@/lib/status-format"
import type { UserAccountListPayload, UserAccountPayload, UserRole } from "@/lib/users"

type UsersLanguage = "en" | "ru"
type FetchJson = <T>(url: string, init?: RequestInit) => Promise<T>

const COPY = {
  en: { title: "Users", description: "People who have signed in to this CleanArr instance.", search: "Search users", user: "User", role: "Role", source: "Sign-in", lastSeen: "Last online", created: "Added", admin: "Administrator", viewer: "Viewer", local: "Local", sso: "SSO", never: "Never", loading: "Loading users", empty: "No users match this search.", saved: "Role updated.", adminOnly: "Only administrators can change roles.", signedInAs: "Signed in as", lastAdmin: "At least one administrator must remain." },
  ru: { title: "Пользователи", description: "Все, кто входил в этот экземпляр CleanArr.", search: "Поиск пользователя", user: "Пользователь", role: "Роль", source: "Способ входа", lastSeen: "Последний онлайн", created: "Добавлен", admin: "Администратор", viewer: "Наблюдатель", local: "Локально", sso: "SSO", never: "Никогда", loading: "Загружаем пользователей", empty: "По этому запросу пользователи не найдены.", saved: "Роль обновлена.", adminOnly: "Изменять роли могут только администраторы.", signedInAs: "Вы вошли как", lastAdmin: "В системе должен остаться хотя бы один администратор." },
} as const

export function UsersPanel({ active, language, currentUsername, currentRole, fetchJson, onCurrentRoleChange }: { active: boolean; language: UsersLanguage; currentUsername: string | null; currentRole: UserRole | null; fetchJson: FetchJson; onCurrentRoleChange?: (role: UserRole) => void }) {
  const text = COPY[language]
  const [users, setUsers] = useState<UserAccountPayload[]>([])
  const [query, setQuery] = useState("")
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState<string | null>(null)

  const load = useCallback(async () => {
    if (!active) return
    setLoading(true)
    try { setUsers((await fetchJson<UserAccountListPayload>("/api/users")).users) }
    catch (error) { toast.error(normalizeError(error)) }
    finally { setLoading(false) }
  }, [active, fetchJson])

  useEffect(() => { void load() }, [load])

  const filtered = useMemo(() => {
    const needle = query.trim().toLocaleLowerCase()
    if (!needle) return users
    return users.filter((user) => `${user.username} ${user.role} ${user.auth_source}`.toLocaleLowerCase().includes(needle))
  }, [query, users])
  const adminCount = users.filter((user) => user.role === "admin").length

  const updateRole = async (user: UserAccountPayload, role: UserRole) => {
    if (user.role === role || saving || currentRole !== "admin") return
    setSaving(user.username)
    try {
      const updated = await fetchJson<UserAccountPayload>(`/api/users/${encodeURIComponent(user.username)}/role`, { method: "PATCH", body: JSON.stringify({ role }) })
      setUsers((current) => current.map((account) => account.username === updated.username ? updated : account))
      if (updated.username.toLocaleLowerCase() === currentUsername?.toLocaleLowerCase()) onCurrentRoleChange?.(updated.role)
      toast.success(text.saved)
    } catch (error) { toast.error(normalizeError(error)) }
    finally { setSaving(null) }
  }

  return <section className="space-y-5">
    <header><h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight sm:text-3xl"><Users className="size-6 text-primary" />{text.title}</h1><p className="mt-1 text-sm text-muted-foreground">{text.description}</p></header>
    <Card>
      <CardHeader className="gap-4">
        <div className="flex items-start justify-between gap-4"><CardTitle className="text-base">{text.title}</CardTitle><Badge variant="secondary" className="min-w-8 justify-center tabular-nums" aria-label={`${text.title}: ${users.length}`}>{users.length}</Badge></div>
        {currentUsername ? <div className="flex items-start gap-2 rounded-lg border border-primary/20 bg-primary/5 px-3 py-2 text-xs text-muted-foreground"><ShieldCheck className="mt-0.5 size-4 shrink-0 text-primary" aria-hidden="true" /><p><span>{text.signedInAs} <strong className="font-semibold text-foreground">{currentUsername}</strong>.</span>{adminCount === 1 ? <span className="ml-1">{text.lastAdmin}</span> : null}</p></div> : null}
        <div className="relative w-full sm:max-w-xs"><Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" /><Input value={query} onChange={(event) => setQuery(event.target.value)} placeholder={text.search} aria-label={text.search} className="pl-9" /></div>
      </CardHeader>
      <CardContent className="p-0">
        {currentRole !== "admin" ? <p className="border-y bg-muted/40 px-4 py-2 text-xs text-muted-foreground">{text.adminOnly}</p> : null}
        {loading && !users.length ? <div className="space-y-2 p-4" role="status" aria-label={text.loading}><Skeleton className="h-12 w-full" /><Skeleton className="h-12 w-full" /></div> : filtered.length ? <Table>
          <TableHeader><TableRow><TableHead>{text.user}</TableHead><TableHead>{text.role}</TableHead><TableHead>{text.source}</TableHead><TableHead>{text.lastSeen}</TableHead><TableHead>{text.created}</TableHead></TableRow></TableHeader>
          <TableBody>{filtered.map((user) => {
            return <TableRow key={user.username}><TableCell><div className="flex items-center gap-3"><UserAvatar name={user.username} className="size-9 text-xs" /><p className="font-medium">{user.username}</p></div></TableCell><TableCell><Select items={{ admin: text.admin, viewer: text.viewer }} value={user.role} disabled={currentRole !== "admin" || saving === user.username} onValueChange={(value) => void updateRole(user, value as UserRole)}><SelectTrigger className="w-40" aria-label={`${text.role}: ${user.username}`}><SelectValue /></SelectTrigger><SelectContent><SelectItem value="admin">{text.admin}</SelectItem><SelectItem value="viewer">{text.viewer}</SelectItem></SelectContent></Select></TableCell><TableCell><Badge variant="secondary">{user.auth_source === "local" ? text.local : text.sso}</Badge></TableCell><TableCell>{formatDate(user.last_seen_at, language, text.never)}</TableCell><TableCell>{formatDate(user.created_at, language, text.never)}</TableCell></TableRow>
          })}</TableBody>
        </Table> : <p className="p-8 text-center text-sm text-muted-foreground">{text.empty}</p>}
      </CardContent>
    </Card>
  </section>
}

function formatDate(value: string | null, language: UsersLanguage, fallback: string) {
  if (!value) return fallback
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? fallback : date.toLocaleString(language === "ru" ? "ru-RU" : "en-US")
}
