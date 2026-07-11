import { useEffect, useState } from 'react'
import { getEmuProviders } from '../api/nomenclature'

export interface ProviderOption {
  code: string
  label: string
}

interface ProviderPriorityPickerProps {
  order: string[]
  onChange: (order: string[]) => void
}

// Checkbox (enable/disable) + native HTML5 drag-and-drop reorder — no new
// dependency (frontend has no drag-and-drop library today).
//
// The provider list comes from the same backend source as the upload wizard
// (GET /nomenclature/providers → services/source_assistant.EMU_PROVIDERS,
// already returned sorted), so Crunchyroll and the rest stay in sync and are
// shown alphabetically everywhere.
export function ProviderPriorityPicker({ order, onChange }: ProviderPriorityPickerProps) {
  const [dragIndex, setDragIndex] = useState<number | null>(null)
  const [options, setOptions] = useState<ProviderOption[]>([])

  useEffect(() => {
    getEmuProviders()
      .then(r => setOptions(
        r.providers
          .map(p => ({ code: p.code, label: p.name }))
          .sort((a, b) => a.code.localeCompare(b.code, undefined, { sensitivity: 'base' })),
      ))
      .catch(() => setOptions([]))
  }, [])

  function enable(code: string) {
    if (!order.includes(code)) onChange([...order, code])
  }

  function disable(code: string) {
    onChange(order.filter(c => c !== code))
  }

  function handleDrop(targetIndex: number) {
    if (dragIndex === null || dragIndex === targetIndex) { setDragIndex(null); return }
    const next = [...order]
    const [moved] = next.splice(dragIndex, 1)
    next.splice(targetIndex, 0, moved)
    onChange(next)
    setDragIndex(null)
  }

  const available = options.filter(p => !order.includes(p.code))

  return (
    <div>
      {order.length === 0 && (
        <p style={{ fontSize: 12, color: 'var(--text-muted)', margin: '0 0 8px' }}>
          Ningún provider activado — se añadirán por orden de prioridad.
        </p>
      )}
      {order.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4, marginBottom: 10, maxHeight: 220, overflowY: 'auto' }}>
          {order.map((code, idx) => {
            const opt = options.find(p => p.code === code)
            return (
              <div
                key={code}
                draggable
                onDragStart={() => setDragIndex(idx)}
                onDragOver={e => e.preventDefault()}
                onDrop={() => handleDrop(idx)}
                style={{
                  display: 'flex', alignItems: 'center', gap: 8,
                  padding: '6px 10px', background: 'rgba(255,255,255,0.04)',
                  border: '1px solid var(--border, rgba(255,255,255,0.08))',
                  borderRadius: 6, cursor: 'grab', fontSize: 13,
                }}
              >
                <span style={{ color: 'var(--text-muted)', fontSize: 11, width: 16 }}>{idx + 1}</span>
                <span style={{ color: 'var(--text-muted)' }} aria-hidden>⠿</span>
                <span style={{ flex: 1 }}>
                  {opt?.label ?? code} <span style={{ color: 'var(--text-muted)', fontSize: 11 }}>({code})</span>
                </span>
                <button
                  type="button"
                  onClick={() => disable(code)}
                  title="Quitar"
                  style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', fontSize: 13, padding: '2px 6px' }}
                >
                  ✕
                </button>
              </div>
            )
          })}
        </div>
      )}
      {available.length > 0 && (
        <details>
          <summary style={{ cursor: 'pointer', fontSize: 12, color: 'var(--text-secondary)' }}>
            + Añadir provider ({available.length} disponibles)
          </summary>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(170px, 1fr))', gap: 4, marginTop: 8, maxHeight: 200, overflowY: 'auto' }}>
            {available.map(opt => (
              <label key={opt.code} className="checkbox-label" style={{ fontSize: 12 }}>
                <input type="checkbox" checked={false} onChange={() => enable(opt.code)} /> {opt.label}
              </label>
            ))}
          </div>
        </details>
      )}
    </div>
  )
}
