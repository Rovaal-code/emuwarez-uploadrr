import { useState, useEffect, useCallback } from 'react'
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

  const load = useCallback(async (force = false) => {
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
  }, [itemId])

  useEffect(() => { load(false) }, [load])

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
  // Un archivo de la biblioteca no se renombra nunca: solo los de la carpeta de subidas.
  const noRenombrable = applyResult?.renombrable === false

  return (
    <Modal titulo="Nomenclatura eMuwarez" onClose={onClose}>
      <div className="modal-body">
        <p className="text-muted nomen-titulo">{itemTitle}</p>

        {loading && <p>Generando propuesta…</p>}
        {error && <p className="error-text">{error}</p>}

        {proposal && (
          <>
            <div className="nomen-estado">
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
              <span className="nomen-quiebra">{proposal.proposed_torrent_name || proposal.proposed_filename || '—'}</span>
            </div>
            <div className="detail-row">
              <span className="text-muted">Archivo propuesto:</span>
              <span className="nomen-quiebra">{proposal.proposed_filename || '—'}</span>
            </div>
            <div className="detail-row">
              <span className="text-muted">Carpeta actual:</span>
              <span className="nomen-quiebra">
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
              <div className="detail-panel__section nomen-sec-avisos">
                <div className="detail-panel__section-title">Avisos</div>
                <ul className="detail-panel__reasons">
                  {proposal.warnings.map((w, i) => <li key={i}>{w}</li>)}
                </ul>
              </div>
            )}
            {proposal.errors.length > 0 && (
              <div className="detail-panel__section nomen-sec-errores">
                <div className="detail-panel__section-title">Errores</div>
                <ul className="detail-panel__reasons">
                  {proposal.errors.map((err, i) => (
                    <li key={i} className="nomen-error">{err}</li>
                  ))}
                </ul>
              </div>
            )}

            {/* Apply section */}
            {canApply && (
              <div className="detail-panel__section nomen-aplicar">
                <div className="detail-panel__section-title nomen-aplicar-titulo">
                  Aplicar nomenclatura
                </div>
                {!showApplySection ? (
                  <button className="btn btn-secondary" onClick={() => { setShowApplySection(true); handleDryRun() }}>
                    Mostrar opciones de aplicación
                  </button>
                ) : noRenombrable ? (
                  <p className="form-hint">{applyResult?.message}</p>
                ) : (
                  <>
                    <p className="nomen-ayuda">
                      El archivo está en la carpeta de subidas: se renombrará con el nombre propuesto
                      (mismo directorio). Uploadrr no se ejecuta.
                    </p>
                    <div className="nomen-fila-botones">
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
                        <div className="nomen-token-texto">
                          Para aplicar, escribe el token de confirmación:
                        </div>
                        <div className="nomen-fila-token">
                          <input
                            type="text"
                            value={confirmInput}
                            onChange={e => setConfirmInput(e.target.value)}
                            placeholder={CONFIRMATION_TOKEN}
                            className="nomen-token"
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

                {applyLoading && <p className="nomen-procesando">Procesando…</p>}
                {applyError && (
                  <p className="nomen-aplicar-error">
                    {applyError}
                  </p>
                )}
                {applyResult && !noRenombrable && (
                  <div className="nomen-resultado">
                    <div className="nomen-resultado-estado">
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
                      <div className="detail-row nomen-resultado-fila">
                        <span className="text-muted">Nuevo nombre:</span>
                        <span className="nomen-quiebra">{applyResult.destination_path}</span>
                      </div>
                    )}
                    {applyResult.message && (
                      <p className="nomen-resultado-mensaje">
                        {applyResult.message}
                      </p>
                    )}
                    {applyResult.warnings.length > 0 && (
                      <ul className="detail-panel__reasons nomen-lista">
                        {applyResult.warnings.map((w, i) => <li key={i} className="nomen-li-chico">{w}</li>)}
                      </ul>
                    )}
                    {applyResult.errors.length > 0 && (
                      <ul className="detail-panel__reasons nomen-lista">
                        {applyResult.errors.map((e, i) => (
                          <li key={i} className="nomen-li-chico nomen-error">{e}</li>
                        ))}
                      </ul>
                    )}
                  </div>
                )}
              </div>
            )}
          </>
        )}

        <div className="detail-panel__section nomen-seguridad">
          Seguridad: los archivos de la biblioteca nunca se renombran, solo los de la carpeta de subidas.
          Uploadrr y mkvpropedit no se ejecutan.
        </div>
      </div>
      <div className="detail-panel__actions nomen-acciones">
        <button className="btn btn-secondary" onClick={() => load(true)} disabled={loading}>
          Generar de nuevo
        </button>
        <button className="btn btn-secondary" onClick={onClose}>Cerrar</button>
      </div>
    </Modal>
  )
}
