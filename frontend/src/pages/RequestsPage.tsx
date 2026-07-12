import { useState, useEffect, useCallback } from 'react'
import {
  getRequests,
  syncRequests,
  getSyncStatus,
  getRequestDetail,
} from '../api/requests'
import { getCandidates } from '../api/requestReadiness'
import type {
  RequestItemResponse, RequestDetailResponse, RequestSyncStatusResponse,
  RequestReadinessResponse, RequestCandidateResponse,
} from '../types/api'
import { LoadingState } from '../components/LoadingState'
import { ErrorState } from '../components/ErrorState'
import { EmptyState } from '../components/EmptyState'
import { SyncInfo } from '../components/SyncInfo'
import { posterUrl } from '../utils/libraryItem'

// A request's category maps to a friendly "Tipo" with an icon.
function tipoOf(category: string | null): { icon: string; label: string } {
  const c = (category || '').toLowerCase()
  if (c.includes('serie')) return { icon: '📺', label: category || 'Serie' }
  if (c.includes('docu')) return { icon: '🎥', label: category || 'Documental' }
  if (c.includes('pel') || c.includes('movie') || c.includes('film')) return { icon: '🎬', label: category || 'Película' }
  return { icon: '🎬', label: category || '—' }
}

function RequestPoster({ url, category, size = 'sm' }: { url: string | null; category: string | null; size?: 'sm' | 'lg' }) {
  const dims = size === 'lg'
    ? { width: 120, height: 180, radius: 8, font: 44 }
    : { width: 30, height: 45, radius: 4, font: 15 }
  const t = tipoOf(category)
  return (
    <div style={{ flexShrink: 0, width: dims.width, height: dims.height, borderRadius: dims.radius, overflow: 'hidden', background: 'rgba(255,255,255,0.04)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      {url ? (
        <img
          src={posterUrl(url, size === 'lg' ? 'w342' : 'w154')}
          alt=""
          loading="lazy"
          style={{ width: '100%', height: '100%', objectFit: 'cover' }}
          onError={e => { (e.currentTarget as HTMLImageElement).style.display = 'none' }}
        />
      ) : (
        <span style={{ fontSize: dims.font, opacity: 0.35 }}>{t.icon}</span>
      )}
    </div>
  )
}

const COMPATIBILITY_STATUSES = [
  { value: '', label: 'Compatibilidad: Todas' },
  { value: 'Compatible', label: 'Compatible' },
  { value: 'No disponible', label: 'No disponible' },
  { value: 'Parcial', label: 'Parcial' },
  { value: 'No compatible', label: 'No compatible' },
  { value: 'Reclamado', label: 'Reclamado' },
  { value: 'Pendiente', label: 'Pendiente' },
  { value: 'Llena', label: 'Llena' },
  { value: 'Sin coincidencia', label: 'Sin coincidencia' },
]

const EMU_STATUS_OPTIONS = [
  { value: '', label: 'Estado EMU: Todos' },
  { value: 'open', label: 'Abierta' },
  { value: 'filled', label: 'Llena' },
]

const SORT_OPTIONS = [
  { value: 'created_desc', label: 'Orden: Más recientes' },
  { value: 'created_asc', label: 'Orden: Más antiguas' },
  { value: 'title', label: 'Orden: Título (A-Z)' },
  { value: 'points_desc', label: 'Orden: Puntos (↓)' },
]

// Comparison-table helpers.
function matchMark(v: boolean | null) {
  if (v === true) return <span style={{ color: '#22c55e', fontWeight: 700 }}>✓</span>
  if (v === false) return <span style={{ color: '#ef4444', fontWeight: 700 }}>✗</span>
  return <span style={{ color: 'var(--text-muted)' }}>—</span>
}

const _AVAILABLE_LOCAL = new Set(['Disponible', 'Subido', 'Subiendo', 'Parcial'])
function _availableLocal(status: string | null): boolean | null {
  if (!status) return null
  return _AVAILABLE_LOCAL.has(status)
}

function noReq(v: string | null): string {
  if (!v || ['any', 'cualquiera', 'todos', 'all'].includes(v.trim().toLowerCase())) return 'Cualquiera'
  return v
}

function CompatibilityBadge({ status }: { status: string | null }) {
  if (!status) return <span className="badge req-none">Sin coincidencia</span>
  const cls =
    status === 'Compatible' ? 'badge req-compatible' :
    status === 'No disponible' ? 'badge req-unavailable' :
    status === 'Parcial' ? 'badge req-partial' :
    status === 'No compatible' ? 'badge req-not-compatible' :
    status === 'Reclamado' ? 'badge req-claimed' :
    status === 'Pendiente' ? 'badge req-pending' :
    status === 'Llena' ? 'badge req-filled' :
    'badge req-unknown'
  return <span className={cls}>{status}</span>
}

