import { useState, useEffect, useCallback } from 'react'
import { getLibrary, TOP_LEVEL_PARENT_FILTER } from '../api/library'
import { getInstances } from '../api/instances'
import { refreshArrHealth, verifyLibraryFiles, refreshRecommendations } from '../api/diagnostics'
import type { LibraryItemResponse, LibraryListResponse, InstanceSafeResponse } from '../types/api'
import { StatusBadge } from '../components/StatusBadge'
import { LoadingState } from '../components/LoadingState'
import { ErrorState } from '../components/ErrorState'
import { EmptyState } from '../components/EmptyState'
import { NomenclatureModal } from '../components/NomenclatureModal'
import { NomenclatureFieldsModal } from '../components/NomenclatureFieldsModal'
import { UploadPreflightModal } from '../components/UploadPreflightModal'
import { LibraryTreeRow, type LibraryActionKind } from '../components/LibraryTreeRow'
import { SeriesSeasonsSection } from '../components/SeriesSeasonsSection'
import { LargePosterCard } from '../components/LargePosterCard'
import { LibraryDetailCard } from '../components/LibraryDetailCard'
import { formatBytes, formatDate, formatItemType } from '../utils/format'
import { titleMismatchesFilename, buildDeepLink } from '../utils/libraryItem'

const PAGE_SIZE = 50
const VIEW_MODE_STORAGE_KEY = 'emuwarez_uploadrr_library_view'
// Sentinel matching the backend's NOT_AVAILABLE_STATUS_FILTER
// (services/library.py) — expands server-side to the same LocalStatus
// "not available" set the old standalone Faltantes tab used, so removing
// that tab doesn't lose the combined view.
const NOT_AVAILABLE_STATUS_FILTER = '__not_available__'

type ViewMode = 'grid' | 'grid-lg' | 'list'

function loadViewMode(): ViewMode {
  const stored = localStorage.getItem(VIEW_MODE_STORAGE_KEY)
  return stored === 'list' || stored === 'grid-lg' ? stored : 'grid'
}

