import { useEffect, useId, useRef } from 'react'
import { useTooltip } from './Tooltip'
import { IconoCerrar } from './Iconos'
import { siguienteFoco } from '../utils/foco'

const ENFOCABLES = 'a[href], button:not([disabled]), input:not([disabled]):not([type="hidden"]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'

// Los modales abiertos, el de arriba al final: el asistente de subida abre
// MediaInfo encima de sí mismo, y Escape o Tab solo son para el de arriba.
const abiertos: HTMLElement[] = []

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

  useEffect(() => {
    const el = panel.current
    if (!el) return
    const antes = document.activeElement instanceof HTMLElement ? document.activeElement : null
    abiertos.push(el)
    el.focus()
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
      if (antes?.isConnected) antes.focus()
    }
  }, [])

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div
        ref={panel}
        className={className ? `modal-panel ${className}` : 'modal-panel'}
        role="dialog"
        aria-modal="true"
        aria-labelledby={idTitulo}
        tabIndex={-1}
        style={style}
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
