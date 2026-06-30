import { useState, useEffect, useCallback } from 'react'
import { getMissing } from '../api/missing'
import { refreshArrHealth, verifyLibraryFiles, refreshRecommendations } from '../api/diagnostics'
import type { MissingListResponse } from '../types/api'
import { StatusBadge } from '../components/StatusBadge'
import { ServiceLabel } from '../components/ServiceIcon'
import { LoadingState } from '../components/LoadingState'
import { ErrorState } from '../components/ErrorState'
import { EmptyState } from '../components/EmptyState'
import { formatDate, formatItemType } from '../utils/format'

const PAGE_SIZE = 50

function _queueLabel(status: string | null | undefined): string {
  if (!status) return '—'
  const map: Record<string, string> = {
    downloading: 'Descargando',
    queued: 'En cola',
    pending_import: 'Pend. importar',
    import_error: 'Error importación',
  }
  return map[status] ?? status
}

function _queueColor(status: string | null | undefined): string {
  if (!status) return 'var(--text-muted)'
  if (status === 'downloading') return '#34d399'
  if (status === 'queued') return '#60a5fa'
  if (status === 'import_error') return 'var(--color-missing)'
  return 'var(--text-secondary)'
}

export function MissingPage() {
  const [data, setData] = useState<MissingListResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [offset, setOffset] = useState(0)
  const [actionMsg, setActionMsg] = useState<string | null>(null)
  const [actionLoading, setActionLoading] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const result = await getMissing({ limit: PAGE_SIZE, offset })
      setData(result)
    } catch {
      setError('Error al cargar los faltantes')
    } finally {
      setLoading(false)
    }
  }, [offset])

  useEffect(() => { load() }, [load])

  async function handleRefreshHealth() {
    setActionLoading(true)
    setActionMsg(null)
    try {
      await refreshArrHealth({ include_queue: true, include_history: true })
      setActionMsg('Salud ARR actualizada')
      await load()
    } catch {
      setActionMsg('Error al refrescar salud ARR')
    } finally {
      setActionLoading(false)
    }
  }

  async function handleVerifyFiles() {
    setActionLoading(true)
    setActionMsg(null)
    try {
      const r = await verifyLibraryFiles()
      setActionMsg(`Archivos verificados: ${r.items_checked} · Encontrados: ${r.files_found}`)
      await load()
    } catch {
      setActionMsg('Error al verificar archivos')
    } finally {
      setActionLoading(false)
    }
  }

  async function handleRefreshRecommendations() {
    setActionLoading(true)
    setActionMsg(null)
    try {
      const r = await refreshRecommendations()
      setActionMsg(`Recomendaciones actualizadas: ${r.items_updated}`)
      await load()
    } catch {
      setActionMsg('Error al recalcular recomendaciones')
    } finally {
      setActionLoading(false)
    }
  }

  const items = data?.items ?? []
  const total = data?.total ?? 0

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="page-title">Faltantes</div>
          <div className="page-subtitle">
            Contenido monitorizado en Radarr/Sonarr no disponible localmente
            {total > 0 ? ` · ${total} elementos` : ''}
          </div>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          <button className="btn btn-secondary btn-sm" onClick={handleRefreshHealth} disabled={actionLoading}>
            Refrescar salud ARR
          </button>
          <button className="btn btn-secondary btn-sm" onClick={handleVerifyFiles} disabled={actionLoading}>
            Verificar archivos
          </button>
          <button className="btn btn-secondary btn-sm" onClick={handleRefreshRecommendations} disabled={actionLoading}>
            Recalcular recomendaciones
          </button>
          {actionMsg && <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{actionMsg}</span>}
        </div>
      </div>

      {loading ? (
        <LoadingState label="Cargando faltantes…" />
      ) : error ? (
        <ErrorState message={error} onRetry={load} />
      ) : items.length === 0 ? (
        <EmptyState
          icon="✅"
          title="Sin faltantes"
          body="Toda la biblioteca está disponible localmente. ¡Bien hecho!"
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
                  <th>Queue ARR</th>
                  <th>Diagnóstico</th>
                  <th>Acción recomendada</th>
                  <th>Petición</th>
                  <th>Actualizado</th>
                </tr>
              </thead>
              <tbody>
                {items.map(item => (
                  <tr key={item.id}>
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
                      <span style={{ color: _queueColor(item.arr_queue_status) }}>
                        {_queueLabel(item.arr_queue_status)}
                      </span>
                      {item.arr_queue_progress != null && (
                        <span style={{ color: 'var(--text-muted)', marginLeft: 4 }}>{item.arr_queue_progress}%</span>
                      )}
                      {item.arr_queue_error && (
                        <div style={{ fontSize: 10, color: 'var(--color-missing)', maxWidth: 100, overflow: 'hidden', textOverflow: 'ellipsis' }} title={item.arr_queue_error}>
                          {item.arr_queue_error}
                        </div>
                      )}
                    </td>
                    <td style={{ fontSize: 11, color: 'var(--text-secondary)' }}>
                      {item.diagnostic_status ?? '—'}
                    </td>
                    <td style={{ fontSize: 11, color: '#a78bfa' }}>
                      {item.recommended_action ?? '—'}
                    </td>
                    <td><StatusBadge status={item.request_status} type="request" /></td>
                    <td style={{ fontSize: 12, color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>
                      {formatDate(item.updated_at)}
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
    </div>
  )
}
