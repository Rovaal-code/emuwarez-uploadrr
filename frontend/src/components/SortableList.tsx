import { useLayoutEffect, useRef, useState } from 'react'
import { medir, type RectoSinEscalar } from '../utils/uiScale'
import { moverConTecla } from '../utils/reordenar'
import { IconoDesplegar } from './Iconos'

// 1×1 transparent GIF used to hide the browser's default (shrunk/translucent)
// drag ghost — the feedback is the in-list illumination + slide instead.
const TRANSPARENT_IMG = typeof Image !== 'undefined'
  ? (() => { const i = new Image(); i.src = 'data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7'; return i })()
  : null

export interface DragHandleProps {
  onMouseDown: () => void
  onMouseUp: () => void
  // Con el teclado: la asa se alcanza con Tab, y las flechas (o Inicio/Fin)
  // mueven la fila. Quien la pinta solo tiene que pasarle todo esto.
  onKeyDown: (e: React.KeyboardEvent) => void
  tabIndex: number
  role: 'button'
  'aria-label': string
  'data-asa': string
  style: React.CSSProperties
}

// 6-dot grip icon for the drag handle — an SVG instead of a text glyph
// ("⠿") on purpose: a Braille-pattern character's vertical metrics vary by
// font and often sit off the text baseline, so it never quite centers
// against a plain digit/icon next to it no matter how the surrounding box
// is aligned. An SVG has no such ambiguity — its own geometry centers
// exactly wherever the flex box puts it.
export function DragHandleIcon({ size = 14 }: { size?: number }) {
  return (
    <svg width={size * 0.6} height={size} viewBox="0 0 10 16" fill="currentColor" aria-hidden>
      <circle cx="2.5" cy="2.5" r="1.5" />
      <circle cx="7.5" cy="2.5" r="1.5" />
      <circle cx="2.5" cy="8" r="1.5" />
      <circle cx="7.5" cy="8" r="1.5" />
      <circle cx="2.5" cy="13.5" r="1.5" />
      <circle cx="7.5" cy="13.5" r="1.5" />
    </svg>
  )
}

// La indicación de cómo reordenar, según haya ratón o solo dedo: cada texto se
// ve (y se lee) solo con su puntero, por el CSS de `.sortable-pista-*`.
export function PistaReordenar({ raton, dedo }: { raton: string; dedo: string }) {
  return (
    <>
      <span className="sortable-pista-raton">{raton}</span>
      <span className="sortable-pista-dedo">{dedo}</span>
    </>
  )
}

