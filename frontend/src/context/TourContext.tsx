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
  // Forces the bubble to the top-center of the screen instead of hugging the
  // target's edge — needed when the target is (near) the whole page, since
  // there's no room above/below it that wouldn't cover the page's own title.
  placement?: 'top-center'
  // El objetivo vive en la barra lateral, que en el móvil es un cajón cerrado: el paso se salta (ver `pasosDelTour`).
  soloEscritorio?: boolean
}

interface StartOptions {
  // Called once, when the tour closes (via "Cerrar" or reaching the last
  // step) — the caller decides what that means (e.g. AppShell marks the
  // one-time "ya visto" flag only for the automatic first run; the manual
  // relaunch from the Info button passes none).
  onClose?: () => void
}

interface TourContextValue {
  active: boolean
  stepIndex: number
  steps: TourStep[]
  start: (steps: TourStep[], opts?: StartOptions) => void
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
  const onCloseRef = useRef<(() => void) | undefined>(undefined)

  const start = useCallback((newSteps: TourStep[], opts?: StartOptions) => {
    onCloseRef.current = opts?.onClose
    setSteps(newSteps)
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

  const value: TourContextValue = { active, stepIndex, steps, start, next, prev, close }
  return <TourContext.Provider value={value}>{children}</TourContext.Provider>
}
