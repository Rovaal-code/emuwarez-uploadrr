import { useState, useEffect, useCallback } from 'react'
import {
  getRequests,
  syncRequests,
  getSyncStatus,
  getRequestDetail,
  markRequestReviewed,
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

const COMPATIBILITY_STATUSES = [
  { value: '', label: 'Todos' },
  { value: 'Compatible', label: 'Compatible' },
  { value: 'Parcial', label: 'Parcial' },
  { value: 'No compatible', label: 'No compatible' },
  { value: 'Llena', label: 'Llena' },
  { value: 'Sin coincidencia', label: 'Sin coincidencia' },
]

function CompatibilityBadge({ status }: { status: string | null }) {
  if (!status) return <span className="badge req-none">Sin coincidencia</span>
  const cls =
    status === 'Compatible' ? 'badge req-compatible' :
    status === 'Parcial' ? 'badge req-partial' :
    status === 'No compatible' ? 'badge req-not-compatible' :
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

function DetailPanel({ item, readiness, onClose, onReviewed, onShowCandidates }: {
  item: RequestDetailResponse
  readiness: RequestReadinessResponse | null
  onClose: () => void
  onReviewed: () => void
  onShowCandidates: () => void
}) {
  const m = item.match
  return (
    <div className="detail-panel">
      <div className="detail-panel__header">
        <div>
          <div className="detail-panel__title">{item.title}</div>
          {item.category && <div className="detail-panel__subtitle">{item.category}</div>}
        </div>
        <button className="btn-icon" onClick={onClose}>✕</button>
      </div>

      <div className="detail-panel__section">
        <div className="detail-row"><span>Resolución pedida</span><span>{item.requested_resolution || '—'}</span></div>
        <div className="detail-row"><span>Source pedido</span><span>{item.requested_source || '—'}</span></div>
        <div className="detail-row"><span>Estado EMU</span><span>{item.emu_status || '—'}</span></div>
        <div className="detail-row"><span>Puntos</span><span>{item.points ?? '—'}</span></div>
        {item.tmdb_id && <div className="detail-row"><span>TMDb</span><span>{item.tmdb_id}</span></div>}
        {item.imdb_id && <div className="detail-row"><span>IMDb</span><span>{item.imdb_id}</span></div>}
        {item.url && (
          <div className="detail-row">
            <span>Enlace</span>
            <a href={item.url} target="_blank" rel="noreferrer" className="link">Ver en eMuwarez</a>
          </div>
        )}
      </div>

      {readiness && (
        <div className="detail-panel__section">
          <div className="detail-panel__section-title">Readiness (Fase 8B)</div>
          <div className="detail-row"><span>Estado</span><ReadinessBadge status={readiness.status} /></div>
          <div className="detail-row"><span>Acción</span><span style={{ fontSize: 12, color: '#a78bfa' }}>{readiness.recommended_action || '—'}</span></div>
          <div className="detail-row"><span>Compat. score</span><span>{readiness.compatibility_score?.toFixed(0) ?? '—'}/100</span></div>
          <div className="detail-row"><span>Readiness score</span><span>{readiness.upload_readiness_score?.toFixed(0) ?? '—'}/100</span></div>
          {readiness.best_library_item_id && (
            <div className="detail-row"><span>Candidato</span><span>#{readiness.best_library_item_id}</span></div>
          )}
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
        </div>
      )}

      {m && (
        <div className="detail-panel__section">
          <div className="detail-panel__section-title">Cruce con biblioteca</div>
          <div className="detail-row"><span>Compatibilidad</span><CompatibilityBadge status={m.status} /></div>
          <div className="detail-row"><span>Confianza</span><span>{Math.round(m.confidence * 100)}%</span></div>
          <div className="detail-row"><span>Contenido local</span><span>{m.library_title || '—'}</span></div>
          <div className="detail-row"><span>Estado local</span><span>{m.local_status || '—'}</span></div>
          <div className="detail-row"><span>Resolución local</span><span>{m.local_resolution || '—'}</span></div>
          <div className="detail-row"><span>Source local</span><span>{m.local_source || '—'}</span></div>
          {m.nomenclature_status && (
            <div className="detail-row"><span>Nomenclatura</span><span>{m.nomenclature_status}</span></div>
          )}
          {m.reasons.length > 0 && (
            <div className="detail-panel__reasons">
              <div className="detail-panel__section-title">Motivos</div>
              <ul>{m.reasons.map((r, i) => <li key={i}>{r}</li>)}</ul>
            </div>
          )}
        </div>
      )}

      {!m && (
        <div className="detail-panel__section">
          <div className="empty-inline">Sin coincidencia en biblioteca local</div>
        </div>
      )}

      <div className="detail-panel__actions">
        {!item.reviewed_at && (
          <button className="btn btn-secondary btn-sm" onClick={onReviewed}>Marcar como revisada</button>
        )}
        {item.reviewed_at && (
          <span className="text-muted" style={{ fontSize: 12 }}>
            Revisada {new Date(item.reviewed_at).toLocaleDateString('es-ES')}
          </span>
        )}
      </div>
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

  const loadItems = useCallback(async (off = 0, q = search, st = statusFilter) => {
    setLoading(true)
    setError(null)
    try {
      const res = await getRequests({ search: q || undefined, status: st || undefined, limit: PAGE_SIZE, offset: off })
      setItems(res.items)
      setTotal(res.total)
      setOffset(off)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Error cargando peticiones')
    } finally {
      setLoading(false)
    }
  }, [search, statusFilter])

  const loadSyncStatus = useCallback(async () => {
    try {
      const s = await getSyncStatus()
      setSyncStatus(s)
    } catch { /* optional */ }
  }, [])

  useEffect(() => {
    loadItems()
    loadSyncStatus()
  }, [])


  const handleStatusChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const val = e.target.value
    setStatusFilter(val)
    loadItems(0, search, val)
  }

  const handleSync = async (force: boolean) => {
    setSyncing(true)
    setSyncMsg(null)
    try {
      const res = await syncRequests(force)
      setSyncMsg(res.message)
      if (res.ok) {
        await loadItems(0)
        await loadSyncStatus()
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

  const handleReviewed = async () => {
    if (!detail) return
    try {
      await markRequestReviewed(detail.id)
      const d = await getRequestDetail(detail.id)
      setDetail(d)
      setItems(prev => prev.map(i => i.id === d.id ? { ...i, reviewed_at: d.reviewed_at } : i))
    } catch { /* silent */ }
  }

  const displayItems = items

  const totalPages = Math.ceil(total / PAGE_SIZE)
  const currentPage = Math.floor(offset / PAGE_SIZE) + 1

  return (
    <div className="page-split" style={{ display: 'flex', gap: 16, alignItems: 'flex-start', height: '100%' }}>
      <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', height: '100%' }}>
        <div className="page-header">
          <div>
            <div className="page-title">Peticiones eMuwarez</div>
            <div className="page-subtitle">
              {total > 0 ? `${total} peticiones` : 'Peticiones activas cruzadas con tu biblioteca local'}
            </div>
          </div>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
            <SyncInfo syncStatus={syncStatus} onSync={handleSync} syncing={syncing} />
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
            onKeyDown={e => e.key === 'Enter' && loadItems(0, search, statusFilter)}
            style={{ minWidth: 220 }}
          />
          <select className="form-input form-select" value={statusFilter} onChange={handleStatusChange} style={{ width: 190 }}>
            {COMPATIBILITY_STATUSES.map(s => (
              <option key={s.value} value={s.value}>{s.label}</option>
            ))}
          </select>
        </div>

        <div style={{ flex: 1, minHeight: 0, overflow: 'auto' }}>
        {loading ? (
          <LoadingState label="Cargando peticiones…" />
        ) : error ? (
          <ErrorState message={error} onRetry={() => loadItems()} />
        ) : displayItems.length === 0 ? (
          <EmptyState
            title="Sin peticiones"
            body={
              total === 0 && !search && !statusFilter
                ? 'Sincroniza las peticiones de eMuwarez para verlas aquí.'
                : 'No hay peticiones que coincidan con los filtros.'
            }
            action={total === 0 ? (
              <button className="btn btn-primary btn-sm" onClick={() => handleSync(false)}>Sincronizar</button>
            ) : undefined}
          />
        ) : (
          <>
            <div className="table-wrapper">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Título</th>
                    <th>Resolución</th>
                    <th>Source</th>
                    <th>Compatibilidad</th>
                    <th>Readiness</th>
                    <th>Acción</th>
                    <th>Candidato</th>
                    <th>Estado EMU</th>
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
                          <div style={{ fontWeight: 500 }}>{item.title}</div>
                          {item.category && <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>{item.category}</div>}
                          {item.reviewed_at && <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>✓ Revisada</span>}
                        </td>
                        <td>{item.requested_resolution || '—'}</td>
                        <td>{item.requested_source || '—'}</td>
                        <td><CompatibilityBadge status={item.compatibility_status} /></td>
                        <td><ReadinessBadge status={item.readiness_status} /></td>
                        <td style={{ fontSize: 11, color: '#a78bfa' }}>{item.readiness_action || '—'}</td>
                        <td style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                          {item.readiness_best_library_item_id ? `#${item.readiness_best_library_item_id}` : '—'}
                        </td>
                        <td style={{ fontSize: 12 }}>{item.emu_status || '—'}</td>
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
          </>
        )}
        </div>
      </div>

      {selectedId !== null && (
        <div style={{ width: 340, flexShrink: 0 }}>
          {detailLoading ? (
            <div className="detail-panel"><LoadingState label="Cargando detalle…" /></div>
          ) : showCandidates ? (
            <CandidatesPanel requestId={selectedId} onClose={() => setShowCandidates(false)} />
          ) : detail ? (
            <DetailPanel
              item={detail}
              readiness={readiness}
              onClose={() => { setSelectedId(null); setDetail(null); setReadiness(null); setShowCandidates(false) }}
              onReviewed={handleReviewed}
              onShowCandidates={() => setShowCandidates(true)}
            />
          ) : null}
        </div>
      )}
    </div>
  )
}