function PosterCard({ item, instances, onClick }: { item: LibraryItemResponse; instances: InstanceSafeResponse[]; onClick: () => void }) {
  const deepLink = buildDeepLink(item, instances)
  const mismatched = titleMismatchesFilename(item)
  return (
    <div
      className="clickable"
      onClick={onClick}
      style={{
        display: 'flex', flexDirection: 'column', borderRadius: 8, overflow: 'hidden',
        background: 'var(--bg-surface)', border: '1px solid var(--border)', cursor: 'pointer',
      }}
    >
      <div style={{ position: 'relative', width: '100%', aspectRatio: '2 / 3', background: 'rgba(255,255,255,0.04)' }}>
        {item.poster_url ? (
          <img
            src={item.poster_url}
            alt={item.title}
            loading="lazy"
            style={{ width: '100%', height: '100%', objectFit: 'cover' }}
            onError={e => { (e.currentTarget as HTMLImageElement).style.display = 'none' }}
          />
        ) : (
          <div style={{ width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 36, opacity: 0.35 }}>
            {item.item_type === 'series' || item.item_type === 'episode' ? '📺' : '🎬'}
          </div>
        )}
        <div style={{ position: 'absolute', top: 6, right: 6 }}>
          <StatusBadge status={item.local_status} type="local" />
        </div>
        {deepLink && (
          <a
            href={deepLink}
            target="_blank"
            rel="noreferrer"
            onClick={e => e.stopPropagation()}
            title={`Ver en ${item.instance_name ?? item.instance_type}`}
            style={{
              position: 'absolute', top: 6, left: 6, width: 22, height: 22, borderRadius: 5,
              background: 'rgba(0,0,0,0.6)', display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: 12, textDecoration: 'none',
            }}
          >
            🔗
          </a>
        )}
      </div>
      <div style={{ padding: '8px 10px' }}>
        <div style={{ fontSize: 12.5, fontWeight: 500, lineHeight: 1.3, overflow: 'hidden', textOverflow: 'ellipsis', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical' }}>
          {item.title}
        </div>
        <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>{item.year ?? '—'}</div>
        {mismatched && (
          <div style={{ fontSize: 10, color: 'var(--color-missing, #ef4444)', marginTop: 2 }} title={`Título original: ${item.original_title}`}>
            ⚠ Título distinto al archivo
          </div>
        )}
      </div>
    </div>
  )
}

export function LibraryPage() {
  const [data, setData] = useState<LibraryListResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selected, setSelected] = useState<LibraryItemResponse | null>(null)
  // Only opened from the "Pósters grandes" view — the small modal (grid/list) stays as-is.
  const [largeDetailItem, setLargeDetailItem] = useState<LibraryItemResponse | null>(null)
  const [nomenclatureItem, setNomenclatureItem] = useState<LibraryItemResponse | null>(null)
  const [fieldsItem, setFieldsItem] = useState<LibraryItemResponse | null>(null)
  const [uploadItem, setUploadItem] = useState<LibraryItemResponse | null>(null)
  const [viewMode, setViewMode] = useState<ViewMode>(loadViewMode)

  // Movie/episode leaf rows only — series/season rows show these same 3
  // buttons disabled (LibraryTreeRow), real batch wiring lands in Phase 6.
  function handleTreeAction(kind: LibraryActionKind, item: LibraryItemResponse) {
    if (kind === 'nomenclature') setNomenclatureItem(item)
    else if (kind === 'fields') setFieldsItem(item)
    else setUploadItem(item)
  }

  useEffect(() => { localStorage.setItem(VIEW_MODE_STORAGE_KEY, viewMode) }, [viewMode])

  const [instances, setInstances] = useState<InstanceSafeResponse[]>([])
  useEffect(() => { getInstances().then(setInstances).catch(() => {}) }, [])

  // Diagnostic actions — relocated here from the removed standalone
  // Faltantes tab (its own filtered view of Biblioteca now covers what it
  // used to show; these 3 buttons were the only functionality that didn't
  // already exist elsewhere).
  const [diagActionMsg, setDiagActionMsg] = useState<string | null>(null)
  const [diagActionLoading, setDiagActionLoading] = useState(false)

  async function handleRefreshHealth() {
    setDiagActionLoading(true)
    setDiagActionMsg(null)
    try {
      await refreshArrHealth({ include_queue: true, include_history: true })
      setDiagActionMsg('Salud ARR actualizada')
      await load()
    } catch {
      setDiagActionMsg('Error al refrescar salud ARR')
    } finally {
      setDiagActionLoading(false)
    }
  }

  async function handleVerifyFiles() {
    setDiagActionLoading(true)
    setDiagActionMsg(null)
    try {
      const r = await verifyLibraryFiles()
      setDiagActionMsg(`Archivos verificados: ${r.items_checked} · Encontrados: ${r.files_found}`)
      await load()
    } catch {
      setDiagActionMsg('Error al verificar archivos')
    } finally {
      setDiagActionLoading(false)
    }
  }

  async function handleRefreshRecommendations() {
    setDiagActionLoading(true)
    setDiagActionMsg(null)
    try {
      const r = await refreshRecommendations()
      setDiagActionMsg(`Recomendaciones actualizadas: ${r.items_updated}`)
      await load()
    } catch {
      setDiagActionMsg('Error al recalcular recomendaciones')
    } finally {
      setDiagActionLoading(false)
    }
  }

  // Filters
  const [search, setSearch] = useState('')
  const [filterType, setFilterType] = useState('')
  const [filterStatus, setFilterStatus] = useState('')
  const [filterInstanceId, setFilterInstanceId] = useState('')
  const [filterNomenclature, setFilterNomenclature] = useState('')
  const [filterRequest, setFilterRequest] = useState('')
  const [offset, setOffset] = useState(0)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const result = await getLibrary({
        search: search || undefined,
        type: filterType || undefined,
        status: filterStatus || undefined,
        instance_id: filterInstanceId ? Number(filterInstanceId) : undefined,
        nomenclature: filterNomenclature || undefined,
        request_status: filterRequest || undefined,
        // Top level only — series/season/episode hierarchy is browsed by
        // expanding LibraryTreeRow, never flooding this list with raw
        // episodes/seasons.
        parent_id: TOP_LEVEL_PARENT_FILTER,
        limit: PAGE_SIZE,
        offset,
      })
      setData(result)
    } catch {
      setError('Error al cargar la biblioteca')
    } finally {
      setLoading(false)
    }
  }, [search, filterType, filterStatus, filterInstanceId, filterNomenclature, filterRequest, offset])

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
        <div style={{ display: 'flex', gap: 4 }}>
          <button
            className={`btn btn-sm ${viewMode === 'grid' ? 'btn-primary' : 'btn-secondary'}`}
            onClick={() => setViewMode('grid')}
            title="Vista de pósters"
          >
            ▦ Pósters
          </button>
          <button
            className={`btn btn-sm ${viewMode === 'grid-lg' ? 'btn-primary' : 'btn-secondary'}`}
            onClick={() => setViewMode('grid-lg')}
            title="Vista de pósters grandes"
          >
            ▦▦ Pósters grandes
          </button>
          <button
            className={`btn btn-sm ${viewMode === 'list' ? 'btn-primary' : 'btn-secondary'}`}
            onClick={() => setViewMode('list')}
            title="Vista de lista"
          >
            ☰ Lista
          </button>
        </div>
      </div>

      {/* Diagnostic toolbar — relocated from the removed Faltantes tab */}
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap', marginBottom: 12 }}>
        <button className="btn btn-secondary btn-sm" onClick={handleRefreshHealth} disabled={diagActionLoading}>
          Refrescar salud ARR
        </button>
        <button className="btn btn-secondary btn-sm" onClick={handleVerifyFiles} disabled={diagActionLoading}>
          Verificar archivos
        </button>
        <button className="btn btn-secondary btn-sm" onClick={handleRefreshRecommendations} disabled={diagActionLoading}>
          Recalcular recomendaciones
        </button>
        {diagActionMsg && <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{diagActionMsg}</span>}
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
        <select className="form-input form-select" value={filterStatus} onChange={e => { setFilterStatus(e.target.value); setOffset(0) }} style={{ width: 190 }}>
          <option value="">Estado: Todos</option>
          <option value="Disponible">Disponible</option>
          <option value="Parcial">Parcial</option>
          <option value={NOT_AVAILABLE_STATUS_FILTER}>Todos los no disponibles</option>
          <option value="Faltante">Faltante</option>
          <option value="En cola">En cola</option>
          <option value="Descargando">Descargando</option>
          <option value="Pendiente de importar">Pendiente de importar</option>
          <option value="Error de importación">Error de importación</option>
          <option value="Error de búsqueda">Error de búsqueda</option>
        </select>
        <select className="form-input form-select" value={filterInstanceId} onChange={e => { setFilterInstanceId(e.target.value); setOffset(0) }} style={{ width: 170 }}>
          <option value="">Origen: Todos</option>
          {instances.map(inst => (
            <option key={inst.id} value={inst.id}>{inst.type === 'radarr' ? 'Radarr' : 'Sonarr'} — {inst.name}</option>
          ))}
        </select>
        <select className="form-input form-select" value={filterNomenclature} onChange={e => { setFilterNomenclature(e.target.value); setOffset(0) }} style={{ width: 160 }}>
          <option value="">Nomenclatura: Todas</option>
          <option value="Correcta">Correcta</option>
          <option value="No adaptada">No adaptada</option>
          <option value="N/A">N/A</option>
        </select>
        <select className="form-input form-select" value={filterRequest} onChange={e => { setFilterRequest(e.target.value); setOffset(0) }} style={{ width: 160 }}>
          <option value="">Petición: Todas</option>
          <option value="Sin petición">Sin petición</option>
          <option value="Compatible">Compatible</option>
          <option value="Parcial">Parcial</option>
          <option value="No compatible">No compatible</option>
          <option value="Llena">Llena</option>
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
      ) : viewMode === 'grid' ? (
        <div className="activity-section" style={{ padding: 20 }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))', gap: 16 }}>
            {items.map(item => (
              <PosterCard key={item.id} item={item} instances={instances} onClick={() => setSelected(item)} />
            ))}
          </div>
          {total > PAGE_SIZE && (
            <div style={{ padding: '16px 0 0', display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
              <button className="btn btn-secondary btn-sm" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>← Anterior</button>
              <span style={{ fontSize: 12, color: 'var(--text-muted)', alignSelf: 'center' }}>{Math.floor(offset / PAGE_SIZE) + 1} / {Math.ceil(total / PAGE_SIZE)}</span>
              <button className="btn btn-secondary btn-sm" disabled={offset + PAGE_SIZE >= total} onClick={() => setOffset(offset + PAGE_SIZE)}>Siguiente →</button>
            </div>
          )}
        </div>
      ) : viewMode === 'grid-lg' ? (
        <div className="activity-section" style={{ padding: 20 }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 20 }}>
            {items.map(item => (
              <LargePosterCard key={item.id} item={item} instances={instances} onClick={() => setLargeDetailItem(item)} />
            ))}
          </div>
          {total > PAGE_SIZE && (
            <div style={{ padding: '16px 0 0', display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
              <button className="btn btn-secondary btn-sm" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>← Anterior</button>
              <span style={{ fontSize: 12, color: 'var(--text-muted)', alignSelf: 'center' }}>{Math.floor(offset / PAGE_SIZE) + 1} / {Math.ceil(total / PAGE_SIZE)}</span>
              <button className="btn btn-secondary btn-sm" disabled={offset + PAGE_SIZE >= total} onClick={() => setOffset(offset + PAGE_SIZE)}>Siguiente →</button>
            </div>
          )}
        </div>
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
                  <LibraryTreeRow
                    key={item.id}
                    item={item}
                    depth={0}
                    instances={instances}
                    onSelect={setSelected}
                    onAction={handleTreeAction}
                  />
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

      {/* Nomenclature fields modal (Phase 10A) */}
      {fieldsItem && (
        <NomenclatureFieldsModal
          itemId={fieldsItem.id}
          itemTitle={fieldsItem.title}
          onClose={() => setFieldsItem(null)}
          onSaved={load}
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

      {/* Large "Serr-style" detail card — Pósters grandes view only */}
      {largeDetailItem && (
        <LibraryDetailCard
          item={largeDetailItem}
          instances={instances}
          onClose={() => setLargeDetailItem(null)}
          onSelect={setLargeDetailItem}
          onAction={handleTreeAction}
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
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 20, gap: 16 }}>
              <div style={{ display: 'flex', gap: 14 }}>
                {selected.poster_url && (
                  <img
                    src={selected.poster_url}
                    alt={selected.title}
                    style={{ width: 64, height: 96, objectFit: 'cover', borderRadius: 6, flexShrink: 0 }}
                    onError={e => { (e.currentTarget as HTMLImageElement).style.display = 'none' }}
                  />
                )}
                <div>
                  <div style={{ fontWeight: 700, fontSize: 16, display: 'flex', alignItems: 'center', gap: 8 }}>
                    {selected.title} {selected.year ? `(${selected.year})` : ''}
                    {buildDeepLink(selected, instances) && (
                      <a
                        href={buildDeepLink(selected, instances)!}
                        target="_blank"
                        rel="noreferrer"
                        title={`Ver en ${selected.instance_name ?? selected.instance_type}`}
                        style={{ fontSize: 13, textDecoration: 'none' }}
                      >
                        🔗
                      </a>
                    )}
                  </div>
                  {titleMismatchesFilename(selected) && (
                    <div style={{ fontSize: 11, color: 'var(--color-missing)', marginTop: 2 }}>
                      ⚠ Título distinto al del archivo original ({selected.original_title})
                    </div>
                  )}
                </div>
              </div>
              <button className="btn btn-ghost btn-sm" onClick={() => setSelected(null)}>✕</button>
            </div>
            <div style={{ display: 'flex', gap: 8, marginBottom: 16, flexWrap: 'wrap' }}>
              {(() => {
                const isRollup = selected.item_type === 'series' || selected.item_type === 'season'
                const title = isRollup ? 'Acción por lotes disponible próximamente' : undefined
                return (
                  <>
                    <button className="btn btn-secondary btn-sm" disabled={isRollup} title={title} onClick={() => { setNomenclatureItem(selected); setSelected(null) }}>Adaptar nomenclatura</button>
                    <button className="btn btn-secondary btn-sm" disabled={isRollup} title={title} onClick={() => { setFieldsItem(selected); setSelected(null) }}>Editar campos</button>
                    <button className="btn btn-secondary btn-sm" disabled={isRollup} title={title} onClick={() => { setUploadItem(selected); setSelected(null) }}>Subir</button>
                  </>
                )
              })()}
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
            {selected.item_type === 'series' && (
              <SeriesSeasonsSection seriesId={selected.id} instances={instances} onSelect={setSelected} onAction={handleTreeAction} />
            )}
          </div>
        </div>
      )}
    </div>
  )
}
