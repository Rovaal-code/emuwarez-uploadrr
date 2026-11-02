import { useState } from 'react'
import { useSync } from '../context/SyncContext'
import { Tooltip } from './Tooltip'
import { Modal } from './Modal'

function fmtWait(seconds: number): string {
  const m = Math.ceil(seconds / 60)
  if (m < 60) return `${m} min`
  const h = Math.floor(m / 60)
  const rem = m % 60
  return rem ? `${h} h ${rem} min` : `${h} h`
}

// eMuwarez catalog sync. The button opens a centered card with the two sync
// modes and their descriptions:
//  · "Solo nuevos" (incremental, 1/hour) — fast, only torrents uploaded since
//    last time.
//  · "Completo" (full, 1/day) — re-downloads everything and reconciles torrents
//    deleted on the tracker (the incremental pass can't detect deletions).
// Backed by the global SyncContext, so it stays disabled while a sync runs on
// any tab. Used in the Dashboard and the Biblioteca header.
export function EmuSyncButton({ label = 'Sincronizar eMuwarez' }: { label?: string }) {
  const { catalogSyncing, catalogStatus, startCatalogSync, isAnySyncing } = useSync()
  const [open, setOpen] = useState(false)

  const incWait = catalogStatus && !catalogStatus.incremental_can_sync ? catalogStatus.incremental_wait_seconds : 0
  const fullWait = catalogStatus && !catalogStatus.full_can_sync ? catalogStatus.full_wait_seconds : 0

  const pick = (mode: 'incremental' | 'full') => { setOpen(false); startCatalogSync(mode) }

  return (
    <>
      <Tooltip content="Sincroniza el catálogo de eMuwarez para comparar con tu biblioteca (elige rápido o completo).">
        <button className="btn btn-primary btn-sm" onClick={() => setOpen(true)} disabled={isAnySyncing}>
          {catalogSyncing
            ? <><span className="spinner emusync-spinner" /> Comparando…</>
            : `↻ ${label}`}
        </button>
      </Tooltip>

      {open && (
        <Modal titulo="Sincronizar eMuwarez" onClose={() => setOpen(false)} className="emusync-modal">
          <div className="modal-body emusync-cuerpo">
            <SyncOption
              icon="↻"
              title="Solo nuevos"
              desc="Trae solo los torrents subidos a eMuwarez desde la última vez. Rápido."
              cadence="1 vez/hora"
              wait={incWait}
              blocked={isAnySyncing}
              onClick={() => pick('incremental')}
            />
            <SyncOption
              icon="⇅"
              title="Completo"
              desc="Re-descarga todo el catálogo y quita los torrents borrados del tracker. Lento (varios minutos)."
              cadence="1 vez/día"
              wait={fullWait}
              blocked={isAnySyncing}
              onClick={() => pick('full')}
            />
          </div>
        </Modal>
      )}
    </>
  )
}

function SyncOption({ icon, title, desc, cadence, wait, blocked: externallyBlocked = false, onClick }: {
  icon: string; title: string; desc: string; cadence: string; wait: number; blocked?: boolean; onClick: () => void
}) {
  const blocked = wait > 0 || externallyBlocked
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={blocked}
      className="emusync-opcion"
    >
      <div className="emusync-opcion-cabecera">
        <span className="emusync-opcion-titulo">{icon} {title}</span>
        <span className="emusync-opcion-cadencia">
          {wait > 0 ? `Disponible en ${fmtWait(wait)}` : blocked ? 'Otra sincronización en curso' : cadence}
        </span>
      </div>
      <div className="emusync-opcion-desc">{desc}</div>
    </button>
  )
}
