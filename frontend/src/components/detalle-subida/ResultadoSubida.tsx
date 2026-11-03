import type { UploadJob } from '../../types/api'
import type { SeedingEstado } from '../../hooks/useSeeding'
import { estadoVisible } from '../../utils/estadoDeSubida'
import { opcionesDeReintento } from '../../utils/pasosSubida'
import { formatDateTimeSeconds } from '../../utils/format'
import { formatElapsed } from '../../utils/uploadStatus'
import { InfoIcon } from '../InfoIcon'
import { PeticionDeSubida } from '../PeticionDeSubida'
import { RellenarPeticion } from '../RellenarPeticion'
import { ExternalIdLink } from '../ExternalIdLink'
import { ServiceLabel } from '../ServiceIcon'
import {
  ValueChip, UploadButtonIcon, LibraryButtonIcon, ExternalLinkButtonIcon, RetryButtonIcon, CancelButtonIcon,
  DeleteButtonIcon, LogsValueIcon,
} from '../DetailCard'

export type Consulta = 'nomenclatura' | 'remux' | 'checks' | 'registro'

const AYUDA_NOMENCLATURA = 'Los campos que componen el nombre final del torrent, del archivo y de su título interno.'
const AYUDA_PISTAS = 'Antes de subir se hace un remux para reordenar las pistas de audio y subtítulos y ponerles el nombre adecuado, siguiendo la prioridad de idioma: Español (Castellano) → Català → Inglés → el resto.'
const AYUDA_VERIFICACION = 'Las comprobaciones que se hacen antes de subir: que el archivo se pueda renombrar o enlazar, que el directorio de salida sea escribible, y que qBittorrent, el repositorio de imágenes y eMuwarez estén disponibles. Si alguna falla (no las que se omiten), la subida no continúa.'

function Dato({ etiqueta, ayuda, children }: { etiqueta: string; ayuda?: string; children: React.ReactNode }) {
  return (
    <div className="dsub-dato">
      <dt>{etiqueta}{ayuda && <InfoIcon text={ayuda} />}</dt>
      <dd>{children}</dd>
    </div>
  )
}

function Espera() {
  return <span className="spinner dsub-spinner-14" />
}

