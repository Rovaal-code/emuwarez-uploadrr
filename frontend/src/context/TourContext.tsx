import { createContext, useCallback, useContext, useRef, useState } from 'react'

// A single spotlight step: `tab` (a VALID_PAGES id from AppShell.tsx) is the
// page the tour must be on before this step shows — omitted when the target
// lives outside the page body (the sidebar's system-status gauges, the
// topbar buttons) and is already visible no matter which tab is active.
// `selector` is a CSS selector for the one real DOM element to highlight.
export interface TourStep {
  id: string
  tab?: string
  selector: string
  title: string
  description: string
}

interface StartOptions {
  skippable: boolean
  // Called once, when the tour closes (via "Finalizar" on the last step, or
  // "Saltar" if skippable) — the caller decides what that means (e.g. AppShell
  // marks the one-time "ya visto" flag only for the mandatory first run; the
  // manual relaunch from the Info button passes none).
  onClose?: () => void
}

interface TourContextValue {
  active: boolean
  stepIndex: number
  steps: TourStep[]
  skippable: boolean
  start: (steps: TourStep[], opts: StartOptions) => void
  next: () => void
  prev: () => void
  close: () => void
}

const TourContext = createContext<TourContextValue | null>(null)

export function useTour(): TourContextValue {
  const ctx = useContext(TourContext)
  if (!ctx) throw new Error('useTour must be used within <TourProvider>')
  return ctx
}

export function TourProvider({ children }: { children: React.ReactNode }) {
  const [active, setActive] = useState(false)
  const [stepIndex, setStepIndex] = useState(0)
  const [steps, setSteps] = useState<TourStep[]>([])
  const [skippable, setSkippable] = useState(true)
  const onCloseRef = useRef<(() => void) | undefined>(undefined)

  const start = useCallback((newSteps: TourStep[], opts: StartOptions) => {
    onCloseRef.current = opts.onClose
    setSteps(newSteps)
    setSkippable(opts.skippable)
    setStepIndex(0)
    setActive(true)
  }, [])

  const close = useCallback(() => {
    setActive(false)
    onCloseRef.current?.()
    onCloseRef.current = undefined
  }, [])

  const next = useCallback(() => {
    setStepIndex(i => {
      if (i + 1 >= steps.length) {
        close()
        return i
      }
      return i + 1
    })
  }, [steps.length, close])

  const prev = useCallback(() => {
    setStepIndex(i => Math.max(0, i - 1))
  }, [])

  const value: TourContextValue = { active, stepIndex, steps, skippable, start, next, prev, close }
  return <TourContext.Provider value={value}>{children}</TourContext.Provider>
}
