import React, {
  useState,
  useCallback,
  Children,
  useRef,
  useLayoutEffect,
  type HTMLAttributes,
  type ReactNode,
} from "react"
import { motion, AnimatePresence, type Variants } from "motion/react"
import { useReducedMotion } from "motion/react"
import { Check, LoaderCircle } from "lucide-react"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

interface StepperProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode
  initialStep?: number
  onStepChange?: (step: number) => void
  onFinalStepCompleted?: () => void
  onBeforeStepChange?: (currentStep: number, nextStep: number) => boolean | void | Promise<boolean | void>
  stepCircleContainerClassName?: string
  stepContainerClassName?: string
  contentClassName?: string
  footerClassName?: string
  backButtonProps?: React.ButtonHTMLAttributes<HTMLButtonElement>
  nextButtonProps?: React.ButtonHTMLAttributes<HTMLButtonElement>
  backButtonText?: string
  nextButtonText?: string
  completeButtonText?: string
  stepLabel?: string
  disableStepIndicators?: boolean
  renderStepIndicator?: (props: {
    step: number
    currentStep: number
    onStepClick: (clicked: number) => void
  }) => ReactNode
}

export default function Stepper({
  children,
  initialStep = 1,
  onStepChange = () => {},
  onFinalStepCompleted = () => {},
  onBeforeStepChange,
  stepCircleContainerClassName = "",
  stepContainerClassName = "",
  contentClassName = "",
  footerClassName = "",
  backButtonProps = {},
  nextButtonProps = {},
  backButtonText = "Back",
  nextButtonText = "Continue",
  completeButtonText = nextButtonText,
  stepLabel = "Step",
  disableStepIndicators = false,
  renderStepIndicator,
  ...rest
}: StepperProps) {
  const [currentStep, setCurrentStep] = useState<number>(initialStep)
  const [direction, setDirection] = useState<number>(0)
  const [isTransitioning, setIsTransitioning] = useState(false)
  const stepsArray = Children.toArray(children)
  const totalSteps = stepsArray.length
  const isCompleted = currentStep > totalSteps
  const isLastStep = currentStep === totalSteps
  const reduceMotion = useReducedMotion()

  const updateStep = (newStep: number) => {
    setCurrentStep(newStep)
    if (newStep > totalSteps) {
      onFinalStepCompleted()
    } else {
      onStepChange(newStep)
    }
  }

  const requestStep = async (nextStep: number) => {
    if (isTransitioning || nextStep === currentStep) return
    setIsTransitioning(true)
    try {
      const proceed = await onBeforeStepChange?.(currentStep, nextStep)
      if (proceed === false) return
      setDirection(nextStep > currentStep ? 1 : -1)
      updateStep(nextStep)
    } finally {
      setIsTransitioning(false)
    }
  }

  return (
    <div className="flex flex-col" data-slot="stepper" data-reduced-motion={reduceMotion ? "true" : "false"} aria-busy={isTransitioning || undefined} {...rest}>
      <div
        className={`w-full overflow-hidden rounded-2xl border bg-card shadow-sm ${stepCircleContainerClassName}`}
      >
        <div className={`${stepContainerClassName} flex w-full items-center px-2 py-6 sm:px-8`}>
          {stepsArray.map((_, index) => {
            const stepNumber = index + 1
            const isNotLastStep = index < totalSteps - 1
            return (
              <React.Fragment key={stepNumber}>
                {renderStepIndicator ? (
                  renderStepIndicator({
                    step: stepNumber,
                    currentStep,
                    onStepClick: (clicked) => {
                      void requestStep(clicked)
                    },
                  })
                ) : (
                  <StepIndicator
                    step={stepNumber}
                    stepLabel={stepLabel}
                    disableStepIndicators={disableStepIndicators || isTransitioning}
                    currentStep={currentStep}
                    onClickStep={(clicked) => {
                      void requestStep(clicked)
                    }}
                  />
                )}
                {isNotLastStep && (
                  <StepConnector
                    isComplete={currentStep > stepNumber}
                    reduceMotion={Boolean(reduceMotion)}
                  />
                )}
              </React.Fragment>
            )
          })}
        </div>

        <StepContentWrapper
          isCompleted={isCompleted}
          currentStep={currentStep}
          direction={direction}
          reduceMotion={Boolean(reduceMotion)}
          className={`space-y-2 px-8 ${contentClassName}`}
        >
          {stepsArray[currentStep - 1]}
        </StepContentWrapper>

        {!isCompleted && (
          <div className={`px-8 pb-8 ${footerClassName}`}>
            <div
              className={`mt-8 flex ${currentStep !== 1 ? "justify-between" : "justify-end"}`}
            >
              {currentStep !== 1 && (
                <Button
                  variant="ghost"
                  size="sm"
                  {...backButtonProps}
                  disabled={isTransitioning || backButtonProps.disabled}
                  onClick={() => void requestStep(currentStep - 1)}
                >
                  {backButtonText}
                </Button>
              )}
              <Button
                {...nextButtonProps}
                disabled={isTransitioning || nextButtonProps.disabled}
                onClick={() => void requestStep(isLastStep ? totalSteps + 1 : currentStep + 1)}
              >
                {isTransitioning ? <LoaderCircle className="size-4 animate-spin" aria-hidden="true" /> : null}
                {isLastStep ? completeButtonText : nextButtonText}
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

interface StepContentWrapperProps {
  isCompleted: boolean
  currentStep: number
  direction: number
  reduceMotion: boolean
  children: ReactNode
  className?: string
}

function StepContentWrapper({
  isCompleted,
  currentStep,
  direction,
  reduceMotion,
  children,
  className = "",
}: StepContentWrapperProps) {
  const [parentHeight, setParentHeight] = useState<number>(0)
  const onHeightReady = useCallback((h: number) => setParentHeight(h), [])

  return (
    <motion.div
      style={{ position: "relative", overflow: "hidden" }}
      animate={{ height: isCompleted ? 0 : parentHeight }}
      transition={{ type: "tween", ease: "easeInOut", duration: reduceMotion ? 0 : 0.35 }}
    >
      <AnimatePresence initial={false} mode="sync" custom={direction}>
        {!isCompleted && (
          <SlideTransition
            key={currentStep}
            direction={direction}
            reduceMotion={reduceMotion}
            className={className}
            onHeightReady={onHeightReady}
          >
            {children}
          </SlideTransition>
        )}
      </AnimatePresence>
    </motion.div>
  )
}

interface SlideTransitionProps {
  children: ReactNode
  direction: number
  onHeightReady: (height: number) => void
  className?: string
  reduceMotion: boolean
}

function SlideTransition({ children, direction, onHeightReady, className = "", reduceMotion }: SlideTransitionProps) {
  const containerRef = useRef<HTMLDivElement | null>(null)

  useLayoutEffect(() => {
    const el = containerRef.current
    if (!el) return
    onHeightReady(el.offsetHeight)
    if (typeof ResizeObserver === "undefined") return
    const observer = new ResizeObserver(() => onHeightReady(el.offsetHeight))
    observer.observe(el)
    return () => observer.disconnect()
  }, [onHeightReady])

  return (
    <motion.div
      ref={containerRef}
      custom={direction}
      variants={stepVariants}
      initial="enter"
      animate="center"
      exit="exit"
      transition={{ duration: reduceMotion ? 0 : 0.4 }}
      style={{ position: "absolute", left: 0, right: 0, top: 0 }}
      className={className}
    >
      {children}
    </motion.div>
  )
}

const stepVariants: Variants = {
  enter: (dir: number) => ({
    x: dir >= 0 ? "100%" : "-100%",
    opacity: 0,
  }),
  center: {
    x: "0%",
    opacity: 1,
  },
  exit: (dir: number) => ({
    x: dir >= 0 ? "-50%" : "50%",
    opacity: 0,
  }),
}

export interface StepProps {
  children: ReactNode
}

export function Step({ children }: StepProps) {
  return <div className="pb-2">{children}</div>
}

interface StepIndicatorProps {
  step: number
  stepLabel: string
  currentStep: number
  onClickStep: (clicked: number) => void
  disableStepIndicators?: boolean
}

function StepIndicator({
  step,
  stepLabel,
  currentStep,
  onClickStep,
  disableStepIndicators = false,
}: StepIndicatorProps) {
  const status =
    currentStep === step ? "active" : currentStep < step ? "inactive" : "complete"

  return (
    <button
      type="button"
      disabled={disableStepIndicators}
      aria-current={status === "active" ? "step" : undefined}
      aria-label={`${stepLabel} ${step}`}
      onClick={() => {
        if (step !== currentStep && !disableStepIndicators) {
          onClickStep(step)
        }
      }}
      className="relative rounded-full outline-none focus-visible:ring-3 focus-visible:ring-ring/50 disabled:cursor-not-allowed"
    >
      <div
        className={cn(
          "flex h-9 w-9 items-center justify-center rounded-full text-sm font-semibold transition-colors duration-300",
          status === "inactive" && "bg-muted text-muted-foreground",
          (status === "active" || status === "complete") &&
            "bg-primary text-primary-foreground",
        )}
      >
        {status === "complete" ? (
          <Check className="h-4 w-4" aria-hidden="true" />
        ) : status === "active" ? (
          <div className="h-3 w-3 rounded-full bg-primary-foreground" />
        ) : (
          <span>{step}</span>
        )}
      </div>
    </button>
  )
}

interface StepConnectorProps {
  isComplete: boolean
  reduceMotion: boolean
}

function StepConnector({ isComplete, reduceMotion }: StepConnectorProps) {
  return (
    <div className="relative mx-0.5 h-0.5 flex-1 overflow-hidden rounded bg-muted sm:mx-2">
      <motion.div
        className="absolute left-0 top-0 h-full bg-primary"
        initial={false}
        animate={{ width: isComplete ? "100%" : "0%" }}
        transition={{ duration: reduceMotion ? 0 : 0.4 }}
      />
    </div>
  )
}
