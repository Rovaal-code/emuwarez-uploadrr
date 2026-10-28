import { useState, useRef, useEffect, useLayoutEffect } from 'react'
import { createPortal } from 'react-dom'
import { useTooltip } from './Tooltip'
import { medir, anchoVentana, altoVentana } from '../utils/uiScale'

export interface FilterOption { value: string; label: string }

// Its own component (not inlined in the .map() below) so useTooltip's hook
// call is legal — the option list is a plain callback invoked once per row,
// not a separate component instance.
function FilterOptionButton({ option, selected, multiple, onClick }: { option: FilterOption; selected: boolean; multiple: boolean; onClick: () => void }) {
  const { triggerProps, tooltipNode } = useTooltip(option.label)
  return (
    <button
      type="button"
      className={`hf-option${selected ? ' selected' : ''}`}
      onClick={onClick}
      {...(multiple ? { role: 'menuitemcheckbox', 'aria-checked': selected } : {})}
      {...triggerProps}
    >
      {multiple && <span aria-hidden style={{ display: 'inline-block', width: 14 }}>{selected ? '✓' : ''}</span>}
      {option.label}
      {tooltipNode}
    </button>
  )
}

// Excel-style column-header filter: the column title with a small dropdown
// caret; clicking opens a menu of options. When a filter is active the title
// (and caret) turn blue so it's obvious a filter is applied.
//
// Con `value` como lista es de selección múltiple: cada opción se marca o
// desmarca sin cerrar el menú, y la de valor '' («Todos») las quita todas.
export function HeaderFilter<T extends string | string[]>({ label, value, options, onChange }: {
  label: string
  value: T
  options: FilterOption[]
  onChange: (v: T) => void
}) {
  const [open, setOpen] = useState(false)
  const [pos, setPos] = useState({ top: 0, left: 0 })
  const btnRef = useRef<HTMLButtonElement>(null)
  const menuRef = useRef<HTMLDivElement>(null)
  const multiple = Array.isArray(value)
  const elegidos: string[] = Array.isArray(value) ? value : value ? [value] : []
  const active = elegidos.length > 0
  const accent = '#3b82f6'
  const { triggerProps: caretTip, tooltipNode: caretTooltip } = useTooltip(
    active ? `Filtrado: ${elegidos.map(v => options.find(o => o.value === v)?.label ?? v).join(', ')}` : 'Filtrar',
  )
  const elegir = (v: string) => {
    if (!multiple) {
      onChange(v as T)
      setOpen(false)
      return
    }
    onChange((v === '' ? [] : elegidos.includes(v) ? elegidos.filter(x => x !== v) : [...elegidos, v]) as T)
  }

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
    // medir() y no getBoundingClientRect(): lo que sale de aquí acaba en un
    // style.top/left, que el zoom del body vuelve a escalar. Ver utils/uiScale.
    const r = btnRef.current ? medir(btnRef.current) : null
    if (r) setPos({ top: r.bottom + 4, left: r.left })
    setOpen(o => !o)
  }

  // Longer option labels (provider names, eMuwarez authors/sources — all
  // unbounded strings from the backend) could otherwise push the menu past
  // the right/bottom edge of the viewport, since it's positioned from the
  // button alone with no clamping. Re-clamp once the menu has real
  // dimensions to measure (before paint, so there's no visible jump).
  useLayoutEffect(() => {
    if (!open) return
    const menu = menuRef.current
    const btn = btnRef.current
    if (!menu || !btn) return
    const menuRect = medir(menu)
    const btnRect = medir(btn)
    const maxLeft = anchoVentana() - menuRect.width - 8
    const maxTop = altoVentana() - menuRect.height - 8
    setPos({
      left: Math.max(8, Math.min(btnRect.left, maxLeft)),
      top: Math.max(8, Math.min(btnRect.bottom + 4, maxTop)),
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 3, color: active ? accent : undefined }}>
      {label}
      <button
        ref={btnRef}
        type="button"
        onClick={e => { e.stopPropagation(); toggle() }}
        aria-label={`Filtrar ${label}`}
        style={{
          display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
          width: 16, height: 16, padding: 0, cursor: 'pointer', lineHeight: 1,
          border: 'none', background: 'transparent',
          color: active ? accent : 'var(--text-muted)', fontSize: 10,
        }}
        {...caretTip}
      >
        ▼
        {caretTooltip}
      </button>

      {open && createPortal(
        <div
          ref={menuRef}
          onClick={e => e.stopPropagation()}
          style={{
            position: 'fixed', top: pos.top, left: pos.left, zIndex: 2000,
            minWidth: 170, maxWidth: 'min(340px, calc(var(--vw100) - 16px))',
            maxHeight: 300, overflowY: 'auto', padding: 4,
            background: 'var(--bg-surface, #0f1420)', border: '1px solid var(--border)',
            borderRadius: 8, boxShadow: 'var(--shadow-modal, 0 10px 30px rgba(0,0,0,0.45))',
          }}
        >
          {options.map(o => (
            <FilterOptionButton
              key={o.value || '__all__'}
              option={o}
              selected={o.value === '' ? !active : elegidos.includes(o.value)}
              multiple={multiple && o.value !== ''}
              onClick={() => elegir(o.value)}
            />
          ))}
        </div>,
        document.body,
      )}
    </span>
  )
}
