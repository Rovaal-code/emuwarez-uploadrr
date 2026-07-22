import { useState, useEffect, useMemo, Fragment } from 'react'
import { getUploads, startUploadJob, retryUploadJobQueued, cancelUploadJob } from '../api/uploads'
import type { UploadJob } from '../types/api'
import { EmptyState } from '../components/EmptyState'
import { LoadingState } from '../components/LoadingState'
import { ErrorState } from '../components/ErrorState'
import { HeaderFilter } from '../components/HeaderFilter'
import { UploadJobDetailPage } from '../components/UploadJobDetailPage'
import { DeleteUploadModal } from '../components/DeleteUploadModal'
import { StatusBadge } from '../components/StatusBadge'
import { ServiceLabel } from '../components/ServiceIcon'
import { CancelButtonIcon, RetryButtonIcon } from '../components/DetailCard'
import { useTooltip } from '../components/Tooltip'
import { formatDateTimeSeconds } from '../utils/format'
import { posterUrl } from '../utils/libraryItem'
import { getDetailIdFromPath, pushDetailPath, closeDetailPath } from '../utils/detailUrl'
import {
  UPLOAD_TYPE_LABEL, STATUS_CLASS, statusLabel, phaseLabel, currentPhaseInfo,
  progressCounter, queuedSecondsLeft, useTicker,
} from '../utils/uploadStatus'

// Backend-real gates — mirror cancel_upload_job()/queue_retry_for_job() in
// services/upload_execution.py / upload_queue.py exactly, so the button is
// only enabled when the action would actually succeed. Cancelar excludes
// raw 'preparing' on purpose: it displays as "Subiendo" same as 'running',
// but the server is mid rename/remux at that point and can't safely abort.
// Reintentar excludes 'completed' on purpose: retrying an already-successful
// upload isn't supported server-side.
const CANCELLABLE_STATUSES = new Set(['staging', 'queued', 'running'])
const RETRYABLE_STATUSES = new Set(['failed', 'cancelled'])

const CONFIRMATION_TOKEN = 'INICIAR_UPLOADRR'

// Only real upload states — a job now only exists once the user uploads, so
// the preparatory "ready"/"blocked" states no longer appear here. 'preparing'
// isn't offered as its own filter option — it displays as "Subiendo" same as
// 'running' (see STATUS_LABEL), and the "Subiendo" filter option matches both.
const STATUS_OPTIONS = ['', 'staging', 'queued', 'running', 'completed', 'failed', 'cancelled']
// Preparatory states never represent a real upload — hide any stale leftovers.
const HIDDEN_STATES = new Set(['draft', 'preflight', 'blocked', 'ready', 'config_staging'])

