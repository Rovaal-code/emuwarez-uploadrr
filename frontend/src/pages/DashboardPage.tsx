import { useState, useEffect, useCallback } from 'react'
import { getDashboardSummary, getDashboardActivity, getDashboardRecommendations, type DashboardRecommendationItem } from '../api/dashboard'
import { getUploads } from '../api/uploads'
import { fetchSettings, type SettingsData } from '../api/settings'
import { getInstances } from '../api/instances'
import type { InstanceSafeResponse } from '../types/api'
import type { DashboardSummaryResponse, DashboardActivityResponse, UploadJob } from '../types/api'
import { StatCard } from '../components/StatCard'
import { SyncCard } from '../components/SyncCard'
import { useSync } from '../context/SyncContext'
import { EmptyState } from '../components/EmptyState'
import { LoadingState } from '../components/LoadingState'
import { ErrorState } from '../components/ErrorState'
import { StatusBadge } from '../components/StatusBadge'
import { ServiceLabel, ServiceIcon } from '../components/ServiceIcon'
import { Favicon, domainOf } from '../components/Favicon'
import { UploadWizardModal } from '../components/UploadWizardModal'
import { RequestFormModal } from '../components/RequestFormModal'
import { useTooltip, HoverTitle } from '../components/Tooltip'
import { getLibraryItem } from '../api/library'
import type { LibraryItemResponse } from '../types/api'
import { formatBytes, formatDate, formatItemType } from '../utils/format'
import { posterUrl } from '../utils/libraryItem'
import {
  ACTIVE_JOB_STATUSES, STATUS_CLASS, statusLabel, phaseLabel, currentPhaseInfo,
  progressCounter, queuedSecondsLeft, useTicker,
} from '../utils/uploadStatus'

// Phase 11G — "Recomendaciones" groups, in the order they appear. The content
// name always links to its Biblioteca detail; the "Acción" button is
// group-specific: view the existing request, upload, or create a request.
type RecAction = 'view-request' | 'upload' | 'request'
const REC_GROUP_META: Record<number, {
  category: string; recommendation: string
  action: RecAction; actionLabel: string
  color: string; bg: string; border: string
}> = {
  1: { category: 'Petición Compatible', recommendation: 'Revisa la petición, quizás puedas reclamarla',
       action: 'view-request', actionLabel: 'Ver Petición',
       color: '#22c55e', bg: 'rgba(34,197,94,0.14)', border: 'rgba(34,197,94,0.35)' },
  2: { category: 'Contenido único', recommendation: 'Podrías subirlo a eMuwarez',
       action: 'upload', actionLabel: 'Subir a eMuwarez',
       color: '#a855f7', bg: 'rgba(168,85,247,0.14)', border: 'rgba(168,85,247,0.35)' },
  3: { category: 'Faltante', recommendation: 'Pídelo en eMuwarez',
       action: 'request', actionLabel: 'Petición a eMuwarez',
       color: '#ef4444', bg: 'rgba(239,68,68,0.14)', border: 'rgba(239,68,68,0.35)' },
}

// task_runs.name is the internal task key (services/scheduler.py's
// TASK_LIBRARY_SYNC/TASK_EMU_SYNC) — same human names Ajustes → Tareas
// programadas already shows for these same keys (services/scheduler.py's
// DEFAULT_TASKS). Unknown/future keys just fall back to the raw key.
const TASK_NAME_LABEL: Record<string, string> = {
  'sync-library': 'Sincronizar bibliotecas',
  'sync-emu-requests': 'Sincronizar peticiones eMuwarez',
}
function taskNameLabel(name: string): string {
  return TASK_NAME_LABEL[name] || name
}

