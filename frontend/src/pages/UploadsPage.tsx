import { useState, useEffect } from 'react'
import { getUploads } from '../api/uploads'
import type { UploadJob } from '../types/api'
import { EmptyState } from '../components/EmptyState'
import { LoadingState } from '../components/LoadingState'
import { ErrorState } from '../components/ErrorState'
import { formatDate } from '../utils/format'

const STATUS_CLASS: Record<string, string> = {
  ready: 'badge req-compatible',
  preflight: 'badge req-partial',
  blocked: 'badge req-not-compatible',
  draft: 'badge req-unknown',
  completed: 'badge req-filled',
  failed: 'badge req-not-compatible',
}

export function UploadsPage() {
  const [jobs, setJobs] = useState<UploadJob[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await getUploads()
      setJobs(data)
    } catch {
      setError('Error al cargar los preflights de subida.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="page-title">Subidas</div>
          <div className="page-subtitle">Preflights y trabajos de subida con Uploadrr</div>
        </div>
        <button className="btn btn-secondary btn-sm" onClick={load} disabled={loading}>
          Actualizar
        </button>
      </div>

      {loading ? (
        <LoadingState label="Cargando preflights…" />
      ) : error ? (
        <ErrorState message={error} onRetry={load} />
      ) : jobs.length === 0 ? (
        <EmptyState
          icon="📤"
          title="Todavía no hay preflights de subida."
          body="Usa el botón 'Subir' desde Biblioteca para generar un preflight y validar las precondiciones de subida."
        />
      ) : (
        <div className="activity-section">
          <div className="section-header">
            <div className="section-title">Preflights de subida</div>
            <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>{jobs.length} registro{jobs.length !== 1 ? 's' : ''}</span>
          </div>
          <div style={{ overflowX: 'auto' }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Título</th>
                  <th>Estado</th>
                  <th>Etapa</th>
                  <th>Error</th>
                  <th>Creado</th>
                </tr>
              </thead>
              <tbody>
                {jobs.map(job => (
                  <tr key={job.id}>
                    <td style={{ color: 'var(--text-muted)', fontSize: 12 }}>{job.id}</td>
                    <td style={{ fontWeight: 500 }}>{job.title || '–'}</td>
                    <td>
                      <span className={STATUS_CLASS[job.status] || 'badge req-unknown'}>
                        {job.status}
                      </span>
                    </td>
                    <td style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{job.stage || '–'}</td>
                    <td style={{ fontSize: 12, color: 'var(--color-error, #f87171)', maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {job.error_message || '–'}
                    </td>
                    <td style={{ fontSize: 12, color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>
                      {formatDate(job.created_at ?? null)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <div style={{ marginTop: 16, padding: '10px 16px', background: 'rgba(255,200,0,0.06)', borderRadius: 8, fontSize: '0.82rem', color: 'var(--text-muted)' }}>
        La ejecución real de Uploadrr se implementará en una fase posterior. Esta pantalla muestra solo preflights y validaciones.
      </div>
    </div>
  )
}
