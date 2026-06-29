import { useState, useEffect } from 'react'
import type { NomenclatureProposal } from '../types/api'
import { previewNomenclature } from '../api/nomenclature'

interface Props {
  itemId: number
  itemTitle: string
  onClose: () => void
}

const STATUS_LABELS: Record<string, string> = {
  valid: 'Lista',
  warning: 'Con avisos',
  blocked: 'Bloqueada',
  draft: 'Borrador',
  applied: 'Aplicada',
  expired: 'Expirada',
}

const STATUS_CLASS: Record<string, string> = {
  valid: 'badge req-compatible',
  warning: 'badge req-partial',
  blocked: 'badge req-not-compatible',
  draft: 'badge req-unknown',
  applied: 'badge req-filled',
}

export function NomenclatureModal({ itemId, itemTitle, onClose }: Props) {
  const [proposal, setProposal] = useState<NomenclatureProposal | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = async (force = false) => {
    setLoading(true)
    setError(null)
    try {
      const p = await previewNomenclature(itemId, force)
      setProposal(p)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Error al generar propuesta.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load(false) }, [itemId])

  const statusLabel = proposal ? (STATUS_LABELS[proposal.status] || proposal.status) : ''
  const statusClass = proposal ? (STATUS_CLASS[proposal.status] || 'badge req-unknown') : ''

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h2 className="modal-title">Nomenclatura eMuwarez</h2>
          <button className="btn-icon" onClick={onClose} title="Cerrar">✕</button>
        </div>
        <div className="modal-body">
          <p className="text-muted" style={{ marginBottom: 12 }}>{itemTitle}</p>

          {loading && <p>Generando propuesta…</p>}
          {error && <p className="error-text">{error}</p>}

          {proposal && (
            <>
              <div style={{ marginBottom: 12 }}>
                <span className={statusClass}>{statusLabel}</span>
              </div>
              <div className="detail-row">
                <span className="text-muted">Nombre actual:</span>
                <span>{proposal.current_name || '–'}</span>
              </div>
              <div className="detail-row">
                <span className="text-muted">Título propuesto:</span>
                <span>{proposal.proposed_title || '–'}</span>
              </div>
              <div className="detail-row">
                <span className="text-muted">Archivo propuesto:</span>
                <span style={{ wordBreak: 'break-all' }}>{proposal.proposed_filename || '–'}</span>
              </div>
              <div className="detail-row">
                <span className="text-muted">Carpeta propuesta:</span>
                <span style={{ wordBreak: 'break-all' }}>{proposal.proposed_folder || '–'}</span>
              </div>
              <div className="detail-row">
                <span className="text-muted">Resolución:</span>
                <span>{proposal.resolution || '–'}</span>
              </div>
              <div className="detail-row">
                <span className="text-muted">Source:</span>
                <span>{proposal.source || '–'}</span>
              </div>
              <div className="detail-row">
                <span className="text-muted">Vídeo:</span>
                <span>{proposal.video_codec || '–'}</span>
              </div>
              <div className="detail-row">
                <span className="text-muted">Audio:</span>
                <span>{proposal.audio_summary || '–'}</span>
              </div>
              <div className="detail-row">
                <span className="text-muted">Subtítulos:</span>
                <span>{proposal.subtitle_summary || '–'}</span>
              </div>
              {proposal.warnings.length > 0 && (
                <div className="detail-panel__section" style={{ marginTop: 12 }}>
                  <div className="detail-panel__section-title">Avisos</div>
                  <ul className="detail-panel__reasons">
                    {proposal.warnings.map((w, i) => <li key={i}>{w}</li>)}
                  </ul>
                </div>
              )}
              {proposal.errors.length > 0 && (
                <div className="detail-panel__section" style={{ marginTop: 8 }}>
                  <div className="detail-panel__section-title">Errores</div>
                  <ul className="detail-panel__reasons">
                    {proposal.errors.map((err, i) => (
                      <li key={i} style={{ color: 'var(--color-error, #f87171)' }}>{err}</li>
                    ))}
                  </ul>
                </div>
              )}
            </>
          )}

          <div className="detail-panel__section" style={{ marginTop: 16, padding: '8px 12px', background: 'rgba(255,200,0,0.08)', borderRadius: 6, fontSize: '0.85rem' }}>
            Esto es una previsualización. No se ha renombrado, hardlinkeado ni subido nada.
          </div>
        </div>
        <div className="detail-panel__actions" style={{ padding: '12px 16px' }}>
          <button className="btn btn-secondary" onClick={() => load(true)} disabled={loading}>
            Generar de nuevo
          </button>
          <button
            className="btn btn-primary"
            disabled
            title="Disponible en una fase posterior. Esta versión solo genera previsualización segura."
          >
            Aplicar cambios
          </button>
          <button className="btn btn-secondary" onClick={onClose}>Cerrar</button>
        </div>
      </div>
    </div>
  )
}
