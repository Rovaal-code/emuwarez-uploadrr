import { useState, useEffect, useCallback, useRef } from 'react'
import { getDashboardSummary, getDashboardActivity, getDashboardLibraryActivity } from '../api/dashboard'
import { getUploads } from '../api/uploads'
import { syncAll } from '../api/library'
import type { DashboardSummaryResponse, DashboardActivityResponse, LibraryItemResponse, UploadJob } from '../types/api'
import { StatCard } from '../components/StatCard'
import { EmptyState } from '../components/EmptyState'
import { LoadingState } from '../components/LoadingState'
import { ErrorState } from '../components/ErrorState'
import { StatusBadge } from '../components/StatusBadge'
import { ServiceLabel } from '../components/ServiceIcon'
import { UploadPreflightModal } from '../components/UploadPreflightModal'
import { formatBytes, formatDate, formatItemType } from '../utils/format'

// Phase 11F — the four sub-phases a *running* upload job can be in, in
// order. compute_progress_phase() on the backend never emits a numeric
// percentage (Uploadrr-EMU doesn't report one) — this is a discrete-step
// bar, not a fabricated percentage.
const RUNNING_PHASES = ['preflight', 'config_staging', 'running', 'finalizing'] as const
const PHASE_LABEL: Record<string, string> = {
  preflight: 'Preflight',
  config_staging: 'Preparando configuración',
  running: 'Subiendo',
  finalizing: 'Finalizando',
}

function elapsedLabel(startedAt: string | null | undefined, now: number): string {
  if (!startedAt) return '—'
  const started = new Date(startedAt).getTime()
  const diffSec = Math.max(0, Math.floor((now - started) / 1000))
  const m = Math.floor(diffSec / 60)
  const sec = diffSec % 60
  return m > 0 ? `${m}m ${sec}s` : `${sec}s`
}

interface DashboardPageProps {
  onNavigate?: (page: string) => void
}

