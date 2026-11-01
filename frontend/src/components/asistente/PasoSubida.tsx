// Paso 2 de un solo elemento: el nombre final, las comprobaciones previas y
// el botón que encola la subida.
import { FitText, FitTextPair } from '../FitText'
import { useTooltip } from '../Tooltip'
import { CHECK_STEP_ORDER, CHECK_STEP_ORDER_SEASON, CHECK_STEP_PENDING_LABEL, INTERNAL_TITLE_LABEL, labelStyle } from './constantes'
import { CheckRow } from './piezas'
import type { Asistente } from './useAsistente'

export function PasoSubida({ a }: { a: Asistente }) {
  const {
    item, targetIsSeason, seasonDisplayTitle, preview, checks, checksLoading, liveChecks, runChecks,
    uploadMsg, uploading, canUpload, recalculandoIdioma, setStep, doUpload,
  } = a
  const uploadBtnTip = useTooltip(canUpload ? null : 'Alguna comprobación ha fallado o aún está en curso')
  return (
    <div className="modal-body">
      <div className="detail-card" style={{ marginBottom: 14, padding: '12px 14px', borderRadius: 8 }}>
        {targetIsSeason ? (
          <>
            <div style={labelStyle}>Nombre final del torrent (pack de temporada)</div>
            <FitText min={9} text={seasonDisplayTitle || '—'} />
          </>
        ) : (
          <FitTextPair
            min={9}
            items={[
              { label: 'Nombre final del torrent', text: preview?.torrent_name || '—', labelStyle },
              { label: INTERNAL_TITLE_LABEL, text: preview?.internal_mkv_title || '—', labelStyle },
            ]}
          />
        )}
      </div>

      {/* Pre-upload checks card */}
      <div className="detail-card" style={{ padding: '12px 14px', borderRadius: 8 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
          <div style={labelStyle}>Comprobaciones previas</div>
          {checksLoading && <span className="spinner" style={{ width: 14, height: 14, borderWidth: 2 }} />}
        </div>
        {checksLoading ? (
          // Progressive reveal: one line naming whichever check is
          // currently running ("Comprobando si es accesible…"),
          // replacing itself as each one finishes and the next starts —
          // instead of a silent wait (the full run is real network
          // calls, ~30s). liveChecks only holds COMPLETED checks, so
          // its length is the index of the one in flight right now.
          <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
            {CHECK_STEP_PENDING_LABEL[(targetIsSeason ? CHECK_STEP_ORDER_SEASON : CHECK_STEP_ORDER)[liveChecks.length]] ?? 'Finalizando comprobaciones…'}
          </div>
        ) : (
          checks?.checks.map(c => <CheckRow key={c.id} c={c} />)
        )}
        {!checksLoading && checks && (
          <div style={{ marginTop: 14, fontWeight: 600, color: checks.ready ? 'var(--color-available)' : 'var(--color-error)' }}>
            {checks.ready ? '✓ Todo listo para subir' : '✗ La subida no se puede realizar'}
          </div>
        )}
        {!checksLoading && (
          <button className="btn btn-secondary btn-sm" style={{ marginTop: 12, fontSize: 12 }} onClick={runChecks} type="button">
            ↻ Volver a comprobar
          </button>
        )}
      </div>

      {checks?.ready && (
        <p style={{ marginTop: 12, fontSize: 13 }}>
          ¿Seguro que quieres subir <strong>«{item.title}»</strong> a eMuwarez? Se iniciará la subida real.
        </p>
      )}
      {uploadMsg && (
        <p style={{
          fontSize: 13, marginTop: 8, padding: '8px 12px', borderRadius: 6, fontWeight: 500,
          background: uploadMsg.startsWith('✗') ? 'color-mix(in srgb, var(--color-error) 12%, transparent)' : 'color-mix(in srgb, var(--color-available) 12%, transparent)',
          border: `1px solid ${uploadMsg.startsWith('✗') ? 'color-mix(in srgb, var(--color-error) 35%, transparent)' : 'color-mix(in srgb, var(--color-available) 35%, transparent)'}`,
          color: uploadMsg.startsWith('✗') ? 'var(--color-error-pale)' : 'var(--color-available-pale)',
        }}>{uploadMsg}</p>
      )}

      <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 16 }}>
        <button className="btn btn-secondary" onClick={() => setStep(1)} disabled={uploading}>Volver</button>
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
