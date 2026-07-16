import { useEffect, useState } from 'react'
import { getEmuProviders } from '../api/nomenclature'
import { Favicon } from './Favicon'

export interface ProviderOption {
  code: string
  label: string
  domain?: string | null
}

// The provider's favicon, linking to its official page when the domain is known.
function ProviderIcon({ domain, size = 16 }: { domain?: string | null; size?: number }) {
  const icon = <Favicon domain={domain} size={size} fallback={<span aria-hidden style={{ opacity: 0.4 }}>🎬</span>} />
  if (!domain) return icon
  return (
    <a
      href={`https://${domain}`}
      target="_blank"
      rel="noreferrer"
      title={`Abrir ${domain}`}
      onClick={e => e.stopPropagation()}
      draggable={false}
      style={{ display: 'flex', flexShrink: 0 }}
    >
      {icon}
    </a>
  )
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
  const [showAdd, setShowAdd] = useState(false)

  useEffect(() => {
    getEmuProviders()
      .then(r => setOptions(
        r.providers
          .map(p => ({ code: p.code, label: p.name, domain: p.domain }))
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

  // Live reorder: while dragging, hovering over another row moves the dragged
  // item there immediately, so the list rearranges under the cursor.
  function handleDragEnter(targetIndex: number) {
    if (dragIndex === null || dragIndex === targetIndex) return
    const next = [...order]
    const [moved] = next.splice(dragIndex, 1)
    next.splice(targetIndex, 0, moved)
    onChange(next)
    setDragIndex(targetIndex)
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
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4, marginBottom: 10, maxHeight: 340, overflowY: 'auto' }}>
          {order.map((code, idx) => {
            const opt = options.find(p => p.code === code)
            return (
              <div
                key={code}
                draggable
                onDragStart={e => {
                  setDragIndex(idx)
                  // Grab the row as-is (full size), not the browser's shrunk ghost.
                  const rect = e.currentTarget.getBoundingClientRect()
                  e.dataTransfer.setDragImage(e.currentTarget, e.clientX - rect.left, e.clientY - rect.top)
                  e.dataTransfer.effectAllowed = 'move'
                }}
                onDragEnter={() => handleDragEnter(idx)}
                onDragOver={e => e.preventDefault()}
                onDragEnd={() => setDragIndex(null)}
                style={{
                  display: 'flex', alignItems: 'center', gap: 8,
                  padding: '6px 10px', background: 'rgba(255,255,255,0.04)',
                  border: '1px solid var(--border, rgba(255,255,255,0.08))',
                  borderRadius: 6, cursor: 'grab', fontSize: 13,
                  opacity: dragIndex === idx ? 0.4 : 1,
                }}
              >
                <span style={{ color: 'var(--text-muted)', fontSize: 11, width: 16 }}>{idx + 1}</span>
                <span style={{ color: 'var(--text-muted)' }} aria-hidden>⠿</span>
                <ProviderIcon domain={opt?.domain} size={16} />
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
        <button className="btn btn-secondary btn-sm" type="button" onClick={() => setShowAdd(true)}>
          + Añadir provider ({available.length})
        </button>
      )}

      {showAdd && (
        <div className="modal-overlay" onClick={() => setShowAdd(false)}>
          <div className="modal-panel" onClick={e => e.stopPropagation()} style={{ maxWidth: 480 }}>
            <div className="modal-header">
              <h2 className="modal-title">Añadir provider de vídeo</h2>
              <button className="modal-close" onClick={() => setShowAdd(false)}>✕</button>
            </div>
            <div className="modal-body">
              {available.length === 0 ? (
                <p style={{ fontSize: 13, color: 'var(--text-muted)' }}>Ya están todos añadidos.</p>
              ) : (
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(150px, 1fr))', gap: 6, maxHeight: '55vh', overflowY: 'auto' }}>
                  {available.map(opt => (
                    <button
                      key={opt.code}
                      type="button"
                      className="btn btn-ghost btn-sm"
                      style={{ display: 'flex', alignItems: 'center', gap: 8, justifyContent: 'flex-start', fontSize: 12 }}
                      onClick={() => enable(opt.code)}
                    >
                      <Favicon domain={opt.domain} size={16} radius={4} background="#fff" fallback={<span aria-hidden>🎬</span>} />
                      {opt.label}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