function ReadinessBadge({ status }: { status: string | null | undefined }) {
  if (!status) return <span style={{ color: 'var(--text-muted)', fontSize: 11 }}>—</span>
  const color =
    status === 'ready_to_upload' ? '#34d399' :
    status === 'needs_nomenclature' ? '#f59e0b' :
    status === 'preflight_needed' ? '#60a5fa' :
    status === 'downloading' ? '#818cf8' :
    status === 'uploaded' ? '#6ee7b7' :
    status === 'no_local_match' ? 'var(--text-muted)' :
    status.includes('error') || status.includes('missing') || status === 'blocked' ? 'var(--color-missing)' :
    'var(--text-secondary)'
  return <span style={{ fontSize: 11, color, fontWeight: 500 }}>{status}</span>
}

function CandidatesPanel({ requestId, onClose }: { requestId: number; onClose: () => void }) {
  const [candidates, setCandidates] = useState<RequestCandidateResponse[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    getCandidates(requestId)
      .then(setCandidates)
      .catch(() => setCandidates([]))
      .finally(() => setLoading(false))
  }, [requestId])

  return (
    <div className="detail-panel">
      <div className="detail-panel__header">
        <div className="detail-panel__title">Candidatos locales</div>
        <button className="btn-icon" onClick={onClose}>✕</button>
      </div>
      {loading ? <LoadingState label="Cargando candidatos…" /> : candidates.length === 0 ? (
        <div className="empty-inline">Sin candidatos en biblioteca. Ejecuta "Recalcular readiness".</div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8, padding: '8px 0' }}>
          {candidates.map(c => (
            <div key={c.id} style={{ padding: '10px 14px', background: 'rgba(255,255,255,0.03)', borderRadius: 6, border: '1px solid var(--border)', fontSize: 12 }}>
              <div style={{ fontWeight: 600, marginBottom: 4 }}>#{c.candidate_rank} — {c.lib_title || `Lib #${c.library_item_id}`}</div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '2px 12px', color: 'var(--text-secondary)' }}>
                <span>Compat: <strong>{c.compatibility_score?.toFixed(0) ?? '—'}</strong></span>
                <span>Readiness: <strong>{c.readiness_score?.toFixed(0) ?? '—'}</strong></span>
                <span>Estado: {c.local_status || '—'}</span>
                <span>Resolución: {c.resolution || '—'}</span>
              </div>
              {c.blockers.length > 0 && (
                <div style={{ marginTop: 4, color: 'var(--color-missing)', fontSize: 11 }}>
                  ⛔ {c.blockers.join(' · ')}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function DetailPanel({ item, readiness, onClose, onShowCandidates }: {
  item: RequestDetailResponse
  readiness: RequestReadinessResponse | null
  onClose: () => void
  onShowCandidates: () => void
}) {
  const m = item.match
  return (
    <div className="detail-panel">
      <div className="detail-panel__header">
        <div style={{ display: 'flex', gap: 14, alignItems: 'flex-start' }}>
          <RequestPoster url={item.poster_url} category={item.category} size="lg" />
          <div>
            <div className="detail-panel__title">{item.title}</div>
            {item.category && <div className="detail-panel__subtitle">{tipoOf(item.category).icon} {tipoOf(item.category).label}</div>}
            <div style={{ marginTop: 8 }}><CompatibilityBadge status={m ? m.status : (item.compatibility_status ?? null)} /></div>
          </div>
        </div>
        <button className="btn-icon" onClick={onClose}>✕</button>
      </div>

      {m ? (
        <div className="detail-panel__section">
          <div className="detail-panel__section-title">Petición vs. tu biblioteca</div>
          <table className="cmp-table">
            <thead>
              <tr>
                <th></th>
                <th>Petición</th>
                <th>Tu biblioteca</th>
                <th aria-label="Cumple"></th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <th>Contenido</th>
                <td>{item.title}</td>
                <td>{m.library_title || '—'}</td>
                <td>{matchMark(m.id_match ? true : null)}</td>
              </tr>
              <tr>
                <th>Resolución</th>
                <td>{noReq(item.requested_resolution)}</td>
                <td>{m.local_resolution || '—'}</td>
                <td>{matchMark(m.resolution_match)}</td>
              </tr>
              <tr>
                <th>Source</th>
                <td>{noReq(item.requested_source)}</td>
                <td>{m.local_source || '—'}</td>
                <td>{matchMark(m.source_match)}</td>
              </tr>
              <tr>
                <th>En disco</th>
                <td>—</td>
                <td>{m.local_status || '—'}</td>
                <td>{matchMark(_availableLocal(m.local_status))}</td>
              </tr>
              {m.nomenclature_status && m.nomenclature_status !== 'N/A' && (
                <tr>
                  <th>Nomenclatura</th>
                  <td>—</td>
                  <td>{m.nomenclature_status}</td>
                  <td>{matchMark(m.nomenclature_status === 'Correcta' ? true : null)}</td>
                </tr>
              )}
            </tbody>
          </table>
          <div className="cmp-confidence">Confianza del emparejamiento: <strong>{Math.round(m.confidence * 100)}%</strong></div>
          {m.reasons.length > 0 && (
            <ul className="cmp-reasons">
              {m.reasons.map((r, i) => <li key={i}>{r}</li>)}
            </ul>
          )}
        </div>
      ) : (
        <div className="detail-panel__section">
          <div className="empty-inline">Sin coincidencia en tu biblioteca local — no tienes este contenido.</div>
        </div>
      )}

      <div className="detail-panel__section">
        <div className="detail-panel__section-title">Datos de la petición</div>
        <div className="detail-row"><span>Resolución pedida</span><span>{noReq(item.requested_resolution)}</span></div>
        <div className="detail-row"><span>Source pedido</span><span>{noReq(item.requested_source)}</span></div>
        <div className="detail-row"><span>Puntos</span><span>{item.points ?? '—'}</span></div>
        {item.comments != null && <div className="detail-row"><span>Comentarios</span><span>{item.comments}</span></div>}
        {item.tmdb_id && <div className="detail-row"><span>TMDb</span><span>{item.tmdb_id}</span></div>}
        {item.imdb_id && <div className="detail-row"><span>IMDb</span><span>{item.imdb_id}</span></div>}
        {item.created_at && (
          <div className="detail-row"><span>Creada</span><span>{new Date(item.created_at).toLocaleDateString('es-ES')}</span></div>
        )}
        {item.url && (
          <div className="detail-row">
            <span>Enlace</span>
            <a href={item.url} target="_blank" rel="noreferrer" className="link">Ver en eMuwarez ↗</a>
          </div>
        )}
      </div>

      {readiness && (
        <details className="detail-panel__section cmp-readiness">
          <summary>Preparación de subida (avanzado)</summary>
          <div className="detail-row"><span>Estado</span><ReadinessBadge status={readiness.status} /></div>
          <div className="detail-row"><span>Acción</span><span style={{ fontSize: 12, color: '#a78bfa' }}>{readiness.recommended_action || '—'}</span></div>
          <div className="detail-row"><span>Compat. score</span><span>{readiness.compatibility_score?.toFixed(0) ?? '—'}/100</span></div>
          <div className="detail-row"><span>Readiness score</span><span>{readiness.upload_readiness_score?.toFixed(0) ?? '—'}/100</span></div>
          {readiness.blockers.length > 0 && (
            <div style={{ marginTop: 8 }}>
              <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 4 }}>BLOQUEADORES</div>
              {readiness.blockers.map((b, i) => (
                <div key={i} style={{ fontSize: 11, color: 'var(--color-missing)' }}>⛔ {b}</div>
              ))}
            </div>
          )}
          <div style={{ marginTop: 8 }}>
            <button className="btn btn-ghost btn-sm" onClick={onShowCandidates}>Ver candidatos</button>
          </div>
        </details>
      )}
    </div>
  )
}

const PAGE_SIZE = 2000  // show everything in one scrollable container (like Biblioteca)

export function RequestsPage() {
  const [items, setItems] = useState<RequestItemResponse[]>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [categoryFilter, setCategoryFilter] = useState('')
  const [resolutionFilter, setResolutionFilter] = useState('')
  const [sourceFilter, setSourceFilter] = useState('')
  const [emuFilter, setEmuFilter] = useState('')
  const [sortBy, setSortBy] = useState('created_desc')
  const [facets, setFacets] = useState<{ categories: string[]; resolutions: string[]; sources: string[] }>({
    categories: [], resolutions: [], sources: [],
  })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [syncing, setSyncing] = useState(false)
  const [syncMsg, setSyncMsg] = useState<string | null>(null)
  const [syncStatus, setSyncStatus] = useState<RequestSyncStatusResponse | null>(null)
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [detail, setDetail] = useState<RequestDetailResponse | null>(null)
  const [readiness, setReadiness] = useState<RequestReadinessResponse | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [showCandidates, setShowCandidates] = useState(false)

  const loadItems = useCallback(async (off = 0) => {
    setLoading(true)
    setError(null)
    try {
      const res = await getRequests({
        search: search || undefined,
        status: statusFilter || undefined,
        category: categoryFilter || undefined,
        resolution: resolutionFilter || undefined,
        source: sourceFilter || undefined,
        emu_status: emuFilter || undefined,
        sort: sortBy,
        limit: PAGE_SIZE,
        offset: off,
      })
      setItems(res.items)
      setTotal(res.total)
      setOffset(off)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Error cargando peticiones')
    } finally {
      setLoading(false)
    }
  }, [search, statusFilter, categoryFilter, resolutionFilter, sourceFilter, emuFilter, sortBy])

  const loadSyncStatus = useCallback(async () => {
    try {
      const s = await getSyncStatus()
      setSyncStatus(s)
    } catch { /* optional */ }
  }, [])

  // Populate filter dropdown options from the full (unfiltered) dataset so they
  // stay stable regardless of the active filters.
  const loadFacets = useCallback(async () => {
    try {
      const res = await getRequests({ sort: 'created_desc', limit: PAGE_SIZE, offset: 0 })
      const uniq = (vals: (string | null | undefined)[]) =>
        Array.from(new Set(vals.filter((v): v is string => !!v && v.trim() !== ''))).sort()
      setFacets({
        categories: uniq(res.items.map(i => i.category)),
        resolutions: uniq(res.items.map(i => i.requested_resolution)),
        sources: uniq(res.items.map(i => i.requested_source)),
      })
    } catch { /* optional */ }
  }, [])

  useEffect(() => {
    loadSyncStatus()
    loadFacets()
  }, [loadSyncStatus, loadFacets])

  // Reload the table whenever a filter or the sort order changes.
  useEffect(() => {
    loadItems(0)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statusFilter, categoryFilter, resolutionFilter, sourceFilter, emuFilter, sortBy])

  const handleSync = async (force: boolean) => {
    setSyncing(true)
    setSyncMsg(null)
    try {
      const res = await syncRequests(force)
      setSyncMsg(res.message)
      if (res.ok) {
        await loadItems(0)
        await loadSyncStatus()
        await loadFacets()
      }
    } catch (e: unknown) {
      setSyncMsg(e instanceof Error ? e.message : 'Error al sincronizar')
    } finally {
      setSyncing(false)
    }
  }

  const handleRowClick = async (id: number) => {
    if (selectedId === id) {
      setSelectedId(null)
      setDetail(null)
      setReadiness(null)
      setShowCandidates(false)
      return
    }
    setSelectedId(id)
    setShowCandidates(false)
    setDetailLoading(true)
    try {
      const [d, rr] = await Promise.allSettled([
        getRequestDetail(id),
        import('../api/requestReadiness').then(m => m.getReadiness(id)).catch(() => null),
      ])
      setDetail(d.status === 'fulfilled' ? d.value : null)
      setReadiness(rr.status === 'fulfilled' && rr.value !== null ? rr.value as RequestReadinessResponse : null)
    } catch { setDetail(null) }
    finally { setDetailLoading(false) }
  }

  const displayItems = items

  const totalPages = Math.ceil(total / PAGE_SIZE)
  const currentPage = Math.floor(offset / PAGE_SIZE) + 1

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
        <div className="page-header">
          <div>
            <div className="page-title">Peticiones eMuwarez</div>
            <div className="page-subtitle">
              {total > 0 ? `${total} peticiones` : 'Peticiones activas cruzadas con tu biblioteca local'}
            </div>
          </div>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
            <SyncInfo
              syncStatus={syncStatus}
              onSync={handleSync}
              syncing={syncing}
              label="Sincronizar peticiones"
              title="Descarga de eMuwarez las peticiones activas y las cruza con tu biblioteca local para ver cuáles puedes cubrir. Limitado a una vez por hora."
            />
          </div>
        </div>

        {syncMsg && (
          <div style={{ marginBottom: 12, fontSize: 13, color: 'var(--text-secondary)' }}>
            <div>{syncMsg}</div>
          </div>
        )}

        <div className="filters-bar">
          <input
            className="form-input"
            type="search"
            placeholder="Buscar por título…"
            value={search}
            onChange={e => setSearch(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && loadItems(0)}
            style={{ minWidth: 220 }}
          />
          <select className="form-input form-select" value={categoryFilter} onChange={e => setCategoryFilter(e.target.value)}>
            <option value="">Tipo: Todos</option>
            {facets.categories.map(c => <option key={c} value={c}>{c}</option>)}
          </select>
          <select className="form-input form-select" value={resolutionFilter} onChange={e => setResolutionFilter(e.target.value)}>
            <option value="">Resolución: Todas</option>
            {facets.resolutions.map(r => <option key={r} value={r}>{r}</option>)}
          </select>
          <select className="form-input form-select" value={sourceFilter} onChange={e => setSourceFilter(e.target.value)}>
            <option value="">Source: Todos</option>
            {facets.sources.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
          <select className="form-input form-select" value={emuFilter} onChange={e => setEmuFilter(e.target.value)}>
            {EMU_STATUS_OPTIONS.map(s => <option key={s.value} value={s.value}>{s.label}</option>)}
          </select>
          <select className="form-input form-select" value={statusFilter} onChange={e => setStatusFilter(e.target.value)}>
            {COMPATIBILITY_STATUSES.map(s => (
              <option key={s.value} value={s.value}>{s.label}</option>
            ))}
          </select>
          <select className="form-input form-select" value={sortBy} onChange={e => setSortBy(e.target.value)}>
            {SORT_OPTIONS.map(s => <option key={s.value} value={s.value}>{s.label}</option>)}
          </select>
        </div>

        {loading ? (
          <LoadingState label="Cargando peticiones…" />
        ) : error ? (
          <ErrorState message={error} onRetry={() => loadItems()} />
        ) : displayItems.length === 0 ? (
          <EmptyState
            title="Sin peticiones"
            body={
              total === 0 && !search && !statusFilter && !categoryFilter && !resolutionFilter && !sourceFilter && !emuFilter
                ? 'Sincroniza las peticiones de eMuwarez para verlas aquí.'
                : 'No hay peticiones que coincidan con los filtros.'
            }
            action={total === 0 ? (
              <button className="btn btn-primary btn-sm" onClick={() => handleSync(false)}>Sincronizar peticiones</button>
            ) : undefined}
          />
        ) : (
          <div className="activity-section" style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}>
            <div style={{ overflow: 'auto', flex: 1, minHeight: 0 }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Título</th>
                    <th>Tipo</th>
                    <th>Resolución</th>
                    <th>Source</th>
                    <th>Compatibilidad</th>
                  </tr>
                </thead>
                <tbody>
                  {displayItems
                    .map(item => {
                    return (
                      <tr
                        key={item.id}
                        onClick={() => handleRowClick(item.id)}
                        className={selectedId === item.id ? 'row-selected' : ''}
                        style={{ cursor: 'pointer' }}
                      >
                        <td>
                          <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
                            <RequestPoster url={item.poster_url} category={item.category} />
                            <div style={{ minWidth: 0 }}>
                              <div
                                className="lib-title-link"
                                onClick={e => { e.stopPropagation(); handleRowClick(item.id) }}
                                title="Abrir ficha"
                                style={{ fontWeight: 500 }}
                              >
                                {item.title}
                              </div>
                            </div>
                          </div>
                        </td>
                        <td style={{ fontSize: 12, whiteSpace: 'nowrap' }}>{tipoOf(item.category).icon} {tipoOf(item.category).label}</td>
                        <td>{item.requested_resolution || '—'}</td>
                        <td>{item.requested_source || '—'}</td>
                        <td><CompatibilityBadge status={item.compatibility_status} /></td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>

            {totalPages > 1 && (
              <div className="pagination" style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 12 }}>
                <button className="btn btn-secondary btn-sm" disabled={offset === 0} onClick={() => loadItems(offset - PAGE_SIZE)}>Anterior</button>
                <span style={{ fontSize: 13, color: 'var(--text-secondary)', alignSelf: 'center' }}>{currentPage} / {totalPages}</span>
                <button className="btn btn-secondary btn-sm" disabled={offset + PAGE_SIZE >= total} onClick={() => loadItems(offset + PAGE_SIZE)}>Siguiente</button>
              </div>
            )}
          </div>
        )}

      {selectedId !== null && (
        <div className="modal-overlay" onClick={() => { setSelectedId(null); setDetail(null); setReadiness(null); setShowCandidates(false) }}>
          <div className="modal" style={{ maxWidth: 520 }} onClick={e => e.stopPropagation()}>
            {detailLoading ? (
              <div style={{ padding: 24 }}><LoadingState label="Cargando detalle…" /></div>
            ) : showCandidates ? (
              <CandidatesPanel requestId={selectedId} onClose={() => setShowCandidates(false)} />
            ) : detail ? (
              <DetailPanel
                item={detail}
                readiness={readiness}
                onClose={() => { setSelectedId(null); setDetail(null); setReadiness(null); setShowCandidates(false) }}
                onShowCandidates={() => setShowCandidates(true)}
              />
            ) : null}
          </div>
        </div>
      )}
    </div>
  )
}
