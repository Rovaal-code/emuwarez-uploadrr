import { useState } from 'react'
import { useSync } from '../context/SyncContext'
import { Tooltip } from './Tooltip'

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
            ? <><span className="spinner" style={{ width: 12, height: 12, borderWidth: 2 }} /> Comparando…</>
            : `↻ ${label}`}
        </button>
      </Tooltip>

      {open && (
        <div className="modal-overlay" onClick={() => setOpen(false)}>
          <div className="modal-panel" onClick={e => e.stopPropagation()} style={{ maxWidth: 460 }}>
            <div className="modal-header">
              <h2 className="modal-title">Sincronizar eMuwarez</h2>
              <button className="modal-close" onClick={() => setOpen(false)}>✕</button>
            </div>
            <div className="modal-body" style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
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
          </div>
        </div>
      )}
    </>
  )
}

function SyncOption({ icon, title, desc, cadence, wait, blocked: externallyBlocked = false, onClick }: {
  icon: string; title: string; desc: string; cadence: string; wait: number; blocked?: boolean; onClick: () => void
}) {
  const blocked = wait > 0 || externallyBlocked
  const [hover, setHover] = useState(false)
  const lit = hover && !blocked
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={blocked}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        display: 'block', width: '100%', textAlign: 'left', padding: '12px 14px',
        border: `1px solid ${lit ? 'var(--text-accent, #2563eb)' : 'var(--border)'}`,
        borderRadius: 10, cursor: blocked ? 'not-allowed' : 'pointer',
        background: lit ? 'var(--bg-hover, rgba(255,255,255,0.06))' : 'var(--bg-card, transparent)',
        color: 'var(--text-primary)', opacity: blocked ? 0.55 : 1,
        transition: 'background 0.12s, border-color 0.12s',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
        <span style={{ fontSize: 14, fontWeight: 600 }}>{icon} {title}</span>
        <span style={{ fontSize: 11, color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>
          {wait > 0 ? `Disponible en ${fmtWait(wait)}` : blocked ? 'Otra sincronización en curso' : cadence}
        </span>
      </div>
      <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>{desc}</div>
    </button>
  )
}
