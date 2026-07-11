import { useState, useEffect, useCallback } from 'react'
import { getDashboardSummary, getDashboardActivity, getDashboardLibraryActivity } from '../api/dashboard'
import { getUploads } from '../api/uploads'
import { syncAll } from '../api/library'
import { getSyncStatus, syncRequests } from '../api/requests'
import { fetchSettings, type SettingsData } from '../api/settings'
import type { DashboardSummaryResponse, DashboardActivityResponse, LibraryItemResponse, UploadJob, RequestSyncStatusResponse } from '../types/api'
import { StatCard } from '../components/StatCard'
import { EmptyState } from '../components/EmptyState'
import { LoadingState } from '../components/LoadingState'
import { ErrorState } from '../components/ErrorState'
import { StatusBadge } from '../components/StatusBadge'
import { ServiceLabel, ServiceIcon } from '../components/ServiceIcon'
import { UploadWizardModal } from '../components/UploadWizardModal'
import { RequestFormModal } from '../components/RequestFormModal'
import { LibraryActionButtons } from '../components/LibraryActionButtons'
import type { LibraryActionKind } from '../components/LibraryTreeRow'
import { SyncInfo } from '../components/SyncInfo'
import { formatBytes, formatDate, formatItemType } from '../utils/format'
import { posterUrl } from '../utils/libraryItem'

// Phase 11F — the four sub-phases a *running* upload job can be in, in
// order. compute_progress_phase() on the backend never emits a numeric
// percentage (Uploadrr-EMU doesn't report one) — this is a discrete-step
// bar, not a fabricated percentage.
// Fixed height for the "Actividad reciente" / "Actividad de subida" panels so
// they always match, whether the library is populated or empty. 50% of the
// viewport height, with internal scroll when the content overflows.
const ACTIVITY_PANEL_HEIGHT = '40vh'
// "Últimas tareas ejecutadas" is half the height of the activity panels.
const TASKS_PANEL_HEIGHT = '20vh'

