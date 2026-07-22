import { useState, useEffect } from 'react'
import type { UploadPreflightResponse, UploadStartResult } from '../types/api'
import { uploadPreflight, startUploadJob } from '../api/uploads'
import { useTooltip } from './Tooltip'

interface Props {
  itemId: number
  itemTitle: string
  requestId?: number
  onClose: () => void
}

const CONFIRMATION_TOKEN = 'INICIAR_UPLOADRR'

export function UploadPreflightModal({ itemId, itemTitle, requestId, onClose }: Props) {
  const [result, setResult] = useState<UploadPreflightResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [confirmInput, setConfirmInput] = useState('')
  const [startResult, setStartResult] = useState<UploadStartResult | null>(null)
  const [startLoading, setStartLoading] = useState(false)
  const [startError, setStartError] = useState<string | null>(null)

  const load = async () => {
    setLoading(true)
    setError(null)
    setStartResult(null)
    setStartError(null)
    setConfirmInput('')
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

  const jobId = result?.job?.id

  const handleDryRun = async () => {
    if (!jobId) return
    setStartLoading(true)
    setStartError(null)
    setStartResult(null)
    try {
      const r = await startUploadJob(jobId, { dry_run: true, start: false, confirmation: null })
      setStartResult(r)
    } catch (e: unknown) {
      setStartError(e instanceof Error ? e.message : 'Error en dry-run.')
    } finally {
      setStartLoading(false)
    }
  }

  const handleStart = async () => {
    if (!jobId || confirmInput !== CONFIRMATION_TOKEN) return
    setStartLoading(true)
    setStartError(null)
    setStartResult(null)
    try {
      const r = await startUploadJob(jobId, {
        dry_run: false,
        start: true,
        confirmation: CONFIRMATION_TOKEN,
      })
      setStartResult(r)
    } catch (e: unknown) {
      setStartError(e instanceof Error ? e.message : 'Error al iniciar subida.')
    } finally {
      setStartLoading(false)
    }
  }

  const statusClass = result?.status === 'ready' ? 'badge req-compatible' : 'badge req-not-compatible'
  const statusLabel = result?.status === 'ready' ? 'Listo' : 'Bloqueado'
  const canStart = result?.status === 'ready' && !!jobId
  const closeTip = useTooltip('Cerrar')
  const dryRunTip = useTooltip('Previsualizar el comando sin ejecutar Uploadrr')
  const startTip = useTooltip(canStart ? `Escribe ${CONFIRMATION_TOKEN} para habilitar` : 'El preflight no está listo')

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()} style={{ maxWidth: 680 }}>
        <div className="modal-header">
          <h2 className="modal-title">Preflight Uploadrr</h2>
          <button className="btn-icon" onClick={onClose} {...closeTip.triggerProps}>✕{closeTip.tooltipNode}</button>
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
                    <span className="text-muted">Runtime:</span>
                    <span>
                      {result.command_preview.runtime_type || '–'}
                      {result.command_preview.contract_valid === false && (
                        <span className="badge req-not-compatible" style={{ marginLeft: 6, fontSize: '0.7rem' }}>
                          contrato inválido
                        </span>
                      )}
                      {result.command_preview.contract_valid === true && (
                        <span className="badge req-compatible" style={{ marginLeft: 6, fontSize: '0.7rem' }}>
                          contrato válido
                        </span>
                      )}
                    </span>
                  </div>
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
                    <span style={{ wordBreak: 'break-all', fontSize: '0.8rem' }}>
                      {result.command_preview.source_path || '–'}
                      {result.command_preview.using_prepared_path && (
                        <span className="badge req-filled" style={{ marginLeft: 6, fontSize: '0.7rem' }}>
                          preparado
                        </span>
                      )}
                      {result.command_preview.using_prepared_path === false && (
                        <span className="badge req-partial" style={{ marginLeft: 6, fontSize: '0.7rem' }}>
                          original
                        </span>
                      )}
                    </span>
                  </div>
                  {(result.command_preview.contract_errors?.length ?? 0) > 0 && (
                    <div className="detail-panel__section" style={{ marginTop: 8 }}>
                      <div className="detail-panel__section-title">Errores de contrato Uploadrr-EMU</div>
                      <ul className="detail-panel__reasons">
                        {result.command_preview.contract_errors!.map((err, i) => (
                          <li key={i} style={{ color: 'var(--color-error, #f87171)' }}>{err}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {(result.command_preview.contract_warnings?.length ?? 0) > 0 && (
                    <div className="detail-panel__section" style={{ marginTop: 8 }}>
                      <div className="detail-panel__section-title">Avisos de contrato Uploadrr-EMU</div>
                      <ul className="detail-panel__reasons">
                        {result.command_preview.contract_warnings!.map((w, i) => <li key={i}>{w}</li>)}
                      </ul>
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

          {canStart && (
            <div className="detail-panel__section" style={{ marginTop: 16, padding: '12px 14px', background: 'rgba(255,80,80,0.08)', borderRadius: 6, border: '1px solid rgba(255,80,80,0.2)' }}>
              <div className="detail-panel__section-title" style={{ color: 'var(--color-error, #f87171)', marginBottom: 8 }}>
                Advertencia de seguridad
              </div>
              <ul style={{ margin: 0, paddingLeft: 18, fontSize: '0.83rem', lineHeight: 1.6 }}>
                <li>Esta acción ejecutará Uploadrr y puede publicar/subir contenido a eMuwarez.</li>
                <li>No se crearán peticiones eMuwarez automáticamente.</li>
                <li>No se modificará el archivo original.</li>
                <li>No se modificará el título interno MKV.</li>
              </ul>
              <div style={{ marginTop: 12 }}>
                <label style={{ display: 'block', marginBottom: 6, fontSize: '0.83rem' }}>
                  Escribe <strong>{CONFIRMATION_TOKEN}</strong> para habilitar la subida:
                </label>
                <input
                  type="text"
                  value={confirmInput}
                  onChange={e => setConfirmInput(e.target.value)}
                  placeholder={CONFIRMATION_TOKEN}
                  style={{
                    width: '100%',
                    padding: '6px 10px',
                    background: 'rgba(255,255,255,0.08)',
                    border: `1px solid ${confirmInput === CONFIRMATION_TOKEN ? 'var(--color-success, #4ade80)' : 'rgba(255,255,255,0.15)'}`,
                    borderRadius: 4,
                    color: 'inherit',
                    fontFamily: 'monospace',
                    fontSize: '0.9rem',
                    boxSizing: 'border-box',
                  }}
                />
              </div>
            </div>
          )}

          {startResult && (
            <div className="detail-panel__section" style={{ marginTop: 12, padding: '10px 14px', background: 'rgba(0,200,100,0.06)', borderRadius: 6 }}>
              <div className="detail-panel__section-title">Resultado</div>
              <p style={{ margin: '4px 0', fontSize: '0.85rem' }}>
                <strong>Acción:</strong> {startResult.action} &nbsp;
                <strong>Estado:</strong> {startResult.status}
              </p>
              {startResult.message && <p style={{ margin: '4px 0', fontSize: '0.83rem' }}>{startResult.message}</p>}
            </div>
          )}
          {startError && <p className="error-text" style={{ marginTop: 8 }}>{startError}</p>}

          <div className="detail-panel__section" style={{ marginTop: 16, padding: '8px 12px', background: 'rgba(255,200,0,0.08)', borderRadius: 6, fontSize: '0.85rem' }}>
            Preflight seguro. {canStart ? 'Usa dry-run para previsualizar o confirma para iniciar la subida real.' : 'No se ha ejecutado Uploadrr.'}
          </div>
        </div>
        <div className="detail-panel__actions" style={{ padding: '12px 16px', gap: 8, display: 'flex', flexWrap: 'wrap' }}>
          {canStart && (
            <button
              className="btn btn-secondary"
              onClick={handleDryRun}
              disabled={startLoading}
              {...dryRunTip.triggerProps}
            >
              {startLoading ? 'Procesando…' : 'Dry-run'}
              {dryRunTip.tooltipNode}
            </button>
          )}
          <button
            className="btn btn-primary"
            disabled={!canStart || confirmInput !== CONFIRMATION_TOKEN || startLoading}
            onClick={handleStart}
            {...startTip.triggerProps}
          >
            {startLoading ? 'Iniciando…' : 'Iniciar subida'}
            {startTip.tooltipNode}
          </button>
          <button className="btn btn-secondary" onClick={onClose}>Cerrar</button>
        </div>
      </div>
    </div>
  )
}
