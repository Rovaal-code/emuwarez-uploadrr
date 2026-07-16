import { useState, useEffect, useCallback } from 'react'
import { getDashboardSummary, getDashboardActivity, getDashboardLibraryActivity } from '../api/dashboard'
import { getUploads } from '../api/uploads'
import { fetchSettings, type SettingsData } from '../api/settings'
import { getInstances } from '../api/instances'
import type { InstanceSafeResponse } from '../types/api'
import type { DashboardSummaryResponse, DashboardActivityResponse, LibraryItemResponse, UploadJob } from '../types/api'
import { StatCard } from '../components/StatCard'
import { SyncCard } from '../components/SyncCard'
import { useSync } from '../context/SyncContext'
import { EmptyState } from '../components/EmptyState'
import { LoadingState } from '../components/LoadingState'
import { ErrorState } from '../components/ErrorState'
import { StatusBadge } from '../components/StatusBadge'
import { ServiceLabel, ServiceIcon } from '../components/ServiceIcon'
import { UploadWizardModal } from '../components/UploadWizardModal'
import { RequestFormModal } from '../components/RequestFormModal'
import { LibraryActionButtons } from '../components/LibraryActionButtons'
import type { LibraryActionKind } from '../components/LibraryTreeRow'
import { formatBytes, formatDate, formatItemType, parseServerDate } from '../utils/format'
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