// One row of the "Conexiones" card: icon + label + status badge. Only
// actually-configured connections are rendered, so the badge reads
// "Configurado" (or the instance's last test status when available).
function ConnRow({ icon, label, href, badge = 'Configurado', tone = 'ok' }: {
  icon: React.ReactNode; label: string; href?: string | null; badge?: string; tone?: 'ok' | 'warn' | 'error'
}) {
  const cls = tone === 'error' ? 'status-error' : tone === 'warn' ? 'status-partial' : 'status-available'
  const { triggerProps, tooltipNode } = useTooltip(href ? `Abrir ${label}` : null)
  const inner = (
    <>
      <span style={{ display: 'flex', width: 18, justifyContent: 'center' }}>{icon}</span>
      <span style={{ flex: 1, fontSize: 13, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{label}</span>
    </>
  )
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
      {href
        ? <a className="hover-link" href={href} target="_blank" rel="noreferrer" {...triggerProps}
             style={{ display: 'flex', alignItems: 'center', gap: 10, flex: 1, minWidth: 0 }}>{inner}{tooltipNode}</a>
        : <div style={{ display: 'flex', alignItems: 'center', gap: 10, flex: 1, minWidth: 0 }}>{inner}</div>}
      <span className={`badge ${cls}`}>{badge}</span>
    </div>
  )
}

// Panel HUD stat-card icons — large, single-purpose per metric (matches the
// approved holographic reference; other pages' StatCard usage is unaffected
// since the `icon` prop only renders inside `.panel-hud`'s CSS scope).
function svgIcon(d: React.ReactNode) {
  // strokeLinecap="round" is what makes ICON_MISSING's "M12 17h.01" trick (a
  // near-zero-length segment, the standard way to draw the exclamation
  // mark's dot) actually render as a dot instead of vanishing — without it
  // the default "butt" cap draws nothing for a zero-length line.
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">{d}</svg>
}
const ICON_LIBRARY = svgIcon(<><ellipse cx="12" cy="5" rx="8" ry="3" /><path d="M4 5v6c0 1.7 3.6 3 8 3s8-1.3 8-3V5" /><path d="M4 11v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6" /></>)
const ICON_AVAILABLE = svgIcon(<><path d="M21 15V6a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v9" /><path d="M2 15h20l-2 5H4l-2-5z" /></>)
const ICON_MISSING = svgIcon(<><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z" /><path d="M12 9v4M12 17h.01" /></>)
const ICON_UNIQUE = svgIcon(<><circle cx="12" cy="12" r="9" /><path d="M10 8l6 4-6 4V8z" /></>)
const ICON_UPLOADS = svgIcon(<path d="M12 19V5M5 12l7-7 7 7" />)
const ICON_REQUESTS = svgIcon(<><rect x="9" y="3" width="6" height="4" rx="1" /><path d="M9 12h6M9 16h4" /></>)
const ICON_COMPATIBLE = svgIcon(<><circle cx="12" cy="12" r="9" /><path d="M8.5 12.3l2.3 2.3 4.7-4.7" /></>)
const ICON_PARTIAL = svgIcon(<><circle cx="12" cy="12" r="9" /><path d="M12 3a9 9 0 0 1 0 18z" fill="currentColor" stroke="none" /></>)
const ICON_RECLAIMED = svgIcon(<><path d="M5 21V4" /><path d="M5 4h13l-3.2 4.2L18 12.5H5" /></>)
const ICON_MINE = svgIcon(<><circle cx="12" cy="8" r="4" /><path d="M4 21c0-4 4-6 8-6s8 2 8 6" /></>)

interface DashboardPageProps {
  onNavigate?: (page: string) => void
}

export function DashboardPage({ onNavigate }: DashboardPageProps = {}) {
  // Open a recommendation's target: group 1 → its eMuwarez request (Peticiones
  // tab), groups 2 & 3 → the content's own detail page (Biblioteca tab). Both
  // stash an id that the destination page reads on mount.
  // The content name always opens its own Biblioteca detail page (all groups).
  const openLibraryDetail = (item: DashboardRecommendationItem) => {
    try { sessionStorage.setItem('emuwarez_open_library_item', String(item.id)) } catch { /* ignore */ }
    onNavigate?.('library')
  }

  // "Actividad de subida" title → same stash-and-navigate handoff, opening
  // that job's own detail page in Subidas.
  const goToUpload = (jobId: number) => {
    try { sessionStorage.setItem('emuwarez_open_upload', String(jobId)) } catch { /* ignore */ }
    onNavigate?.('uploads')
  }

  // "Acción" column, group-specific: group 1 → open the existing request;
  // group 2 → open the upload wizard; group 3 → open the request form. Groups
  // 2 & 3 fetch the full library item first.
  const handleRecAction = async (item: DashboardRecommendationItem) => {
    const meta = REC_GROUP_META[item.rec_group] ?? REC_GROUP_META[2]
    if (meta.action === 'view-request') {
      if (item.rec_request_id != null) {
        try { sessionStorage.setItem('emuwarez_open_request', String(item.rec_request_id)) } catch { /* ignore */ }
        onNavigate?.('requests')
      }
      return
    }
    try {
      const libItem = await getLibraryItem(item.id)
      if (meta.action === 'request') setRequestItem(libItem)
      else { setWizardPreselect(undefined); setWizardItem(libItem) }
    } catch { /* ignore — the content may have vanished since the last sync */ }
  }

  const [summary, setSummary] = useState<DashboardSummaryResponse | null>(null)
  const [taskActivity, setTaskActivity] = useState<DashboardActivityResponse | null>(null)
  const [recommendations, setRecommendations] = useState<DashboardRecommendationItem[]>([])
  const [activeUploads, setActiveUploads] = useState<UploadJob[]>([])
  const [connSettings, setConnSettings] = useState<SettingsData | null>(null)
  const [connInstances, setConnInstances] = useState<InstanceSafeResponse[]>([])
  const [loadingData, setLoadingData] = useState(true)
  const [dataError, setDataError] = useState<string | null>(null)
  const [wizardItem, setWizardItem] = useState<LibraryItemResponse | null>(null)
  const [wizardPreselect, setWizardPreselect] = useState<{ season?: number | null; episode?: number | null } | undefined>(undefined)
  const [requestItem, setRequestItem] = useState<LibraryItemResponse | null>(null)
  // Global sync state (shared with Biblioteca/Peticiones and the progress
  // banner). `message` shows the last completion result; `lastCompletedAt`
  // triggers a data reload when any sync finishes.
  const { message: syncMsg, lastCompletedAt } = useSync()
  // The empty-state hologram has no room for a caption of its own — the
  // explanation lives in a hover tooltip instead, styled like the rest of
  // the app's tooltips (not a native title box).
  const { triggerProps: uploadEmptyTip, tooltipNode: uploadEmptyTooltip } = useTooltip('No hay subidas en curso ahora mismo.')

  useTicker(activeUploads.some(j => j.status === 'queued'))

  const loadData = useCallback(async () => {
    setLoadingData(true)
    setDataError(null)
    // Settings first, so "Recomendaciones" honours the configured limit.
    const cfg = await fetchSettings().catch(() => null)
    if (cfg) setConnSettings(cfg)
    getInstances().then(setConnInstances).catch(() => { /* ignore */ })
    const recentLimit = cfg?.recent_activity_limit ?? 100
    // Promise.allSettled never rejects — each branch's own status carries
    // its outcome, so failures are handled per-item below, not via catch.
    const [s, a, la, up] = await Promise.allSettled([
      getDashboardSummary(),
      getDashboardActivity(),
      getDashboardRecommendations(recentLimit),
      // Unfiltered — 'running' alone would miss 'staging'/'queued'/'preparing'
      // jobs (e.g. a job that was just retried starts 'queued', not
      // 'running'); narrowed to the live statuses client-side below.
      getUploads({ limit: 50 }),
    ])
    if (s.status === 'fulfilled') setSummary(s.value)
    else setDataError('No se pudieron cargar los datos del dashboard')
    if (a.status === 'fulfilled') setTaskActivity(a.value)
    if (la.status === 'fulfilled') setRecommendations(la.value.items)
    if (up.status === 'fulfilled') setActiveUploads(up.value.filter(j => ACTIVE_JOB_STATUSES.has(j.status)))
    setLoadingData(false)
  }, [])

  useEffect(() => { loadData() }, [loadData])

  // Reload the dashboard data whenever any global sync finishes.
  useEffect(() => { if (lastCompletedAt) loadData() }, [lastCompletedAt, loadData])

  // Light polling for the whole dashboard (summary/recommendations/tasks).
  useEffect(() => {
    const t = setInterval(loadData, 15000)
    return () => clearInterval(t)
  }, [loadData])

  // "Actividad de subida" needs a much faster refresh than the rest of the
  // dashboard — at 15s, a job's progress visibly jumps in big steps instead
  // of reading as live. Same 2.5s cadence Subidas' own table uses, but
  // scoped to just this fetch so it doesn't reload the whole dashboard.
  const loadActiveUploads = useCallback(async () => {
    try {
      const up = await getUploads({ limit: 50 })
      setActiveUploads(up.filter(j => ACTIVE_JOB_STATUSES.has(j.status)))
    } catch { /* ignore — next tick retries */ }
  }, [])
  const hasLiveUpload = activeUploads.length > 0
  useEffect(() => {
    if (!hasLiveUpload) return
    const t = setInterval(loadActiveUploads, 2500)
    return () => clearInterval(t)
  }, [hasLiveUpload, loadActiveUploads])

  if (loadingData && !summary) return <LoadingState label="Cargando Panel…" />
  if (!summary) return <ErrorState message={dataError ?? 'No se pudieron cargar los datos del dashboard'} onRetry={loadData} />

  const s = summary
  const taskRuns = (taskActivity?.items ?? []).slice(0, 50)

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      {wizardItem && (
        <UploadWizardModal item={wizardItem} preselect={wizardPreselect} onClose={() => setWizardItem(null)} onDone={loadData} onNavigate={onNavigate} />
      )}
      {requestItem && (
        <RequestFormModal item={requestItem} onClose={() => setRequestItem(null)} />
      )}

      <div className="page-header" style={{ flexShrink: 0 }}>
        <div>
          <div className="page-title">Panel</div>
        </div>
        <SyncCard />
      </div>

      {syncMsg && (
        <div style={{ marginBottom: 12, fontSize: 12, color: 'var(--text-secondary)', flexShrink: 0 }}>{syncMsg}</div>
      )}

      {/* Stat cards */}
      <div className="stat-cards-row" style={{ flexShrink: 0 }}>
        <StatCard
          icon={ICON_LIBRARY}
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
          icon={ICON_AVAILABLE}
          label="Disponibles"
          value={s.available}
          accentColor="var(--color-available)"
          info="Contenido cuyo archivo está presente en disco, listo para comparar o subir."
        />

        <StatCard
          icon={ICON_MISSING}
          label="Faltantes"
          value={s.missing}
          accentColor="var(--color-missing)"
          info="Contenido que Radarr/Sonarr conocen pero cuyo archivo aún no está en disco (falta, en cola o con error)."
        />

        <StatCard
          icon={ICON_UNIQUE}
          label="Contenido único"
          value={s.unique_content ?? 0}
          accentColor="#a855f7"
          info="Contenido disponible que aún no está en eMuwarez: las películas, las temporadas completas de series o documentales y sus capítulos. Son tus oportunidades de subida."
        >
          <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            <div className="stat-card-sub-row">🎬 {s.unique_movies ?? 0} películas</div>
            <div className="stat-card-sub-row">📺 {s.unique_seasons ?? 0} temporadas · {s.unique_episodes ?? 0} capítulos</div>
          </div>
        </StatCard>

        <StatCard
          icon={ICON_UPLOADS}
          label="Tus subidas"
          value={s.uploads_completed ?? 0}
          accentColor="#3b82f6"
          info="Número de subidas a eMuwarez que has completado con Uploadrr."
        />
      </div>

      {/* eMuwarez requests — cards + a "Sincronizar peticiones" button below.
          20px bottom margin = the flex gap between the activity panels and
          their lower cards, so spacing above and below each panel matches. */}
      <div style={{ marginBottom: 20, flexShrink: 0 }}>
        <div className="stat-cards-row">
          <StatCard
            icon={ICON_REQUESTS}
            label="Peticiones eMuwarez"
            value={s.requests_total ?? 0}
            info="Total de peticiones activas descargadas de eMuwarez."
          />
          <StatCard
            icon={ICON_COMPATIBLE}
            label="Peticiones Compatibles"
            value={s.requests_compatible ?? 0}
            accentColor="#22c55e"
            info="Peticiones cuya mejor coincidencia en tu biblioteca cumple resolución y source: quizás puedas cubrirlas."
          />
          <StatCard
            icon={ICON_PARTIAL}
            label="Peticiones Parciales"
            value={s.requests_partial ?? 0}
            accentColor="#f59e0b"
            info="Peticiones cuya mejor coincidencia cumple solo parte de lo pedido (resolución o source, pero no ambos)."
          />
          <StatCard
            icon={ICON_RECLAIMED}
            label="Reclamadas"
            value={s.requests_reclaimed ?? 0}
            accentColor="#a855f7"
            info="Peticiones ya Reclamadas en eMuwarez. eMuwarez no permite saber si el reclamo es tuyo, así que es el total de reclamadas, no solo las tuyas."
          />
          <StatCard
            icon={ICON_MINE}
            label="Mis Peticiones"
            value={s.requests_mine ?? 0}
            accentColor="#3b82f6"
            info="Peticiones creadas por tu propio usuario de eMuwarez (según el nombre configurado en Ajustes)."
          />
        </div>
      </div>

      {/* Main grid — fills the remaining height exactly (flex:1, minHeight:0)
          so the page itself never scrolls; each panel below keeps its own
          internal scroll via its inner `overflow: auto` div. */}
      <div className="dashboard-grid" style={{ flex: 1, minHeight: 0 }}>
        {/* Left column — "Actividad reciente" (50vh) with "Últimas tareas
            ejecutadas" (25vh) stacked under it, so tasks sits parallel to the
            "Conexiones" card in the right column. */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 20, minHeight: 0 }}>
          <div className="activity-section" style={{ flex: 2, minHeight: 0, display: 'flex', flexDirection: 'column', marginBottom: 0 }}>
            <div className="section-header">
              <div className="section-title">Recomendaciones</div>
            </div>
            {recommendations.length === 0 ? (
              <EmptyState
                icon="✨"
                title="No hay recomendaciones todavía"
                body="Sincroniza tu biblioteca, eMuwarez y las peticiones para ver aquí qué subir o pedir."
              />
            ) : (
              <div style={{ overflowX: 'auto', overflowY: 'auto', flex: 1 }}>
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Nombre</th>
                      <th>Tipo</th>
                      <th>Categoría</th>
                      <th>Recomendación</th>
                      <th>Tamaño</th>
                      <th className="col-actions">Acción</th>
                    </tr>
                  </thead>
                  <tbody>
                    {recommendations.map(item => {
                      const meta = REC_GROUP_META[item.rec_group] ?? REC_GROUP_META[2]
                      return (
                      <tr key={`${item.rec_group}-${item.rec_request_id ?? item.id}`}>
                        <td>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                            <div className="poster-thumb" style={{
                              flexShrink: 0, width: 28, height: 42, borderRadius: 4, overflow: 'hidden',
                              display: 'flex', alignItems: 'center', justifyContent: 'center',
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
                                  {item.item_type === 'series' || item.item_type === 'season' || item.item_type === 'episode' ? '📺' : '🎬'}
                                </span>
                              )}
                            </div>
                            <HoverTitle className="hover-link" style={{ fontWeight: 500, minWidth: 0 }} onClick={() => openLibraryDetail(item)} tip="Ver ficha del contenido">{item.content_name}</HoverTitle>
                          </div>
                        </td>
                        <td style={{ fontSize: 12, color: 'var(--text-secondary)', whiteSpace: 'nowrap' }}>{formatItemType(item.item_type)}</td>
                        <td>
                          <span className="badge" style={{
                            color: meta.color, background: meta.bg, border: `1px solid ${meta.border}`, whiteSpace: 'nowrap',
                          }}>{meta.category}</span>
                        </td>
                        <td style={{ fontSize: 12, color: 'var(--text-secondary)', whiteSpace: 'nowrap' }}>{meta.recommendation}</td>
                        <td style={{ fontSize: 12, color: 'var(--text-secondary)', whiteSpace: 'nowrap' }}>{formatBytes(item.size_bytes)}</td>
                        <td className="col-actions">
                          <button className="btn btn-primary btn-sm" style={{ whiteSpace: 'nowrap' }} onClick={() => handleRecAction(item)}>
                            {meta.actionLabel}
                          </button>
                        </td>
                      </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* Últimas tareas ejecutadas — parallel to "Conexiones" on the right. */}
          <div className="activity-section" style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', marginBottom: 0 }}>
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
                        <td>{taskNameLabel(item.name)}</td>
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
        <div style={{ display: 'flex', flexDirection: 'column', gap: 20, minHeight: 0 }}>
          <div className="upload-panel" style={{ flex: 2, minHeight: 0, display: 'flex', flexDirection: 'column' }}>
            <div className="section-header">
              <div className="section-title">Actividad de subida</div>
            </div>
            <div className="upload-panel-body" style={{
              padding: '12px 16px', display: 'flex', flexDirection: 'column',
              justifyContent: activeUploads.length === 0 ? 'flex-end' : 'flex-start',
              alignItems: 'stretch',
              minHeight: 'auto', flex: 1, overflowY: 'auto',
            }}>
              {activeUploads.length === 0 ? (
                <div className="hud-projection" {...uploadEmptyTip} style={{ cursor: 'help' }}>
                  {uploadEmptyTooltip}
                  <svg viewBox="0 0 260 196" className="hud-projection-svg">
                    <defs>
                      <linearGradient id="hudBeamGrad" x1="0" y1="1" x2="0" y2="0">
                        <stop offset="0%" stopColor="#2fd8ff" stopOpacity=".95" /><stop offset="100%" stopColor="#2fd8ff" stopOpacity="0" />
                      </linearGradient>
                      <radialGradient id="hudFloorGrad" cx="50%" cy="50%" r="50%">
                        <stop offset="0%" stopColor="#2fd8ff" stopOpacity=".5" /><stop offset="100%" stopColor="#2fd8ff" stopOpacity="0" />
                      </radialGradient>
                    </defs>
                    <ellipse cx="130" cy="150" rx="18" ry="6" fill="url(#hudFloorGrad)" />
                    <ellipse cx="130" cy="150" rx="105" ry="20" fill="none" stroke="#2fd8ff" opacity=".18" strokeWidth="1" />
                    <ellipse cx="130" cy="150" rx="80" ry="15" fill="none" stroke="#2fd8ff" opacity=".28" strokeWidth="1" />
                    <ellipse cx="130" cy="150" rx="55" ry="10" fill="none" stroke="#2fd8ff" opacity=".35" strokeWidth="1" />
                    <ellipse cx="130" cy="150" rx="28" ry="5.5" fill="none" stroke="#a9ecff" opacity=".55" strokeWidth="1.2" />
                    <rect className="hud-bar" x="96" y="112" width="4" height="30" fill="#2fd8ff" opacity=".7" style={{ animationDelay: '.2s' }} />
                    <rect className="hud-bar" x="106" y="100" width="4" height="42" fill="#a9ecff" opacity=".8" style={{ animationDelay: '.9s' }} />
                    <rect className="hud-bar" x="150" y="106" width="4" height="36" fill="#2fd8ff" opacity=".75" style={{ animationDelay: '1.6s' }} />
                    <rect className="hud-bar" x="160" y="118" width="4" height="24" fill="#a9ecff" opacity=".65" style={{ animationDelay: '.5s' }} />
                    <line x1="130" y1="150" x2="130" y2="4" stroke="url(#hudBeamGrad)" strokeWidth="3" className="hud-beam" />
                    <line x1="130" y1="150" x2="130" y2="10" stroke="#a9ecff" strokeWidth="1" opacity=".5" />
                    <circle cx="130" cy="150" r="4" fill="#a9ecff" />
                    <circle className="hud-particle" cx="112" cy="128" r="1.8" fill="#a9ecff" style={{ animationDelay: '.3s' }} />
                    <circle className="hud-particle" cx="150" cy="132" r="1.8" fill="#a9ecff" style={{ animationDelay: '1.6s' }} />
                    <circle className="hud-particle" cx="128" cy="118" r="1.8" fill="#a9ecff" style={{ animationDelay: '2.8s' }} />
                  </svg>
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                  {activeUploads.map(job => {
                    const isPreparingOrRunning = job.status === 'preparing' || job.status === 'running'
                    const phaseInfo = isPreparingOrRunning ? currentPhaseInfo(job) : null
                    const phaseLabelText = phaseInfo?.label ?? (isPreparingOrRunning ? phaseLabel(job.progress_phase) : null)
                    // Total time since the job started (not just this sub-phase) — the
                    // number that actually answers "how long has this been going".
                    const totalElapsedText = isPreparingOrRunning ? progressCounter(job) : null
                    return (
                    <div key={job.id} style={{ display: 'flex', alignItems: 'center', gap: 10, borderBottom: '1px solid var(--border)', paddingBottom: 12 }}>
                      <div className="poster-thumb" style={{ width: 28, height: 42, borderRadius: 4, overflow: 'hidden', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                        {job.poster_url ? (
                          <img
                            src={posterUrl(job.poster_url, 'w154')}
                            alt=""
                            loading="lazy"
                            style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                            onError={e => { (e.currentTarget as HTMLImageElement).style.display = 'none' }}
                          />
                        ) : (
                          <span style={{ fontSize: 14, opacity: 0.35 }}>
                            {job.media_type === 'series' || job.media_type === 'episode' ? '📺' : '🎬'}
                          </span>
                        )}
                      </div>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 8 }}>
                          <HoverTitle
                            className="hover-link"
                            style={{ fontSize: 13, fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', minWidth: 0 }}
                            onClick={() => goToUpload(job.id!)}
                            tip="Ver progreso / detalle"
                          >
                            {job.title ?? `Job #${job.id}`}
                          </HoverTitle>
                          {totalElapsedText && (
                            <span style={{ fontSize: 11, color: 'var(--text-muted)', flexShrink: 0 }}>{totalElapsedText}</span>
                          )}
                        </div>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 3, marginTop: 4 }}>
                          <div style={{ display: 'flex', gap: 8, alignItems: 'center', minWidth: 0 }}>
                            {job.status === 'queued' ? (
                              <span className="badge status-queued">En cola</span>
                            ) : isPreparingOrRunning ? (
                              <span className={`${STATUS_CLASS[job.status] || 'badge req-unknown'} badge-blink`}>{statusLabel(job.status)}</span>
                            ) : (
                              <span className={STATUS_CLASS[job.status] || 'badge req-unknown'}>{statusLabel(job.status)}</span>
                            )}
                            {job.status === 'queued' && queuedSecondsLeft(job) != null && (
                              <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>{queuedSecondsLeft(job)}s</span>
                            )}
                            {isPreparingOrRunning && (
                              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 11, color: 'var(--text-muted)', minWidth: 0, overflow: 'hidden' }}>
                                <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{phaseLabelText}</span>
                                {phaseInfo?.counterText && <span style={{ flexShrink: 0 }}>{phaseInfo.counterText}</span>}
                                <span className="spinner" style={{ width: 10, height: 10, borderWidth: 2, flexShrink: 0 }} />
                              </span>
                            )}
                          </div>
                        </div>
                      </div>
                    </div>
                    )
                  })}
                </div>
              )}
            </div>
          </div>

          {/* Estado de conexiones — misma altura que "Últimas tareas ejecutadas" */}
          <div className="upload-panel" style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}>
            <div className="section-header">
              <div className="section-title">Conexiones</div>
            </div>
            <div style={{ padding: '10px 16px', display: 'flex', flexDirection: 'column', gap: 10, overflowY: 'auto', flex: 1 }}>
              {(() => {
                const rows: React.ReactNode[] = []
                const qbitUrl = connSettings?.qbit_url
                  ? `${connSettings.qbit_url}${connSettings.qbit_port ? `:${connSettings.qbit_port}` : ''}`
                  : null
                // Radarr/Sonarr instances (each configured one, with its icon).
                for (const inst of connInstances) {
                  rows.push(
                    <ConnRow key={`inst-${inst.id}`} icon={<ServiceIcon type={inst.type === 'sonarr' ? 'sonarr' : 'radarr'} size={16} />}
                      label={inst.name} href={inst.url} />
                  )
                }
                if (connSettings?.emu_api_key_configured)
                  rows.push(<ConnRow key="emu" icon={<ServiceIcon type="emu" size={16} />} label="API eMuwarez" href="https://emuwarez.com" />)
                if (connSettings?.tmdb_api_key_configured)
                  rows.push(<ConnRow key="tmdb" icon={<ServiceIcon type="tmdb" size={16} />} label="API TMDb" href="https://www.themoviedb.org" />)
                if (connSettings?.qbit_configured)
                  rows.push(<ConnRow key="qbit" icon={<ServiceIcon type="qbittorrent" size={16} />} label="qBittorrent" href={qbitUrl} />)
                // Image hosts: imgbox is always the default fallback, plus enabled ones.
                const imgIds = Array.from(new Set(['imgbox', ...(connSettings?.image_hosts_enabled ?? [])]))
                for (const id of imgIds) {
                  const meta = connSettings?.image_hosts_available?.find(h => h.id === id)
                  rows.push(<ConnRow key={`img-${id}`} icon={<Favicon domain={domainOf(meta?.url)} src={meta?.favicon} size={16} background="#fff" fallback={<ServiceIcon type="imghost" size={16} />} />}
                    label={meta?.label ?? id} href={meta?.url} />)
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
