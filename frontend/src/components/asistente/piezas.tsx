// Piezas pequeñas que comparten los pasos del asistente.
import type { SourceComparison } from '../../api/nomenclature'
import type { UploadCheck } from '../../api/uploads'
import type { UploadJob } from '../../types/api'
import { statusLabel } from '../../utils/uploadStatus'
import { CheckStatusIcon } from '../DetailCard'
import { InfoIcon } from '../InfoIcon'
import { Tooltip } from '../Tooltip'
import { FIELD_INFO } from './constantes'

// El marco de cada paso: el cuerpo hace scroll y el pie (Volver, Continuar, Subir) queda siempre a la vista, a
// cualquier alto de ventana. El pie va fuera del cuerpo, no pegado a él con sticky: así nunca tapa lo que se
// está leyendo.
export function MarcoPaso({ pie, finPie, children }: {
  pie?: React.ReactNode
  // El pie lleva solo acciones a la derecha (paso 0, o el final de una tanda).
  finPie?: boolean
  children: React.ReactNode
}) {
  return (
    <div className="asist-seccion">
      <div className="modal-body asist-cuerpo">{children}</div>
      {pie && <div className={finPie ? 'asist-pie asist-pie-fin' : 'asist-pie'}>{pie}</div>}
    </div>
  )
}

// Shown in place of a table whose data isn't loaded yet, so a slow fetch (e.g.
// mkvmerge/MediaInfo reading a real file over a remote mount) never looks like
// the UI has frozen — always show a spinner instead of a blank area.
export function TableLoadingSpinner({ label = 'Cargando…' }: { label?: string }) {
  return (
    <div className="asist-cargando">
      <span className="spinner asist-spinner-24" />
      <span className="asist-t12 text-muted">{label}</span>
    </div>
  )
}

// One check's icon + label + message — used for the final full list once the
// run is done.
export function CheckRow({ c }: { c: UploadCheck }) {
  return (
    <div className="asist-check">
      <span className="asist-check-icono"><CheckStatusIcon status={c.status} /></span>
      <div className="asist-check-texto">
        <div className="asist-t13">{c.label}</div>
        {c.message && <div className="asist-check-mensaje">{c.message}</div>}
      </div>
    </div>
  )
}

// Field label + an info "?" explaining where the field's data comes from.
export function FieldLabel({ label, info }: { label: string; info?: React.ReactNode }) {
  return (
    <span className="asist-etiqueta asist-fila-info">
      {label}{info && <InfoIcon text={info} />}
    </span>
  )
}

// Placeholder shown while the torrent name / ficha title is still being
// generated (the preview arrives a moment after opening), so the box is never
// empty first.
export function GeneratingHint() {
  return (
    <span className="asist-generando">
      <span className="spinner asist-spinner-12" /> Generando…
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
        aria-label="Comparar el source: nombre del archivo, Radarr/Sonarr y MediaInfo"
        className="asist-boton-source"
      >
        <span
          className={comparison.agree ? 'asist-source-icono asist-source-coincide' : 'asist-source-icono asist-source-difiere badge-blink'}
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
    <div className={bloquea ? 'asist-aviso-existente asist-aviso-bloquea' : 'asist-aviso-existente'}>
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
