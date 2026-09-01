import { useEffect, useRef, type RefObject } from "react"

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
      <DialogPopup initialFocus={skipRef} finalFocus={returnFocusRef} className="pointer-events-auto flex max-h-[calc(100dvh-2rem)] w-full max-w-4xl flex-col overflow-hidden rounded-xl border bg-background outline-none">
        <DialogTitle className="sr-only">{text.firstTimeSetup}</DialogTitle>
        <DialogDescription className="sr-only">{text.firstTimeSetup}</DialogDescription>
        {/* Header */}
        <div className="flex shrink-0 items-center justify-between px-6 pt-6">
          <div>
          <div className="flex items-center gap-2 text-base"><svg width="18" height="18" viewBox="0 0 48 48" fill="none" className="text-primary"><path d="M28,6 L8,28 L24,28 L22,42 L40,20 L24,20 Z" fill="currentColor" /></svg><span><span className="font-light text-foreground">Clean</span><span className="font-bold text-primary">Arr</span></span></div>
            <p className="mt-1 text-sm text-muted-foreground">
              {text.firstTimeSetup}
            </p>
          </div>
          <Button ref={skipRef} variant="ghost" size="sm" onClick={onClose}>
            {text.skipForNow}
          </Button>
        </div>

        <ScrollArea className="min-h-0 flex-1" viewportClassName="h-full px-6 pb-6">
        <Stepper
          onFinalStepCompleted={onClose}
          nextButtonText={text.next}
          backButtonText={text.back}
          completeButtonText={text.done}
          stepLabel={text.setup}
          stepCircleContainerClassName="bg-card"
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
