import { Modal } from './Modal'
import { PasoArchivo } from './asistente/PasoArchivo'
import { PasoSeleccion } from './asistente/PasoSeleccion'
import { PasoSubida } from './asistente/PasoSubida'
import { PasoSubidaTanda } from './asistente/PasoSubidaTanda'
import { PasoTemporada } from './asistente/PasoTemporada'
import { useAsistente, type PropsAsistente } from './asistente/useAsistente'

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
  const clasePaso = (n: number) => (step === n ? 'asist-paso asist-paso-actual' : 'asist-paso')
  return (
    <Modal titulo={item.title} onClose={cerrarModal} className="modal-wide asist-modal-ancho">

      <div className="asist-pasos">
        {needsSelection && <><span className={clasePaso(0)}>0. Selección</span><span className="asist-paso-flecha">→</span></>}
        <span className={clasePaso(1)}>1. Nomenclatura</span>
        <span className="asist-paso-flecha">→</span>
        <span className={clasePaso(2)}>2. Subida a eMuwarez</span>
      </div>

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