function StartModal({ job, onClose, onDone }: { job: UploadJob; onClose: () => void; onDone: () => void }) {
  const [confirm, setConfirm] = useState('')
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const jobId = job.id!

  const handleDryRun = async () => {
    setLoading(true); setError(null); setMessage(null)
    try {
      const r = await startUploadJob(jobId, { dry_run: true, start: false, confirmation: null })
      setMessage(r.command_preview ? `Comando previsto:\n${r.command_preview}` : r.message || 'Dry-run completado.')
    } catch (e: unknown) { setError(e instanceof Error ? e.message : 'Error.') }
    finally { setLoading(false) }
  }

  const handleStart = async () => {
    if (confirm !== CONFIRMATION_TOKEN) return
    setLoading(true); setError(null); setMessage(null)
    try {
      const r = await startUploadJob(jobId, { dry_run: false, start: true, confirmation: CONFIRMATION_TOKEN })
      setMessage(r.message || 'Uploadrr iniciado.')
      onDone()
    } catch (e: unknown) { setError(e instanceof Error ? e.message : 'Error al iniciar.') }
    finally { setLoading(false) }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()} style={{ maxWidth: 560 }}>
        <div className="modal-header">
          <h2 className="modal-title">Iniciar Uploadrr — Job {jobId}</h2>
          <button className="btn-icon" onClick={onClose}>✕</button>
        </div>
        <div className="modal-body">
          <p style={{ marginBottom: 8 }}><strong>{job.title || '–'}</strong></p>
          <div style={{ padding: '10px 14px', background: 'rgba(255,80,80,0.08)', borderRadius: 6, border: '1px solid rgba(255,80,80,0.2)', marginBottom: 12 }}>
            <ul style={{ margin: 0, paddingLeft: 18, fontSize: '0.83rem', lineHeight: 1.6 }}>
              <li>Esta acción puede publicar/subir contenido a eMuwarez.</li>
              <li>No se crearán peticiones automáticamente.</li>
              <li>No se modificará el archivo original ni el título MKV.</li>
            </ul>
          </div>
          <label style={{ display: 'block', marginBottom: 6, fontSize: '0.83rem' }}>
            Escribe <strong>{CONFIRMATION_TOKEN}</strong> para confirmar:
          </label>
          <input type="text" value={confirm} onChange={e => setConfirm(e.target.value)} placeholder={CONFIRMATION_TOKEN}
            style={{ width: '100%', padding: '6px 10px', background: 'rgba(255,255,255,0.08)', border: `1px solid ${confirm === CONFIRMATION_TOKEN ? 'var(--color-success, #4ade80)' : 'rgba(255,255,255,0.15)'}`, borderRadius: 4, color: 'inherit', fontFamily: 'monospace', fontSize: '0.9rem', boxSizing: 'border-box' }} />
          {message && <pre style={{ marginTop: 12, fontSize: '0.78rem', whiteSpace: 'pre-wrap', background: 'rgba(0,0,0,0.2)', padding: 8, borderRadius: 4 }}>{message}</pre>}
          {error && <p className="error-text" style={{ marginTop: 8 }}>{error}</p>}
        </div>
        <div className="detail-panel__actions" style={{ padding: '10px 16px', gap: 8, display: 'flex' }}>
          <button className="btn btn-secondary" onClick={handleDryRun} disabled={loading}>Dry-run</button>
          <button className="btn btn-primary" onClick={handleStart} disabled={confirm !== CONFIRMATION_TOKEN || loading}>{loading ? 'Iniciando…' : 'Iniciar subida'}</button>
          <button className="btn btn-secondary" onClick={onClose}>Cerrar</button>
        </div>
      </div>
    </div>
  )
}

