import { useId } from 'react'
import type { UploadJob } from '../../types/api'
import { DESVANECER_MS } from '../../utils/despedidaSubidas'
import { timeAgo } from '../../utils/format'
import {
  STATUS_CLASS, ACTIVE_JOB_STATUSES, statusLabel, phaseLabel, currentPhaseInfo,
  progressCounter, queuedWaitText, formatSecondsHM, useTicker,
} from '../../utils/uploadStatus'
import { EmptyState } from '../EmptyState'
import { IconoSubida } from '../Iconos'
import { HoverTitle } from '../Tooltip'
import { Carril } from './Carril'
import { Cartel } from './Cartel'

// Una fila de «En curso» o de «Recientes»: entera es un enlace al
// detalle de la subida en Subidas. Lleva su propio reloj para que el tiempo corra sin repintar el Panel entero cada segundo.
function FilaSubida({ job, yendose = false, onOpen }: {
  job: UploadJob; yendose?: boolean; onOpen: (jobId: number) => void
}) {
  useTicker(ACTIVE_JOB_STATUSES.has(job.status))
  const isPreparingOrRunning = job.status === 'preparing' || job.status === 'running'
  const phaseInfo = isPreparingOrRunning ? currentPhaseInfo(job) : null
  const phaseLabelText = phaseInfo?.label ?? (isPreparingOrRunning ? phaseLabel(job.progress_phase) : null)
  // Total time since the job started (not just this sub-phase) — the
  // number that actually answers "how long has this been going".
  const totalElapsedText = isPreparingOrRunning ? progressCounter(job) : null
  const terminada = !ACTIVE_JOB_STATUSES.has(job.status)
  // El global que ya calcula el backend (uploadrr_progress.PHASES
  // pondera cada fase); se acota por si llega algo raro.
  const globalPct = Math.min(100, Math.max(0, Math.round(job.progress?.global_pct ?? 0)))
  return (
    // Terminada, se queda quieta ESPERA_MS y luego se va poco a
    // poco. Las que se despiden van al final de la lista, así
    // que al desaparecer no mueven de sitio a las de arriba.
    // En línea solo la duración, que es una constante del código.
    <HoverTitle className={`upload-row${yendose ? ' panel-fila-saliendo' : ''}`} tip="Ver detalle de la subida" onClick={() => onOpen(job.id!)}
      style={{ transition: `opacity ${DESVANECER_MS}ms ease-out` }}>
      <Cartel url={job.poster_url} serie={job.media_type === 'series' || job.media_type === 'episode'} />
      <div className="panel-fila-texto">
        <div className="panel-fila-titulo">
          <span className="upload-row-title">{job.title ?? `Job #${job.id}`}</span>
          {(totalElapsedText || terminada) && (
            <span className="panel-fila-tiempo">
              {totalElapsedText ?? timeAgo(job.finished_at ?? job.updated_at)}
            </span>
          )}
        </div>
        <div className="panel-fila-estado">
          <div className="panel-fila-badges">
            <span className={`${STATUS_CLASS[job.status] || 'badge req-unknown'}${isPreparingOrRunning ? ' badge-blink' : ''}`}>{statusLabel(job.status)}</span>
            {job.status === 'queued' && (
              <span className="panel-fila-nota">{queuedWaitText(job)}</span>
            )}
            {isPreparingOrRunning && (
              <span className="panel-fila-fase">
                <span className="panel-fila-fase-texto">{phaseLabelText}</span>
                {phaseInfo?.counterText && <span className="panel-fila-contador">{phaseInfo.counterText}</span>}
                <span className="spinner panel-spinner-10" />
              </span>
            )}
            {terminada && job.duration_seconds != null && (
              <span className="panel-fila-duracion">en {formatSecondsHM(job.duration_seconds)}</span>
            )}
          </div>
          {/* Progreso global, en la misma barra fina que usa el resto
              del Panel, con su porcentaje al lado. Solo mientras trabaja: en
              cola no hay nada que medir todavía, y terminada la barra no dice
              nada que el estado no diga ya. */}
          {isPreparingOrRunning && (
            <div className="panel-fila-progreso">
              <div className="progress-bar panel-fila-barra">
                {/* En línea: el avance es un valor calculado. */}
                <div className="progress-fill" style={{ transform: `scaleX(${globalPct / 100})` }} />
              </div>
              <span className="panel-fila-pct">{globalPct}%</span>
            </div>
          )}
        </div>
      </div>
    </HoverTitle>
  )
}

// «1 subiendo · 2 en cola»; sin nada vivo (solo filas que se despiden), sin nota.
export function notaEnCurso(filas: { job: UploadJob }[]): string | undefined {
  const vivas = filas.filter(f => ACTIVE_JOB_STATUSES.has(f.job.status))
  const enCola = vivas.filter(f => f.job.status === 'queued').length
  const subiendo = vivas.length - enCola
  return [subiendo && `${subiendo} subiendo`, enCola && `${enCola} en cola`].filter(Boolean).join(' · ') || undefined
}

// «En curso»: las subidas vivas con su fase y su progreso y las que acaban de terminar, hasta que se van; debajo,
// «Recientes»: las últimas terminadas (también las fallidas, que además salen en «Necesita atención»).
export function CarrilEnCurso({ filas, recientes, onOpen, onVerTodas }: {
  filas: { job: UploadJob; yendose: boolean }[]
  recientes: UploadJob[]
  onOpen: (jobId: number) => void
  onVerTodas: () => void
}) {
  const idRecientes = useId()
  return (
    <Carril titulo="En curso" nota={notaEnCurso(filas)} tour="dashboard-running">
      {filas.length === 0 && recientes.length === 0 && (
        <EmptyState
          icon={<IconoSubida />}
          title="Sin subidas en curso"
          body="Sube algo de «Listo para subir» o desde Biblioteca y lo verás aquí con su progreso."
        />
      )}
      {filas.length === 0 && recientes.length > 0 && <p className="panel-sin-curso">Sin subidas en curso</p>}
      {filas.map(({ job, yendose }) => <FilaSubida key={job.id} job={job} yendose={yendose} onOpen={onOpen} />)}
      {recientes.length > 0 && (
        <>
          <h3 className="upload-panel-group panel-recientes-titulo" id={idRecientes}>Recientes</h3>
          <ul className="panel-lista" aria-labelledby={idRecientes}>
            {recientes.map(job => <li key={job.id}><FilaSubida job={job} onOpen={onOpen} /></li>)}
          </ul>
        </>
      )}
      <div className="panel-pie">
        <HoverTitle as="span" className="hover-link" onClick={onVerTodas} tip="Abrir Subidas">Ver todas las subidas</HoverTitle>
      </div>
    </Carril>
  )
}