// Lo primero del detalle de una subida: cómo acabó (o cómo va), por qué, los datos clave y qué se puede hacer.
// Las acciones y las consultas viven aquí; el resto de la página es el detalle de lo que pasó.
export function ResultadoSubida({ job, seeding, retryError, onStart, onRetry, onCancel, onDelete, onOpenLibraryItem, onConsulta }: {
  job: UploadJob
  seeding: SeedingEstado
  retryError?: string | null
  onStart: (job: UploadJob) => void
  onRetry: (job: UploadJob, desdeElPrincipio?: boolean) => void
  onCancel: (jobId: number) => void
  onDelete: (job: UploadJob) => void
  onOpenLibraryItem?: (id: number) => void
  onConsulta: (c: Consulta) => void
}) {
  const jobId = job.id!
  const estado = estadoVisible(job, seeding.datos)
  const enMarcha = ['running', 'preparing'].includes(job.status)
  const preparando = job.status === 'staging'
  const puedeCancelar = job.status === 'running' || job.status === 'queued' || preparando
  const puedeBorrar = job.status === 'failed' || job.status === 'cancelled'
  const checksListos = job.checks_snapshot?.ready
  const checksFallan = job.checks_snapshot != null && checksListos === false
  const etiquetaChecks = !job.checks_snapshot ? 'Pendiente' : checksListos ? 'OK' : 'Error'
  const terminada = ['completed', 'failed', 'cancelled'].includes(job.status)
  const globalPct = job.progress?.global_pct ?? 0
  const reintentos = job.retry_count ?? 0

  return (
    <section className={`detail-card dsub-resultado dsub-tono-${estado.tono}`} aria-label="Resultado de la subida">
      {retryError && <div className="dsub-error-reintento" role="alert">{retryError}</div>}

      {/* El estado se anuncia solo cuando cambia (un aviso del servidor lo pasa de «Subiendo» a «Completado»). */}
      <div className="dsub-estado">
        <span className="dsub-estado-simbolo" aria-hidden="true">{estado.simbolo}</span>
        <div className="dsub-estado-texto">
          <div role="status" aria-live="polite" aria-atomic="true">
            <p className="dsub-estado-titulo">
              {estado.titulo}
              {estado.seeding && <span className={`${estado.seeding.clase} dsub-estado-seeding`}>{estado.seeding.texto}</span>}
            </p>
            {estado.resumen && <p className="dsub-estado-resumen">{estado.resumen}</p>}
            {estado.motivo && <p className="dsub-estado-motivo">{estado.motivo}</p>}
          </div>
          {estado.transcurrido && <p className="dsub-estado-resumen">{estado.transcurrido}</p>}
        </div>
      </div>
      {enMarcha && (
        <div className="dsub-progreso dsub-progreso-global" role="img" aria-label={`Progreso global: ${globalPct} %`}>
          <span className="dsub-progreso-pct dsub-progreso-pct-negrita">{globalPct}%</span>
          <div className="sync-chip-bar dsub-barra">
            <div className="sync-chip-bar-fill" style={{ transform: `scaleX(${globalPct / 100})` }} />
          </div>
        </div>
      )}

      <div className="dsub-acciones">
        {job.status === 'ready' && (
          <button className="btn btn-primary btn-sm" onClick={() => onStart(job)}><UploadButtonIcon /> Iniciar subida</button>
        )}
        {['failed', 'cancelled'].includes(job.status) && opcionesDeReintento(job).map((o, i) => (
          <button key={o.etiqueta} className={`btn ${i === 0 ? 'btn-primary' : 'btn-secondary'} btn-sm`}
            onClick={() => onRetry(job, o.desdeElPrincipio)}
            title={o.desdeElPrincipio && i > 0
              ? 'Vuelve a preparar los ficheros y a empezar Uploadrr, en vez de reutilizar lo que ya estaba hecho'
              : o.ayuda}>
            <RetryButtonIcon /> {o.etiqueta}
          </button>
        ))}
        {job.result_url && (
          <a className="btn btn-primary btn-sm dsub-sin-subrayado" href={job.result_url} target="_blank" rel="noreferrer">
            <ExternalLinkButtonIcon /> Ver en eMuwarez
          </a>
        )}
        <RellenarPeticion job={job} />
        {job.library_item_id != null && (
          <button className="btn btn-secondary btn-sm" onClick={() => onOpenLibraryItem?.(job.library_item_id!)}><LibraryButtonIcon /> Ver en Biblioteca</button>
        )}
        <button className="btn btn-secondary btn-sm" onClick={() => onConsulta('registro')}><LogsValueIcon /> Ver registro</button>
        {puedeCancelar && <button className="btn btn-danger btn-sm" onClick={() => onCancel(jobId)}><CancelButtonIcon /> Cancelar</button>}
        {puedeBorrar && <button className="btn btn-danger btn-sm" onClick={() => onDelete(job)}><DeleteButtonIcon /> Borrar</button>}
      </div>

      <dl className="dsub-datos">
        {terminada && job.finished_at && (
          <Dato etiqueta={job.status === 'completed' ? 'Terminado' : job.status === 'failed' ? 'Falló' : 'Cancelada'}>
            {formatDateTimeSeconds(job.finished_at)}
          </Dato>
        )}
        <Dato etiqueta="Duración">{formatElapsed(job)}</Dato>
        <Dato etiqueta="Creada">{formatDateTimeSeconds(job.created_at ?? null)}</Dato>
        <Dato etiqueta="Origen">
          {job.instance_type
            ? <ValueChip><ServiceLabel type={job.instance_type} label={job.instance_name ?? job.instance_type} size={15} /></ValueChip>
            : '—'}
        </Dato>
        <Dato etiqueta="Petición"><PeticionDeSubida job={job} /></Dato>
        {job.result_url && (
          <Dato etiqueta="Torrent" ayuda="La ficha del torrent en eMuwarez, con su número.">
            <ValueChip linkable>
              <ExternalIdLink id={job.result_torrent_id ? `#${job.result_torrent_id}` : 'Ver torrent'} href={job.result_url} label="eMuwarez" />
            </ValueChip>
          </Dato>
        )}
        {reintentos > 0 && <Dato etiqueta="Reintentos">x{reintentos}</Dato>}
        <Dato etiqueta="Nomenclatura" ayuda={AYUDA_NOMENCLATURA}>
          <ValueChip as="button" linkable onClick={() => onConsulta('nomenclatura')} title="Ver nomenclatura">
            {preparando && job.stage === 'nomenclature' && <Espera />}
            <span className="txt">{job.nomenclature_snapshot ? 'Ver' : 'Pendiente'}</span>
          </ValueChip>
        </Dato>
        <Dato etiqueta="Pistas" ayuda={AYUDA_PISTAS}>
          <ValueChip as="button" linkable onClick={() => onConsulta('remux')} title="Ver reordenación de pistas">
            {preparando && job.stage === 'remux' && <Espera />}
            <span className="txt">
              {job.remux_snapshot?.omitida ? `Omitidas (${job.remux_snapshot.omitida})` : job.remux_snapshot ? 'Ver' : 'Pendiente'}
            </span>
          </ValueChip>
        </Dato>
        <Dato etiqueta="Verificación" ayuda={AYUDA_VERIFICACION}>
          <ValueChip as="button" linkable onClick={() => onConsulta('checks')} title="Ver verificación pre-subida">
            {preparando && job.stage === 'checks' && <Espera />}
            <span className={checksFallan ? 'txt dsub-dato-alerta' : 'txt'}>{etiquetaChecks}</span>
          </ValueChip>
        </Dato>
      </dl>
    </section>
  )
}
