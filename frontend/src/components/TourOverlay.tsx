import { useEffect, useId, useLayoutEffect, useRef, useState } from 'react'
import { useTour } from '../context/TourContext'
import { medir, anchoVentana, altoVentana, type RectoSinEscalar } from '../utils/uiScale'
import { siguienteFoco } from '../utils/foco'

const ENFOCABLES = 'button:not([disabled]), a[href], [tabindex]:not([tabindex="-1"])'

interface TourOverlayProps {
  activePage: string
  navigate: (page: string) => void
}

const BUBBLE_WIDTH = 340
const BUBBLE_MARGIN = 14
// Alto supuesto de la burbuja hasta medirla tras el primer pintado (mide entre 190 y 260 px según el texto).
const BUBBLE_HEIGHT_GUESS = 180
const WAIT_TIMEOUT_MS = 4000

// Finds `selector`'s bounding rect, polling (it may not be mounted yet — a
// tour step usually just switched tabs, and the new page's content can take
// a moment to fetch/render) or a zero-size rect (mounted but still empty
// while its own data loads). Gives up after WAIT_TIMEOUT_MS and resolves
// null, so a step whose target genuinely never appears still lets the tour
// continue (centered, no spotlight) instead of getting stuck forever.
function waitForRect(selector: string, onFound: (rect: RectoSinEscalar) => void): () => void {
  let cancelled = false
  const start = performance.now()
  function poll() {
    if (cancelled) return
    const el = document.querySelector<HTMLElement>(selector)
    if (el) {
      // medir() y no getBoundingClientRect(): el recorte y la burbuja se
      // posicionan con estos números dentro del body escalado. Ver uiScale.
      const rect = medir(el)
      if (rect.width > 0 && rect.height > 0) {
        // Un objetivo que cabe en la ventana pero está fuera de la parte visible (en el móvil, una tarjeta más abajo)
        // se trae a la vista antes de medirlo; uno más alto que la ventana (una página entera) se deja donde está.
        const caja = el.getBoundingClientRect()
        if (caja.height < window.innerHeight && (caja.top < 0 || caja.bottom > window.innerHeight)) {
          el.scrollIntoView({ block: 'center' })
          requestAnimationFrame(() => { if (!cancelled) onFound(medir(el)) })
        } else {
          onFound(rect)
        }
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

function placeBubble(rect: RectoSinEscalar | null, placement?: 'top-center', alto = BUBBLE_HEIGHT_GUESS): { top: number; left: number } {
  if (placement === 'top-center') {
    return { top: BUBBLE_MARGIN + 56, left: anchoVentana() / 2 - BUBBLE_WIDTH / 2 }
  }
  if (!rect) {
    return { top: altoVentana() / 2 - alto / 2, left: anchoVentana() / 2 - BUBBLE_WIDTH / 2 }
  }
  // Con el alto real de la burbuja: encima del objetivo acaba justo antes de él, y no lo tapa.
  const spaceBelow = altoVentana() - rect.bottom
  const spaceAbove = rect.top
  const cabeDebajo = spaceBelow >= alto + 2 * BUBBLE_MARGIN
  const cabeEncima = spaceAbove >= alto + 2 * BUBBLE_MARGIN
  let top: number
  if (cabeDebajo || (!cabeEncima && spaceBelow >= spaceAbove)) {
    top = rect.bottom + BUBBLE_MARGIN
  } else {
    top = rect.top - BUBBLE_MARGIN - alto
  }
  // Si no cabe ni encima ni debajo (un objetivo muy alto), al menos entera dentro de la ventana.
  top = Math.max(BUBBLE_MARGIN, Math.min(top, altoVentana() - alto - BUBBLE_MARGIN))
  let left = rect.left
  if (left + BUBBLE_WIDTH > anchoVentana() - BUBBLE_MARGIN) {
    left = anchoVentana() - BUBBLE_WIDTH - BUBBLE_MARGIN
  }
  left = Math.max(BUBBLE_MARGIN, left)
  return { top, left }
}

export function TourOverlay({ activePage, navigate }: TourOverlayProps) {
  const { active, stepIndex, steps, next, prev, close } = useTour()
  const [rect, setRect] = useState<RectoSinEscalar | null>(null)
  const step = steps[stepIndex]
  const burbuja = useRef<HTMLDivElement>(null)
  const idTitulo = useId()
  const [alto, setAlto] = useState(BUBBLE_HEIGHT_GUESS)

  // La burbuja se mide tras pintarla (el texto de cada paso le da otro alto) y se vuelve a colocar antes de que se vea.
  // offsetHeight va sin la escala de la interfaz, como los números de medir().
  useLayoutEffect(() => {
    const h = burbuja.current?.offsetHeight
    if (h && h !== alto) setAlto(h)
  }, [active, stepIndex, alto])

  useEffect(() => {
    if (!active || !step) return
    setRect(null)
    if (step.tab && step.tab !== activePage) {
      navigate(step.tab)
    }
    const cancel = waitForRect(step.selector, setRect)
    return cancel
    // eslint-disable-next-line react-hooks/exhaustive-deps -- solo al cambiar de paso, no con cada pintado
  }, [active, stepIndex])

  useEffect(() => {
    if (!active || !step) return
    const onResize = () => {
      const el = document.querySelector<HTMLElement>(step.selector)
      if (el) setRect(medir(el))
      // Con otro ancho el texto puede ocupar más líneas: la burbuja se vuelve a medir.
      const h = burbuja.current?.offsetHeight
      if (h) setAlto(h)
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

  // Es un diálogo: al abrirse el foco entra en la burbuja y al cerrarse vuelve a quien lo abrió; Tab no sale a la página
  // de detrás (el velo ya bloquea el ratón, pero no el teclado).
  useEffect(() => {
    if (!active) return
    const antes = document.activeElement instanceof HTMLElement ? document.activeElement : null
    burbuja.current?.focus()
    return () => { if (antes?.isConnected) antes.focus() }
  }, [active])

  // Al cambiar de paso, si el botón que tenía el foco ya no existe (Atrás en el primer paso), el foco vuelve a la burbuja.
  useEffect(() => {
    const el = burbuja.current
    if (active && el && !el.contains(document.activeElement)) el.focus()
  }, [active, stepIndex])

  useEffect(() => {
    if (!active) return
    const onTab = (e: KeyboardEvent) => {
      const el = burbuja.current
      if (e.key !== 'Tab' || !el) return
      const lista = [...el.querySelectorAll<HTMLElement>(ENFOCABLES)]
      const actual = document.activeElement as HTMLElement | null
      // El panel mismo (tabindex -1) cuenta como "fuera de la lista": entra por el borde que toca.
      const destino = siguienteFoco(lista, actual && lista.includes(actual) ? actual : null, e.shiftKey)
      if (destino) { e.preventDefault(); destino.focus() }
    }
    document.addEventListener('keydown', onTab)
    return () => document.removeEventListener('keydown', onTab)
  }, [active])

  if (!active || !step) return null

  const { top, left } = placeBubble(rect, step.placement, alto)
  const isLast = stepIndex === steps.length - 1

  return (
    <div className={`tour-backdrop${rect ? '' : ' no-target'}`}>
      {rect && (
        <div
          className="tour-cutout"
          style={{ top: rect.top - 6, left: rect.left - 6, width: rect.width + 12, height: rect.height + 12 }}
        />
      )}
      <div
        ref={burbuja}
        className="tour-bubble"
        style={{ top, left }}
        role="dialog"
        aria-modal="true"
        aria-labelledby={idTitulo}
        tabIndex={-1}
      >
        {/* Región viva: al pasar de paso con el foco en «Siguiente», el lector de pantalla lee el paso nuevo */}
        <div aria-live="polite" aria-atomic="true">
          <div className="tour-bubble-title" id={idTitulo}>{step.title}</div>
          <div className="tour-bubble-desc">{step.description}</div>
        </div>
        <div className="tour-bubble-footer">
          <span className="tour-bubble-counter">Paso {stepIndex + 1} de {steps.length}</span>
          <div className="tour-bubble-actions">
            {/* Cerrar no destruye nada: fantasma, no rojo. Atrás, secundario. Solo Siguiente es principal. */}
            <button className="btn btn-ghost btn-sm" onClick={close}>Cerrar</button>
            {stepIndex > 0 && (
              <button className="btn btn-secondary btn-sm" onClick={prev}>Atrás</button>
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
