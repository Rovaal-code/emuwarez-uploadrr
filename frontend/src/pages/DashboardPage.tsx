import { useState, useEffect, useCallback } from 'react'
import { getDashboardSummary, getDashboardActivity } from '../api/dashboard'
import { syncAll } from '../api/library'
import type { DashboardSummaryResponse, DashboardActivityResponse } from '../types/api'
import { StatCard } from '../components/StatCard'
import { EmptyState } from '../components/EmptyState'
import { LoadingState } from '../components/LoadingState'
import { ErrorState } from '../components/ErrorState'
import { StatusBadge } from '../components/StatusBadge'
import { ServiceLabel } from '../components/ServiceIcon'
import { formatDate } from '../utils/format'

export function DashboardPage() {
  const [summary, setSummary] = useState<DashboardSummaryResponse | null>(null)
  const [activity, setActivity] = useState<DashboardActivityResponse | null>(null)
  const [loadingData, setLoadingData] = useState(true)
  const [dataError, setDataError] = useState<string | null>(null)
  const [syncing, setSyncing] = useState(false)
  const [syncMsg, setSyncMsg] = useState<string | null>(null)

  const loadData = useCallback(async () => {
    setLoadingData(true)
    setDataError(null)
    try {
      const [s, a] = await Promise.all([getDashboardSummary(), getDashboardActivity()])
      setSummary(s)
      setActivity(a)
    } catch {
      setDataError('No se pudieron cargar los datos del dashboard')
    } finally {
      setLoadingData(false)
    }
  }, [])

  useEffect(() => { loadData() }, [loadData])

  async function handleSync() {
    setSyncing(true)
    setSyncMsg(null)
    try {
      const result = await syncAll(true)
      setSyncMsg(`Sincronizado: ${result.imported} elementos · ${result.missing} no disponibles`)
      await loadData()
    } catch {
      setSyncMsg('Error durante la sincronización')
    } finally {
      setSyncing(false)
    }
  }

  if (loadingData) return <LoadingState label="Cargando dashboard…" />
  if (dataError) return <ErrorState message={dataError} onRetry={loadData} />

  const s = summary!
  const acts = activity?.items ?? []

  return (
    <div>
      {/* Stat cards */}
      <div className="stat-cards-row">
        <StatCard label="Biblioteca sincronizada" value={s.library_total}>
          <div className="stat-card-sub-row">
            <ServiceLabel type="radarr" label={`Radarr: ${s.radarr_items}`} size={13} />
          </div>
          <div className="stat-card-sub-row">
            <ServiceLabel type="sonarr" label={`Sonarr: ${s.sonarr_items}`} size={13} />
          </div>
        </StatCard>

        <StatCard label="Faltantes" value={s.missing} accentColor="var(--color-missing)">
          <div className="stat-card-sub-row" style={{ color: 'var(--text-muted)', fontSize: 12 }}>
            {s.last_sync_at ? `Última sync: ${formatDate(s.last_sync_at)}` : 'Sin sincronizar'}
          </div>
        </StatCard>

        <StatCard label="Disponibles" value={s.available} accentColor="var(--color-available)" />

        <StatCard label="Subiendo" value={s.uploading} accentColor="var(--color-uploading)" />

        <StatCard label="Completadas" value={s.completed} accentColor="var(--color-uploaded)" />
      </div>

      {/* Sync action bar */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 20 }}>
        <button className="btn btn-primary btn-sm" onClick={handleSync} disabled={syncing}>
          {syncing ? <><span className="spinner" style={{ width: 12, height: 12, borderWidth: 2 }} /> Sincronizando…</> : '↻ Sincronizar biblioteca'}
        </button>
        {syncMsg && (
          <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{syncMsg}</span>
        )}
      </div>

      {/* Main grid */}
      <div className="dashboard-grid">
        {/* Left — activity table */}
        <div>
          <div className="activity-section">
            <div className="section-header">
              <div className="section-title">Actividad reciente</div>
            </div>
            {acts.length === 0 ? (
              <EmptyState
                icon="📋"
                title="No hay actividad reciente todavía"
                body="Ejecuta una sincronización desde el botón superior o desde la sección Instancias."
              />
            ) : (
              <div style={{ overflowX: 'auto' }}>
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Tarea</th>
                      <th>Estado</th>
                      <th>Resumen</th>
                      <th>Iniciada</th>
                      <th>Finalizada</th>
                    </tr>
                  </thead>
                  <tbody>
                    {acts.map(item => (
                      <tr key={item.id}>
                        <td>{item.name}</td>
                        <td>
                          <StatusBadge
                            status={item.status === 'ok' ? 'Disponible' : item.status === 'error' ? 'Error' : 'Desconocido'}
                            type="local"
                          />
                        </td>
                        <td style={{ color: 'var(--text-secondary)', fontSize: 12 }}>{item.summary ?? '—'}</td>
                        <td style={{ color: 'var(--text-muted)', fontSize: 12, whiteSpace: 'nowrap' }}>{formatDate(item.started_at)}</td>
                        <td style={{ color: 'var(--text-muted)', fontSize: 12, whiteSpace: 'nowrap' }}>{formatDate(item.finished_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>

        {/* Right — upload activity panel */}
        <div>
          <div className="upload-panel">
            <div className="section-header">
              <div className="section-title">Actividad de subida</div>
            </div>
            <div className="upload-panel-body">
              <EmptyState
                icon="📤"
                title="Sin subidas activas"
                body="Los trabajos de subida aparecerán aquí cuando inicies una subida desde Biblioteca o Peticiones."
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
