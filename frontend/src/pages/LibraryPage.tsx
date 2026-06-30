import { useState, useEffect, useCallback } from 'react'
import { getLibrary } from '../api/library'
import type { LibraryItemResponse, LibraryListResponse } from '../types/api'
import { StatusBadge } from '../components/StatusBadge'
import { ServiceLabel } from '../components/ServiceIcon'
import { LoadingState } from '../components/LoadingState'
import { ErrorState } from '../components/ErrorState'
import { EmptyState } from '../components/EmptyState'
import { NomenclatureModal } from '../components/NomenclatureModal'
import { UploadPreflightModal } from '../components/UploadPreflightModal'
import { formatBytes, formatDate, formatItemType } from '../utils/format'

const PAGE_SIZE = 50

export function LibraryPage() {
  const [data, setData] = useState<LibraryListResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selected, setSelected] = useState<LibraryItemResponse | null>(null)
  const [nomenclatureItem, setNomenclatureItem] = useState<LibraryItemResponse | null>(null)
  const [uploadItem, setUploadItem] = useState<LibraryItemResponse | null>(null)

  // Filters
  const [search, setSearch] = useState('')
  const [filterType, setFilterType] = useState('')
  const [filterStatus, setFilterStatus] = useState('')
  const [filterOrigin, setFilterOrigin] = useState('')
  const [offset, setOffset] = useState(0)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const result = await getLibrary({
        search: search || undefined,
        type: filterType || undefined,
        status: filterStatus || undefined,
        origin: filterOrigin || undefined,
        limit: PAGE_SIZE,
        offset,
      })
      setData(result)
    } catch {
      setError('Error al cargar la biblioteca')
    } finally {
      setLoading(false)
    }
  }, [search, filterType, filterStatus, filterOrigin, offset])

  useEffect(() => { load() }, [load])

  function applyFilters() {
    setOffset(0)
    load()
  }

  const items = data?.items ?? []
  const total = data?.total ?? 0

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="page-title">Biblioteca</div>
          <div className="page-subtitle">
            {total > 0 ? `${total} elementos sincronizados` : 'Sin elementos'}
          </div>
        </div>
      </div>

      {/* Filters */}
      <div className="filters-bar">
        <input
          className="form-input"
          placeholder="Buscar título…"
          value={search}
          onChange={e => { setSearch(e.target.value); if (!e.target.value) { setOffset(0) } }}
          onKeyDown={e => e.key === 'Enter' && applyFilters()}
          style={{ minWidth: 220 }}
        />
        <select className="form-input form-select" value={filterType} onChange={e => { setFilterType(e.target.value); setOffset(0) }} style={{ width: 140 }}>
          <option value="">Tipo: Todos</option>
          <option value="movie">Película</option>
          <option value="series">Serie</option>
          <option value="episode">Episodio</option>
        </select>
        <select className="form-input form-select" value={filterStatus} onChange={e => { setFilterStatus(e.target.value); setOffset(0) }} style={{ width: 160 }}>
          <option value="">Estado: Todos</option>
          <option value="Disponible">Disponible</option>
          <option value="Faltante">Faltante</option>
          <option value="En cola">En cola</option>
          <option value="Descargando">Descargando</option>
          <option value="Error de importación">Error de importación</option>
        </select>
        <select className="form-input form-select" value={filterOrigin} onChange={e => { setFilterOrigin(e.target.value); setOffset(0) }} style={{ width: 140 }}>
          <option value="">Origen: Todos</option>
          <option value="radarr">Radarr</option>
          <option value="sonarr">Sonarr</option>
        </select>
        <button className="btn btn-secondary btn-sm" onClick={applyFilters}>Filtrar</button>
      </div>

      {loading ? (
        <LoadingState label="Cargando biblioteca…" />
      ) : error ? (
        <ErrorState message={error} onRetry={load} />
      ) : items.length === 0 ? (
        <EmptyState
          icon="📚"
          title="Biblioteca vacía"
          body="Añade instancias Radarr/Sonarr en la sección Instancias y sincroniza para ver el contenido aquí."
        />
      ) : (
        <div className="activity-section">
          <div style={{ overflowX: 'auto' }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Título</th>
                  <th>Tipo</th>
                  <th>Origen</th>
                  <th>Estado</th>
                  <th>Archivo</th>
                  <th>Petición</th>
                  <th>Nomenclatura</th>
                  <th>Diagnóstico</th>
                  <th>Acción</th>
                  <th>Calidad</th>
                  <th>Actualizado</th>
                  <th className="col-actions">Acciones</th>
                </tr>
              </thead>
              <tbody>
                {items.map(item => (
                  <tr key={item.id} className="clickable" onClick={() => setSelected(item)}>
                    <td>
                      <div style={{ fontWeight: 500 }}>{item.title}</div>
                      {item.year && <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>{item.year}</div>}
                    </td>
                    <td style={{ color: 'var(--text-secondary)', fontSize: 12 }}>{formatItemType(item.item_type)}</td>
                    <td>
                      {item.instance_type
                        ? <ServiceLabel type={item.instance_type} label={item.instance_name ?? item.instance_type} size={13} />
                        : <span style={{ color: 'var(--text-muted)' }}>—</span>}
                    </td>
                    <td><StatusBadge status={item.local_status} type="local" /></td>
                    <td style={{ fontSize: 11, whiteSpace: 'nowrap' }}>
                      {item.file_exists === null
                        ? <span style={{ color: 'var(--text-muted)' }}>—</span>
                        : item.file_exists
                          ? <span style={{ color: 'var(--color-available)' }}>OK</span>
                          : <span style={{ color: 'var(--color-missing)' }}>NO</span>}
                    </td>
                    <td><StatusBadge status={item.request_status} type="request" /></td>
                    <td><StatusBadge status={item.nomenclature_status} type="nomenclature" /></td>
                    <td style={{ fontSize: 11, color: 'var(--text-secondary)', maxWidth: 120, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {item.diagnostic_summary ?? '—'}
                    </td>
                    <td style={{ fontSize: 11, color: '#a78bfa', maxWidth: 120, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {item.recommended_action ?? '—'}
                    </td>
                    <td style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                      {[item.resolution, item.source].filter(Boolean).join(' · ') || '—'}
                    </td>
                    <td style={{ fontSize: 12, color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>
                      {formatDate(item.updated_at)}
                    </td>
                    <td className="col-actions" onClick={e => e.stopPropagation()} style={{ display: 'flex', gap: 4 }}>
                      <button className="btn btn-ghost btn-sm" onClick={() => setNomenclatureItem(item)} title="Adaptar nomenclatura">Nomenclatura</button>
                      <button className="btn btn-ghost btn-sm" onClick={() => setUploadItem(item)} title="Preflight Uploadrr">Subir</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {total > PAGE_SIZE && (
            <div style={{ padding: '12px 20px', display: 'flex', gap: 8, justifyContent: 'flex-end', borderTop: '1px solid var(--border)' }}>
              <button className="btn btn-secondary btn-sm" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>← Anterior</button>
              <span style={{ fontSize: 12, color: 'var(--text-muted)', alignSelf: 'center' }}>{Math.floor(offset / PAGE_SIZE) + 1} / {Math.ceil(total / PAGE_SIZE)}</span>
              <button className="btn btn-secondary btn-sm" disabled={offset + PAGE_SIZE >= total} onClick={() => setOffset(offset + PAGE_SIZE)}>Siguiente →</button>
            </div>
          )}
        </div>
      )}

      {/* Nomenclature modal */}
      {nomenclatureItem && (
        <NomenclatureModal
          itemId={nomenclatureItem.id}
          itemTitle={nomenclatureItem.title}
          onClose={() => setNomenclatureItem(null)}
        />
      )}

      {/* Upload preflight modal */}
      {uploadItem && (
        <UploadPreflightModal
          itemId={uploadItem.id}
          itemTitle={uploadItem.title}
          onClose={() => setUploadItem(null)}
        />
      )}

      {/* Detail panel */}
      {selected && (
        <div
          style={{
            position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', display: 'flex',
            alignItems: 'center', justifyContent: 'center', zIndex: 1000, padding: 20,
          }}
          onClick={() => setSelected(null)}
        >
          <div
            style={{
              background: 'var(--bg-surface)', border: '1px solid var(--border)', borderRadius: 12,
              padding: 28, maxWidth: 560, width: '100%', maxHeight: '80vh', overflowY: 'auto',
            }}
            onClick={e => e.stopPropagation()}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 20 }}>
              <div style={{ fontWeight: 700, fontSize: 16 }}>{selected.title} {selected.year ? `(${selected.year})` : ''}</div>
              <button className="btn btn-ghost btn-sm" onClick={() => setSelected(null)}>✕</button>
            </div>
            <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
              <button className="btn btn-secondary btn-sm" onClick={() => { setNomenclatureItem(selected); setSelected(null) }}>Adaptar nomenclatura</button>
              <button className="btn btn-secondary btn-sm" onClick={() => { setUploadItem(selected); setSelected(null) }}>Subir</button>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px 20px', fontSize: 13 }}>
              {[
                ['Tipo', formatItemType(selected.item_type)],
                ['Origen', selected.instance_name ?? '—'],
                ['Estado', null],
                ['Petición', null],
                ['Nomenclatura', null],
                ['Resolución', selected.resolution ?? '—'],
                ['Source', selected.source ?? '—'],
                ['Calidad', selected.quality ?? '—'],
                ['Tamaño', formatBytes(selected.size_bytes)],
                ['TMDb', selected.tmdb_id ?? '—'],
                ['IMDb', selected.imdb_id ?? '—'],
                ['Ruta', selected.path ?? '—'],
              ].map(([key, val]) => (
                <div key={String(key)}>
                  <div style={{ fontSize: 11, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 2 }}>{key}</div>
                  {key === 'Estado' ? <StatusBadge status={selected.local_status} type="local" />
                   : key === 'Petición' ? <StatusBadge status={selected.request_status} type="request" />
                   : key === 'Nomenclatura' ? <StatusBadge status={selected.nomenclature_status} type="nomenclature" />
                   : <div style={{ color: 'var(--text-primary)', wordBreak: 'break-all' }}>{val}</div>}
                </div>
              ))}
            </div>
            {/* Phase 8A — diagnostic fields */}
            {(selected.file_exists !== null || selected.diagnostic_status || selected.recommended_action) && (
              <div style={{ marginTop: 16, padding: '12px 14px', background: 'rgba(255,255,255,0.03)', borderRadius: 8, border: '1px solid var(--border)' }}>
                <div style={{ fontSize: 11, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 8 }}>Diagnóstico (Fase 8A)</div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '6px 16px', fontSize: 12 }}>
                  {selected.file_exists !== null && (
                    <div>
                      <span style={{ color: 'var(--text-muted)' }}>Archivo en disco: </span>
                      <span style={{ color: selected.file_exists ? 'var(--color-available)' : 'var(--color-missing)', fontWeight: 600 }}>
                        {selected.file_exists ? 'Sí' : 'No'}
                      </span>
                    </div>
                  )}
                  {selected.file_verified_at && (
                    <div><span style={{ color: 'var(--text-muted)' }}>Verificado: </span>{formatDate(selected.file_verified_at)}</div>
                  )}
                  {selected.arr_queue_status && (
                    <div><span style={{ color: 'var(--text-muted)' }}>Queue ARR: </span><strong>{selected.arr_queue_status}</strong></div>
                  )}
                  {selected.arr_history_status && (
                    <div><span style={{ color: 'var(--text-muted)' }}>Historial ARR: </span>{selected.arr_history_status}</div>
                  )}
                  {selected.diagnostic_summary && (
                    <div style={{ gridColumn: '1 / -1' }}><span style={{ color: 'var(--text-muted)' }}>Diagnóstico: </span>{selected.diagnostic_summary}</div>
                  )}
                  {selected.recommended_action && (
                    <div style={{ gridColumn: '1 / -1' }}>
                      <span style={{ color: 'var(--text-muted)' }}>Acción recomendada: </span>
                      <span style={{ color: '#a78bfa', fontWeight: 600 }}>{selected.recommended_action}</span>
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
