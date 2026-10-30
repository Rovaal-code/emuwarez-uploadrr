import { useState, useEffect } from 'react'
import type { NomenclatureProposal, NomenclatureApplyResult } from '../types/api'
import { previewNomenclature, adaptNomenclature } from '../api/nomenclature'
import { Modal } from './Modal'

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

const CONFIRMATION_TOKEN = 'APLICAR_NOMENCLATURA'

export function NomenclatureModal({ itemId, itemTitle, onClose }: Props) {
  const [proposal, setProposal] = useState<NomenclatureProposal | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Apply section state
  const [applyResult, setApplyResult] = useState<NomenclatureApplyResult | null>(null)
  const [applyLoading, setApplyLoading] = useState(false)
  const [applyError, setApplyError] = useState<string | null>(null)
  const [confirmInput, setConfirmInput] = useState('')
  const [showApplySection, setShowApplySection] = useState(false)

  const load = async (force = false) => {
    setLoading(true)
    setError(null)
    setApplyResult(null)
    setApplyError(null)
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

  const handleDryRun = async () => {
    setApplyLoading(true)
    setApplyError(null)
    setApplyResult(null)
    try {
      const r = await adaptNomenclature(itemId, { dryRun: true })
      setApplyResult(r)
    } catch (e: unknown) {
      setApplyError(e instanceof Error ? e.message : 'Error al ejecutar dry-run.')
    } finally {
      setApplyLoading(false)
    }
  }

  const handleApply = async () => {
    if (confirmInput !== CONFIRMATION_TOKEN) {
      setApplyError(`Escribe exactamente: ${CONFIRMATION_TOKEN}`)
      return
    }
    setApplyLoading(true)
    setApplyError(null)
    setApplyResult(null)
    try {
      const r = await adaptNomenclature(itemId, {
        dryRun: false,
        apply: true,
        confirmation: confirmInput,
      })
      setApplyResult(r)
    } catch (e: unknown) {
      setApplyError(e instanceof Error ? e.message : 'Error al aplicar nomenclatura.')
    } finally {
      setApplyLoading(false)
    }
  }

  const statusLabel = proposal ? (STATUS_LABELS[proposal.status] || proposal.status) : ''
  const statusClass = proposal ? (STATUS_CLASS[proposal.status] || 'badge req-unknown') : ''
  const canApply = proposal && proposal.status !== 'blocked'
  const alreadyApplied = applyResult?.status === 'applied'

  return (
    <Modal titulo="Nomenclatura eMuwarez" onClose={onClose}>
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
              <span>{proposal.current_name || '—'}</span>
            </div>
            <div className="detail-row">
              <span className="text-muted">Título propuesto:</span>
              <span>{proposal.proposed_title || '—'}</span>
            </div>
            <div className="detail-row">
              <span className="text-muted">Título en eMuwarez:</span>
              <span style={{ wordBreak: 'break-all' }}>{proposal.proposed_torrent_name || proposal.proposed_filename || '—'}</span>
            </div>
            <div className="detail-row">
              <span className="text-muted">Archivo propuesto:</span>
              <span style={{ wordBreak: 'break-all' }}>{proposal.proposed_filename || '—'}</span>
            </div>
            <div className="detail-row">
              <span className="text-muted">Carpeta actual:</span>
              <span style={{ wordBreak: 'break-all' }}>
                {proposal.current_path ? proposal.current_path.substring(0, proposal.current_path.lastIndexOf('/')) || '/' : '—'}
              </span>
            </div>
            <div className="detail-row">
              <span className="text-muted">Resolución:</span>
              <span>{proposal.resolution || '—'}</span>
            </div>
            <div className="detail-row">
              <span className="text-muted">Source:</span>
              <span>{proposal.source || '—'}</span>
            </div>
            {proposal.provider && (
              <div className="detail-row">
                <span className="text-muted">Proveedor:</span>
                <span>{proposal.provider}</span>
              </div>
            )}
            <div className="detail-row">
              <span className="text-muted">Vídeo:</span>
              <span>{proposal.video_codec || '—'}</span>
            </div>
            <div className="detail-row">
              <span className="text-muted">Audio:</span>
              <span>{proposal.audio_summary || '—'}</span>
            </div>
            <div className="detail-row">
              <span className="text-muted">Subtítulos:</span>
              <span>{proposal.subtitle_summary || '—'}</span>
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
                    <li key={i} style={{ color: 'var(--color-error)' }}>{err}</li>
                  ))}
                </ul>
              </div>
            )}

            {/* Apply section */}
            {canApply && (
              <div
                className="detail-panel__section"
                style={{ marginTop: 16, padding: '12px', background: 'color-mix(in srgb, var(--color-indigo) 8%, transparent)', borderRadius: 6 }}
              >
                <div className="detail-panel__section-title" style={{ marginBottom: 8 }}>
                  Aplicar nomenclatura
                </div>
                {!showApplySection ? (
                  <button className="btn btn-secondary" onClick={() => setShowApplySection(true)}>
                    Mostrar opciones de aplicación
                  </button>
                ) : (
                  <>
                    <p style={{ fontSize: '0.85rem', marginBottom: 8, color: 'var(--text-secondary)' }}>
                      Se renombrará el archivo original con el nombre propuesto (mismo directorio).
                      Uploadrr no se ejecuta.
                    </p>
                    <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
                      <button
                        className="btn btn-secondary"
                        onClick={handleDryRun}
                        disabled={applyLoading}
                      >
                        Previsualizar
                      </button>
                    </div>
                    {!alreadyApplied && (
                      <>
                        <div style={{ marginTop: 8, marginBottom: 4, fontSize: '0.85rem' }}>
                          Para aplicar, escribe el token de confirmación:
                        </div>
                        <div style={{ display: 'flex', gap: 8 }}>
                          <input
                            type="text"
                            value={confirmInput}
                            onChange={e => setConfirmInput(e.target.value)}
                            placeholder={CONFIRMATION_TOKEN}
                            style={{
                              flex: 1,
                              padding: '4px 8px',
                              fontFamily: 'var(--font-mono)',
                              fontSize: '0.85rem',
                              background: 'color-mix(in srgb, var(--overlay-dark) 30%, transparent)',
                              border: '1px solid color-mix(in srgb, var(--overlay-light) 15%, transparent)',
                              borderRadius: 4,
                              color: 'inherit',
                            }}
                          />
                          <button
                            className="btn btn-primary"
                            onClick={handleApply}
                            disabled={applyLoading || confirmInput !== CONFIRMATION_TOKEN}
                          >
                            Aplicar
                          </button>
                        </div>
                      </>
                    )}
                  </>
                )}

                {applyLoading && <p style={{ marginTop: 8, fontSize: '0.85rem' }}>Procesando…</p>}
                {applyError && (
                  <p style={{ marginTop: 8, fontSize: '0.85rem', color: 'var(--color-error)' }}>
                    {applyError}
                  </p>
                )}
                {applyResult && (
                  <div style={{ marginTop: 8 }}>
                    <div style={{ marginBottom: 4 }}>
                      <span
                        className={applyResult.status === 'applied'
                          ? 'badge req-filled'
                          : applyResult.status === 'ready'
                          ? 'badge req-compatible'
                          : 'badge req-not-compatible'}
                      >
                        {applyResult.status === 'applied' ? 'Aplicado'
                          : applyResult.status === 'ready' ? 'Previsualización OK'
                          : applyResult.status}
                      </span>
                    </div>
                    {applyResult.destination_path && (
                      <div className="detail-row" style={{ fontSize: '0.8rem' }}>
                        <span className="text-muted">Nuevo nombre:</span>
                        <span style={{ wordBreak: 'break-all' }}>{applyResult.destination_path}</span>
                      </div>
                    )}
                    {applyResult.message && (
                      <p style={{ fontSize: '0.8rem', marginTop: 4, color: 'var(--text-secondary)' }}>
                        {applyResult.message}
                      </p>
                    )}
                    {applyResult.warnings.length > 0 && (
                      <ul className="detail-panel__reasons" style={{ marginTop: 4 }}>
                        {applyResult.warnings.map((w, i) => <li key={i} style={{ fontSize: '0.8rem' }}>{w}</li>)}
                      </ul>
                    )}
                    {applyResult.errors.length > 0 && (
                      <ul className="detail-panel__reasons" style={{ marginTop: 4 }}>
                        {applyResult.errors.map((e, i) => (
                          <li key={i} style={{ fontSize: '0.8rem', color: 'var(--color-error)' }}>{e}</li>
                        ))}
                      </ul>
                    )}
                  </div>
                )}
              </div>
            )}
          </>
        )}

        <div className="detail-panel__section" style={{ marginTop: 16, padding: '8px 12px', background: 'color-mix(in srgb, var(--color-warning-soft) 8%, transparent)', borderRadius: 6, fontSize: '0.85rem' }}>
          Seguridad: el archivo original nunca se renombra. Uploadrr y mkvpropedit no se ejecutan.
        </div>
      </div>
      <div className="detail-panel__actions" style={{ padding: '12px 16px' }}>
        <button className="btn btn-secondary" onClick={() => load(true)} disabled={loading}>
          Generar de nuevo
        </button>
        <button className="btn btn-secondary" onClick={onClose}>Cerrar</button>
      </div>
    </Modal>
  )
}