// One row of the "Conexiones" card: icon + label + connected/not-connected badge.
function ConnRow({ icon, label, ok }: { icon: React.ReactNode; label: string; ok: boolean }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
      <span style={{ display: 'flex', width: 18, justifyContent: 'center' }}>{icon}</span>
      <span style={{ flex: 1, fontSize: 13 }}>{label}</span>
      <span className={`badge ${ok ? 'status-available' : 'status-error'}`}>
        {ok ? 'Conectado' : 'No configurado'}
      </span>
    </div>
  )
}

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
  const [connSettings, setConnSettings] = useState<SettingsData | null>(null)
  const [loadingData, setLoadingData] = useState(true)
  const [dataError, setDataError] = useState<string | null>(null)
  const [syncing, setSyncing] = useState(false)
  const [syncMsg, setSyncMsg] = useState<string | null>(null)
  const [wizardItem, setWizardItem] = useState<LibraryItemResponse | null>(null)
  const [requestItem, setRequestItem] = useState<LibraryItemResponse | null>(null)

  function handleActivityAction(kind: LibraryActionKind, item: LibraryItemResponse) {
    if (kind === 'request') setRequestItem(item)
    else setWizardItem(item)  // 'upload' → wizard
  }
  const [now, setNow] = useState(Date.now())

  // eMuwarez requests sync — deliberately separate from library sync
  // (different throttle: 1h vs none) and from readiness recalculation
  // (kept as its own manual action on Peticiones, since it may later get
  // its own independent scheduled cadence).
  const [emuSyncStatus, setEmuSyncStatus] = useState<RequestSyncStatusResponse | null>(null)
  const [emuSyncing, setEmuSyncing] = useState(false)
  const [emuSyncMsg, setEmuSyncMsg] = useState<string | null>(null)

  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(t)
  }, [])

  const loadData = useCallback(async () => {
    setLoadingData(true)
    setDataError(null)
    // Settings first, so "Actividad reciente" honours the configured limit.
    const cfg = await fetchSettings().catch(() => null)
    if (cfg) setConnSettings(cfg)
    const recentLimit = cfg?.recent_activity_limit ?? 50
    // Promise.allSettled never rejects — each branch's own status carries
    // its outcome, so failures are handled per-item below, not via catch.
    const [s, a, la, up] = await Promise.allSettled([
      getDashboardSummary(),
      getDashboardActivity(),
      getDashboardLibraryActivity(recentLimit),
      getUploads({ status: 'running', limit: 50 }),
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

  const loadEmuSyncStatus = useCallback(async () => {
    try {
      const s = await getSyncStatus()
      setEmuSyncStatus(s)
    } catch { /* optional */ }
  }, [])

  useEffect(() => { loadEmuSyncStatus() }, [loadEmuSyncStatus])

  async function handleEmuSync(force: boolean) {
    setEmuSyncing(true)
    setEmuSyncMsg(null)
    try {
      const res = await syncRequests(force)
      setEmuSyncMsg(res.message)
      if (res.ok) {
        await loadData()
        await loadEmuSyncStatus()
      }
    } catch (e: unknown) {
      setEmuSyncMsg(e instanceof Error ? e.message : 'Error al sincronizar')
    } finally {
      setEmuSyncing(false)
    }
  }

  if (loadingData && !summary) return <LoadingState label="Cargando dashboard…" />
  if (!summary) return <ErrorState message={dataError ?? 'No se pudieron cargar los datos del dashboard'} onRetry={loadData} />

  const s = summary
  const taskRuns = (taskActivity?.items ?? []).slice(0, 50)

  return (
    <div>
      {wizardItem && (
        <UploadWizardModal item={wizardItem} onClose={() => setWizardItem(null)} onDone={loadData} />
      )}
      {requestItem && (
        <RequestFormModal item={requestItem} onClose={() => setRequestItem(null)} />
      )}

      <div className="page-header">
        <div>
          <div className="page-title">Dashboard</div>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          <button className="btn btn-primary btn-sm" onClick={handleSync} disabled={syncing}>
            {syncing ? <><span className="spinner" style={{ width: 12, height: 12, borderWidth: 2 }} /> Sincronizando…</> : '↻ Sincronizar biblioteca'}
          </button>
          <SyncInfo syncStatus={emuSyncStatus} onSync={handleEmuSync} syncing={emuSyncing} label="Sincronizar peticiones" allowForce={false} />
        </div>
      </div>
      {(syncMsg || emuSyncMsg) && (
        <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', marginBottom: 12, fontSize: 12, color: 'var(--text-secondary)' }}>
          {syncMsg && <span>{syncMsg}</span>}
          {emuSyncMsg && <span>{emuSyncMsg}</span>}
        </div>
      )}

      {/* Stat cards */}
      <div className="stat-cards-row">
        <StatCard label="Biblioteca sincronizada" value={s.library_total}>
          <div style={{ maxHeight: 78, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 2 }}>
            <div className="stat-card-sub-row">
              <ServiceLabel type="radarr" label={`Radarr: ${s.radarr_items}`} size={13} />
            </div>
            <div className="stat-card-sub-row">
              <ServiceLabel type="sonarr" label={`Sonarr: ${s.sonarr_items}`} size={13} />
            </div>
          </div>
        </StatCard>

        <StatCard label="Disponibles" value={s.available} accentColor="var(--color-available)" />

        <StatCard label="Faltantes" value={s.missing} accentColor="var(--color-missing)">
          <div className="stat-card-sub-row" style={{ color: 'var(--text-muted)', fontSize: 12 }}>
            {s.last_sync_at ? `Última sync: ${formatDate(s.last_sync_at)}` : 'Sin sincronizar'}
          </div>
        </StatCard>

        <StatCard label="Subiendo" value={s.uploading} accentColor="var(--color-uploading)" />

        <StatCard label="Completadas" value={s.completed} accentColor="var(--color-uploaded)" />
      </div>

      {/* eMuwarez requests — cards + a "Sincronizar peticiones" button below.
          20px bottom margin = the flex gap between the activity panels and
          their lower cards, so spacing above and below each panel matches. */}
      <div style={{ marginBottom: 20 }}>
        <div className="stat-cards-row">
          <StatCard label="Peticiones eMuwarez" value={s.requests_total ?? 0} />
          <StatCard label="Lista para subir" value={s.requests_ready_to_upload ?? 0} accentColor="var(--color-available)" />
          <StatCard label="Compatibles" value={s.requests_need_nomenclature ?? 0} accentColor="#f59e0b" />
          <StatCard label="Mis peticiones" value={s.requests_mine ?? 0} accentColor="#818cf8" />
          <StatCard label="Completadas" value={s.requests_filled ?? 0} accentColor="var(--color-uploaded)" />
        </div>
      </div>

      {/* Main grid */}
      <div className="dashboard-grid">
        {/* Left column — "Actividad reciente" (50vh) with "Últimas tareas
            ejecutadas" (25vh) stacked under it, so tasks sits parallel to the
            "Conexiones" card in the right column. */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
          <div className="activity-section" style={{ height: ACTIVITY_PANEL_HEIGHT, display: 'flex', flexDirection: 'column', marginBottom: 0 }}>
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
              <div style={{ overflowX: 'auto', overflowY: 'auto', flex: 1 }}>
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
                                  src={posterUrl(item.poster_url, 'w154')}
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
                          <div style={{ display: 'flex', gap: 6, justifyContent: 'flex-start', alignItems: 'center' }}>
                            <LibraryActionButtons item={item} onAction={handleActivityAction} />
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* Últimas tareas ejecutadas — parallel to "Conexiones" on the right. */}
          <div className="activity-section" style={{ height: TASKS_PANEL_HEIGHT, display: 'flex', flexDirection: 'column', marginBottom: 0 }}>
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
              <div style={{ overflowX: 'auto', overflowY: 'auto', flex: 1 }}>
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
                          <StatusBadge status={item.status ?? ''} type="task" />
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

        {/* Right — Actividad de subida: real running upload jobs, honest data only.
            Stretches to the full height of "Actividad reciente" on its left. */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
          <div className="upload-panel" style={{ height: ACTIVITY_PANEL_HEIGHT, display: 'flex', flexDirection: 'column' }}>
            <div className="section-header">
              <div className="section-title">Actividad de subida</div>
            </div>
            <div className="upload-panel-body" style={{ padding: '12px 16px', display: 'block', minHeight: 'auto', flex: 1, overflowY: 'auto' }}>
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

          {/* Estado de conexiones — misma altura que "Últimas tareas ejecutadas" */}
          <div className="upload-panel" style={{ height: TASKS_PANEL_HEIGHT, display: 'flex', flexDirection: 'column' }}>
            <div className="section-header">
              <div className="section-title">Conexiones</div>
            </div>
            <div style={{ padding: '10px 16px', display: 'flex', flexDirection: 'column', gap: 10, overflowY: 'auto', flex: 1 }}>
              <ConnRow icon={<ServiceIcon type="emu" size={16} />} label="API eMuwarez" ok={!!connSettings?.emu_api_key_configured} />
              <ConnRow icon={<span style={{ fontSize: 15, lineHeight: 1 }}>🎬</span>} label="API TMDb" ok={!!connSettings?.tmdb_api_key_configured} />
              <ConnRow icon={<ServiceIcon type="discord" size={16} />} label="Bot de Discord" ok={!!connSettings?.notify_discord_webhook_configured} />
              <ConnRow icon={<ServiceIcon type="telegram" size={16} />} label="Bot de Telegram" ok={!!connSettings?.notify_telegram_bot_token_configured} />
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
