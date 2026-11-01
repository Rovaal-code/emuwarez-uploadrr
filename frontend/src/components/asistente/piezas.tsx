// Piezas pequeñas que comparten los pasos del asistente.
import type { SourceComparison } from '../../api/nomenclature'
import type { UploadCheck } from '../../api/uploads'
import type { UploadJob } from '../../types/api'
import { statusLabel } from '../../utils/uploadStatus'
import { CheckStatusIcon } from '../DetailCard'
import { InfoIcon } from '../InfoIcon'
import { Tooltip } from '../Tooltip'
import { FIELD_INFO, labelStyle } from './constantes'

// Shown in place of a table whose data isn't loaded yet, so a slow fetch (e.g.
// mkvmerge/MediaInfo reading a real file over a remote mount) never looks like
// the UI has frozen — always show a spinner instead of a blank area.
export function TableLoadingSpinner({ label = 'Cargando…' }: { label?: string }) {
  return (
    <div style={{ padding: '28px 0', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10 }}>
      <span className="spinner" style={{ width: 24, height: 24, borderWidth: 3 }} />
      <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>{label}</span>
    </div>
  )
}

// One check's icon + label + message — used for the final full list once the
// run is done.
export function CheckRow({ c }: { c: UploadCheck }) {
  return (
    <div style={{ display: 'flex', gap: 8, alignItems: 'flex-start', padding: '3px 0' }}>
      <span style={{ marginTop: 2 }}><CheckStatusIcon status={c.status} /></span>
      <div style={{ minWidth: 0 }}>
        <div style={{ fontSize: 13 }}>{c.label}</div>
        {c.message && <div style={{ fontSize: 11, color: 'var(--text-muted)', wordBreak: 'break-all', marginTop: 2, marginBottom: 4 }}>{c.message}</div>}
      </div>
    </div>
  )
}

// Field label + an info "?" explaining where the field's data comes from.
export function FieldLabel({ label, info }: { label: string; info?: React.ReactNode }) {
  return (
    <span style={{ ...labelStyle, display: 'inline-flex', alignItems: 'center', gap: 5 }}>
      {label}{info && <InfoIcon text={info} />}
    </span>
  )
}

// Placeholder shown while the torrent name / ficha title is still being
// generated (the preview arrives a moment after opening), so the box is never
// empty first.
export function GeneratingHint() {
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, color: 'var(--text-muted)', fontSize: 13, padding: '2px 0' }}>
      <span className="spinner" style={{ width: 12, height: 12, borderWidth: 2 }} /> Generando…
    </span>
  )
}

// El botón junto a Source que abre la comparación del source (nombre,
// Radarr/Sonarr y MediaInfo). Parpadea cuando no coinciden. En un pack la
// comparación es la del capítulo representativo.
export function BotonComparacionSource({ comparison, representativo, onClick }: {
  comparison: SourceComparison
  representativo?: boolean
  onClick: () => void
}) {
  const deQuien = representativo ? ' (capítulo representativo)' : ''
  return (
    <Tooltip content={comparison.agree
      ? `Nombre, Radarr/Sonarr y MediaInfo coinciden en el source${deQuien}. Clic para ver el detalle.`
      : `El source no coincide entre el nombre del archivo, Radarr/Sonarr y MediaInfo${deQuien}. Clic para comparar.`}>
      <button
        type="button"
        onClick={onClick}
        style={{
          display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
          width: 34, height: 34, background: 'none', border: 'none', cursor: 'pointer',
          padding: 0, flexShrink: 0,
        }}
      >
        <span
          className={comparison.agree ? undefined : 'badge-blink'}
          style={{ display: 'inline-flex', color: comparison.agree ? 'var(--text-accent)' : 'var(--color-req-pending)' }}
        >
          <svg aria-hidden="true" width="34" height="34" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <rect x="2" y="5" width="20" height="14" rx="4" />
            <path d="M10 9.3v5.4l5-2.7z" fill="currentColor" stroke="none" />
          </svg>
        </span>
      </button>
    </Tooltip>
  )
}

// "Ya existe una subida" — shown at the top of step 1 once the target
// resolves. Never blocks continuing unless the existing job is still
// active (queued/staging/preparing/running); a terminal one (Completado/
// Fallido/Cancelado) just informs — the new job chains onto it either way
// (services/upload_queue.py's _find_latest_job_for_item).
export function AvisoSubidaExistente({ job, bloquea }: { job: UploadJob | null; bloquea: boolean }) {
  if (!job) return null
  return (
    <div style={{
      marginBottom: 14, padding: '10px 14px', borderRadius: 8, fontSize: 12.5, display: 'flex',
      alignItems: 'center', gap: 10, flexWrap: 'wrap',
      background: bloquea ? 'color-mix(in srgb, var(--color-error-soft) 10%, transparent)' : 'color-mix(in srgb, var(--text-accent) 10%, transparent)',
      border: `1px solid ${bloquea ? 'color-mix(in srgb, var(--color-error-soft) 30%, transparent)' : 'color-mix(in srgb, var(--text-accent) 30%, transparent)'}`,
    }}>
      <span>
        {bloquea
          ? `Ya hay una subida en curso para este contenido (${statusLabel(job.status)}). Espera a que termine o cancélala antes de continuar.`
          : `Ya existe este contenido (${statusLabel(job.status)}) en Subidas. Si continúas, esta nueva subida se encadenará a su historial.`}
      </span>
    </div>
  )
}

// El desplegable de Tag, igual en un fichero suelto y en un pack.
export function CampoTag({ value, opciones, onChange }: {
  value: string | null | undefined
  opciones: string[]
  onChange: (tag: string) => void
}) {
  return (
    <label><FieldLabel label="Tag" info={FIELD_INFO.tag} />
      <select className="form-input form-select" value={value || ''} onChange={e => onChange(e.target.value)}>
        {opciones.map(t => (
          <option key={t} value={t}>{t}</option>
        ))}
      </select>
    </label>
  )
}
