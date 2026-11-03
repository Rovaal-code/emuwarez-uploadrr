import { useEffect, useRef, useState } from 'react'
import { Modal } from './Modal'
import { getLibrary, TOP_LEVEL_PARENT_FILTER } from '../api/library'
import type { LibraryItemResponse } from '../types/api'
import { formatItemType } from '../utils/format'
import { filtrarSecciones, moverSeleccion, type Seccion } from '../utils/paleta'

const MIN_LETRAS_BIBLIOTECA = 2
const MAX_RESULTADOS_BIBLIOTECA = 8
const ESPERA_BUSQUEDA_MS = 250

type Opcion =
  | { tipo: 'seccion'; clave: string; seccion: Seccion }
  | { tipo: 'elemento'; clave: string; item: LibraryItemResponse }

/**
 * Paleta de búsqueda (Ctrl+K / Cmd+K): saltar a una sección o abrir la ficha de una película o serie de la
 * Biblioteca escribiendo su nombre. Flechas para moverse, Intro para elegir, Escape para cerrar (lo hace `Modal`).
 */
export function CommandPalette({ secciones, onSeccion, onElemento, onClose }: {
  secciones: Seccion[]
  onSeccion: (id: string) => void
  onElemento: (id: number) => void
  onClose: () => void
}) {
  const [consulta, setConsulta] = useState('')
  const [elementos, setElementos] = useState<LibraryItemResponse[]>([])
  const [buscando, setBuscando] = useState(false)
  const [seleccion, setSeleccion] = useState(0)
  const lista = useRef<HTMLUListElement>(null)

  // Búsqueda en la biblioteca con espera; una respuesta que llega tarde (la consulta ya cambió) se descarta.
  useEffect(() => {
    const q = consulta.trim()
    if (q.length < MIN_LETRAS_BIBLIOTECA) {
      setElementos([])
      setBuscando(false)
      return
    }
    setBuscando(true)
    let vigente = true
    const t = setTimeout(() => {
      getLibrary({ search: q, parent_id: TOP_LEVEL_PARENT_FILTER, limit: MAX_RESULTADOS_BIBLIOTECA })
        .then(r => { if (vigente) setElementos(r.items) })
        .catch(() => { if (vigente) setElementos([]) })
        .finally(() => { if (vigente) setBuscando(false) })
    }, ESPERA_BUSQUEDA_MS)
    return () => { vigente = false; clearTimeout(t) }
  }, [consulta])

  const opciones: Opcion[] = [
    ...filtrarSecciones(secciones, consulta).map(s => ({ tipo: 'seccion' as const, clave: `s-${s.id}`, seccion: s })),
    ...elementos.map(i => ({ tipo: 'elemento' as const, clave: `e-${i.id}`, item: i })),
  ]
  const actual = Math.min(seleccion, Math.max(opciones.length - 1, 0))

  useEffect(() => {
    lista.current?.querySelector('[aria-selected="true"]')?.scrollIntoView?.({ block: 'nearest' })
  }, [actual, opciones.length])

  function elegir(o: Opcion | undefined) {
    if (!o) return
    onClose()
    if (o.tipo === 'seccion') onSeccion(o.seccion.id)
    else onElemento(o.item.id)
  }

  function onKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault()
      setSeleccion(moverSeleccion(actual, e.key === 'ArrowDown' ? 1 : -1, opciones.length))
    } else if (e.key === 'Enter') {
      e.preventDefault()
      elegir(opciones[actual])
    }
  }

  return (
    <Modal titulo="Buscar" onClose={onClose} className="paleta-modal">
      <input
        className="form-input paleta-entrada"
        type="text"
        autoFocus
        value={consulta}
        placeholder="Ir a una sección o buscar en la Biblioteca…"
        aria-label="Buscar"
        role="combobox"
        aria-expanded="true"
        aria-controls="paleta-lista"
        aria-activedescendant={opciones[actual] ? `paleta-${opciones[actual].clave}` : undefined}
        onChange={e => { setConsulta(e.target.value); setSeleccion(0) }}
        onKeyDown={onKeyDown}
      />
      <ul className="paleta-lista" id="paleta-lista" role="listbox" ref={lista}>
        {opciones.map((o, i) => (
          <li
            key={o.clave}
            id={`paleta-${o.clave}`}
            role="option"
            aria-selected={i === actual}
            className={`paleta-opcion${i === actual ? ' paleta-activa' : ''}`}
            onMouseMove={() => setSeleccion(i)}
            onClick={() => elegir(o)}
          >
            {o.tipo === 'seccion' ? (
              <>
                <span className="paleta-titulo">{o.seccion.titulo}</span>
                <span className="paleta-etiqueta">Sección</span>
              </>
            ) : (
              <>
                <span className="paleta-titulo">{o.item.title}{o.item.year ? ` (${o.item.year})` : ''}</span>
                <span className="paleta-etiqueta">{formatItemType(o.item.item_type)}</span>
              </>
            )}
          </li>
        ))}
        {opciones.length === 0 && (
          <li className="paleta-vacio" role="presentation">
            {buscando ? 'Buscando…' : `Nada que coincida con «${consulta.trim()}».`}
          </li>
        )}
        {opciones.length > 0 && buscando && <li className="paleta-vacio" role="presentation">Buscando en la Biblioteca…</li>}
      </ul>
      <p className="paleta-ayuda">↑ ↓ para moverte · Intro para abrir · Esc para cerrar</p>
    </Modal>
  )
}
