import { useCallback, useEffect, useRef, type RefObject } from "react"
import { Zap } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Dialog, DialogBackdrop, DialogDescription, DialogPopup, DialogPortal, DialogTitle } from "@/components/ui/dialog"
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
  const stepSavers = useRef(new Map<number, () => Promise<boolean>>())
  const registerStepSaver = useCallback((step: number, saver: () => Promise<boolean>) => {
    stepSavers.current.set(step, saver)
    return () => {
      if (stepSavers.current.get(step) === saver) stepSavers.current.delete(step)
    }
  }, [])
  const saveBeforeLeavingStep = useCallback(async (currentStep: number) => {
    const save = stepSavers.current.get(currentStep)
    return save ? save() : true
  }, [])
  useEffect(() => {
    const returnFocusTarget = returnFocusRef?.current
    return () => returnFocusTarget?.focus()
  }, [returnFocusRef])

  return (
    <Dialog open onOpenChange={(open) => { if (!open) onClose() }}>
      <DialogPortal>
        <DialogBackdrop data-testid="setup-wizard-backdrop" className="fixed inset-0 z-50 bg-background/98 backdrop-blur-sm" />
        <div className="pointer-events-none fixed inset-0 z-50 flex items-center justify-center p-4">
      <DialogPopup initialFocus={skipRef} finalFocus={returnFocusRef} className="pointer-events-auto flex max-h-[calc(100dvh-2rem)] w-full max-w-3xl flex-col overflow-hidden rounded-2xl border border-border bg-background shadow-2xl outline-none [&_[data-slot=button]]:min-h-11">
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

        <div role="region" aria-label={text.firstTimeSetup} tabIndex={0} className="setup-wizard__viewport min-h-0 flex-1 overflow-y-auto px-4 py-4 outline-none focus-visible:ring-3 focus-visible:ring-inset focus-visible:ring-ring/50 sm:px-6 sm:py-5">
        <Stepper
          onFinalStepCompleted={onClose}
          onBeforeStepChange={saveBeforeLeavingStep}
          nextButtonText={text.next}
          backButtonText={text.back}
          completeButtonText={text.done}
          stepLabel={text.setup}
          stepCircleContainerClassName="border-border bg-card shadow-sm"
          stepContainerClassName="border-b border-border bg-background py-3 sm:py-4"
          contentClassName="px-4 pt-4 sm:px-6 sm:pt-5"
          footerClassName="px-4 pb-4 sm:px-6 sm:pb-5"
        >
          {/* Step 1: General */}
          <Step>
            <WizardGeneralStep config={config} onSave={onSaveGeneral} text={text} registerSave={(save) => registerStepSaver(1, save)} />
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
              registerSave={(save) => registerStepSaver(2, save)}
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
              registerSave={(save) => registerStepSaver(3, save)}
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
              registerSave={(save) => registerStepSaver(4, save)}
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
              registerSave={(save) => registerStepSaver(5, save)}
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
              registerSave={(save) => registerStepSaver(6, save)}
            />
          </Step>
        </Stepper>
        </div>
      </DialogPopup>
        </div>
      </DialogPortal>
    </Dialog>
  )
}
