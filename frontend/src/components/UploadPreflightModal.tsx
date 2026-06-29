import { useState, useEffect } from 'react'
import type { UploadPreflightResponse } from '../types/api'
import { uploadPreflight } from '../api/uploads'

interface Props {
  itemId: number
  itemTitle: string
  requestId?: number
  onClose: () => void
}

export function UploadPreflightModal({ itemId, itemTitle, requestId, onClose }: Props) {
  const [result, setResult] = useState<UploadPreflightResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const r = await uploadPreflight(itemId, requestId)
      setResult(r)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Error al ejecutar preflight.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [itemId])

  const statusClass = result?.status === 'ready' ? 'badge req-compatible' : 'badge req-not-compatible'
  const statusLabel = result?.status === 'ready' ? 'Listo' : 'Bloqueado'

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()} style={{ maxWidth: 640 }}>
        <div className="modal-header">
          <h2 className="modal-title">Preflight Uploadrr</h2>
          <button className="btn-icon" onClick={onClose} title="Cerrar">✕</button>
        </div>
        <div className="modal-body">
          <p className="text-muted" style={{ marginBottom: 12 }}>{itemTitle}</p>

          {loading && <p>Ejecutando preflight…</p>}
          {error && <p className="error-text">{error}</p>}

          {result && (
            <>
              <div style={{ marginBottom: 12 }}>
                <span className={statusClass}>{statusLabel}</span>
              </div>
              {result.command_preview && (
                <>
                  <div className="detail-row">
                    <span className="text-muted">Tracker:</span>
                    <span>{result.command_preview.tracker || '–'}</span>
                  </div>
                  <div className="detail-row">
                    <span className="text-muted">Categoría:</span>
                    <span>{result.command_preview.category || '–'}</span>
                  </div>
                  <div className="detail-row">
                    <span className="text-muted">TMDb:</span>
                    <span>{result.command_preview.tmdb_id || '–'}</span>
                  </div>
                  <div className="detail-row">
                    <span className="text-muted">Resolución:</span>
                    <span>{result.command_preview.resolution || '–'}</span>
                  </div>
                  <div className="detail-row">
                    <span className="text-muted">Archivo origen:</span>
                    <span style={{ wordBreak: 'break-all', fontSize: '0.8rem' }}>{result.command_preview.source_path || '–'}</span>
                  </div>
                  {result.command_preview.command_preview && (
                    <div className="detail-panel__section" style={{ marginTop: 12 }}>
                      <div className="detail-panel__section-title">Comando previsto</div>
                      <pre style={{ fontSize: '0.75rem', overflow: 'auto', padding: 8, background: 'rgba(0,0,0,0.2)', borderRadius: 4 }}>
                        {result.command_preview.command_preview}
                      </pre>
                    </div>
                  )}
                </>
              )}
              {result.warnings.length > 0 && (
                <div className="detail-panel__section" style={{ marginTop: 12 }}>
                  <div className="detail-panel__section-title">Avisos</div>
                  <ul className="detail-panel__reasons">
                    {result.warnings.map((w, i) => <li key={i}>{w}</li>)}
                  </ul>
                </div>
              )}
              {result.errors.length > 0 && (
                <div className="detail-panel__section" style={{ marginTop: 8 }}>
                  <div className="detail-panel__section-title">Errores</div>
                  <ul className="detail-panel__reasons">
                    {result.errors.map((err, i) => (
                      <li key={i} style={{ color: 'var(--color-error, #f87171)' }}>{err}</li>
                    ))}
                  </ul>
                </div>
              )}
            </>
          )}

          <div className="detail-panel__section" style={{ marginTop: 16, padding: '8px 12px', background: 'rgba(255,200,0,0.08)', borderRadius: 6, fontSize: '0.85rem' }}>
            Preflight seguro. No se ha ejecutado Uploadrr ni subido ningún archivo.
          </div>
        </div>
        <div className="detail-panel__actions" style={{ padding: '12px 16px' }}>
          <button
            className="btn btn-primary"
            disabled
            title="La ejecución real de Uploadrr se implementará en una fase posterior."
          >
            Iniciar subida
          </button>
          <button className="btn btn-secondary" onClick={onClose}>Cerrar</button>
        </div>
      </div>
    </div>
  )
}
