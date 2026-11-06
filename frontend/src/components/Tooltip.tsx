import { useState, useCallback, useRef, useLayoutEffect, useEffect, useId, isValidElement, cloneElement } from 'react'
import { createPortal } from 'react-dom'
import { sinEscalar, anchoVentana, altoVentana, medir } from '../utils/uiScale'
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
  // Si el texto cambia mientras ese hijo sigue con el foco, cambia el id de la
  // descripción (y la vieja puede haberse quitado): se le pone el nuevo,
  // conservando lo que traía de antes.
  useLayoutEffect(() => {
    const d = descrito.current
    if (d) d.el.setAttribute('aria-describedby', d.previo ? `${d.previo} ${id}` : id)
  }, [id])
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
    // Sin ratón (móvil, tableta) un toque genera un «mouseenter» que nadie retira: el tooltip se quedaba pegado en
    // pantalla hasta tocar en otro sitio. Ahí solo se muestra con el foco del teclado.
    if (window.matchMedia?.('(hover: none)').matches) return
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
  // Con el dedo (sin hover) un toque abre y cierra la explicación, anclada bajo el disparador como con el teclado, y se
  // cierra al tocar fuera o con Escape. Solo cuando el toque no es la acción de un control: si lo tocado es un enlace o
  // un botón (también una asa de arrastre, que es role="button"), o va dentro de una fila que se abre al tocarla
  // (`.clickable`), el toque hace lo suyo. Una ayuda que es un botón (el «?» de InfoIcon) lo dice con `data-ayuda`.
  // Un disparador informativo (un HoverTitle sin onClick, una tarjeta de cifra) sí se abre. Se usa pointerup y no click para no pisar el onClick de quien reparte
  // triggerProps; un desplazamiento termina en pointercancel, así que deslizar el dedo no lo abre.
  const disparador = useRef<Element | null>(null)
  const porToque = useRef(false)
  const alToque = useCallback((e: React.PointerEvent) => {
    if (e.pointerType === 'mouse' || !window.matchMedia?.('(hover: none)').matches) return
    const control = (e.target as Element).closest?.('a[href], button, input, select, textarea, summary, label, [role="button"], [role="link"], .clickable')
    if (control && !control.hasAttribute('data-ayuda') && !(control as HTMLButtonElement).disabled) return
    if (show) { ocultar(); return }
    disparador.current = e.currentTarget
    porToque.current = true
    const r = medir(e.currentTarget)
    if (timer.current) { window.clearTimeout(timer.current); timer.current = null }
    setPt({ x: r.left + r.width / 2, y: r.bottom - 8 })
    setShow(true)
  }, [show, ocultar])
  useEffect(() => {
    if (!show || !porToque.current) return
    const fuera = (e: PointerEvent) => {
      if (disparador.current && e.target instanceof Node && disparador.current.contains(e.target)) return
      ocultar()
    }
    const escape = (e: KeyboardEvent) => { if (e.key === 'Escape') ocultar() }
    document.addEventListener('pointerdown', fuera, true)
    document.addEventListener('keydown', escape)
    return () => {
      document.removeEventListener('pointerdown', fuera, true)
      document.removeEventListener('keydown', escape)
      porToque.current = false
    }
  }, [show, ocultar])

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
    // Si no cabe debajo (una tarjeta pegada al borde de abajo), se abre por encima del cursor.
    if (pt.y + 14 + el.offsetHeight > altoVentana() - 6) el.style.top = `${Math.max(6, pt.y - 14 - el.offsetHeight)}px`
  }, [show, pt.x, pt.y])

  const triggerProps = {
    onMouseEnter: open,
    onMouseMove: track,
    onMouseLeave: leave,
    onFocus: openOnFocus,
    onBlur: closeOnBlur,
    onKeyDown: closeOnEscape,
    onPointerUp: alToque,
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
// Atributos sueltos que también se pueden pasar (role, tabIndex, aria-*,
// onKeyDown, data-*): los usa, por ejemplo, la asa de una lista reordenable.
type AtributosExtra = Omit<React.HTMLAttributes<HTMLElement>, 'onClick' | 'onMouseDown' | 'onMouseUp' | 'children' | 'style' | 'className'>
  & { [dato: `data-${string}`]: string | undefined }

export function HoverTitle({ as = 'div', href, className, style, onClick, onMouseDown, onMouseUp, tip, children, onKeyDown, ...resto }: {
  as?: 'div' | 'span'
  /** Con onClick: la ruta a la que lleva. Se pinta un enlace de verdad (<a href>), así que el clic central y Ctrl/⌘+clic
   *  abren esa ruta en otra pestaña; el clic normal hace preventDefault y llama a onClick (la navegación de la SPA). */
  href?: string
  className?: string
  style?: React.CSSProperties
  onClick?: (e: React.SyntheticEvent) => void
  onMouseDown?: (e: React.MouseEvent) => void
  onMouseUp?: (e: React.MouseEvent) => void
  tip: string
  children: React.ReactNode
} & AtributosExtra) {
  const { triggerProps, tooltipNode } = useTooltip(tip)
  // Las teclas pasan por todos: Escape cierra el tooltip y el onKeyDown de quien llama hace lo suyo. Intro ya lo
  // resuelven el <a> y el <button> nativos (disparan el clic).
  const teclas = (e: React.KeyboardEvent<HTMLElement>) => {
    triggerProps.onKeyDown(e)
    onKeyDown?.(e)
  }
  // El toque que abre el tooltip va también aquí: como enlace o botón (con onClick) no hace nada, porque el toque es
  // su acción, y dentro de una fila `.clickable` tampoco; solo abre el de un HoverTitle informativo.
  const comunes = { style, onMouseDown, onMouseUp, ...resto, ...triggerProps, onKeyDown: teclas }
  // Con as="div" el enlace ocupa su línea, como el div de antes.
  const bloque = as === 'div' ? ' titulo-bloque' : ''
  if (onClick && href) {
    // Clic con modificador o con otro botón: lo hace el navegador (otra pestaña o ventana), y no sube a la fila,
    // que si no abriría el detalle también en esta pestaña.
    const alPulsar = (e: React.MouseEvent<HTMLAnchorElement>) => {
      if (e.defaultPrevented) return
      if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) {
        e.stopPropagation()
        return
      }
      e.preventDefault()
      onClick(e)
    }
    return (
      <a href={href} className={clases('enlace-titulo' + bloque, className)} onClick={alPulsar} {...comunes}>
        {children}
        {tooltipNode}
      </a>
    )
  }
  if (onClick) {
    // Sin ruta propia es una acción: botón, con el aspecto del texto que lo rodea.
    return (
      <button type="button" className={clases('boton-titulo' + bloque, className)} onClick={onClick} {...comunes}>
        {children}
        {tooltipNode}
      </button>
    )
  }
  const Tag = as as 'div'
  return (
    <Tag className={className} {...comunes}>
      {children}
      {tooltipNode}
    </Tag>
  )
}

function clases(base: string, extra?: string): string {
  return extra ? `${base} ${extra}` : base
}
