import { useState, useEffect, useMemo } from 'react'
import { getUploads, getUploadJobLogs, getUploadJobArtifacts, startUploadJob, retryUploadJob, cancelUploadJob } from '../api/uploads'
import type { UploadJob, UploadJobLog, UploadArtifact } from '../types/api'
import { EmptyState } from '../components/EmptyState'
import { LoadingState } from '../components/LoadingState'
import { ErrorState } from '../components/ErrorState'
import { formatDate } from '../utils/format'

const CONFIRMATION_TOKEN = 'INICIAR_UPLOADRR'

const STATUS_CLASS: Record<string, string> = {
  ready: 'badge req-compatible',
  preflight: 'badge req-partial',
  blocked: 'badge req-not-compatible',
  draft: 'badge req-unknown',
  queued: 'badge req-partial',
  running: 'badge req-filled',
  completed: 'badge req-compatible',
  failed: 'badge req-not-compatible',
  cancelled: 'badge req-unknown',
}

const STATUS_LABEL: Record<string, string> = {
  ready: 'Listo',
  preflight: 'Verificación',
  config_staging: 'Preparando',
  blocked: 'Bloqueado',
  draft: 'Borrador',
  queued: 'En cola',
  running: 'Subiendo',
  completed: 'Completado',
  failed: 'Fallido',
  cancelled: 'Cancelado',
}

function statusLabel(status: string): string {
  return STATUS_LABEL[status] || (status ? status.charAt(0).toUpperCase() + status.slice(1) : '–')
}

// Human labels for the computed progress_phase (uploadrr works in phases, not %).
const PHASE_LABEL: Record<string, string> = {
  preflight: 'Verificando (preflight)',
  queued: 'En cola',
  config_staging: 'Preparando configuración',
  running: 'Subiendo a eMuwarez',
  finalizing: 'Finalizando',
  succeeded: 'Completado',
  failed: 'Fallido',
  timeout: 'Tiempo agotado',
  cancelled: 'Cancelado',
}

function phaseLabel(phase?: string | null): string {
  if (!phase) return '–'
  return PHASE_LABEL[phase] || phase
}

function formatElapsed(job: UploadJob): string {
  if (job.duration_seconds != null) return `${job.duration_seconds}s`
  if (job.status === 'running' && job.started_at) {
    const secs = Math.max(0, Math.round((Date.now() - new Date(job.started_at).getTime()) / 1000))
    return `${secs}s`
  }
  return '–'
}

// Only real upload states — a job now only exists once the user uploads, so
// the preparatory "ready"/"blocked" states no longer appear here.
const STATUS_OPTIONS = ['', 'running', 'completed', 'failed', 'cancelled', 'queued']
// Preparatory states never represent a real upload — hide any stale leftovers.
const HIDDEN_STATES = new Set(['draft', 'preflight', 'blocked', 'ready', 'config_staging'])

function LogsPanel({ jobId, onClose, autoRefresh }: { jobId: number; onClose: () => void; autoRefresh?: boolean }) {
  const [logs, setLogs] = useState<UploadJobLog[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)

  const load = async () => {
    setLoading(true)
    try {
      const r = await getUploadJobLogs(jobId, 500, 0)
      setLogs(r.logs)
      setTotal(r.total)
    } catch { /* ignore */ } finally { setLoading(false) }
  }

  useEffect(() => { load() }, [jobId])

  useEffect(() => {
    if (!autoRefresh) return
    const timer = setInterval(load, 2500)
    return () => clearInterval(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId, autoRefresh])

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()} style={{ maxWidth: 780 }}>
        <div className="modal-header">
          <h2 className="modal-title">Logs / Job {jobId}</h2>
          <button className="btn-icon" onClick={onClose}>✕</button>
        </div>
        <div className="modal-body" style={{ maxHeight: 500, overflowY: 'auto' }}>
          {loading ? <p>Cargando logs…</p> : logs.length === 0 ? (
            <p className="text-muted">No hay logs para este job.</p>
          ) : (
            <pre style={{ fontSize: '0.78rem', lineHeight: 1.5, whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>
              {logs.map(log => {
                const ts = log.created_at.slice(0, 19).replace('T', ' ')
                const stream = log.stream || 'system'
                return `[${ts}] [${stream}/${log.level}] ${log.message}\n`
              })}
            </pre>
          )}
        </div>
        <div className="detail-panel__actions" style={{ padding: '10px 16px' }}>
          <button className="btn btn-secondary btn-sm" onClick={load} disabled={loading}>Actualizar</button>
          <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginLeft: 12 }}>{total} entradas</span>
          <button className="btn btn-secondary" onClick={onClose} style={{ marginLeft: 'auto' }}>Cerrar</button>
        </div>
      </div>
    </div>
  )
}

