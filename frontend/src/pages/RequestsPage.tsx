import { useState, useEffect, useCallback } from 'react'
import {
  getRequests,
  syncRequests,
  getSyncStatus,
  getRequestDetail,
  markRequestReviewed,
} from '../api/requests'
import type { RequestItemResponse, RequestDetailResponse, RequestSyncStatusResponse } from '../types/api'
import { LoadingState } from '../components/LoadingState'
import { ErrorState } from '../components/ErrorState'
import { EmptyState } from '../components/EmptyState'

const COMPATIBILITY_STATUSES = [
  { value: '', label: 'Todos' },
  { value: 'Compatible', label: 'Compatible' },
  { value: 'Parcial', label: 'Parcial' },
  { value: 'No compatible', label: 'No compatible' },
  { value: 'Llena', label: 'Llena' },
  { value: 'Sin coincidencia', label: 'Sin coincidencia' },
]

function CompatibilityBadge({ status }: { status: string | null }) {
  if (!status) {
    return <span className="badge req-none">Sin coincidencia</span>
  }
  const cls =
    status === 'Compatible' ? 'badge req-compatible' :
    status === 'Parcial' ? 'badge req-partial' :
    status === 'No compatible' ? 'badge req-not-compatible' :
    status === 'Llena' ? 'badge req-filled' :
    'badge req-unknown'
  return <span className={cls}>{status}</span>
}

function SyncInfo({ syncStatus, onSync, syncing }: {
  syncStatus: RequestSyncStatusResponse | null
  onSync: (force: boolean) => void
  syncing: boolean
}) {
  if (!syncStatus) return null
  const { can_sync, wait_seconds, last_sync_at } = syncStatus
  const mins = Math.ceil(wait_seconds / 60)
  return (
    <div className="sync-info">
      {last_sync_at && (
        <span className="sync-info__last">
          Última sync: {new Date(last_sync_at).toLocaleString('es-ES')}
        </span>
      )}
      {!can_sync && (
        <span className="sync-info__throttle">
          Disponible en {mins} min
        </span>
      )}
      <button
        className="btn btn-primary btn-sm"
        onClick={() => onSync(false)}
        disabled={syncing || !can_sync}
      >
        {syncing ? 'Sincronizando…' : 'Sincronizar'}
      </button>
      {!can_sync && (
        <button
          className="btn btn-secondary btn-sm"
          onClick={() => onSync(true)}
          disabled={syncing}
          title="Forzar sincronización ignorando el límite de 1 hora"
        >
          Forzar
        </button>
      )}
    </div>
  )
}

function DetailPanel({ item, onClose, onReviewed }: {
  item: RequestDetailResponse
  onClose: () => void
  onReviewed: () => void
}) {
  const m = item.match
  return (
    <div className="detail-panel">
      <div className="detail-panel__header">
        <div>
          <div className="detail-panel__title">{item.title}</div>
          {item.category && <div className="detail-panel__subtitle">{item.category}</div>}
        </div>
        <button className="btn-icon" onClick={onClose} title="Cerrar">✕</button>
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

      {m && (
        <div className="detail-panel__section">
          <div className="detail-panel__section-title">Cruce con biblioteca</div>
          <div className="detail-row">
            <span>Compatibilidad</span>
            <CompatibilityBadge status={m.status} />
          </div>
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
              <ul>
                {m.reasons.map((r, i) => <li key={i}>{r}</li>)}
              </ul>
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
          <button className="btn btn-secondary btn-sm" onClick={onReviewed}>
            Marcar como revisada
          </button>
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

const PAGE_SIZE = 50

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
  const [detailLoading, setDetailLoading] = useState(false)

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

  const handleSearchChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setSearch(e.target.value)
  }

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    loadItems(0, search, statusFilter)
  }

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
      return
    }
    setSelectedId(id)
    setDetailLoading(true)
    try {
      const d = await getRequestDetail(id)
      setDetail(d)
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

  const totalPages = Math.ceil(total / PAGE_SIZE)
  const currentPage = Math.floor(offset / PAGE_SIZE) + 1

  return (
    <div className="page-split" style={{ display: 'flex', gap: 16, alignItems: 'flex-start' }}>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div className="page-header">
          <div>
            <div className="page-title">Peticiones eMuwarez</div>
            <div className="page-subtitle">
              {total > 0 ? `${total} peticiones` : 'Peticiones activas cruzadas con tu biblioteca local'}
            </div>
          </div>
          <SyncInfo syncStatus={syncStatus} onSync={handleSync} syncing={syncing} />
        </div>

        {syncMsg && (
          <div className="sync-message" style={{ marginBottom: 12, fontSize: 13, color: 'var(--text-secondary)' }}>
            {syncMsg}
          </div>
        )}

        <div className="filters-row" style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
          <form onSubmit={handleSearchSubmit} style={{ flex: 1 }}>
            <input
              className="input"
              type="search"
              placeholder="Buscar por título…"
              value={search}
              onChange={handleSearchChange}
            />
          </form>
          <select className="select" value={statusFilter} onChange={handleStatusChange}>
            {COMPATIBILITY_STATUSES.map(s => (
              <option key={s.value} value={s.value}>{s.label}</option>
            ))}
          </select>
        </div>

        {loading ? (
          <LoadingState label="Cargando peticiones…" />
        ) : error ? (
          <ErrorState message={error} onRetry={() => loadItems()} />
        ) : items.length === 0 ? (
          <EmptyState
            title="Sin peticiones"
            body={
              total === 0 && !search && !statusFilter
                ? 'Sincroniza las peticiones de eMuwarez para verlas aquí.'
                : 'No hay peticiones que coincidan con los filtros.'
            }
            action={total === 0 ? (
              <button className="btn btn-primary btn-sm" onClick={() => handleSync(false)}>
                Sincronizar
              </button>
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
                    <th>Contenido local</th>
                    <th>Estado EMU</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map(item => (
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
                      <td style={{ fontSize: 12 }}>{item.library_title || <span className="text-muted">—</span>}</td>
                      <td style={{ fontSize: 12 }}>{item.emu_status || '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {totalPages > 1 && (
              <div className="pagination" style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 12 }}>
                <button
                  className="btn btn-secondary btn-sm"
                  disabled={offset === 0}
                  onClick={() => loadItems(offset - PAGE_SIZE)}
                >
                  Anterior
                </button>
                <span style={{ fontSize: 13, color: 'var(--text-secondary)', alignSelf: 'center' }}>
                  {currentPage} / {totalPages}
                </span>
                <button
                  className="btn btn-secondary btn-sm"
                  disabled={offset + PAGE_SIZE >= total}
                  onClick={() => loadItems(offset + PAGE_SIZE)}
                >
                  Siguiente
                </button>
              </div>
            )}
          </>
        )}
      </div>

      {selectedId !== null && (
        <div style={{ width: 320, flexShrink: 0 }}>
          {detailLoading ? (
            <div className="detail-panel"><LoadingState label="Cargando detalle…" /></div>
          ) : detail ? (
            <DetailPanel
              item={detail}
              onClose={() => { setSelectedId(null); setDetail(null) }}
              onReviewed={handleReviewed}
            />
          ) : null}
        </div>
      )}
    </div>
  )
}
