import { useEffect, useRef, type RefObject } from "react"
import { Zap } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Dialog, DialogBackdrop, DialogDescription, DialogPopup, DialogPortal, DialogTitle } from "@/components/ui/dialog"
import { ScrollArea } from "@/components/ui/scroll-area"
import Stepper, { Step } from "@/components/ui/stepper"
import { WizardGeneralStep, WizardServiceStep } from "@/features/setup/wizard-steps"
import type { DashboardPayload } from "@/lib/dashboard"
import type { UiTextMap } from "@/lib/i18n"
import type { ServiceDraft, ServiceFamily } from "@/lib/service-config"
import type { ConnectionTestResponse, GeneralConfig, RuntimeConfigPayload } from "@/lib/runtime-config"

export function SetupWizard({
  config,
  dashboard,
  origin,
  curlPreview,
  text,
  onSaveGeneral,
  onSaveService,
  onTestService,
  onSetupWebhook,
  onClose,
  returnFocusRef,
  testedDownloaderFingerprints,
}: {
  config: RuntimeConfigPayload | null
  dashboard: DashboardPayload | null
  origin: string
  curlPreview: string
  text: UiTextMap
  onSaveGeneral: (payload: GeneralConfig) => Promise<void>
  onSaveService: (family: ServiceFamily, draft: ServiceDraft) => Promise<void>
  onTestService: (family: ServiceFamily, draft: ServiceDraft) => Promise<ConnectionTestResponse>
  onSetupWebhook: (webhookUrl: string) => Promise<{ found: boolean; configured: boolean; message: string }>
  onClose: () => void
  returnFocusRef?: RefObject<HTMLElement | null>
  testedDownloaderFingerprints: ReadonlySet<string>
}) {
  const skipRef = useRef<HTMLButtonElement>(null)
  useEffect(() => {
    const returnFocusTarget = returnFocusRef?.current
    return () => returnFocusTarget?.focus()
  }, [returnFocusRef])

  return (
    <Dialog open onOpenChange={(open) => { if (!open) onClose() }}>
      <DialogPortal>
        <DialogBackdrop data-testid="setup-wizard-backdrop" className="fixed inset-0 z-50 bg-background/98 backdrop-blur-sm" />
        <div className="pointer-events-none fixed inset-0 z-50 flex items-center justify-center p-4">
      <DialogPopup initialFocus={skipRef} finalFocus={returnFocusRef} className="pointer-events-auto flex max-h-[calc(100dvh-2rem)] w-full max-w-4xl flex-col overflow-hidden rounded-2xl border border-border bg-background shadow-2xl outline-none [&_[data-slot=button]]:min-h-11">
        <DialogTitle className="sr-only">{text.firstTimeSetup}</DialogTitle>
        <DialogDescription className="sr-only">{text.firstTimeSetup}</DialogDescription>
        {/* Header */}
        <div className="flex shrink-0 items-center justify-between border-b border-border bg-card px-5 py-4 sm:px-7">
          <div>
          <div className="flex min-h-11 items-center gap-2 text-base tracking-tight"><Zap aria-hidden="true" className="size-5 rotate-12 text-primary" strokeWidth={1.8} /><span><span className="font-light text-foreground">Clean</span><span className="font-bold text-primary">Arr</span></span></div>
            <p className="mt-1 text-sm text-muted-foreground">
              {text.firstTimeSetup}
            </p>
          </div>
          <Button ref={skipRef} variant="ghost" size="sm" className="min-h-11 px-3" onClick={onClose}>
            {text.skipForNow}
          </Button>
        </div>

        <ScrollArea className="min-h-0 flex-1" viewportClassName="h-full px-4 py-5 sm:px-7 sm:py-6">
        <Stepper
          onFinalStepCompleted={onClose}
          nextButtonText={text.next}
          backButtonText={text.back}
          completeButtonText={text.done}
          stepLabel={text.setup}
          stepCircleContainerClassName="border-border bg-card shadow-sm"
          stepContainerClassName="border-b border-border bg-background py-4 sm:py-5"
          contentClassName="px-4 pt-5 sm:px-7 sm:pt-7"
          footerClassName="px-4 pb-5 sm:px-7 sm:pb-7"
        >
          {/* Step 1: General */}
          <Step>
            <WizardGeneralStep config={config} onSave={onSaveGeneral} text={text} />
          </Step>

          {/* Step 2: Jellyfin */}
          <Step>
            <WizardServiceStep
              family="jellyfin_server"
              config={config}
              text={text}
              onSave={onSaveService}
              onTest={onTestService}
              testedDownloaderFingerprints={testedDownloaderFingerprints}
              jellyfinSetupProps={{
                dashboard,
                origin,
                curlPreview,
                tokenConfigured: Boolean(config?.general.webhook_shared_token),
                onSetupWebhook,
              }}
            />
          </Step>

          {/* Step 3: Radarr */}
          <Step>
            <WizardServiceStep
              family="radarr"
              config={config}
              text={text}
              onSave={onSaveService}
              onTest={onTestService}
              testedDownloaderFingerprints={testedDownloaderFingerprints}
            />
          </Step>

          {/* Step 4: Sonarr */}
          <Step>
            <WizardServiceStep
              family="sonarr"
              config={config}
              text={text}
              onSave={onSaveService}
              onTest={onTestService}
              testedDownloaderFingerprints={testedDownloaderFingerprints}
            />
          </Step>

          {/* Step 5: Seerr */}
          <Step>
            <WizardServiceStep
              family="seerr"
              config={config}
              text={text}
              onSave={onSaveService}
              onTest={onTestService}
              testedDownloaderFingerprints={testedDownloaderFingerprints}
            />
          </Step>

          {/* Step 6: torrent client */}
          <Step>
            <WizardServiceStep
              family="downloaders"
              config={config}
              text={text}
              onSave={onSaveService}
              onTest={onTestService}
              testedDownloaderFingerprints={testedDownloaderFingerprints}
            />
          </Step>
        </Stepper>
        </ScrollArea>
      </DialogPopup>
        </div>
      </DialogPortal>
    </Dialog>
  )
}