// One table row — used both for the latest attempt in a retry chain (normal
// row) and for its older attempts (indented/muted, revealed by expanding the
// Reintentos toggle). `retryToggle` is only passed on the latest-attempt row.
function JobRow({ job, onOpen, indent, retryToggle, onCancel, onRetry }: {
  job: UploadJob
  onOpen: () => void
  indent?: boolean
  retryToggle?: { count: number; expanded: boolean; onClick: () => void }
  onCancel: (jobId: number) => void
  onRetry: (job: UploadJob) => void
}) {
  const canCancel = CANCELLABLE_STATUSES.has(job.status)
  const canRetry = RETRYABLE_STATUSES.has(job.status)
  const isPreparingOrRunning = job.status === 'preparing' || job.status === 'running'
  const phaseInfo = isPreparingOrRunning ? currentPhaseInfo(job) : null
  const phaseLabelText = phaseInfo?.label ?? (isPreparingOrRunning ? phaseLabel(job.progress_phase) : null)
  const phaseElapsedText = isPreparingOrRunning ? progressCounter(job) : null
  const { triggerProps: titleTip, tooltipNode: titleTooltip } = useTooltip('Ver progreso / detalle')
  return (
    <tr style={indent ? { opacity: 0.65 } : undefined}>
      <td style={{ width: 36 }}>
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
      </td>
      <td style={{ maxWidth: 220, paddingLeft: indent ? 24 : undefined }}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 4, minWidth: 0 }}>
          {indent && <span style={{ color: 'var(--text-muted)', flexShrink: 0 }}>↳</span>}
          <span
            className="lib-title-link"
            style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', minWidth: 0 }}
            onClick={onOpen}
            {...titleTip}
          >
            {job.title || '–'}
            {titleTooltip}
          </span>
          {job.year ? <span style={{ fontSize: 11, color: 'var(--text-muted)', flexShrink: 0 }}>({job.year})</span> : null}
        </div>
      </td>
      <td style={{ fontSize: 12, color: 'var(--text-secondary)', whiteSpace: 'nowrap' }}>
        {UPLOAD_TYPE_LABEL[job.media_type ?? ''] ?? '–'}
      </td>
      <td style={{ whiteSpace: 'nowrap' }}>
        {job.instance_type ? <ServiceLabel type={job.instance_type} label={job.instance_name ?? job.instance_type} size={14} /> : <span style={{ color: 'var(--text-muted)' }}>–</span>}
      </td>
      <td>
        {job.status === 'queued' ? (
          <span className="badge status-queued">En cola</span>
        ) : (job.status === 'preparing' || job.status === 'running') ? (
          <span className={`${STATUS_CLASS[job.status] || 'badge req-unknown'} badge-blink`}>
            {statusLabel(job.status)}
          </span>
        ) : (
          <span className={STATUS_CLASS[job.status] || 'badge req-unknown'}>
            {statusLabel(job.status)}
          </span>
        )}
      </td>
      <td style={{ whiteSpace: 'nowrap' }}>
        {job.status === 'staging' ? (
          <span className="badge status-queued" style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
            <span className="spinner" style={{ width: 10, height: 10, borderWidth: 2 }} />
            Generando nomenclatura
          </span>
        ) : job.status === 'queued' ? (
          <span className="badge status-queued" style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
            <span className="spinner" style={{ width: 10, height: 10, borderWidth: 2 }} />
            {queuedSecondsLeft(job) ?? '–'}s
          </span>
        ) : (job.status === 'preparing' || job.status === 'running') ? (
          <span className="badge status-queued" style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
            <span className="spinner" style={{ width: 10, height: 10, borderWidth: 2 }} />
            {phaseLabelText}{phaseElapsedText ? ` · ${phaseElapsedText}` : ''}
          </span>
        ) : '–'}
      </td>
      <td style={{ fontSize: 12, color: 'var(--text-muted)' }}>
        {retryToggle ? (
          <span
            className="lib-title-link"
            onClick={retryToggle.onClick}
            title={retryToggle.expanded ? 'Ocultar intentos anteriores' : 'Ver intentos anteriores'}
            style={{ display: 'inline-flex', alignItems: 'center', gap: 3 }}
          >
            x{job.retry_count} <span style={{ fontSize: 10 }}>{retryToggle.expanded ? '▾' : '▸'}</span>
          </span>
        ) : (job.retry_count ?? 0) > 0 ? `x${job.retry_count}` : '–'}
      </td>
      <td style={{ fontSize: 11, color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>{formatDateTimeSeconds(job.created_at ?? null)}</td>
      <td style={{ fontSize: 11, color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>{formatDateTimeSeconds(job.finished_at ?? null)}</td>
      <td style={{ fontSize: 12, color: 'var(--text-muted)' }}>
        {job.duration_seconds != null ? `${job.duration_seconds}s` : '–'}
      </td>
      <td style={{ whiteSpace: 'nowrap' }}>
        <StatusBadge status={job.request_status || 'Sin petición'} type="request" />
      </td>
      <td style={{ whiteSpace: 'nowrap' }}>
        <div style={{ display: 'flex', gap: 6 }}>
          <button
            type="button"
            className="btn btn-primary btn-sm"
            disabled={!canRetry}
            onClick={() => onRetry(job)}
            title={canRetry ? 'Reintentar subida' : 'Solo se puede reintentar una subida cancelada o fallida'}
          >
            <RetryButtonIcon /> Reintentar
          </button>
          <button
            type="button"
            className="btn btn-danger btn-sm"
            disabled={!canCancel}
            onClick={() => onCancel(job.id!)}
            title={canCancel ? 'Cancelar subida' : 'Solo se puede cancelar mientras está preparando, en cola o subiendo'}
          >
            <CancelButtonIcon /> Cancelar
          </button>
        </div>
      </td>
    </tr>
  )
}

export function UploadsPage({ onNavigate }: { onNavigate?: (page: string) => void } = {}) {
  const [jobs, setJobs] = useState<UploadJob[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [statusFilter, setStatusFilter] = useState('')
  const [search, setSearch] = useState('')
  const [sortBy, setSortBy] = useState('created_desc')
  const [typeFilter, setTypeFilter] = useState('')
  const [selectedJobId, setSelectedJobId] = useState<number | null>(null)

  // Keeps /uploads/:id in sync with whichever job's detail page is open.
  function openUpload(id: number) {
    pushDetailPath('uploads', id)
    setSelectedJobId(id)
  }
  function closeUpload() {
    closeDetailPath('uploads')
    setSelectedJobId(null)
  }
  const [startJob, setStartJob] = useState<UploadJob | null>(null)
  const [deleteJob, setDeleteJob] = useState<UploadJob | null>(null)
  // Retry chains: which terminal (latest-attempt) job ids currently have
  // their older attempts expanded below them.
  const [expandedChains, setExpandedChains] = useState<Set<number>>(new Set())

  const load = async (opts?: { silent?: boolean }) => {
    if (!opts?.silent) { setLoading(true); setError(null) }
    try {
      // The "Subiendo" filter option (value 'running') must also catch
      // 'preparing' jobs — they display identically as "Subiendo" now (see
      // STATUS_LABEL) — so it can't be a single exact server-side match;
      // fetch unfiltered and narrow client-side in visibleJobs instead.
      const data = await getUploads(statusFilter && statusFilter !== 'running' ? { status: statusFilter } : undefined)
      setJobs(data)
    } catch { if (!opts?.silent) setError('Error al cargar los trabajos de subida.') }
    finally { if (!opts?.silent) setLoading(false) }
  }

  useEffect(() => { load() }, [statusFilter])

  // Opened from the dashboard "Actividad de subida" (clicking a title): pick
  // up the stashed job id once the list has loaded and show its detail page.
  useEffect(() => {
    if (jobs.length === 0) return
    let pending: string | null = null
    try { pending = sessionStorage.getItem('emuwarez_open_upload') } catch { /* ignore */ }
    if (!pending) return
    if (!jobs.some(j => j.id === Number(pending))) return
    try { sessionStorage.removeItem('emuwarez_open_upload') } catch { /* ignore */ }
    openUpload(Number(pending))
  }, [jobs])

  // Deep link: /uploads/:id — resolve straight from the URL. selectedJob's
  // own `jobs.find(...)` gracefully returns undefined until `jobs` finishes
  // loading, so this doesn't need to wait on it like the sessionStorage
  // hand-off above does. On mount this only OPENS (never force-closes on a
  // bare /uploads) — the sessionStorage/CustomEvent hand-offs above land on a
  // bare /uploads path themselves and may resolve the same tick, so
  // unconditionally clearing here on mount would win the race and wipe out
  // whatever they just opened. Closing on a bare path is left to real
  // back/forward navigation (popstate), which happens well after mount.
  useEffect(() => {
    const id = getDetailIdFromPath('uploads')
    if (id != null) setSelectedJobId(id)

    const onPopState = () => setSelectedJobId(getDetailIdFromPath('uploads'))
    window.addEventListener('popstate', onPopState)
    return () => window.removeEventListener('popstate', onPopState)
  }, [])

  // Same hand-off, but live — the sessionStorage read above only re-checks
  // when `jobs` changes, so clicking a notification while Subidas is
  // ALREADY the open page (no reload, `jobs` unchanged) would otherwise do
  // nothing. NotificationBell dispatches this same-tick, in addition to
  // stashing sessionStorage for the cross-page case.
  useEffect(() => {
    const onOpenUpload = (e: Event) => {
      const id = (e as CustomEvent<number>).detail
      if (id == null) return
      try { sessionStorage.removeItem('emuwarez_open_upload') } catch { /* ignore */ }
      openUpload(id)
    }
    window.addEventListener('emuwarez:open-upload', onOpenUpload)
    return () => window.removeEventListener('emuwarez:open-upload', onOpenUpload)
  }, [])

  // Poll every 2.5s while at least one job is live (staging/queued/preparing/
  // running), so status/progress/logs — and the staging→queued→preparing→
  // running transition — update on their own.
  const hasLiveJob = jobs.some(j => j.status === 'running' || j.status === 'preparing' || j.status === 'queued' || j.status === 'staging')
  useEffect(() => {
    if (!hasLiveJob) return
    const timer = setInterval(() => load({ silent: true }), 2500)
    return () => clearInterval(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasLiveJob, statusFilter])
  useTicker(jobs.some(j => j.status === 'queued'))

  const handleCancel = async (jobId: number) => {
    try { await cancelUploadJob(jobId); await load() } catch { /* ignore */ }
  }

  // No confirmation — retrying only ever creates a brand new 'queued' job
  // row (same 60s grace period as a fresh "Subir a eMuwarez"); the original
  // failed/cancelled job is never touched. Jumps straight to the new job's
  // detail page so its countdown is visible immediately. Errors are surfaced
  // (not swallowed) — a silent failure here looked exactly like the button
  // "doing nothing".
  const [retryError, setRetryError] = useState<string | null>(null)
  const handleRetryQueued = async (job: UploadJob) => {
    setRetryError(null)
    try {
      const r = await retryUploadJobQueued(job.id!)
      await load()
      if (r.job?.id != null) openUpload(r.job.id)
    } catch (e: unknown) {
      setRetryError(e instanceof Error ? e.message : 'No se pudo reintentar la subida.')
    }
  }

  // Same sessionStorage handoff RequestsPage uses to open a specific
  // library item's detail page in Biblioteca.
  const goToLibraryItem = (id: number) => {
    try { sessionStorage.setItem('emuwarez_open_library_item', String(id)) } catch { /* ignore */ }
    onNavigate?.('library')
  }

  // Retry chains: a job created via "Reintentar" points back at the job it
  // retried (retry_of_job_id), and the original is never touched — so a
  // retried item would otherwise show up twice (or more) as unrelated-
  // looking rows. Only the LATEST attempt in each chain (the one nothing
  // else retries) shows as a normal row; its older attempts are reachable
  // by expanding the Reintentos cell instead of cluttering the main list.
  const jobById = useMemo(() => new Map(jobs.map(j => [j.id!, j])), [jobs])
  const hasNewerRetry = useMemo(() => {
    const s = new Set<number>()
    for (const j of jobs) if (j.retry_of_job_id != null) s.add(j.retry_of_job_id)
    return s
  }, [jobs])
  const ancestorsOf = (job: UploadJob): UploadJob[] => {
    const chain: UploadJob[] = []
    let cur = job.retry_of_job_id != null ? jobById.get(job.retry_of_job_id) : undefined
    while (cur) {
      chain.push(cur)
      cur = cur.retry_of_job_id != null ? jobById.get(cur.retry_of_job_id) : undefined
    }
    return chain // most recent ancestor first, original last
  }
  const toggleChain = (jobId: number) => {
    setExpandedChains(prev => {
      const next = new Set(prev)
      if (next.has(jobId)) next.delete(jobId); else next.add(jobId)
      return next
    })
  }

  // Client-side filter + sort over the loaded jobs (status stays server-side,
  // except 'running' — see load() — which also has to catch 'preparing').
  const visibleJobs = useMemo(() => {
    const q = search.trim().toLowerCase()
    const out = jobs.filter(j => {
      if (HIDDEN_STATES.has(j.status)) return false
      if (hasNewerRetry.has(j.id!)) return false // shown nested under its retry instead
      const titleOk = !q || (j.title || '').toLowerCase().includes(q)
      const typeOk = !typeFilter || j.media_type === typeFilter
      const statusOk = statusFilter !== 'running' || j.status === 'running' || j.status === 'preparing'
      return titleOk && typeOk && statusOk
    })
    const dt = (s?: string | null) => (s ? new Date(s).getTime() : 0)
    out.sort((a, b) => {
      switch (sortBy) {
        case 'created_asc': return dt(a.created_at) - dt(b.created_at)
        case 'title': return (a.title || '').localeCompare(b.title || '')
        case 'status': return (a.status || '').localeCompare(b.status || '')
        case 'duration_desc': return (b.duration_seconds ?? -1) - (a.duration_seconds ?? -1)
        default: return dt(b.created_at) - dt(a.created_at) // created_desc
      }
    })
    return out
  }, [jobs, search, sortBy, typeFilter, statusFilter, hasNewerRetry])

  const selectedJob = selectedJobId != null ? jobs.find(j => j.id === selectedJobId) : undefined

  const modals = (
    <>
      {startJob && <StartModal job={startJob} onClose={() => setStartJob(null)} onDone={() => { setStartJob(null); load() }} />}
      {deleteJob && (
        <DeleteUploadModal
          job={deleteJob}
          onClose={() => setDeleteJob(null)}
          onDeleted={() => { setDeleteJob(null); closeUpload(); load() }}
        />
      )}
    </>
  )

  // Dedicated detail page — shown in place of the list when a job is
  // selected, instead of the old JobProgressPanel modal.
  if (selectedJob) {
    return (
      <div>
        <UploadJobDetailPage
          job={selectedJob}
          onBack={closeUpload}
          onStart={j => setStartJob(j)}
          onRetry={j => handleRetryQueued(j)}
          onCancel={id => handleCancel(id)}
          onDelete={j => setDeleteJob(j)}
          onOpenLibraryItem={goToLibraryItem}
          retryError={retryError}
        />
        {modals}
      </div>
    )
  }

  return (
    <div data-tour="uploads-content" style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      {modals}

      <div className="page-header" style={{ flexShrink: 0 }}>
        <div>
          <div className="page-title">Subidas</div>
          <div className="page-subtitle">{visibleJobs.length} subidas</div>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          {hasLiveJob && <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>● actualizando en vivo</span>}
        </div>
      </div>

      <div className="filters-bar" style={{ flexShrink: 0 }}>
        <input
          className="form-input"
          placeholder="Buscar título…"
          value={search}
          onChange={e => setSearch(e.target.value)}
          style={{ width: 160 }}
        />
        <select className="form-input form-select" value={sortBy} onChange={e => setSortBy(e.target.value)}>
          <option value="created_desc">Orden: Reciente primero</option>
          <option value="created_asc">Orden: Antiguo primero</option>
          <option value="title">Orden: Título (A-Z)</option>
          <option value="status">Orden: Estado</option>
          <option value="duration_desc">Orden: Duración</option>
        </select>
      </div>

      {loading ? <LoadingState label="Cargando Subidas…" /> : error ? <ErrorState message={error} onRetry={load} /> : jobs.length === 0 ? (
        <EmptyState icon="📤" title="No hay trabajos de subida." body="Usa el botón 'Subir' desde Biblioteca para generar un preflight." />
      ) : (
        <div className="activity-section" style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', marginBottom: 0 }}>
          <div style={{ overflow: 'auto', flex: 1, minHeight: 0 }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th></th>
                  <th>Título</th>
                  <th><HeaderFilter label="Tipo" value={typeFilter} onChange={setTypeFilter} options={[
                    { value: '', label: 'Todos' }, { value: 'movie', label: 'Película' }, { value: 'series', label: 'Serie' }, { value: 'season', label: 'Temporada' }, { value: 'episode', label: 'Episodio' },
                  ]} /></th>
                  <th>Origen</th>
                  <th><HeaderFilter label="Estado" value={statusFilter} onChange={setStatusFilter} options={[
                    { value: '', label: 'Todos' }, ...STATUS_OPTIONS.filter(Boolean).map(s => ({ value: s, label: statusLabel(s) })),
                  ]} /></th>
                  <th>Progreso</th>
                  <th>Reintentos</th>
                  <th>Creado</th>
                  <th>Finalizado</th>
                  <th>Duración</th>
                  <th>Petición</th>
                  <th>Acciones</th>
                </tr>
              </thead>
              <tbody>
                {visibleJobs.map(job => {
                  const ancestors = ancestorsOf(job)
                  const expanded = expandedChains.has(job.id!)
                  return (
                    <Fragment key={job.id}>
                      <JobRow
                        job={job}
                        onOpen={() => openUpload(job.id!)}
                        retryToggle={ancestors.length > 0 ? { count: ancestors.length, expanded, onClick: () => toggleChain(job.id!) } : undefined}
                        onCancel={handleCancel}
                        onRetry={handleRetryQueued}
                      />
                      {expanded && ancestors.map(a => (
                        <JobRow key={a.id} job={a} indent onOpen={() => openUpload(a.id!)} onCancel={handleCancel} onRetry={handleRetryQueued} />
                      ))}
                    </Fragment>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
