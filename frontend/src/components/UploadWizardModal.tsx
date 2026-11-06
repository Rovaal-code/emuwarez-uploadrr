import { useEffect, useRef } from 'react'
import { Modal } from './Modal'
import { PasoArchivo } from './asistente/PasoArchivo'
import { PasoSeleccion } from './asistente/PasoSeleccion'
import { PasoSubida } from './asistente/PasoSubida'
import { PasoSubidaTanda } from './asistente/PasoSubidaTanda'
import { PasoTemporada } from './asistente/PasoTemporada'
import { useAsistente, type PropsAsistente } from './asistente/useAsistente'

// Los pasos que de verdad tiene cada camino: «Contenido» solo existe al abrir una serie o una temporada.
function pasosDelAsistente(needsSelection: boolean): { paso: 0 | 1 | 2; nombre: string }[] {
  return [
    ...(needsSelection ? [{ paso: 0 as const, nombre: 'Contenido' }] : []),
    { paso: 1, nombre: 'Nombre y pistas' },
    { paso: 2, nombre: 'Resumen' },
  ]
}

// Unified "Subir" wizard (replaces the separate Nomenclatura + Campos + Subir
// buttons). For a Series/Season it first asks which season (and episode, or the
// whole season) to target; then Step 1 generates the eMuwarez nomenclature —
// Spanish title + year from Radarr/Sonarr, Source/Provider from the filename,
// the rest from mediainfo — as editable boxes with a live preview of the final
// torrent name; Step 2 runs the pre-upload checks and, once confirmed, QUEUES
// the upload (services/upload_queue.py hace integridad/nomenclatura/remux/arranque
// en el servidor, en el momento o cuando queda libre una plaza de «Subidas en paralelo») y pasa a
// Subidas: aquí ya no se aplica la nomenclatura ni se arranca Uploadrr.
//
// El estado y la lógica están en asistente/useAsistente.ts; cada paso se pinta
// en su propio componente de asistente/.
export function UploadWizardModal(props: PropsAsistente) {
  const a = useAsistente(props)
  const { item, step, needsSelection, targetIsSeason, batchQueue, seasonQueue, episodeQueue } = a
  const { cerrarModal, confirmandoCierre, setConfirmandoCierre, onClose } = a
  const pasos = pasosDelAsistente(needsSelection)
  // El alto fijo del paso 1 es para que no salte al cambiar de pestaña; con solo un error dejaba ~430 px de vacío.
  const altoFijo = step === 1 && !(a.error && !a.loading)
  // Al cambiar de paso el foco pasa al paso nuevo, para que el lector lo anuncie y Tab siga desde arriba.
  const pasoActual = useRef<HTMLLIElement>(null)
  const primerPintado = useRef(true)
  useEffect(() => {
    if (primerPintado.current) { primerPintado.current = false; return }
    pasoActual.current?.focus()
  }, [step])
  return (
    <Modal titulo={item.title} onClose={cerrarModal} className={`modal-wide asist-modal-ancho asist-marco${altoFijo ? ' asist-alto-fijo' : ''}`}>

      <nav aria-label="Pasos de la subida" className="asist-pasos">
        <ol>
          {pasos.map(({ paso, nombre }, i) => {
            const estado = paso < step ? 'hecho' : paso === step ? 'actual' : 'pendiente'
            return (
              <li
                key={paso} className={`asist-paso asist-paso-${estado}`}
                aria-current={estado === 'actual' ? 'step' : undefined}
                ref={estado === 'actual' ? pasoActual : undefined} tabIndex={estado === 'actual' ? -1 : undefined}
              >
                {estado === 'hecho' && <span aria-hidden="true">✓ </span>}{i + 1} · {nombre}
                {estado === 'hecho' && <span className="solo-lector"> (hecho)</span>}
              </li>
            )
          })}
        </ol>
      </nav>

      {step === 0 && <PasoSeleccion a={a} />}
      {step === 1 && targetIsSeason && <PasoTemporada a={a} />}
      {step === 1 && !targetIsSeason && <PasoArchivo a={a} />}
      {step === 2 && batchQueue.length > 1 && <PasoSubidaTanda a={a} />}
      {step === 2 && seasonQueue.length <= 1 && episodeQueue.length <= 1 && <PasoSubida a={a} />}

      {confirmandoCierre && (
        <Modal titulo="¿Descartar los cambios?" onClose={() => setConfirmandoCierre(false)} className="modal-estrecho">
          <div className="modal-body">
            <p className="text-muted">
              Has cambiado datos de la subida y todavía no se ha encolado. Si cierras ahora se perderán los cambios sin guardar; la nomenclatura que ya guardaste al pasar de paso se queda como está.
            </p>
            <div className="modal-actions">
              <button className="btn btn-secondary" type="button" onClick={() => setConfirmandoCierre(false)}>Seguir editando</button>
              <button className="btn btn-danger" type="button" onClick={onClose}>Cerrar y descartar</button>
            </div>
          </div>
        </Modal>
      )}
    </Modal>
  )
}
