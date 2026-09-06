import { ExternalLink, ShieldAlert, ShieldCheck } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import type { DashboardAction } from "@/lib/dashboard"
import type { ManualDeletePreviewResponse } from "@/lib/library"
import type { DeleteDialogCopy } from "./delete-confirmation-dialog"
import { isExecutablePlan, actionGroup, localizedActionLabel, localizedSystemLabel, type DeletionLanguage } from "./deletion-copy"
import { actionEffect, actionFacts, actionLink, actionTarget, displayText, planCopy, planScope, providerLinks, type InspectionLink, type InspectionService } from "./plan-presentation"

export function DeletionPlanSummary({ preview, language, copy, services = [] }: { preview: ManualDeletePreviewResponse; language: DeletionLanguage; copy: DeleteDialogCopy; services?: InspectionService[] }) {
  const { plan } = preview
  const c = planCopy[language]
  const groups = plan.actions.reduce<Record<"remove" | "retain" | "attention", DashboardAction[]>>((result, action) => {
    result[actionGroup(action)].push(action)
    return result
  }, { remove: [], retain: [], attention: [] })
  const providers = providerLinks(plan)
  return <div className="space-y-5">
    <div className="rounded-xl border border-border bg-card p-4">
      <div className="flex items-start gap-3">
        {isExecutablePlan(preview) ? <ShieldCheck aria-hidden className="mt-0.5 size-5 shrink-0 text-status-success" /> : <ShieldAlert aria-hidden className="mt-0.5 size-5 shrink-0 text-status-warning" />}
        <div className="min-w-0 space-y-1">
          <p className="font-semibold [overflow-wrap:anywhere]">{plan.display_name ?? plan.name}</p>
          <p className="text-sm text-muted-foreground">{planScope(plan, language)}</p>
          {providers.length ? <div className="flex flex-wrap gap-x-4">{providers.map((link) => <InspectLink key={link.href} link={link} language={language} />)}</div> : null}
        </div>
      </div>
      <p className="mt-2 text-xs text-muted-foreground">{c.spaceUnknown}</p>
    </div>
    {(["remove", "retain", "attention"] as const).map((group) => groups[group].length ? <section key={group} aria-label={group === "remove" ? c.changes : copy[group]} className="space-y-2">
      <h3 className="flex items-center gap-2 text-sm font-semibold">{group === "remove" ? c.changes : copy[group]}<Badge variant="secondary">{groups[group].length}</Badge></h3>
      <ul className="divide-y divide-border overflow-hidden rounded-xl border border-border bg-card">
        {groups[group].map((action, index) => <ActionTarget key={`${action.system}-${action.action}-${index}`} action={action} preview={preview} language={language} services={services} />)}
      </ul>
    </section> : null)}
    {plan.actions.some((action) => actionLink(action, plan, services)) ? <p className="text-xs leading-relaxed text-muted-foreground">{c.linkHint}</p> : null}
    <details className="rounded-xl border border-border bg-muted/20 p-3 text-xs">
      <summary className="min-h-8 cursor-pointer content-center rounded-md font-medium focus-visible:outline-2 focus-visible:outline-ring">{c.technical}</summary>
      <div className="mt-3 space-y-4">
        <p className="leading-relaxed text-muted-foreground">{c.size}</p>
        {displayText(plan.fingerprint?.path) ? <dl className="space-y-1"><dt className="text-muted-foreground">{c.mediaPath}</dt><dd className="font-mono [overflow-wrap:anywhere]">{displayText(plan.fingerprint.path)}</dd></dl> : null}
        {plan.actions.map((action, index) => {
          const facts = actionFacts(action, language)
          return <div key={index} className="border-t border-border pt-3">
            <p className="mb-2 font-medium [overflow-wrap:anywhere]">{index + 1}. {localizedSystemLabel(action.system, language)} · {actionTarget(action, plan, language)}</p>
            <dl className="grid grid-cols-1 gap-x-3 gap-y-1.5 sm:grid-cols-[9rem_minmax(0,1fr)]">
              <dt className="text-muted-foreground">{c.operation}</dt><dd className="font-mono [overflow-wrap:anywhere]">{action.action}</dd>
              {facts.map((fact, position) => <Fact key={`${fact.label}-${position}`} {...fact} />)}
              {action.reason ? <Fact label={c.reason} value={action.reason} /> : null}
            </dl>
            {!facts.length ? <p className="mt-2 text-muted-foreground">{c.noDetails}</p> : null}
          </div>
        })}
      </div>
    </details>
  </div>
}

function Fact({ label, value }: { label: string; value: string }) {
  return <><dt className="text-muted-foreground">{label}</dt><dd className="min-w-0 font-mono [overflow-wrap:anywhere]">{value}</dd></>
}

function InspectLink({ link, language }: { link: InspectionLink; language: DeletionLanguage }) {
  const c = planCopy[language]
  return <a href={link.href} target="_blank" rel="noopener noreferrer" referrerPolicy="no-referrer" className="inline-flex min-h-9 items-center gap-1.5 rounded-sm text-xs font-medium text-primary underline-offset-4 hover:underline focus-visible:outline-2 focus-visible:outline-ring" aria-label={`${link.item ? c.openItem : c.openService}: ${link.label}`}>
    {link.item ? c.openItem : c.openService} · {link.label}<ExternalLink aria-hidden className="size-3.5 shrink-0" />
  </a>
}

function ActionTarget({ action, preview, language, services }: { action: DashboardAction; preview: ManualDeletePreviewResponse; language: DeletionLanguage; services: InspectionService[] }) {
  const c = planCopy[language]
  const { plan } = preview
  const profile = displayText(action.details.downloader_name ?? action.details.client_name ?? action.details.radarr_instance_name ?? action.details.sonarr_instance_name)
  const system = localizedSystemLabel(action.system, language)
  const serviceLabel = profile?.toLowerCase().startsWith(system.toLowerCase()) ? profile : `${system}${profile ? ` · ${profile}` : ""}`
  const path = displayText(action.details.content_path ?? action.details.path ?? action.details.download_directory)
  const link = actionLink(action, plan, services)
  return <li className="min-w-0 space-y-2 p-3 sm:p-4">
    <div className="flex flex-wrap items-center justify-between gap-2">
      <p className="min-w-0 text-xs text-muted-foreground [overflow-wrap:anywhere]">{serviceLabel}</p>
      {actionGroup(action) !== "remove" ? <Badge variant="outline" className="text-[10px]">{localizedActionLabel(action, language)}</Badge> : null}
    </div>
    <p className="text-sm font-semibold leading-snug [overflow-wrap:anywhere]">{actionTarget(action, plan, language)}</p>
    <p className="text-sm leading-relaxed text-muted-foreground">{actionEffect(action, language)}</p>
    {action.action === "delete_hash" && !displayText(action.details.torrent_name) ? <p className="text-xs text-muted-foreground">{c.noName}</p> : null}
    {path ? <dl className="space-y-1 rounded-md bg-muted/50 px-2.5 py-2 text-xs"><dt className="text-muted-foreground">{action.details.content_path ? c.dataPath : action.details.path ? c.mediaPath : c.downloadDirectory}</dt><dd className="font-mono [overflow-wrap:anywhere]">{path}</dd></dl> : action.action === "delete_hash" ? <p className="text-xs text-muted-foreground">{c.noPath}</p> : null}
    {link ? <InspectLink link={link} language={language} /> : null}
  </li>
}