// Live progress card for a job: current phase, elapsed time, result, and a
// live tail of what uploadrr is doing (auto-refreshed while running).
function JobProgressPanel({ job, onClose, onStart, onRetry, onCancel, onArtifacts }: {
  job: UploadJob
  onClose: () => void
  onStart: (job: UploadJob) => void
  onRetry: (job: UploadJob) => void
  onCancel: (jobId: number) => void
  onArtifacts: (jobId: number) => void
}) {
  const jobId = job.id!
  const isRunning = job.status === 'running'
  const [logs, setLogs] = useState<UploadJobLog[]>([])
  const [loadingLogs, setLoadingLogs] = useState(true)

  const loadLogs = async () => {
    try {
      const r = await getUploadJobLogs(jobId, 300, 0)
      const ordered = [...r.logs].sort((a, b) => a.created_at.localeCompare(b.created_at))
      setLogs(ordered)
    } catch { /* ignore */ } finally { setLoadingLogs(false) }
  }
  useEffect(() => { loadLogs(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [jobId])
  useEffect(() => {
    if (!isRunning) return
    const t = setInterval(loadLogs, 2000)
    return () => clearInterval(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId, isRunning])

  const lastLog = logs.length ? logs[logs.length - 1] : null
  const tail = logs.slice(-40)

  const fact = (label: string, value: React.ReactNode) => (
    <div>
      <div style={{ fontSize: 10.5, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>{label}</div>
      <div style={{ fontSize: 13 }}>{value}</div>
    </div>
  )

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()} style={{ maxWidth: 720 }}>
        <div className="modal-header">
          <h2 className="modal-title" style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span className={STATUS_CLASS[job.status] || 'badge req-unknown'}>{statusLabel(job.status)}</span>
            {job.title || `Job ${jobId}`}
            {isRunning && <span style={{ fontSize: 11, color: '#22c55e' }}>● en vivo</span>}
          </h2>
          <button className="btn-icon" onClick={onClose}>✕</button>
        </div>
        <div className="modal-body">
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))', gap: '12px 20px', marginBottom: 16 }}>
            {fact('Fase actual', phaseLabel(job.progress_phase))}
            {fact('Tiempo', formatElapsed(job))}
            {fact('Reintentos', (job.retry_count ?? 0) > 0 ? `x${job.retry_count}` : '–')}
            {fact('Runtime', job.runtime_type || '–')}
            {fact('Exit code', job.exit_code != null ? job.exit_code : '–')}
            {fact('Resultado', job.result_url
              ? <a href={job.result_url} target="_blank" rel="noopener noreferrer" style={{ color: '#4ade80' }}>Ver en eMuwarez ↗</a>
              : job.result_torrent_id ? `ID: ${job.result_torrent_id}` : '–')}
          </div>

          {job.error_message && (
            <div style={{ padding: '8px 12px', background: 'rgba(248,113,113,0.1)', border: '1px solid rgba(248,113,113,0.3)', borderRadius: 6, fontSize: 12.5, color: '#fca5a5', marginBottom: 12 }}>
              {job.error_message}
            </div>
          )}

          <div style={{ fontSize: 10.5, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 6 }}>
            Actividad {isRunning && <span style={{ color: '#22c55e' }}>(en directo)</span>}
          </div>
          {isRunning && lastLog && (
            <div style={{ fontSize: 13, marginBottom: 8, display: 'flex', gap: 8, alignItems: 'baseline' }}>
              <span style={{ color: 'var(--text-muted)' }}>Ahora:</span>
              <span style={{ fontWeight: 500 }}>{lastLog.message}</span>
            </div>
          )}
          <pre style={{ margin: 0, maxHeight: 260, overflowY: 'auto', fontSize: '0.76rem', lineHeight: 1.5, whiteSpace: 'pre-wrap', wordBreak: 'break-all', background: 'rgba(0,0,0,0.2)', padding: 10, borderRadius: 6 }}>
            {loadingLogs ? 'Cargando…' : tail.length === 0 ? 'Sin actividad registrada todavía.' : tail.map(log => {
              const ts = log.created_at.slice(11, 19)
              return `[${ts}] ${log.message}\n`
            })}
          </pre>
        </div>
        <div className="detail-panel__actions" style={{ padding: '10px 16px', gap: 8, display: 'flex', flexWrap: 'wrap' }}>
          {job.status === 'ready' && <button className="btn btn-primary btn-sm" onClick={() => onStart(job)}>Iniciar subida</button>}
          {['failed', 'cancelled'].includes(job.status) && <button className="btn btn-secondary btn-sm" onClick={() => onRetry(job)}>Reintentar</button>}
          {isRunning && <button className="btn btn-secondary btn-sm" style={{ color: '#f87171' }} onClick={() => onCancel(jobId)}>Cancelar</button>}
          <button className="btn btn-secondary btn-sm" onClick={() => onArtifacts(jobId)}>Artefactos</button>
          <button className="btn btn-secondary btn-sm" onClick={onClose} style={{ marginLeft: 'auto' }}>Cerrar</button>
        </div>
      </div>
    </div>
  )
}

function ArtifactsPanel({ jobId, onClose }: { jobId: number; onClose: () => void }) {
  const [artifacts, setArtifacts] = useState<UploadArtifact[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    getUploadJobArtifacts(jobId).then(r => {
      setArtifacts(r.artifacts)
      setLoading(false)
    }).catch(() => setLoading(false))
  }, [jobId])

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()} style={{ maxWidth: 620 }}>
        <div className="modal-header">
          <h2 className="modal-title">Artefactos / Job {jobId}</h2>
          <button className="btn-icon" onClick={onClose}>✕</button>
        </div>
        <div className="modal-body">
          {loading ? <p>Cargando…</p> : artifacts.length === 0 ? (
            <p className="text-muted">No hay artefactos para este job.</p>
          ) : (
            <table className="data-table">
              <thead>
                <tr><th>Tipo</th><th>Nombre</th><th>Valor / URL / Path</th><th>Fecha</th></tr>
              </thead>
              <tbody>
                {artifacts.map(a => (
                  <tr key={a.id}>
                    <td><span className="badge req-partial" style={{ fontSize: '0.72rem' }}>{a.artifact_type}</span></td>
                    <td style={{ fontSize: 12 }}>{a.name || '–'}</td>
                    <td style={{ fontSize: 11, maxWidth: 260, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {a.url || a.path || a.value || '–'}
                    </td>
                    <td style={{ fontSize: 11, color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>{formatDate(a.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
        <div className="detail-panel__actions" style={{ padding: '10px 16px' }}>
          <button className="btn btn-secondary" onClick={onClose} style={{ marginLeft: 'auto' }}>Cerrar</button>
        </div>
      </div>
    </div>
  )
}

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

function RetryModal({ job, onClose, onDone }: { job: UploadJob; onClose: () => void; onDone: () => void }) {
  const [confirm, setConfirm] = useState('')
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const jobId = job.id!

  const handleDryRun = async () => {
    setLoading(true); setError(null); setMessage(null)
    try {
      const r = await retryUploadJob(jobId, { dry_run: true, start: false, confirmation: null })
      setMessage(r.command_preview ? `Comando previsto:\n${r.command_preview}` : r.message || 'Dry-run: no se creará job nuevo.')
    } catch (e: unknown) { setError(e instanceof Error ? e.message : 'Error.') }
    finally { setLoading(false) }
  }

  const handleRetry = async () => {
    if (confirm !== CONFIRMATION_TOKEN) return
    setLoading(true); setError(null); setMessage(null)
    try {
      const r = await retryUploadJob(jobId, { dry_run: false, start: true, confirmation: CONFIRMATION_TOKEN })
      setMessage(r.message || 'Reintento iniciado.')
      onDone()
    } catch (e: unknown) { setError(e instanceof Error ? e.message : 'Error al reintentar.') }
    finally { setLoading(false) }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()} style={{ maxWidth: 520 }}>
        <div className="modal-header">
          <h2 className="modal-title">Reintentar job {jobId}</h2>
          <button className="btn-icon" onClick={onClose}>✕</button>
        </div>
        <div className="modal-body">
          <p style={{ marginBottom: 8 }}><strong>{job.title || '–'}</strong> — {statusLabel(job.status)}</p>
          <p style={{ fontSize: '0.83rem', color: 'var(--text-muted)', marginBottom: 12 }}>Se creará un nuevo job. El job original no se modifica.</p>
          <label style={{ display: 'block', marginBottom: 6, fontSize: '0.83rem' }}>Escribe <strong>{CONFIRMATION_TOKEN}</strong> para confirmar:</label>
          <input type="text" value={confirm} onChange={e => setConfirm(e.target.value)} placeholder={CONFIRMATION_TOKEN}
            style={{ width: '100%', padding: '6px 10px', background: 'rgba(255,255,255,0.08)', border: `1px solid ${confirm === CONFIRMATION_TOKEN ? 'var(--color-success, #4ade80)' : 'rgba(255,255,255,0.15)'}`, borderRadius: 4, color: 'inherit', fontFamily: 'monospace', fontSize: '0.9rem', boxSizing: 'border-box' }} />
          {message && <pre style={{ marginTop: 12, fontSize: '0.78rem', whiteSpace: 'pre-wrap', background: 'rgba(0,0,0,0.2)', padding: 8, borderRadius: 4 }}>{message}</pre>}
          {error && <p className="error-text" style={{ marginTop: 8 }}>{error}</p>}
        </div>
        <div className="detail-panel__actions" style={{ padding: '10px 16px', gap: 8, display: 'flex' }}>
          <button className="btn btn-secondary" onClick={handleDryRun} disabled={loading}>Dry-run</button>
          <button className="btn btn-primary" onClick={handleRetry} disabled={confirm !== CONFIRMATION_TOKEN || loading}>{loading ? 'Reintentando…' : 'Reintentar'}</button>
          <button className="btn btn-secondary" onClick={onClose}>Cerrar</button>
        </div>
      </div>
    </div>
  )
}

export function UploadsPage() {
  const [jobs, setJobs] = useState<UploadJob[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [statusFilter, setStatusFilter] = useState('')
  const [search, setSearch] = useState('')
  const [sortBy, setSortBy] = useState('created_desc')
  const [resultFilter, setResultFilter] = useState('')
  const [typeFilter, setTypeFilter] = useState('')
  const [detailJob, setDetailJob] = useState<number | null>(null)
  const [logsJob, setLogsJob] = useState<number | null>(null)
  const [artifactsJob, setArtifactsJob] = useState<number | null>(null)
  const [startJob, setStartJob] = useState<UploadJob | null>(null)
  const [retryJob, setRetryJob] = useState<UploadJob | null>(null)

  const load = async (opts?: { silent?: boolean }) => {
    if (!opts?.silent) { setLoading(true); setError(null) }
    try {
      const data = await getUploads(statusFilter ? { status: statusFilter } : undefined)
      setJobs(data)
    } catch { if (!opts?.silent) setError('Error al cargar los trabajos de subida.') }
    finally { if (!opts?.silent) setLoading(false) }
  }

  useEffect(() => { load() }, [statusFilter])

  // Poll every 2.5s while at least one job is running, so status/progress/logs update live.
  const hasRunningJob = jobs.some(j => j.status === 'running')
  useEffect(() => {
    if (!hasRunningJob) return
    const timer = setInterval(() => load({ silent: true }), 2500)
    return () => clearInterval(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasRunningJob, statusFilter])

  const handleCancel = async (jobId: number) => {
    try { await cancelUploadJob(jobId); await load() } catch { /* ignore */ }
  }

  // Client-side filter + sort over the loaded jobs (status stays server-side).
  const visibleJobs = useMemo(() => {
    const q = search.trim().toLowerCase()
    const out = jobs.filter(j => {
      if (HIDDEN_STATES.has(j.status)) return false
      const titleOk = !q || (j.title || '').toLowerCase().includes(q)
      const hasResult = !!(j.result_url || j.result_torrent_id)
      const resultOk = !resultFilter || (resultFilter === 'success' ? hasResult : !hasResult)
      const typeOk = !typeFilter || j.media_type === typeFilter
      return titleOk && resultOk && typeOk
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
  }, [jobs, search, sortBy, resultFilter, typeFilter])

  const detailJobData = detailJob != null ? jobs.find(j => j.id === detailJob) : undefined

  return (
    <div>
      {logsJob !== null && (
        <LogsPanel
          jobId={logsJob}
          onClose={() => setLogsJob(null)}
          autoRefresh={jobs.find(j => j.id === logsJob)?.status === 'running'}
        />
      )}
      {detailJobData && (
        <JobProgressPanel
          job={detailJobData}
          onClose={() => setDetailJob(null)}
          onStart={j => setStartJob(j)}
          onRetry={j => setRetryJob(j)}
          onCancel={id => handleCancel(id)}
          onArtifacts={id => setArtifactsJob(id)}
        />
      )}
      {artifactsJob !== null && <ArtifactsPanel jobId={artifactsJob} onClose={() => setArtifactsJob(null)} />}
      {startJob && <StartModal job={startJob} onClose={() => setStartJob(null)} onDone={() => { setStartJob(null); load() }} />}
      {retryJob && <RetryModal job={retryJob} onClose={() => setRetryJob(null)} onDone={() => { setRetryJob(null); load() }} />}

      <div className="page-header">
        <div>
          <div className="page-title">Subidas</div>
          <div className="page-subtitle">Trabajos de subida con Uploadrr</div>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          {hasRunningJob && <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>● actualizando en vivo</span>}
        </div>
      </div>

      <div className="filters-bar">
        <input
          className="form-input"
          placeholder="Buscar título…"
          value={search}
          onChange={e => setSearch(e.target.value)}
          style={{ width: 160 }}
        />
        <select className="form-input form-select" value={statusFilter} onChange={e => setStatusFilter(e.target.value)}>
          {STATUS_OPTIONS.map(s => <option key={s} value={s}>{s ? statusLabel(s) : 'Estado: Todos'}</option>)}
        </select>
        <select className="form-input form-select" value={typeFilter} onChange={e => setTypeFilter(e.target.value)}>
          <option value="">Tipo: Todos</option>
          <option value="movie">Película</option>
          <option value="series">Serie</option>
          <option value="season">Temporada</option>
          <option value="episode">Episodio</option>
        </select>
        <select className="form-input form-select" value={resultFilter} onChange={e => setResultFilter(e.target.value)}>
          <option value="">Resultado: Todos</option>
          <option value="success">Subido (con resultado)</option>
          <option value="none">Sin resultado</option>
        </select>
        <select className="form-input form-select" value={sortBy} onChange={e => setSortBy(e.target.value)}>
          <option value="created_desc">Orden: Reciente primero</option>
          <option value="created_asc">Orden: Antiguo primero</option>
          <option value="title">Orden: Título (A-Z)</option>
          <option value="status">Orden: Estado</option>
          <option value="duration_desc">Orden: Duración</option>
        </select>
      </div>

      {loading ? <LoadingState label="Cargando trabajos…" /> : error ? <ErrorState message={error} onRetry={load} /> : jobs.length === 0 ? (
        <EmptyState icon="📤" title="No hay trabajos de subida." body="Usa el botón 'Subir' desde Biblioteca para generar un preflight." />
      ) : (
        <div className="activity-section">
          <div className="section-header">
            <div className="section-title">Trabajos de subida</div>
            <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>{visibleJobs.length} registro{visibleJobs.length !== 1 ? 's' : ''}</span>
          </div>
          <div style={{ overflowX: 'auto' }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Título</th>
                  <th>Estado</th>
                  <th>Progreso</th>
                  <th>Duración</th>
                  <th>Exit</th>
                  <th>Resultado</th>
                  <th>Preparado</th>
                  <th>Reintentos</th>
                  <th>Creado</th>
                  <th>Finalizado</th>
                  <th>Acciones</th>
                </tr>
              </thead>
              <tbody>
                {visibleJobs.map(job => (
                  <tr key={job.id}>
                    <td style={{ color: 'var(--text-muted)', fontSize: 12 }}>{job.id}</td>
                    <td style={{ maxWidth: 160, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      <span
                        className="lib-title-link"
                        onClick={() => setDetailJob(job.id!)}
                        title="Ver progreso / detalle"
                      >
                        {job.title || '–'}
                      </span>
                    </td>
                    <td>
                      <span className={STATUS_CLASS[job.status] || 'badge req-unknown'}>
                        {statusLabel(job.status)}
                      </span>
                    </td>
                    <td style={{ fontSize: 11, color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>
                      {job.status === 'running' && <span style={{ marginRight: 4 }}>⏳</span>}
                      {job.progress_phase || '–'}
                    </td>
                    <td style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                      {job.duration_seconds != null ? `${job.duration_seconds}s` : '–'}
                    </td>
                    <td style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                      {job.exit_code != null ? job.exit_code : '–'}
                    </td>
                    <td style={{ fontSize: 11, maxWidth: 120, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {job.result_url ? (
                        <a href={job.result_url} target="_blank" rel="noopener noreferrer" style={{ color: 'var(--color-success, #4ade80)' }}>URL</a>
                      ) : job.result_torrent_id ? (
                        <span style={{ color: 'var(--text-secondary)' }}>ID:{job.result_torrent_id}</span>
                      ) : '–'}
                    </td>
                    <td style={{ fontSize: 12 }}>
                      {job.using_prepared_path === true && <span className="badge req-filled" style={{ fontSize: '0.7rem' }}>sí</span>}
                      {job.using_prepared_path === false && <span className="badge req-partial" style={{ fontSize: '0.7rem' }}>no</span>}
                      {job.using_prepared_path == null && '–'}
                    </td>
                    <td style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                      {(job.retry_count ?? 0) > 0 ? `x${job.retry_count}` : '–'}
                    </td>
                    <td style={{ fontSize: 11, color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>{formatDate(job.created_at ?? null)}</td>
                    <td style={{ fontSize: 11, color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>{formatDate(job.finished_at ?? null)}</td>
                    <td>
                      <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                        <button className="btn btn-secondary btn-sm" style={{ fontSize: '0.72rem', padding: '2px 7px' }} onClick={() => setLogsJob(job.id!)} title="Ver logs">Logs</button>
                        <button className="btn btn-secondary btn-sm" style={{ fontSize: '0.72rem', padding: '2px 7px' }} onClick={() => setArtifactsJob(job.id!)} title="Ver artefactos">Artefactos</button>
                        {job.status === 'ready' && (
                          <button className="btn btn-primary btn-sm" style={{ fontSize: '0.72rem', padding: '2px 7px' }} onClick={() => setStartJob(job)} title="Iniciar">Iniciar</button>
                        )}
                        {['failed', 'cancelled'].includes(job.status) && (
                          <button className="btn btn-secondary btn-sm" style={{ fontSize: '0.72rem', padding: '2px 7px', color: 'var(--color-warning, #fbbf24)' }} onClick={() => setRetryJob(job)} title="Reintentar">Retry</button>
                        )}
                        {job.status === 'running' && (
                          <button className="btn btn-secondary btn-sm" style={{ fontSize: '0.72rem', padding: '2px 7px', color: 'var(--color-error, #f87171)' }} onClick={() => handleCancel(job.id!)} title="Cancelar">Cancelar</button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
