import { useState, useEffect, useCallback } from 'react'
import type { UploadPreflightResponse, UploadStartResult } from '../types/api'
import { uploadPreflight, startUploadJob } from '../api/uploads'
import { useTooltip } from './Tooltip'
import { Modal } from './Modal'

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

  const load = useCallback(async () => {
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
  }, [itemId, requestId])

  useEffect(() => { load() }, [load])

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
  const dryRunTip = useTooltip('Previsualizar el comando sin ejecutar Uploadrr')
  const startTip = useTooltip(canStart ? `Escribe ${CONFIRMATION_TOKEN} para habilitar` : 'El preflight no está listo')

  return (
    <Modal titulo="Preflight Uploadrr" onClose={onClose} className="preflight-modal">
      <div className="modal-body">
        <p className="text-muted preflight-titulo">{itemTitle}</p>

        {loading && <p>Ejecutando preflight…</p>}
        {error && <p className="error-text">{error}</p>}

        {result && (
          <>
            <div className="preflight-estado">
              <span className={statusClass}>{statusLabel}</span>
            </div>
            {result.command_preview && (
              <>
                <div className="detail-row">
                  <span className="text-muted">Runtime:</span>
                  <span>
                    {result.command_preview.runtime_type || '—'}
                    {result.command_preview.contract_valid === false && (
                      <span className="badge req-not-compatible preflight-chip">
                        contrato inválido
                      </span>
                    )}
                    {result.command_preview.contract_valid === true && (
                      <span className="badge req-compatible preflight-chip">
                        contrato válido
                      </span>
                    )}
                  </span>
                </div>
                <div className="detail-row">
                  <span className="text-muted">Tracker:</span>
                  <span>{result.command_preview.tracker || '—'}</span>
                </div>
                <div className="detail-row">
                  <span className="text-muted">Categoría:</span>
                  <span>{result.command_preview.category || '—'}</span>
                </div>
                <div className="detail-row">
                  <span className="text-muted">TMDb:</span>
                  <span>{result.command_preview.tmdb_id || '—'}</span>
                </div>
                <div className="detail-row">
                  <span className="text-muted">Resolución:</span>
                  <span>{result.command_preview.resolution || '—'}</span>
                </div>
                <div className="detail-row">
                  <span className="text-muted">Archivo origen:</span>
                  <span className="preflight-origen">
                    {result.command_preview.source_path || '—'}
                    {result.command_preview.using_prepared_path && (
                      <span className="badge req-filled preflight-chip">
                        preparado
                      </span>
                    )}
                    {result.command_preview.using_prepared_path === false && (
                      <span className="badge req-partial preflight-chip">
                        original
                      </span>
                    )}
                  </span>
                </div>
                {(result.command_preview.contract_errors?.length ?? 0) > 0 && (
                  <div className="detail-panel__section preflight-sec-errores">
                    <div className="detail-panel__section-title">Errores de contrato Uploadrr-EMU</div>
                    <ul className="detail-panel__reasons">
                      {result.command_preview.contract_errors!.map((err, i) => (
                        <li key={i} className="preflight-error">{err}</li>
                      ))}
                    </ul>
                  </div>
                )}
                {(result.command_preview.contract_warnings?.length ?? 0) > 0 && (
                  <div className="detail-panel__section preflight-sec-errores">
                    <div className="detail-panel__section-title">Avisos de contrato Uploadrr-EMU</div>
                    <ul className="detail-panel__reasons">
                      {result.command_preview.contract_warnings!.map((w, i) => <li key={i}>{w}</li>)}
                    </ul>
                  </div>
                )}
              </>
            )}
            {result.warnings.length > 0 && (
              <div className="detail-panel__section preflight-sec-avisos">
                <div className="detail-panel__section-title">Avisos</div>
                <ul className="detail-panel__reasons">
                  {result.warnings.map((w, i) => <li key={i}>{w}</li>)}
                </ul>
              </div>
            )}
            {result.errors.length > 0 && (
              <div className="detail-panel__section preflight-sec-errores">
                <div className="detail-panel__section-title">Errores</div>
                <ul className="detail-panel__reasons">
                  {result.errors.map((err, i) => (
                    <li key={i} className="preflight-error">{err}</li>
                  ))}
                </ul>
              </div>
            )}
          </>
        )}

        {canStart && (
          <div className="detail-panel__section preflight-advertencia">
            <div className="detail-panel__section-title preflight-advertencia-titulo">
              Advertencia de seguridad
            </div>
            <ul className="preflight-lista">
              <li>Esta acción ejecutará Uploadrr y puede publicar/subir contenido a eMuwarez.</li>
              <li>No se crearán peticiones eMuwarez automáticamente.</li>
              <li>No se modificará el archivo original.</li>
              <li>No se modificará el título interno MKV.</li>
            </ul>
            <div className="preflight-confirmar">
              <label className="preflight-confirmar-texto">
                Escribe <strong>{CONFIRMATION_TOKEN}</strong> para habilitar la subida:
              </label>
              <input
                type="text"
                value={confirmInput}
                onChange={e => setConfirmInput(e.target.value)}
                placeholder={CONFIRMATION_TOKEN}
                className={`preflight-token${confirmInput === CONFIRMATION_TOKEN ? ' preflight-token-ok' : ''}`}
              />
            </div>
          </div>
        )}

        {startResult && (
          <div className="detail-panel__section preflight-resultado">
            <div className="detail-panel__section-title">Resultado</div>
            <p className="preflight-res-linea">
              <strong>Acción:</strong> {startResult.action} &nbsp;
              <strong>Estado:</strong> {startResult.status}
            </p>
            {startResult.message && <p className="preflight-res-mensaje">{startResult.message}</p>}
          </div>
        )}
        {startError && <p className="error-text preflight-error-inicio">{startError}</p>}

        <div className="detail-panel__section preflight-seguro">
          Preflight seguro. {canStart ? 'Usa dry-run para previsualizar o confirma para iniciar la subida real.' : 'No se ha ejecutado Uploadrr.'}
        </div>
      </div>
      <div className="detail-panel__actions preflight-acciones">
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
    </Modal>
  )
}
