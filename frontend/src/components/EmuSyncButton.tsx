import { useState, useRef, useEffect } from 'react'
import { useSync } from '../context/SyncContext'
import { Tooltip } from './Tooltip'

// eMuwarez catalog sync button with a two-mode dropdown:
//  · "Solo nuevos" (incremental) — fast, only torrents uploaded since last time.
//  · "Completo" (full) — re-downloads everything and reconciles torrents that
//    were deleted on the tracker (the incremental pass can't detect deletions).
// Backed by the global SyncContext, so it stays disabled while a sync runs on
// any tab. Used in the Dashboard and the Biblioteca header.
export function EmuSyncButton({ label = 'Sincronizar eMuwarez' }: { label?: string }) {
  const { catalogSyncing, catalogStatus, startCatalogSync } = useSync()
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  const wait = catalogStatus && !catalogStatus.can_sync ? Math.ceil(catalogStatus.wait_seconds / 60) : 0
  const disabled = catalogSyncing || wait > 0

  useEffect(() => {
    if (!open) return
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onDoc)
    return () => document.removeEventListener('mousedown', onDoc)
  }, [open])

  const pick = (mode: 'incremental' | 'full') => { setOpen(false); startCatalogSync(mode) }

  return (
    <div ref={ref} style={{ position: 'relative', display: 'inline-flex' }}>
      <Tooltip content={wait
        ? `Disponible en ${wait} min`
        : 'Sincroniza el catálogo de eMuwarez para comparar con tu biblioteca (elige rápido o completo).'}>
        <button className="btn btn-primary btn-sm" onClick={() => setOpen(o => !o)} disabled={disabled}>
          {catalogSyncing
            ? <><span className="spinner" style={{ width: 12, height: 12, borderWidth: 2 }} /> Comparando…</>
            : wait
              ? `↻ ${label} (${wait} min)`
              : <>↻ {label} <span style={{ fontSize: 10, opacity: 0.8 }}>▾</span></>}
        </button>
      </Tooltip>

      {open && !disabled && (
        <div style={{
          position: 'absolute', top: '100%', left: 0, marginTop: 4, zIndex: 200,
          background: 'var(--bg-surface, #0f1420)', border: '1px solid var(--border)',
          borderRadius: 8, boxShadow: 'var(--shadow-modal, 0 10px 30px rgba(0,0,0,0.45))',
          minWidth: 260, overflow: 'hidden',
        }}>
          <MenuItem
            onClick={() => pick('incremental')}
            title="↻ Solo nuevos"
            sub="Rápido · trae los torrents subidos desde la última vez"
          />
          <MenuItem
            onClick={() => pick('full')}
            title="⇅ Completo"
            sub="Lento · re-descarga todo y quita los borrados del tracker"
            border
          />
        </div>
      )}
    </div>
  )
}

function MenuItem({ onClick, title, sub, border }: {
  onClick: () => void; title: string; sub: string; border?: boolean
}) {
  const [hover, setHover] = useState(false)
  return (
    <button
      type="button"
      onClick={onClick}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        display: 'block', width: '100%', textAlign: 'left', padding: '9px 12px',
        background: hover ? 'var(--bg-hover, rgba(255,255,255,0.05))' : 'transparent',
        border: 'none', borderTop: border ? '1px solid var(--border)' : 'none',
        cursor: 'pointer', color: 'var(--text-primary)',
      }}
    >
      <div style={{ fontSize: 13, fontWeight: 600 }}>{title}</div>
      <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>{sub}</div>
    </button>
  )
}
