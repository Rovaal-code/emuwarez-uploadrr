import { useEffect, useState } from 'react'
import { useTour } from '../context/TourContext'

interface TourOverlayProps {
  activePage: string
  navigate: (page: string) => void
}

const BUBBLE_WIDTH = 340
const BUBBLE_MARGIN = 14
const WAIT_TIMEOUT_MS = 4000

// Finds `selector`'s bounding rect, polling (it may not be mounted yet — a
// tour step usually just switched tabs, and the new page's content can take
// a moment to fetch/render) or a zero-size rect (mounted but still empty
// while its own data loads). Gives up after WAIT_TIMEOUT_MS and resolves
// null, so a step whose target genuinely never appears still lets the tour
// continue (centered, no spotlight) instead of getting stuck forever.
function waitForRect(selector: string, onFound: (rect: DOMRect) => void): () => void {
  let cancelled = false
  const start = performance.now()
  function poll() {
    if (cancelled) return
    const el = document.querySelector<HTMLElement>(selector)
    if (el) {
      const rect = el.getBoundingClientRect()
      if (rect.width > 0 && rect.height > 0) {
        onFound(rect)
        return
      }
    }
    if (performance.now() - start < WAIT_TIMEOUT_MS) {
      requestAnimationFrame(poll)
    }
  }
  poll()
  return () => { cancelled = true }
}

function placeBubble(rect: DOMRect | null, placement?: 'top-center'): { top: number; left: number } {
  if (placement === 'top-center') {
    return { top: BUBBLE_MARGIN + 56, left: window.innerWidth / 2 - BUBBLE_WIDTH / 2 }
  }
  if (!rect) {
    return { top: window.innerHeight / 2 - 90, left: window.innerWidth / 2 - BUBBLE_WIDTH / 2 }
  }
  const spaceBelow = window.innerHeight - rect.bottom
  const spaceAbove = rect.top
  let top: number
  if (spaceBelow >= 200 || spaceBelow >= spaceAbove) {
    top = rect.bottom + BUBBLE_MARGIN
  } else {
    top = Math.max(BUBBLE_MARGIN, rect.top - BUBBLE_MARGIN - 180)
  }
  let left = rect.left
  if (left + BUBBLE_WIDTH > window.innerWidth - BUBBLE_MARGIN) {
    left = window.innerWidth - BUBBLE_WIDTH - BUBBLE_MARGIN
  }
  left = Math.max(BUBBLE_MARGIN, left)
  return { top, left }
}

export function TourOverlay({ activePage, navigate }: TourOverlayProps) {
  const { active, stepIndex, steps, next, prev, close } = useTour()
  const [rect, setRect] = useState<DOMRect | null>(null)
  const step = steps[stepIndex]

  useEffect(() => {
    if (!active || !step) return
    setRect(null)
    if (step.tab && step.tab !== activePage) {
      navigate(step.tab)
    }
    const cancel = waitForRect(step.selector, setRect)
    return cancel
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, stepIndex])

  useEffect(() => {
    if (!active || !step) return
    const onResize = () => {
      const el = document.querySelector<HTMLElement>(step.selector)
      if (el) setRect(el.getBoundingClientRect())
    }
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [active, step])

  useEffect(() => {
    if (!active) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') close()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [active, close])

  if (!active || !step) return null

  const { top, left } = placeBubble(rect, step.placement)
  const isLast = stepIndex === steps.length - 1

  return (
    <div className={`tour-backdrop${rect ? '' : ' no-target'}`}>
      {rect && (
        <div
          className="tour-cutout"
          style={{ top: rect.top - 6, left: rect.left - 6, width: rect.width + 12, height: rect.height + 12 }}
        />
      )}
      <div className="tour-bubble" style={{ top, left }}>
        <div className="tour-bubble-title">{step.title}</div>
        <div className="tour-bubble-desc">{step.description}</div>
        <div className="tour-bubble-footer">
          <span className="tour-bubble-counter">Paso {stepIndex + 1} de {steps.length}</span>
          <div className="tour-bubble-actions">
            <button className="btn btn-danger btn-sm" onClick={close}>Cerrar</button>
            {stepIndex > 0 && (
              <button className="btn btn-sm" onClick={prev}>Atrás</button>
            )}
            <button className="btn btn-primary btn-sm" onClick={next}>
              {isLast ? 'Finalizar' : 'Siguiente'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
