import { useState } from 'react'
import {
  MAX_NOMBRE_VISTA, hayAlgoQueGuardar, mismosFiltros, type FiltrosDeVista, type VistaGuardada,
} from '../utils/vistasBiblioteca'

/** Las vistas guardadas de Biblioteca, una insignia cada una, y el botón para guardar la combinación de filtros de ahora. */
export function VistasGuardadas({ vistas, actual, onAplicar, onGuardar, onQuitar }: {
  vistas: VistaGuardada[]
  actual: FiltrosDeVista
  onAplicar: (vista: VistaGuardada) => void
  onGuardar: (nombre: string) => void
  onQuitar: (vista: VistaGuardada) => void
}) {
  const [poniendoNombre, setPoniendoNombre] = useState(false)
  const [nombre, setNombre] = useState('')
  const yaGuardada = vistas.some(v => mismosFiltros(v.filtros, actual))

  const cerrar = () => { setPoniendoNombre(false); setNombre('') }
  const guardar = () => {
    if (!nombre.trim()) return
    onGuardar(nombre)
    cerrar()
  }

  return (
    <>
      {vistas.map(v => {
        const activa = mismosFiltros(v.filtros, actual)
        return (
          <span key={v.id} className={`bib-vista${activa ? ' activa' : ''}`}>
            <button type="button" className="bib-vista-nombre" aria-pressed={activa} title={`Volver a la vista «${v.nombre}»`} onClick={() => onAplicar(v)}>
              {v.nombre}
            </button>
            <button type="button" className="bib-vista-quitar" aria-label={`Quitar la vista «${v.nombre}»`} title="Quitar la vista" onClick={() => onQuitar(v)}>
              ×
            </button>
          </span>
        )
      })}
      {poniendoNombre ? (
        <form className="bib-vista-nueva" onSubmit={e => { e.preventDefault(); guardar() }}>
          <input
            className="form-input bib-vista-nombre-campo"
            name="nombre-vista"
            autoComplete="off"
            placeholder="Ej.: Sin subir en 1080p…"
            aria-label="Nombre de la vista"
            maxLength={MAX_NOMBRE_VISTA}
            value={nombre}
            autoFocus
            onChange={e => setNombre(e.target.value)}
            onKeyDown={e => { if (e.key === 'Escape') cerrar() }}
          />
          <button type="submit" className="btn btn-primary btn-sm" disabled={!nombre.trim()}>Guardar</button>
          <button type="button" className="btn btn-secondary btn-sm" onClick={cerrar}>Cancelar</button>
        </form>
      ) : hayAlgoQueGuardar(actual) && !yaGuardada && (
        <button type="button" className="btn btn-secondary btn-sm" title="Guarda los filtros, la búsqueda y el orden de ahora" onClick={() => setPoniendoNombre(true)}>
          + Guardar vista
        </button>
      )}
    </>
  )
}
