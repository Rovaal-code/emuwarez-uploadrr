import { useState } from 'react'
import { createPortal } from 'react-dom'
import type { UploadJob } from '../types/api'
import { copiarTexto } from '../utils/portapapeles'
import { ExternalLinkButtonIcon } from './DetailCard'
import { Modal } from './Modal'
import { useTooltip } from './Tooltip'

// Tras subir algo que cubría una petición: copia la URL del torrent y abre la petición de eMuwarez, para pulsar
// «Fill» y pegarla. eMuwarez no tiene API para rellenarla desde aquí. Si el navegador no deja copiar, se enseña la
// URL para copiarla a mano.
export function RellenarPeticion({ job }: { job: UploadJob }) {
  const [copiada, setCopiada] = useState(false)
  const [aMano, setAMano] = useState(false)
  const { triggerProps, tooltipNode } = useTooltip('Copia la URL del torrent y abre la petición para pegarla en «Fill»')
  const torrent = job.result_url
  const peticion = job.request_url
  if (job.status !== 'completed' || !torrent || !peticion) return null

  const rellenar = async () => {
    const ok = await copiarTexto(torrent)
    setCopiada(ok)
    setAMano(!ok)
    const ventana = window.open(peticion, '_blank')
    if (ventana) ventana.opener = null
  }

  return (
    <>
      <button type="button" className="btn btn-primary btn-sm" onClick={rellenar} {...triggerProps}>
        <ExternalLinkButtonIcon /> {copiada ? 'URL copiada' : 'Rellenar petición'}
        {tooltipNode}
      </button>
      {/* En el body: dentro de la celda fija de acciones, el modal quedaría atrapado bajo la columna. */}
      {aMano && createPortal(<CopiarAMano url={torrent} peticion={peticion} onClose={() => setAMano(false)} />, document.body)}
    </>
  )
}

function CopiarAMano({ url, peticion, onClose }: { url: string; peticion: string; onClose: () => void }) {
  const [copiada, setCopiada] = useState(false)
  return (
    <Modal titulo="Copia la URL del torrent" onClose={onClose} className="modal-estrecho">
      <div className="modal-body">
        <p className="rellenar-texto">
          El navegador no me deja copiarla solo (suele pasar al abrir la app por http). Cópiala a mano y pégala en la
          petición, con «Fill».
        </p>
        <input
          className="rellenar-url"
          readOnly
          autoFocus
          value={url}
          aria-label="URL del torrent"
          onFocus={e => e.currentTarget.select()}
        />
        <div className="modal-actions">
          <button type="button" className="btn btn-primary btn-sm" onClick={async () => setCopiada(await copiarTexto(url))}>
            {copiada ? 'Copiada' : 'Copiar'}
          </button>
          <a className="btn btn-secondary btn-sm" href={peticion} target="_blank" rel="noreferrer">Abrir la petición</a>
        </div>
      </div>
    </Modal>
  )
}
