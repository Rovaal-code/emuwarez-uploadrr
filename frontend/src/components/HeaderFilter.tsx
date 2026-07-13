import { useState, useRef, useEffect } from 'react'
import { createPortal } from 'react-dom'

export interface FilterOption { value: string; label: string }

// Excel-style column-header filter: the column title with a small dropdown
// caret; clicking opens a menu of options. When a filter is active the title
// (and caret) turn blue so it's obvious a filter is applied.
export function HeaderFilter({ label, value, options, onChange }: {
  label: string
  value: string
  options: FilterOption[]
  onChange: (v: string) => void
}) {
  const [open, setOpen] = useState(false)
  const [pos, setPos] = useState({ top: 0, left: 0 })
  const btnRef = useRef<HTMLButtonElement>(null)
  const menuRef = useRef<HTMLDivElement>(null)
  const active = value !== ''
  const accent = '#3b82f6'

  useEffect(() => {
    if (!open) return
    const onDoc = (e: MouseEvent) => {
      const t = e.target as Node
      if (menuRef.current?.contains(t) || btnRef.current?.contains(t)) return
      setOpen(false)
    }
    const onEsc = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('mousedown', onDoc)
    document.addEventListener('keydown', onEsc)
    return () => {
      document.removeEventListener('mousedown', onDoc)
      document.removeEventListener('keydown', onEsc)
    }
  }, [open])

  const toggle = () => {
    const r = btnRef.current?.getBoundingClientRect()
    if (r) setPos({ top: r.bottom + 4, left: r.left })
    setOpen(o => !o)
  }

  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 3, color: active ? accent : undefined }}>
      {label}
      <button
        ref={btnRef}
        type="button"
        onClick={e => { e.stopPropagation(); toggle() }}
        title={active ? `Filtrado: ${options.find(o => o.value === value)?.label ?? value}` : 'Filtrar'}
        aria-label={`Filtrar ${label}`}
        style={{
          display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
          width: 16, height: 16, padding: 0, cursor: 'pointer', lineHeight: 1,
          border: 'none', background: 'transparent',
          color: active ? accent : 'var(--text-muted)', fontSize: 10,
        }}
      >
        ▼
      </button>

      {open && createPortal(
        <div
          ref={menuRef}
          onClick={e => e.stopPropagation()}
          style={{
            position: 'fixed', top: pos.top, left: pos.left, zIndex: 2000,
            minWidth: 170, maxHeight: 300, overflowY: 'auto', padding: 4,
            background: 'var(--bg-surface, #0f1420)', border: '1px solid var(--border)',
            borderRadius: 8, boxShadow: 'var(--shadow-modal, 0 10px 30px rgba(0,0,0,0.45))',
          }}
        >
          {options.map(o => {
            const sel = o.value === value
            return (
              <button
                key={o.value || '__all__'}
                type="button"
                onClick={() => { onChange(o.value); setOpen(false) }}
                style={{
                  display: 'block', width: '100%', textAlign: 'left', padding: '6px 10px',
                  border: 'none', borderRadius: 6, cursor: 'pointer', fontSize: 12.5,
                  fontWeight: sel ? 600 : 400,
                  background: sel ? 'rgba(59,130,246,0.16)' : 'transparent',
                  color: sel ? accent : 'var(--text-primary)',
                }}
              >
                {o.label}
              </button>
            )
          })}
        </div>,
        document.body,
      )}
    </span>
  )
}
