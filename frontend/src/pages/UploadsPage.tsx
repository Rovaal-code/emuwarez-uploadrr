import { useState, useEffect } from 'react'
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

const STATUS_OPTIONS = ['', 'ready', 'running', 'completed', 'failed', 'cancelled', 'queued', 'blocked']

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
          <p style={{ marginBottom: 8 }}><strong>{job.title || '–'}</strong> — {job.status}</p>
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

  return (
    <div>
      {logsJob !== null && (
        <LogsPanel
          jobId={logsJob}
          onClose={() => setLogsJob(null)}
          autoRefresh={jobs.find(j => j.id === logsJob)?.status === 'running'}
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
          <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)}
            style={{ background: 'rgba(255,255,255,0.08)', border: '1px solid rgba(255,255,255,0.15)', borderRadius: 4, color: 'inherit', padding: '4px 8px', fontSize: '0.85rem' }}>
            {STATUS_OPTIONS.map(s => <option key={s} value={s}>{s || 'Todos los estados'}</option>)}
          </select>
          <button className="btn btn-secondary btn-sm" onClick={() => load()} disabled={loading}>Actualizar</button>
          {hasRunningJob && <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>● actualizando en vivo</span>}
        </div>
      </div>

      {loading ? <LoadingState label="Cargando trabajos…" /> : error ? <ErrorState message={error} onRetry={load} /> : jobs.length === 0 ? (
        <EmptyState icon="📤" title="No hay trabajos de subida." body="Usa el botón 'Subir' desde Biblioteca para generar un preflight." />
      ) : (
        <div className="activity-section">
          <div className="section-header">
            <div className="section-title">Trabajos de subida</div>
            <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>{jobs.length} registro{jobs.length !== 1 ? 's' : ''}</span>
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
                {jobs.map(job => (
                  <tr key={job.id}>
                    <td style={{ color: 'var(--text-muted)', fontSize: 12 }}>{job.id}</td>
                    <td style={{ fontWeight: 500, maxWidth: 160, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{job.title || '–'}</td>
                    <td>
                      <span className={STATUS_CLASS[job.status] || 'badge req-unknown'} title={job.command_preview || undefined}>
                        {job.status}
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

      <div style={{ marginTop: 16, padding: '10px 16px', background: 'rgba(255,200,0,0.06)', borderRadius: 8, fontSize: '0.82rem', color: 'var(--text-muted)' }}>
        La ejecución real de Uploadrr requiere confirmación explícita <strong>INICIAR_UPLOADRR</strong>.
        No se crean peticiones eMuwarez automáticamente. No se modifican archivos originales ni títulos MKV.
      </div>
    </div>
  )
}
