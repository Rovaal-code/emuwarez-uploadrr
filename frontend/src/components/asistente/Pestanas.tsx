// Pestañas del paso «Nombre y pistas» (Nomenclatura, Pistas, MediaInfo). Patrón WAI-ARIA de pestañas con activación
// automática: las flechas, Inicio y Fin mueven el foco y abren la pestaña; solo la activa está en el orden de Tab, y de
// ella se baja al panel. El panel activo es lo único que se pinta: lo editado y lo cargado vive en el asistente
// (useAsistente), no en el panel, así que cambiar de pestaña no pierde nada.
import { useId, useRef, type KeyboardEvent, type ReactNode } from 'react'

export interface Pestana<T extends string> {
  id: T
  etiqueta: string
  // Un aviso corto junto al nombre (p. ej. «1 sin idioma»); el lector lo oye tras el nombre.
  aviso?: string
}

export function Pestanas<T extends string>({ nombre, pestanas, activa, onCambiar, children }: {
  // El nombre de la lista de pestañas para el lector.
  nombre: string
  pestanas: Pestana<T>[]
  activa: T
  onCambiar: (id: T) => void
  // El contenido de la pestaña activa.
  children: ReactNode
}) {
  const base = useId()
  const botones = useRef<(HTMLButtonElement | null)[]>([])
  const idPestana = (id: string) => `${base}-pestana-${id}`
  const idPanel = (id: string) => `${base}-panel-${id}`

  const alTeclear = (e: KeyboardEvent<HTMLButtonElement>, i: number) => {
    const n = pestanas.length
    const destino =
      e.key === 'ArrowRight' ? (i + 1) % n
      : e.key === 'ArrowLeft' ? (i - 1 + n) % n
      : e.key === 'Home' ? 0
      : e.key === 'End' ? n - 1
      : null
    if (destino == null) return
    e.preventDefault()
    botones.current[destino]?.focus()
    onCambiar(pestanas[destino].id)
  }

  return (
    <div className="asist-pestanas">
      <div role="tablist" aria-label={nombre} className="asist-pestanas-lista">
        {pestanas.map((p, i) => {
          const esActiva = p.id === activa
          return (
            <button
              key={p.id}
              ref={el => { botones.current[i] = el }}
              type="button"
              role="tab"
              id={idPestana(p.id)}
              aria-selected={esActiva}
              aria-controls={esActiva ? idPanel(p.id) : undefined}
              tabIndex={esActiva ? 0 : -1}
              className={esActiva ? 'asist-pestana asist-pestana-activa' : 'asist-pestana'}
              onClick={() => onCambiar(p.id)}
              onKeyDown={e => alTeclear(e, i)}
            >
              {p.etiqueta}
              {p.aviso && <span className="asist-pestana-aviso"><span className="solo-lector">: </span>{p.aviso}</span>}
            </button>
          )
        })}
      </div>
      <div role="tabpanel" id={idPanel(activa)} aria-labelledby={idPestana(activa)} tabIndex={0} className="asist-pestana-panel">
        {children}
      </div>
    </div>
  )
}
