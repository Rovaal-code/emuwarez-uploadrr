import { useState, useCallback, useRef, useLayoutEffect, useEffect, useId, isValidElement, cloneElement } from 'react'
import { createPortal } from 'react-dom'
import { sinEscalar, anchoVentana, medir } from '../utils/uiScale'
import { crearRegistroDescripciones } from '../utils/descripcionesCompartidas'

// Custom hover tooltip styled like the app's cards (opaque surface, not the
// native browser title box). Rendered in a fixed-position portal just below
// the cursor, so it is never clipped by table/overflow containers.

// Hover dwell before a tooltip appears (ms). The box shows only after the
// cursor has rested on the target for this long.
const HOVER_DELAY_MS = 1000

// clientX/clientY vienen en el espacio escalado por el zoom del body, y de aquí
// salen para un style.top/left, que se vuelve a escalar. Se guardan ya
// convertidos, para que todo lo demás trabaje en un solo espacio. Ver
// utils/uiScale.
function punto(e: React.MouseEvent) {
  return { x: sinEscalar(e.clientX), y: sinEscalar(e.clientY) }
}

// Las descripciones de texto van todas en un solo contenedor oculto al final
// del body, una por texto distinto (ver utils/descripcionesCompartidas).
let contenedorDescripciones: HTMLDivElement | null = null
const descripciones = crearRegistroDescripciones((id, texto) => {
  if (!contenedorDescripciones) {
    contenedorDescripciones = document.createElement('div')
    contenedorDescripciones.hidden = true
    document.body.appendChild(contenedorDescripciones)
  }
  const el = document.createElement('span')
  el.id = id
  el.textContent = texto
  contenedorDescripciones.appendChild(el)
  return el
})

export function useTooltip(content: React.ReactNode, maxWidth = 460) {
  const [show, setShow] = useState(false)
  const [pt, setPt] = useState({ x: 0, y: 0 })
  const ref = useRef<HTMLDivElement>(null)
  const timer = useRef<number | null>(null)
  // La descripción oculta existe antes del foco, para que aria-describedby
  // apunte a algo cuando el lector de pantalla pregunta. Si es texto (casi
  // siempre) se comparte con los demás disparadores que dicen lo mismo; si es
  // contenido con marcado, cada tooltip lleva la suya en el portal.
  const idPropio = useId()
  const texto = typeof content === 'string' || typeof content === 'number' ? String(content) : null
  const id = texto != null ? descripciones.idDe(texto) : idPropio
  useLayoutEffect(() => {
    if (texto == null) return
    descripciones.montar(texto, id)
    return () => descripciones.soltar(texto)
  }, [texto, id])
  // El control que tiene el foco cuando no es el propio disparador (<Tooltip>
  // envuelve al botón en un <span>, y el foco cae en el botón de dentro), con
  // el aria-describedby que ya traía, para devolvérselo al salir.
  const descrito = useRef<{ el: Element; previo: string | null } | null>(null)
  // Ratón y foco van por separado: el tooltip sigue abierto mientras quede
  // cualquiera de los dos, y Escape lo cierra siempre.
  const hover = useRef(false)
  const foco = useRef(false)

  const ocultar = useCallback(() => {
    if (timer.current) { window.clearTimeout(timer.current); timer.current = null }
    setShow(false)
  }, [])
  const track = useCallback((e: React.MouseEvent) => setPt(punto(e)), [])
  const open = useCallback((e: React.MouseEvent) => {
    hover.current = true
    if (foco.current) return
    setPt(punto(e))
    if (timer.current) window.clearTimeout(timer.current)
    timer.current = window.setTimeout(() => setShow(true), HOVER_DELAY_MS)
  }, [])
  const leave = useCallback(() => {
    hover.current = false
    if (!foco.current) ocultar()
  }, [ocultar])
  // Con el teclado no hay cursor ni espera: el foco lo abre al momento, bajo
  // el disparador. El foco puede caer en un hijo (el evento sube), así que se
  // mira e.target, y si no es el disparador se le añade la descripción a las
  // que ya tuviera.
  const openOnFocus = useCallback((e: React.FocusEvent) => {
    const enfocado = e.target as Element
    if (!enfocado.matches(':focus-visible')) return
    foco.current = true
    const previo = enfocado.getAttribute('aria-describedby')
    if (enfocado !== e.currentTarget && !previo?.split(/\s+/).includes(id)) {
      enfocado.setAttribute('aria-describedby', previo ? `${previo} ${id}` : id)
      descrito.current = { el: enfocado, previo }
    }
    const r = medir(e.currentTarget)
    if (timer.current) { window.clearTimeout(timer.current); timer.current = null }
    setPt({ x: r.left + r.width / 2, y: r.bottom - 8 })
    setShow(true)
  }, [id])
  const closeOnBlur = useCallback(() => {
    foco.current = false
    if (descrito.current) {
      const { el, previo } = descrito.current
      if (previo == null) el.removeAttribute('aria-describedby')
      else el.setAttribute('aria-describedby', previo)
      descrito.current = null
    }
    if (!hover.current) ocultar()
  }, [ocultar])
  const closeOnEscape = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Escape') ocultar()
  }, [ocultar])

  useEffect(() => () => { if (timer.current) window.clearTimeout(timer.current) }, [])

  // `max-content` capped at maxWidth wraps long text, but leaves the box as wide
  // as the cap even when the wrapped lines are shorter. So after it wraps, we
  // measure the LONGEST actually-rendered line and shrink the box to it — the
  // box then hugs the text on every line. Then clamp the position on screen.
  useLayoutEffect(() => {
    const el = ref.current
    if (!show || !el) return
    el.style.width = 'max-content'
    const range = document.createRange()
    range.selectNodeContents(el)
    let longest = 0
    for (const r of range.getClientRects()) longest = Math.max(longest, sinEscalar(r.width))
    if (longest > 0) {
      // + horizontal padding (24px) + border (2px)
      el.style.width = `${Math.ceil(longest) + 26}px`
    }
    const half = el.offsetWidth / 2
    const clamped = Math.min(Math.max(pt.x, half + 6), anchoVentana() - half - 6)
    el.style.left = `${clamped}px`
  }, [show, pt.x, pt.y])

  const triggerProps = {
    onMouseEnter: open,
    onMouseMove: track,
    onMouseLeave: leave,
    onFocus: openOnFocus,
    onBlur: closeOnBlur,
    onKeyDown: closeOnEscape,
    'aria-describedby': content != null ? id : undefined,
  }

  // El portal solo existe mientras se ve el tooltip, salvo con contenido con
  // marcado, que lleva ahí su descripción oculta. Va al final del body: el
  // tooltipNode se pone a veces dentro de una tabla, donde un <span> suelto no
  // es HTML válido.
  const tooltipNode = content != null && (show || texto == null)
    ? createPortal(
        <>
        {texto == null && <span id={id} hidden>{content}</span>}
        {show && <div
          ref={ref}
          role="tooltip"
          style={{
            position: 'fixed',
            top: pt.y + 14,          // just below the cursor
            left: pt.x,              // centred under the cursor; useLayoutEffect
            transform: 'translateX(-50%)',  // then clamps it onto the screen
            width: 'max-content',    // hug the text; cap at maxWidth
            maxWidth,
            whiteSpace: 'normal',
            zIndex: 2000,
            background: 'var(--bg-surface)',   // opaque
            border: '1px solid var(--border)',
            borderRadius: 10,
            boxShadow: 'var(--shadow-modal)',
            padding: '10px 12px',
            fontSize: 12.5,
            lineHeight: 1.45,
            color: 'var(--text-secondary)',
            textAlign: 'left',
            pointerEvents: 'none',
          }}
        >
          {content}
        </div>}
        </>,
        document.body,
      )
    : null

  return { triggerProps, tooltipNode }
}

