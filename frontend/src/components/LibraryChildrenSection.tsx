import { useState, useEffect } from 'react'
import { getLibrary } from '../api/library'
import type { LibraryItemResponse, InstanceSafeResponse } from '../types/api'
import { LibraryTreeRow, type LibraryActionKind } from './LibraryTreeRow'

// Direct children (seasons of a series, or episodes of a season) shown below an
// item's detail panel — reuses LibraryTreeRow unchanged, just seeded with the
// parent's children instead of a top-level list. Shared by the Series detail
// (Temporadas) and the Season detail (Capítulos).
export function LibraryChildrenSection({ parentId, childType, title, instances, onSelect, onAction }: {
  parentId: number
  childType: 'season' | 'episode'
  title: string
  instances: InstanceSafeResponse[]
  onSelect: (item: LibraryItemResponse) => void
  onAction: (kind: LibraryActionKind, item: LibraryItemResponse) => void
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

  return (
    <div style={{ marginTop: 28 }}>
      <div style={{ fontSize: 11, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 8 }}>
        {title}
      </div>
      {loading ? (
        <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>Cargando…</div>
      ) : children.length === 0 ? (
        <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>{emptyLabel}</div>
      ) : (
        <div style={{ overflowX: 'auto' }}>
          <table className="data-table">
            <thead>
              <tr>
                <th>Título</th>
                <th>Tipo</th>
                <th>Origen</th>
                <th>Estado</th>
                <th>Petición</th>
                <th>Nomenclatura</th>
                <th>Tamaño</th>
                <th>Provider</th>
                <th>Calidad</th>
                <th>¿En eMuwarez?</th>
                <th>Aportes</th>
              </tr>
            </thead>
            <tbody>
              {children.map(child => (
                <LibraryTreeRow key={child.id} item={child} depth={0} instances={instances} onSelect={onSelect} onAction={onAction} onReload={() => setReloadKey(k => k + 1)} compact />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
