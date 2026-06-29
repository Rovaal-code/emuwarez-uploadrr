import { useState, useEffect, useCallback } from 'react'
import { getMissing } from '../api/missing'
import type { MissingListResponse } from '../types/api'
import { StatusBadge } from '../components/StatusBadge'
import { ServiceLabel } from '../components/ServiceIcon'
import { LoadingState } from '../components/LoadingState'
import { ErrorState } from '../components/ErrorState'
import { EmptyState } from '../components/EmptyState'
import { formatDate, formatItemType } from '../utils/format'

const PAGE_SIZE = 50

export function MissingPage() {
  const [data, setData] = useState<MissingListResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [offset, setOffset] = useState(0)

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
                  <th>Petición</th>
                  <th>Actualizado</th>
                  <th className="col-actions">Acciones</th>
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
                    <td><StatusBadge status={item.request_status} type="request" /></td>
                    <td style={{ fontSize: 12, color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>
                      {formatDate(item.updated_at)}
                    </td>
                    <td className="col-actions">
                      <div style={{ display: 'flex', gap: 6, justifyContent: 'flex-end' }}>
                        <button className="btn btn-ghost btn-sm" disabled title="Pendiente de endpoint EMU">Comprobar en EMU</button>
                        <button
                          className="btn btn-ghost btn-sm"
                          disabled
                          title="Pendiente de capturar endpoint real de eMuwarez"
                        >
                          Crear petición
                        </button>
                      </div>
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
