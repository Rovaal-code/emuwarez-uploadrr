import { useState, useEffect } from 'react'
import { getLibrary } from '../api/library'
import type { LibraryItemResponse, InstanceSafeResponse } from '../types/api'
import { LibraryTreeRow, type LibraryActionKind } from './LibraryTreeRow'

// Seasons (→ episodes, expandable) of a Series, shown below its detail
// panel — reuses LibraryTreeRow unchanged, just seeded with the series'
// direct children instead of a top-level list. Shared by the small detail
// modal and the large "Serr-style" detail card.
export function SeriesSeasonsSection({ seriesId, instances, onSelect, onAction }: {
  seriesId: number
  instances: InstanceSafeResponse[]
  onSelect: (item: LibraryItemResponse) => void
  onAction: (kind: LibraryActionKind, item: LibraryItemResponse) => void
}) {
  const [seasons, setSeasons] = useState<LibraryItemResponse[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    getLibrary({ parent_id: seriesId, type: 'season', limit: 500 })
      .then(r => setSeasons(r.items))
      .catch(() => setSeasons([]))
      .finally(() => setLoading(false))
  }, [seriesId])

  return (
    <div style={{ marginTop: 16 }}>
      <div style={{ fontSize: 11, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 8 }}>
        Temporadas
      </div>
      {loading ? (
        <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>Cargando…</div>
      ) : seasons.length === 0 ? (
        <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>Sin temporadas</div>
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
              {seasons.map(season => (
                <LibraryTreeRow key={season.id} item={season} depth={0} instances={instances} onSelect={onSelect} onAction={onAction} compact />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
