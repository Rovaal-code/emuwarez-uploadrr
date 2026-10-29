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
    <div style={{ marginTop: 28, flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}>
      <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 8, flexShrink: 0, display: 'flex', alignItems: 'center', gap: 2 }}>
        {title}
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
        <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>Cargando…</div>
      ) : children.length === 0 ? (
        <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>{emptyLabel}</div>
      ) : (
        <div className="activity-section" style={{ marginBottom: 0, flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}>
          {/* Fills the remaining space below the detail page's fixed-height
              content (poster/fields/comparison) — same fill+internal-scroll
              pattern as Biblioteca's own list table. */}
          <div style={{ overflow: 'auto', flex: 1, minHeight: 0 }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th style={{ width: '100%' }}>Título</th>
                  <th>Tipo</th>
                  <th>Origen</th>
                  <th>Estado</th>
                  <th>Petición</th>
                  <th>Resolución</th>
                  <th>Proveedor</th>
                  <th>Source</th>
                  <th>Español</th>
                  <th>EMuwarez</th>
                  <th>Tamaño</th>
                  <th>Acciones</th>
                </tr>
              </thead>
              <tbody>
                {children.map(child => (
                  <LibraryTreeRow key={child.id} item={child} depth={0} instances={instances} onSelect={onSelect} onAction={onAction} onReload={() => setReloadKey(k => k + 1)} />
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
