import { useState, useEffect } from 'react'
import { getLibrary } from '../api/library'
import type { LibraryItemResponse, InstanceSafeResponse } from '../types/api'
import { LibraryTreeRow, type LibraryActionKind } from './LibraryTreeRow'
import { useTooltip } from './Tooltip'

// Direct children (seasons of a series, or episodes of a season) shown below an
// item's detail panel — reuses LibraryTreeRow unchanged, just seeded with the
// parent's children instead of a top-level list. Shared by the Series detail
// (Temporadas) and the Season detail (Capítulos).
export function LibraryChildrenSection({ parentId, childType, title, instances, onSelect, onAction, fichaPlegada, onAlternarFicha }: {
  parentId: number
  childType: 'season' | 'episode'
  title: string
  instances: InstanceSafeResponse[]
  onSelect: (item: LibraryItemResponse) => void
  onAction: (kind: LibraryActionKind, item: LibraryItemResponse) => void
  // Pliega la ficha de arriba (póster y las tres tarjetas) para que esta tabla
  // se quede con el alto que ocupaban. La lleva el padre porque lo que se
  // pliega vive allí; aquí solo está el botón, que es donde el usuario lo
  // busca: al lado del título de la tabla que quiere agrandar.
  fichaPlegada?: boolean
  onAlternarFicha?: () => void
}) {
  const [children, setChildren] = useState<LibraryItemResponse[]>([])
  const [loading, setLoading] = useState(true)
  const [reloadKey, setReloadKey] = useState(0)

  useEffect(() => {
    setLoading(true)
    getLibrary({ parent_id: parentId, type: childType, limit: 500 })
      .then(r => setChildren(r.items))
      .catch(() => setChildren([]))
      .finally(() => setLoading(false))
  }, [parentId, childType, reloadKey])

  const emptyLabel = childType === 'season' ? 'Sin temporadas' : 'Sin capítulos'

  const ampliarTip = useTooltip(
    onAlternarFicha
      ? (fichaPlegada ? 'Volver a mostrar la ficha' : 'Plegar la ficha para agrandar la tabla')
      : null)

  return (
    <div className="hijos-seccion">
      <div className="hijos-titulo">
        <h2 className="hijos-nombre">{title}</h2>
        {!loading && children.length > 0 && <span className="hijos-cuenta">{children.length}</span>}
        {/* La flecha apunta a donde va a ir la tabla: arriba para comerse el
            hueco de la ficha, abajo para devolvérselo. Mismo .tree-expander
            que el desplegable de las filas en la lista, para que se lea como
            el mismo gesto. */}
        {onAlternarFicha && (
          <button
            type="button"
            className="tree-expander"
            onClick={onAlternarFicha}
            aria-expanded={!fichaPlegada}
            aria-label={fichaPlegada ? 'Volver a mostrar la ficha' : 'Plegar la ficha para agrandar la tabla'}
            {...ampliarTip.triggerProps}
          >
            {fichaPlegada ? '▼' : '▲'}
            {ampliarTip.tooltipNode}
          </button>
        )}
      </div>
      {loading ? (
        <div className="hijos-aviso">Cargando…</div>
      ) : children.length === 0 ? (
        <div className="hijos-aviso">{emptyLabel}</div>
      ) : (
        <div className="activity-section hijos-caja">
          {/* Fills the remaining space below the detail page's fixed-height
              content (poster/fields/comparison) — same fill+internal-scroll
              pattern as Biblioteca's own list table. */}
          <div className="hijos-scroll">
            <table className="data-table bib-tabla">
              <thead>
                <tr>
                  <th className="hijos-col-titulo">Título</th>
                  <th>Origen</th>
                  <th>Estado</th>
                  <th>Petición</th>
                  <th>Resolución</th>
                  <th>Proveedor</th>
                  <th>Fuente</th>
                  <th>Grupo</th>
                  <th>Español</th>
                  <th>eMuwarez</th>
                  <th>Tamaño</th>
                  <th className="col-actions">Acciones</th>
                </tr>
              </thead>
              <tbody>
                {children.map(child => (
                  <LibraryTreeRow key={child.id} item={child} depth={0} instances={instances} onSelect={onSelect} onAction={onAction} onReload={() => setReloadKey(k => k + 1)} tituloCorto />
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
