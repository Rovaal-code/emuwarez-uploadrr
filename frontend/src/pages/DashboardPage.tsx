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

        {/* Right — panels column */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {/* ARR Health panel (Phase 8A) */}
          <div className="upload-panel">
            <div className="section-header">
              <div className="section-title">Salud Radarr/Sonarr</div>
            </div>
            <div className="upload-panel-body" style={{ padding: '12px 16px' }}>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 8, marginBottom: 10 }}>
                {[
                  { label: 'OK', value: (s as any).arr_health_ok ?? 0, color: 'var(--color-available)' },
                  { label: 'Aviso', value: (s as any).arr_health_warning ?? 0, color: '#f59e0b' },
                  { label: 'Error', value: (s as any).arr_health_error ?? 0, color: 'var(--color-missing)' },
                ].map(item => (
                  <div key={item.label} style={{ padding: '8px 10px', background: 'rgba(255,255,255,0.04)', borderRadius: 6, borderLeft: `3px solid ${item.color}` }}>
                    <div style={{ fontSize: '1.2rem', fontWeight: 600, color: item.color }}>{item.value}</div>
                    <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>{item.label}</div>
                  </div>
                ))}
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6, fontSize: '0.78rem' }}>
                {[
                  { label: 'Archivos OK en disco', value: (s as any).files_verified ?? 0 },
                  { label: 'Path roto', value: (s as any).files_missing_on_disk ?? 0 },
                  { label: 'Listos nomenclatura', value: (s as any).items_ready_for_nomenclature ?? 0 },
                  { label: 'Listos para subir', value: (s as any).items_ready_for_upload ?? 0 },
                  { label: 'Esperando descarga', value: (s as any).items_waiting_download ?? 0 },
                  { label: 'Revisar ARR', value: (s as any).items_need_arr_review ?? 0 },
                ].map(item => (
                  <div key={item.label} style={{ color: 'var(--text-secondary)' }}>
                    <span style={{ color: 'var(--text-muted)' }}>{item.label}: </span>
                    <strong>{item.value}</strong>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Request readiness panel (Phase 8B) */}
          <div className="upload-panel">
            <div className="section-header">
              <div className="section-title">Peticiones accionables</div>
            </div>
            <div className="upload-panel-body" style={{ padding: '12px 16px' }}>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6, fontSize: '0.78rem' }}>
                {[
                  { label: 'Listas para subir', value: (s as any).requests_ready_to_upload ?? 0, color: 'var(--color-available)' },
                  { label: 'Prioridad alta', value: (s as any).requests_high_priority ?? 0, color: '#34d399' },
                  { label: 'Necesitan nomenclatura', value: (s as any).requests_need_nomenclature ?? 0, color: '#f59e0b' },
                  { label: 'Esperando descarga', value: (s as any).requests_waiting_download ?? 0, color: '#818cf8' },
                  { label: 'Bloqueadas', value: (s as any).requests_blocked ?? 0, color: 'var(--color-missing)' },
                ].map(item => (
                  <div key={item.label} style={{ color: 'var(--text-secondary)' }}>
                    <span style={{ color: 'var(--text-muted)' }}>{item.label}: </span>
                    <strong style={{ color: item.color }}>{item.value}</strong>
                  </div>
                ))}
              </div>
              <p style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginTop: 8 }}>
                Ejecuta "Recalcular readiness" en Peticiones para actualizar.
              </p>
            </div>
          </div>

          {/* Upload activity panel */}
          <div className="upload-panel">
            <div className="section-header">
              <div className="section-title">Subidas Uploadrr</div>
            </div>
            <div className="upload-panel-body" style={{ padding: '12px 16px' }}>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
                {[
                  { label: 'Listos', value: (s as any).uploads_ready ?? 0, color: 'var(--color-available)' },
                  { label: 'En curso', value: (s as any).uploads_running ?? 0, color: '#a78bfa' },
                  { label: 'Completados', value: (s as any).uploads_completed ?? 0, color: 'var(--color-uploaded)' },
                  { label: 'Fallidos', value: (s as any).uploads_failed ?? 0, color: 'var(--color-missing)' },
                ].map(item => (
                  <div key={item.label} style={{ padding: '8px 12px', background: 'rgba(255,255,255,0.04)', borderRadius: 6, borderLeft: `3px solid ${item.color}` }}>
                    <div style={{ fontSize: '1.3rem', fontWeight: 600, color: item.color }}>{item.value}</div>
                    <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>{item.label}</div>
                  </div>
                ))}
              </div>
              {(s as any).last_upload_at && (
                <p style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginTop: 10 }}>
                  Última actualización: {formatDate((s as any).last_upload_at)}
                </p>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
