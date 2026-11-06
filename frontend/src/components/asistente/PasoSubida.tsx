// Paso Resumen de un solo elemento: lo que se sube, las comprobaciones previas y
// el botón que encola la subida.
import { useTooltip } from '../Tooltip'
import { CHECK_STEP_ORDER, CHECK_STEP_ORDER_SEASON, CHECK_STEP_PENDING_LABEL } from './constantes'
import { CheckRow, MarcoPaso } from './piezas'
import { ResumenSubida } from './ResumenSubida'
import type { Asistente } from './useAsistente'

export function PasoSubida({ a }: { a: Asistente }) {
  const {
    item, targetIsSeason, checks, checksLoading, checksError, liveChecks, runChecks,
    uploadMsg, uploading, canUpload, recalculandoIdioma, setStep, doUpload,
  } = a
  // Lo que dice el pie: el fallo al encolar, si lo hubo; si no, lo que dijeron las comprobaciones.
  const veredicto = uploadMsg
    ? { texto: uploadMsg, clase: uploadMsg.startsWith('✗') ? 'asist-error' : 'asist-ok' }
    : !checksLoading && checksError
    ? { texto: `✗ No se pudieron completar las comprobaciones: ${checksError}`, clase: 'asist-error' }
    : !checksLoading && checks
    ? checks.ready
      ? { texto: '✓ Todo listo para subir', clase: 'asist-ok' }
      : { texto: '✗ La subida no se puede realizar', clase: 'asist-error' }
    : { texto: '', clase: '' }
  const uploadBtnTip = useTooltip(canUpload ? null : 'Alguna comprobación ha fallado o aún está en curso')
  return (
    <MarcoPaso
      pie={<>
        <button className="btn btn-secondary" onClick={() => setStep(1)} disabled={uploading}>← Volver</button>
        {/* El veredicto va en el pie, junto al botón que lo obedece: así se ve sin bajar por la lista. La región
            existe siempre, para que el lector lo anuncie cuando llega (a los ~30 s). */}
        <div role="status" className={`asist-pie-estado ${veredicto.clase}`}>{veredicto.texto}</div>
        <button
          className="btn btn-primary"
          onClick={doUpload}
          disabled={!canUpload || uploading || checksLoading || recalculandoIdioma}
          {...uploadBtnTip.triggerProps}
        >
          {uploading ? 'Subiendo…' : 'Subir a eMuwarez'}
          {uploadBtnTip.tooltipNode}
        </button>
      </>}
    >
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

    </MarcoPaso>
  )
}