// One row of the "Conexiones" card: icon + label + status badge. Only
// actually-configured connections are rendered, so the badge reads
// "Configurado" (or the instance's last test status when available).
function ConnRow({ icon, label, badge = 'Configurado', tone = 'ok' }: {
  icon: React.ReactNode; label: string; badge?: string; tone?: 'ok' | 'warn' | 'error'
}) {
  const cls = tone === 'error' ? 'status-error' : tone === 'warn' ? 'status-partial' : 'status-available'
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
      <span style={{ display: 'flex', width: 18, justifyContent: 'center' }}>{icon}</span>
      <span style={{ flex: 1, fontSize: 13, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{label}</span>
      <span className={`badge ${cls}`}>{badge}</span>
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
  const started = parseServerDate(startedAt).getTime()
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
  const [connInstances, setConnInstances] = useState<InstanceSafeResponse[]>([])
  const [loadingData, setLoadingData] = useState(true)
  const [dataError, setDataError] = useState<string | null>(null)
  const [wizardItem, setWizardItem] = useState<LibraryItemResponse | null>(null)
  const [requestItem, setRequestItem] = useState<LibraryItemResponse | null>(null)
  // Global sync state (shared with Biblioteca/Peticiones and the progress
  // banner). `message` shows the last completion result; `lastCompletedAt`
  // triggers a data reload when any sync finishes.
  const { message: syncMsg, lastCompletedAt } = useSync()

  function handleActivityAction(kind: LibraryActionKind, item: LibraryItemResponse) {
    if (kind === 'request') setRequestItem(item)
    else setWizardItem(item)  // 'upload' → wizard
  }
  const [now, setNow] = useState(Date.now())

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
    getInstances().then(setConnInstances).catch(() => { /* ignore */ })
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

  // Reload the dashboard data whenever any global sync finishes.
  useEffect(() => { if (lastCompletedAt) loadData() }, [lastCompletedAt, loadData])

  // Light polling so the upload activity panel reflects real progress
  // while the dashboard stays open.
  useEffect(() => {
    const t = setInterval(loadData, 15000)
    return () => clearInterval(t)
  }, [loadData])

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
        <SyncCard />
      </div>

      {syncMsg && (
        <div style={{ marginBottom: 12, fontSize: 12, color: 'var(--text-secondary)' }}>{syncMsg}</div>
      )}

      {/* Stat cards */}
      <div className="stat-cards-row">
        <StatCard
          label="Biblioteca sincronizada"
          value={s.library_total}
          info="Total de películas y episodios importados desde tus instancias de Radarr y Sonarr."
        >
          <div style={{ maxHeight: 78, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 2 }}>
            <div className="stat-card-sub-row">
              <ServiceLabel type="radarr" label={`Radarr: ${s.radarr_items}`} size={13} />
            </div>
            <div className="stat-card-sub-row">
              <ServiceLabel type="sonarr" label={`Sonarr: ${s.sonarr_items}`} size={13} />
            </div>
          </div>
        </StatCard>

        <StatCard
          label="Disponibles"
          value={s.available}
          accentColor="var(--color-available)"
          info="Contenido cuyo archivo está presente en disco, listo para comparar o subir."
        />

        <StatCard
          label="Faltantes"
          value={s.missing}
          accentColor="var(--color-missing)"
          info="Contenido que Radarr/Sonarr conocen pero cuyo archivo aún no está en disco (falta, en cola o con error)."
        >
          <div className="stat-card-sub-row" style={{ color: 'var(--text-muted)', fontSize: 12 }}>
            {s.last_sync_at ? `Última sync: ${formatDate(s.last_sync_at)}` : 'Sin sincronizar'}
          </div>
        </StatCard>

        <StatCard
          label="Contenido único"
          value={s.unique_content ?? 0}
          accentColor="#22c55e"
          info="Contenido disponible que aún no está en eMuwarez: las películas, las temporadas completas de series o documentales y sus capítulos. Son tus oportunidades de subida."
        >
          <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            <div className="stat-card-sub-row">🎬 {s.unique_movies ?? 0} películas</div>
            <div className="stat-card-sub-row">📺 {s.unique_seasons ?? 0} temporadas · {s.unique_episodes ?? 0} capítulos</div>
          </div>
        </StatCard>

        <StatCard
          label="Tus subidas"
          value={s.uploads_completed ?? 0}
          accentColor="#3b82f6"
          info="Número de subidas a eMuwarez que has completado con Uploadrr."
        />
      </div>

      {/* eMuwarez requests — cards + a "Sincronizar peticiones" button below.
          20px bottom margin = the flex gap between the activity panels and
          their lower cards, so spacing above and below each panel matches. */}
      <div style={{ marginBottom: 20 }}>
        <div className="stat-cards-row">
          <StatCard
            label="Peticiones eMuwarez"
            value={s.requests_total ?? 0}
            info="Total de peticiones activas descargadas de eMuwarez."
          />
          <StatCard
            label="Mis peticiones"
            value={s.requests_mine ?? 0}
            accentColor="#3b82f6"
            info="Peticiones creadas por tu propio usuario de eMuwarez (según el nombre configurado en Ajustes)."
          />
          <StatCard
            label="Compatibles"
            value={s.requests_compatible ?? 0}
            accentColor="#22c55e"
            info="Peticiones cuya mejor coincidencia en tu biblioteca cumple resolución y source: puedes cubrirlas."
          />
          <StatCard
            label="Parciales"
            value={s.requests_partial ?? 0}
            accentColor="#f59e0b"
            info="Peticiones cuya mejor coincidencia cumple solo parte de lo pedido (resolución o source, pero no ambos)."
          />
          <StatCard
            label="Llenas"
            value={s.requests_filled ?? 0}
            accentColor="#9ca3af"
            info="Peticiones que ya están cubiertas/llenas en eMuwarez."
          />
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
              {(() => {
                const rows: React.ReactNode[] = []
                // Radarr/Sonarr instances (each configured one, with its icon).
                for (const inst of connInstances) {
                  rows.push(
                    <ConnRow key={`inst-${inst.id}`} icon={<ServiceIcon type={inst.type === 'sonarr' ? 'sonarr' : 'radarr'} size={16} />}
                      label={`${inst.type === 'sonarr' ? 'Sonarr' : 'Radarr'}: ${inst.name}`} />
                  )
                }
                if (connSettings?.emu_api_key_configured)
                  rows.push(<ConnRow key="emu" icon={<ServiceIcon type="emu" size={16} />} label="API eMuwarez" />)
                if (connSettings?.tmdb_api_key_configured)
                  rows.push(<ConnRow key="tmdb" icon={<ServiceIcon type="tmdb" size={16} />} label="API TMDb" />)
                if (connSettings?.qbit_configured)
                  rows.push(<ConnRow key="qbit" icon={<ServiceIcon type="qbittorrent" size={16} />} label="qBittorrent" />)
                // Image hosts: imgbox is always the default fallback, plus enabled ones.
                const imgIds = Array.from(new Set(['imgbox', ...(connSettings?.image_hosts_enabled ?? [])]))
                for (const id of imgIds) {
                  const meta = connSettings?.image_hosts_available?.find(h => h.id === id)
                  rows.push(<ConnRow key={`img-${id}`} icon={<ServiceIcon type="imghost" size={16} />}
                    label={`Imágenes: ${meta?.label ?? id}`} />)
                }
                if (connSettings?.notify_discord_webhook_configured)
                  rows.push(<ConnRow key="discord" icon={<ServiceIcon type="discord" size={16} />} label="Bot de Discord" />)
                if (connSettings?.notify_telegram_bot_token_configured)
                  rows.push(<ConnRow key="telegram" icon={<ServiceIcon type="telegram" size={16} />} label="Bot de Telegram" />)
                return rows.length ? rows : <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>Sin conexiones configuradas todavía.</div>
              })()}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
