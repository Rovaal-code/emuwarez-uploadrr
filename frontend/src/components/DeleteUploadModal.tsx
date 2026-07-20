import { useState } from 'react'
import type { UploadJob } from '../types/api'
import { deleteUploadJob } from '../api/uploads'

// Styled confirmation card for deleting an upload job from its own dedicated
// detail page — only ever opened for a 'failed'/'cancelled' job (the backend
// refuses any other status, see delete_upload_job() in services/upload_execution.py).
export function DeleteUploadModal({ job, onClose, onDeleted }: {
  job: UploadJob
  onClose: () => void
  onDeleted: () => void
}) {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleDelete = async () => {
    setLoading(true); setError(null)
    try {
      await deleteUploadJob(job.id!)
      onDeleted()
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'No se pudo borrar la subida.')
      setLoading(false)
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" style={{ maxWidth: 440 }} onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h2 className="modal-title">Borrar subida</h2>
          <button className="btn-icon" onClick={onClose} title="Cerrar">✕</button>
        </div>
        <div className="modal-body">
          <p style={{ margin: 0, fontWeight: 600 }}>{job.title || `Job ${job.id}`}</p>
          <div style={{ padding: '10px 14px', background: 'rgba(255,80,80,0.08)', borderRadius: 6, border: '1px solid rgba(255,80,80,0.2)', margin: '12px 0' }}>
            <p style={{ margin: 0, fontSize: 13.5, lineHeight: 1.5 }}>
              Se va a borrar todo el material y todo lo que hay registrado de esta subida: registro de actividad, capturas y demás datos generados durante el intento. Esta acción no se puede deshacer.
            </p>
          </div>
          <p style={{ margin: 0, fontSize: 12, color: 'var(--text-muted)' }}>
            El archivo de vídeo de tu biblioteca no se toca — solo se borra el registro de este intento de subida.
          </p>
          {error && <p className="error-text" style={{ marginTop: 8 }}>{error}</p>}
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 16 }}>
            <button className="btn btn-secondary" onClick={onClose} disabled={loading}>Cancelar</button>
            <button className="btn btn-danger" onClick={handleDelete} disabled={loading}>{loading ? 'Borrando…' : 'Borrar subida'}</button>
          </div>
        </div>
      </div>
    </div>
  )
}
