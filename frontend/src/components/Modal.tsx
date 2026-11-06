import { useEffect, useId, useRef, useState } from 'react'
import { useTooltip } from './Tooltip'
import { IconoCerrar } from './Iconos'
import { destinoAlCerrar, siguienteFoco } from '../utils/foco'

const ENFOCABLES = 'a[href], button:not([disabled]), input:not([disabled]):not([type="hidden"]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'

// Los modales abiertos, el de arriba al final: el asistente de subida abre
// MediaInfo encima de sí mismo, y Escape o Tab solo son para el de arriba.
const abiertos: HTMLElement[] = []

// Adónde devolvía el foco cada modal ya cerrado, por su panel. Si un modal se
// abre desde un botón de otro que se cierra en ese mismo paso, al cerrarse
// el segundo el foco vuelve a donde lo habría devuelto el primero.
const devolvia = new WeakMap<HTMLElement, HTMLElement | null>()

// Todos los modales de la app. Es un diálogo de verdad: el lector anuncia su
// título, el foco entra al abrirlo y vuelve a donde estaba al cerrarlo, Tab no
// se sale a la página de detrás y Escape lo cierra, igual que pulsar fuera.
export function Modal({ titulo, onClose, className, style, tituloStyle, children }: {
  titulo: React.ReactNode
  onClose: () => void
  // Clases además de modal-panel (modal-wide).
  className?: string
  style?: React.CSSProperties
  tituloStyle?: React.CSSProperties
  children: React.ReactNode
}) {
  const panel = useRef<HTMLDivElement>(null)
  const idTitulo = useId()
  const cerrarTip = useTooltip('Cerrar')
  // El listener se pone una vez al abrir; con esto llama siempre al onClose
  // del último render aunque quien llama pase una función nueva cada vez.
  const cerrar = useRef(onClose)
  cerrar.current = onClose

  // Se lee en el primer render: ahí el foco sigue en quien abrió el modal.
  const [antes] = useState(() => document.activeElement instanceof HTMLElement ? document.activeElement : null)

  useEffect(() => {
    const el = panel.current
    if (!el) return
    abiertos.push(el)
    // Un hijo con autoFocus ya tiene el foco: no se lo quitamos.
    if (!el.contains(document.activeElement)) el.focus()
    const teclas = (e: KeyboardEvent) => {
      if (e.defaultPrevented || abiertos[abiertos.length - 1] !== el) return
      if (e.key === 'Escape') {
        e.preventDefault()
        cerrar.current()
      } else if (e.key === 'Tab') {
        const lista = [...el.querySelectorAll<HTMLElement>(ENFOCABLES)].filter(n => n.getClientRects().length > 0)
        const destino = siguienteFoco(lista, document.activeElement as HTMLElement | null, e.shiftKey)
        if (destino) { e.preventDefault(); destino.focus() }
        else if (lista.length === 0) e.preventDefault()
      }
    }
    document.addEventListener('keydown', teclas)
    return () => {
      document.removeEventListener('keydown', teclas)
      abiertos.splice(abiertos.indexOf(el), 1)
      devolvia.set(el, antes)
      destinoAlCerrar(antes, quitado => {
        const suPanel = quitado.closest<HTMLElement>('.modal-panel')
        return suPanel ? devolvia.get(suPanel) : null
      })?.focus()
    }
  }, [antes])

  // Pulsar fuera cierra, pero solo si el gesto entero (pulsar y soltar) fue sobre el velo: arrastrar para seleccionar texto
  // desde dentro del panel y soltar fuera no debe cerrarlo. Se cierra al soltar (click) y no al pulsar: en el móvil, quitar el
  // velo al tocar dejaba que el toque cayera en el botón que había debajo.
  const empezoEnElVelo = useRef(false)

  return (
    <div
      className="modal-overlay"
      onPointerDown={e => { empezoEnElVelo.current = e.button === 0 && e.target === e.currentTarget }}
      onClick={e => { if (empezoEnElVelo.current && e.target === e.currentTarget) onClose(); empezoEnElVelo.current = false }}
    >
      <div
        ref={panel}
        className={className ? `modal-panel ${className}` : 'modal-panel'}
        role="dialog"
        aria-modal="true"
        aria-labelledby={idTitulo}
        tabIndex={-1}
        style={style}
        onMouseDown={e => e.stopPropagation()}
        onClick={e => e.stopPropagation()}
      >
        <div className="modal-header">
          <h2 className="modal-title" id={idTitulo} style={tituloStyle}>{titulo}</h2>
          <button type="button" className="modal-close" aria-label="Cerrar" aria-keyshortcuts="Escape" onClick={onClose} {...cerrarTip.triggerProps}>
            <IconoCerrar />{cerrarTip.tooltipNode}
          </button>
        </div>
        {children}
      </div>
    </div>
  )
}