// A drag-to-reorder list where rows are only grabbable from a handle, the
// grabbed row lights up, the native ghost is hidden, and rows slide to their
// new positions (FLIP animation) as the order changes live under the cursor.
//
// Con el dedo no hay arrastre: el mousedown de compatibilidad llega después
// del touchend, así que la fila nunca llega a ser arrastrable. Por eso cada
// fila trae también `botones`, subir y bajar, que quien la pinta pone junto a
// la asa: con `(pointer: coarse)` el CSS los enseña y esconde la asa.
export function SortableList({ ids, onChange, renderRow, gap = 6, etiqueta = id => id }: {
  ids: string[]
  onChange: (ids: string[]) => void
  renderRow: (id: string, index: number, ctx: { dragging: boolean; handleProps: DragHandleProps; botones: React.ReactNode }) => React.ReactNode
  gap?: number
  // El nombre de cada fila para el lector de pantalla ("Reordenar ImgBB").
  etiqueta?: (id: string) => string
}) {
  const [grabbedId, setGrabbedId] = useState<string | null>(null)
  // Lo que se anuncia al mover con el teclado ("ImgBB: posición 2 de 4").
  const [anuncio, setAnuncio] = useState('')
  // La fila que se acaba de mover con el teclado: al recolocarla, React mueve
  // su nodo y el navegador le quita el foco, así que se le devuelve.
  // El botón de subir o bajar que se pulsó: se le devuelve el foco igual, o al
  // otro si la fila ha llegado al borde y el pulsado se ha desactivado.
  const enfocar = useRef<{ id: string; selector: string; otro?: string } | null>(null)
  const [draggingId, setDraggingId] = useState<string | null>(null)
  const nodeRefs = useRef<Map<string, HTMLElement>>(new Map())
  const prevRects = useRef<Map<string, RectoSinEscalar>>(new Map())
  const prevIds = useRef<string[]>(ids)
  // While a FLIP slide is running, rows carry a transform, so their
  // getBoundingClientRect() reports the ANIMATED position — measuring midpoints
  // or a new FLIP baseline off that scrambles the list. So we don't chain a new
  // reorder until the current slide has settled.
  const FLIP_MS = 170
  const reorderLockUntil = useRef(0)

  // FLIP: animate each row from its previous position to the new one — but ONLY
  // when the ORDER actually changed. Otherwise an unrelated re-render that
  // shifts the whole list (e.g. a save button appearing above it) would look
  // like a reorder and slide every row.
  useLayoutEffect(() => {
    const orderChanged = prevIds.current.length !== ids.length
      || prevIds.current.some((v, i) => v !== ids[i])
    if (orderChanged) {
      nodeRefs.current.forEach((node, id) => {
        const prev = prevRects.current.get(id)
        if (prev) {
          // En espacio sin escalar: dy sale de aquí para meterse en un
          // translateY(px), y el zoom del body lo volvería a escalar, así que
          // las filas se pasarían de largo. Ver utils/uiScale.
          const dy = prev.top - medir(node).top
          if (dy) {
            node.style.transition = 'none'
            node.style.transform = `translateY(${dy}px)`
            requestAnimationFrame(() => {
              node.style.transition = `transform ${FLIP_MS}ms ease`
              node.style.transform = ''
            })
          }
        }
      })
    }
    // Always refresh the baseline so the next reorder measures from where the
    // rows currently are (even after a plain layout shift).
    const map = new Map<string, RectoSinEscalar>()
    nodeRefs.current.forEach((node, id) => map.set(id, medir(node)))
    prevRects.current = map
    prevIds.current = ids
    if (enfocar.current) {
      const { id, selector, otro } = enfocar.current
      const fila = nodeRefs.current.get(id)
      const destino = fila?.querySelector<HTMLButtonElement>(selector)
      if (destino && !destino.disabled) destino.focus()
      else if (otro) fila?.querySelector<HTMLElement>(otro)?.focus()
      enfocar.current = null
    }
  }, [ids])

  // Reorder only once the cursor crosses the target row's midpoint in the
  // direction of travel. Without this, moving over an adjacent row ping-pongs
  // (the moved row lands under the cursor and immediately triggers a move back).
  function handleDragOver(e: React.DragEvent<HTMLDivElement>, targetId: string) {
    e.preventDefault()
    if (!draggingId || draggingId === targetId) return
    // Ignore hovers while the previous slide animates — the rects are mid-flight
    // and would produce a bogus reorder (and scramble the FLIP baseline).
    if (performance.now() < reorderLockUntil.current) return
    const from = ids.indexOf(draggingId)
    const to = ids.indexOf(targetId)
    if (from < 0 || to < 0) return
    // Aquí sí vale getBoundingClientRect() a secas: e.clientY viene en el
    // mismo espacio escalado, y de los dos solo sale una proporción, que es
    // igual con zoom y sin él.
    const rect = e.currentTarget.getBoundingClientRect()
    const past = (e.clientY - rect.top) / rect.height  // 0 = top … 1 = bottom
    if (to > from && past < 0.5) return  // going down, not past the midpoint yet
    if (to < from && past > 0.5) return  // going up, not past the midpoint yet
    const list = [...ids]
    list.splice(from, 1)
    list.splice(to, 0, draggingId)
    reorderLockUntil.current = performance.now() + FLIP_MS + 40
    onChange(list)
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap }}>
      <div className="solo-lector" role="status" aria-live="polite">{anuncio}</div>
      {ids.map((id, index) => {
        // Teclado y botones mueven igual y anuncian lo mismo.
        const mover = (tecla: string) => {
          const nueva = moverConTecla(ids, id, tecla)
          if (!nueva) return
          setAnuncio(`${etiqueta(id)}: posición ${nueva.indexOf(id) + 1} de ${nueva.length}`)
          onChange(nueva)
        }
        const handleProps: DragHandleProps = {
          onMouseDown: () => setGrabbedId(id),
          onMouseUp: () => setGrabbedId(null),
          onKeyDown: e => {
            if (!moverConTecla(ids, id, e.key)) return
            e.preventDefault()
            enfocar.current = { id, selector: '[data-asa]' }
            mover(e.key)
          },
          tabIndex: 0,
          role: 'button',
          'aria-label': `Reordenar ${etiqueta(id)}`,
          'data-asa': id,
          style: { cursor: 'grab', userSelect: 'none' },
        }
        const botones = (
          <span className="sortable-mover">
            <button type="button" className="sortable-mover__btn" data-mover="subir"
              aria-label={`Subir ${etiqueta(id)}`} disabled={index === 0}
              onClick={() => { enfocar.current = { id, selector: '[data-mover="subir"]', otro: '[data-mover="bajar"]' }; mover('ArrowUp') }}
            ><IconoDesplegar abierto={false} size={16} style={{ transform: 'rotate(-90deg)' }} /></button>
            <button type="button" className="sortable-mover__btn" data-mover="bajar"
              aria-label={`Bajar ${etiqueta(id)}`} disabled={index === ids.length - 1}
              onClick={() => { enfocar.current = { id, selector: '[data-mover="bajar"]', otro: '[data-mover="subir"]' }; mover('ArrowDown') }}
            ><IconoDesplegar abierto size={16} /></button>
          </span>
        )
        return (
          <div
            key={id}
            ref={n => { if (n) nodeRefs.current.set(id, n); else nodeRefs.current.delete(id) }}
            draggable={grabbedId === id}
            onDragStart={e => {
              setDraggingId(id)
              if (TRANSPARENT_IMG) e.dataTransfer.setDragImage(TRANSPARENT_IMG, 0, 0)
              e.dataTransfer.effectAllowed = 'move'
            }}
            onDragOver={e => handleDragOver(e, id)}
            onDragEnd={() => { setDraggingId(null); setGrabbedId(null) }}
          >
            {renderRow(id, index, { dragging: grabbedId === id || draggingId === id, handleProps, botones })}
          </div>
        )
      })}
    </div>
  )
}