export function Tooltip({ content, children, style, maxWidth }: {
  content: React.ReactNode
  children: React.ReactNode
  style?: React.CSSProperties
  maxWidth?: number
}) {
  const { triggerProps, tooltipNode } = useTooltip(content, maxWidth)
  const { 'aria-describedby': descripcion, ...eventos } = triggerProps
  // Lo normal es envolver un solo botón: la descripción va en él desde el
  // primer render, que es quien recibe el foco, y no en el <span> de fuera.
  // Con otros hijos se queda en el <span>, y openOnFocus la enlaza al control
  // que reciba el foco. Un botón desactivado no recibe el foco, y justo ahí el
  // tooltip explica por qué lo está: entonces el foco y la descripción pasan
  // al <span>.
  const unHijo = isValidElement<{ 'aria-describedby'?: string; disabled?: boolean }>(children)
  const hijoDesactivado = unHijo && children.props.disabled === true
  const enHijo = unHijo && !hijoDesactivado
  const hijo = enHijo && descripcion
    ? cloneElement(children, {
        'aria-describedby': [children.props['aria-describedby'], descripcion].filter(Boolean).join(' '),
      })
    : children
  return (
    <span
      {...eventos}
      tabIndex={hijoDesactivado && descripcion ? 0 : undefined}
      aria-describedby={enHijo ? undefined : descripcion}
      style={{ display: 'inline-flex', alignItems: 'center', ...style }}
    >
      {hijo}
      {tooltipNode}
    </span>
  )
}

// Drop-in replacement for a plain element with a native `title=` attribute —
// same tag/className/style/onClick, just with the app's own styled tooltip
// instead of the browser's default box. Exists so a title-link rendered
// inside a `.map()` (where a hook can't be called directly) still gets one:
// this is a real component instance per row, so its own useTooltip() call
// is perfectly legal.
export function HoverTitle({ as = 'div', className, style, onClick, onMouseDown, onMouseUp, tip, children }: {
  as?: 'div' | 'span'
  className?: string
  style?: React.CSSProperties
  onClick?: (e: React.SyntheticEvent) => void
  onMouseDown?: (e: React.MouseEvent) => void
  onMouseUp?: (e: React.MouseEvent) => void
  tip: string
  children: React.ReactNode
}) {
  const { triggerProps, tooltipNode } = useTooltip(tip)
  const Tag = as as 'div'
  // Con onClick es un enlace (abre una ficha o una subida): se alcanza con
  // Tab y se abre con Intro, igual que con el ratón.
  const comoEnlace = onClick
    ? {
        role: 'link',
        tabIndex: 0,
        onKeyDown: (e: React.KeyboardEvent) => {
          triggerProps.onKeyDown(e)
          if (e.key === 'Enter') onClick(e)
        },
      }
    : {}
  return (
    <Tag className={className} style={style} onClick={onClick} onMouseDown={onMouseDown} onMouseUp={onMouseUp} {...triggerProps} {...comoEnlace}>
      {children}
      {tooltipNode}
    </Tag>
  )
}