export function DashboardPage({ onNavigate: _onNavigate }: DashboardPageProps = {}) {
  const [summary, setSummary] = useState<DashboardSummaryResponse | null>(null)
  const [taskActivity, setTaskActivity] = useState<DashboardActivityResponse | null>(null)
  const [libraryActivity, setLibraryActivity] = useState<LibraryItemResponse[]>([])
  const [activeUploads, setActiveUploads] = useState<UploadJob[]>([])
  const [loadingData, setLoadingData] = useState(true)
  const [dataError, setDataError] = useState<string | null>(null)
  const [syncing, setSyncing] = useState(false)
  const [syncMsg, setSyncMsg] = useState<string | null>(null)
  const [uploadItem, setUploadItem] = useState<LibraryItemResponse | null>(null)
  const [now, setNow] = useState(Date.now())

  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(t)
  }, [])

  const loadData = useCallback(async () => {
    setLoadingData(true)
    setDataError(null)
    // Promise.allSettled never rejects — each branch's own status carries
    // its outcome, so failures are handled per-item below, not via catch.
    const [s, a, la, up] = await Promise.allSettled([
      getDashboardSummary(),
      getDashboardActivity(),
      getDashboardLibraryActivity(10),
      getUploads({ status: 'running', limit: 5 }),
    ])
    if (s.status === 'fulfilled') setSummary(s.value)
    else setDataError('No se pudieron cargar los datos del dashboard')
    if (a.status === 'fulfilled') setTaskActivity(a.value)
    if (la.status === 'fulfilled') setLibraryActivity(la.value.items)
    if (up.status === 'fulfilled') setActiveUploads(up.value)
    setLoadingData(false)
  }, [])

  useEffect(() => { loadData() }, [loadData])

  // Light polling so the upload activity panel reflects real progress
  // while the dashboard stays open.
  useEffect(() => {
    const t = setInterval(loadData, 15000)
    return () => clearInterval(t)
  }, [loadData])

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

  // First-ever visit to the dashboard (last_sync_at is null): the setup
  // wizard's completion screen promises "la primera sincronización se
  // ejecutará desde el dashboard" — this is what actually keeps that
  // promise, since nothing triggered it automatically before. Guarded by
  // a ref so it only fires once per page load, not on every 15s poll.
  const autoSyncTriggered = useRef(false)
  useEffect(() => {
    if (summary && summary.last_sync_at === null && !autoSyncTriggered.current) {
      autoSyncTriggered.current = true
      handleSync()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [summary])

  if (loadingData && !summary) return <LoadingState label="Cargando dashboard…" />
  if (!summary) return <ErrorState message={dataError ?? 'No se pudieron cargar los datos del dashboard'} onRetry={loadData} />

  const s = summary
  const taskRuns = taskActivity?.items ?? []

  return (
    <div>
      {uploadItem && (
        <UploadPreflightModal
          itemId={uploadItem.id}
          itemTitle={uploadItem.title}
          onClose={() => setUploadItem(null)}
        />
      )}

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

      {/* Peticiones accionables — right under the sync bar, Phase 8B */}
      <div className="activity-section" style={{ marginBottom: 20 }}>
        <div className="section-header">
          <div className="section-title">Peticiones accionables</div>
        </div>
        <div style={{ padding: '12px 20px' }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 10 }}>
            {[
              { label: 'Listas para subir', value: s.requests_ready_to_upload ?? 0, color: 'var(--color-available)' },
              { label: 'Prioridad alta', value: s.requests_high_priority ?? 0, color: '#34d399' },
              { label: 'Necesitan nomenclatura', value: s.requests_need_nomenclature ?? 0, color: '#f59e0b' },
              { label: 'Esperando descarga', value: s.requests_waiting_download ?? 0, color: '#818cf8' },
              { label: 'Bloqueadas', value: s.requests_blocked ?? 0, color: 'var(--color-missing)' },
            ].map(item => (
              <div key={item.label} style={{ padding: '8px 12px', background: 'rgba(255,255,255,0.04)', borderRadius: 6, borderLeft: `3px solid ${item.color}` }}>
                <div style={{ fontSize: '1.2rem', fontWeight: 600, color: item.color }}>{item.value}</div>
                <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>{item.label}</div>
              </div>
            ))}
          </div>
          <p style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginTop: 10, marginBottom: 0 }}>
            Ejecuta "Recalcular readiness" en Peticiones para actualizar.
          </p>
        </div>
      </div>

      {/* Main grid */}
      <div className="dashboard-grid">
        {/* Left — Actividad reciente: library items prioritized by EMU request satisfaction */}
        <div>
          <div className="activity-section">
            <div className="section-header">
              <div className="section-title">Actividad reciente</div>
            </div>
            {libraryActivity.length === 0 ? (
              <EmptyState
                icon="📋"
                title="No hay elementos en la biblioteca todavía"
                body="Ejecuta una sincronización desde el botón superior o desde la sección Instancias."
              />
            ) : (
              <div style={{ overflowX: 'auto' }}>
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Título</th>
                      <th>Origen</th>
                      <th>Estado</th>
                      <th>Petición</th>
                      <th>Nomenclatura</th>
                      <th>Tamaño</th>
                      <th>Actualizado</th>
                      <th className="col-actions">Acciones</th>
                    </tr>
                  </thead>
                  <tbody>
                    {libraryActivity.map(item => (
                      <tr key={item.id}>
                        <td>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                            <div style={{
                              flexShrink: 0, width: 28, height: 42, borderRadius: 4, overflow: 'hidden',
                              background: 'rgba(255,255,255,0.04)', display: 'flex', alignItems: 'center', justifyContent: 'center',
                            }}>
                              {item.poster_url ? (
                                <img
                                  src={item.poster_url}
                                  alt=""
                                  loading="lazy"
                                  style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                                  onError={e => { (e.currentTarget as HTMLImageElement).style.display = 'none' }}
                                />
                              ) : (
                                <span style={{ fontSize: 14, opacity: 0.35 }}>
                                  {item.item_type === 'series' || item.item_type === 'episode' ? '📺' : '🎬'}
                                </span>
                              )}
                            </div>
                            <div>
                              <div style={{ fontWeight: 500 }}>{item.title}</div>
                              <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>{formatItemType(item.item_type)}{item.year ? ` · ${item.year}` : ''}</div>
                            </div>
                          </div>
                        </td>
                        <td>
                          {item.instance_type
                            ? <ServiceLabel type={item.instance_type} label={item.instance_name ?? item.instance_type} size={13} />
                            : <span style={{ color: 'var(--text-muted)' }}>—</span>}
                        </td>
                        <td><StatusBadge status={item.local_status} type="local" /></td>
                        <td><StatusBadge status={item.request_status} type="request" /></td>
                        <td><StatusBadge status={item.nomenclature_status} type="nomenclature" /></td>
                        <td style={{ fontSize: 12, color: 'var(--text-secondary)', whiteSpace: 'nowrap' }}>{formatBytes(item.size_bytes)}</td>
                        <td style={{ fontSize: 12, color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>{formatDate(item.updated_at)}</td>
                        <td className="col-actions">
                          <button className="btn btn-ghost btn-sm" onClick={() => setUploadItem(item)}>Subir</button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>

        {/* Right — Actividad de subida: real running upload jobs, honest data only */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div className="upload-panel">
            <div className="section-header">
              <div className="section-title">Actividad de subida</div>
            </div>
            <div className="upload-panel-body" style={{ padding: '12px 16px', display: 'block', minHeight: 'auto' }}>
              {activeUploads.length === 0 ? (
                <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', margin: 0 }}>
                  No hay subidas en curso ahora mismo.
                </p>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
                  {activeUploads.map(job => {
                    const phase = job.progress_phase ?? 'running'
                    const stepIdx = Math.max(0, RUNNING_PHASES.indexOf(phase as typeof RUNNING_PHASES[number]))
                    const pct = ((stepIdx + 1) / RUNNING_PHASES.length) * 100
                    return (
                      <div key={job.id} style={{ borderBottom: '1px solid var(--border)', paddingBottom: 12 }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                          <span style={{ fontSize: 13, fontWeight: 500 }}>{job.title ?? `Job #${job.id}`}</span>
                          <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>{elapsedLabel(job.started_at, now)}</span>
                        </div>
                        <div className="progress-bar" style={{ marginBottom: 4 }}>
                          <div className="progress-fill" style={{ width: `${pct}%` }} />
                        </div>
                        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: 'var(--text-muted)' }}>
                          <span>Etapa: {PHASE_LABEL[phase] ?? phase}</span>
                          <span>Paso {stepIdx + 1}/{RUNNING_PHASES.length}</span>
                        </div>
                        {job.last_log_at && (
                          <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>
                            Última actividad: {formatDate(job.last_log_at)}
                          </div>
                        )}
                      </div>
                    )
                  })}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Últimas tareas ejecutadas — task_runs history (previously mislabeled "Actividad reciente") */}
      <div className="activity-section" style={{ marginTop: 20 }}>
        <div className="section-header">
          <div className="section-title">Últimas tareas ejecutadas</div>
        </div>
        {taskRuns.length === 0 ? (
          <EmptyState
            icon="🗒️"
            title="No hay tareas ejecutadas todavía"
            body="Las sincronizaciones automáticas y manuales aparecerán aquí."
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
                {taskRuns.map(item => (
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
  )
}
