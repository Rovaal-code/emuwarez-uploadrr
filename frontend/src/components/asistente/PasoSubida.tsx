// Paso Resumen de un solo elemento: lo que se sube, las comprobaciones previas y
// el botón que encola la subida.
import { useTooltip } from '../Tooltip'
import { CHECK_STEP_ORDER, CHECK_STEP_ORDER_SEASON, CHECK_STEP_PENDING_LABEL } from './constantes'
import { CheckRow } from './piezas'
import { ResumenSubida } from './ResumenSubida'
import type { Asistente } from './useAsistente'

export function PasoSubida({ a }: { a: Asistente }) {
  const {
    item, targetIsSeason, checks, checksLoading, checksError, liveChecks, runChecks,
    uploadMsg, uploading, canUpload, recalculandoIdioma, setStep, doUpload,
  } = a
  const uploadBtnTip = useTooltip(canUpload ? null : 'Alguna comprobación ha fallado o aún está en curso')
  return (
    <div className="modal-body">
      <ResumenSubida a={a} />

      {/* Pre-upload checks card */}
      <div className="detail-card asist-tarjeta asist-mt-14">
        <div className="asist-fila-titulo">
          <div className="asist-etiqueta">Comprobaciones previas</div>
          {checksLoading && <span className="spinner asist-spinner-14" />}
        </div>
        {checksLoading ? (
          // Progressive reveal: one line naming whichever check is
          // currently running ("Comprobando si es accesible…"),
          // replacing itself as each one finishes and the next starts —
          // instead of a silent wait (the full run is real network
          // calls, ~30s). liveChecks only holds COMPLETED checks, so
          // its length is the index of the one in flight right now.
          <div className="asist-t12 text-muted">
            {CHECK_STEP_PENDING_LABEL[(targetIsSeason ? CHECK_STEP_ORDER_SEASON : CHECK_STEP_ORDER)[liveChecks.length]] ?? 'Finalizando comprobaciones…'}
          </div>
        ) : (
          checks?.checks.map(c => <CheckRow key={c.id} c={c} />)
        )}
        {/* La región existe siempre: así el lector anuncia el veredicto cuando llega, a los ~30 s. */}
        <div role="status">
          {!checksLoading && checks && (
            <div className={checks.ready ? 'asist-mt-14 asist-negrita asist-ok' : 'asist-mt-14 asist-negrita asist-error'}>
              {checks.ready ? '✓ Todo listo para subir' : '✗ La subida no se puede realizar'}
            </div>
          )}
          {!checksLoading && checksError && (
            <div className="asist-mt-14 asist-negrita asist-error">
              {`✗ No se pudieron completar las comprobaciones: ${checksError}`}
            </div>
          )}
        </div>
        {!checksLoading && (
          <button className="btn btn-secondary btn-sm asist-mt-12 asist-t12" onClick={runChecks} type="button">
            ↻ Volver a comprobar
          </button>
        )}
      </div>

      {checks?.ready && (
        <p className="asist-mt-12 asist-t13">
          ¿Seguro que quieres subir <strong>«{item.title}»</strong> a eMuwarez? Se iniciará la subida real.
        </p>
      )}
      {uploadMsg && (
        <p className={uploadMsg.startsWith('✗') ? 'asist-msg-subida asist-msg-fallo' : 'asist-msg-subida'}>{uploadMsg}</p>
      )}

      <div className="asist-pie">
        <button className="btn btn-secondary" onClick={() => setStep(1)} disabled={uploading}>← Volver</button>
        <button
          className="btn btn-primary"
          onClick={doUpload}
          disabled={!canUpload || uploading || checksLoading || recalculandoIdioma}
          {...uploadBtnTip.triggerProps}
        >
          {uploading ? 'Subiendo…' : 'Subir a eMuwarez'}
          {uploadBtnTip.tooltipNode}
        </button>
      </div>
    </div>
  )
}
