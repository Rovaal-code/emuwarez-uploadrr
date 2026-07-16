import { useEffect, useState } from 'react'
import { getEmuProviders } from '../api/nomenclature'
import { Favicon } from './Favicon'
import { SortableList } from './SortableList'

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

  const available = options.filter(p => !order.includes(p.code))

  return (
    <div>
      {order.length === 0 && (
        <p style={{ fontSize: 12, color: 'var(--text-muted)', margin: '0 0 8px' }}>
          Ningún provider activado — se añadirán por orden de prioridad.
        </p>
      )}
      {order.length > 0 && (
        <div style={{ marginBottom: 10, maxHeight: 340, overflowY: 'auto' }}>
          <SortableList ids={order} onChange={onChange} renderRow={(code, idx, { dragging, handleProps }) => {
            const opt = options.find(p => p.code === code)
            return (
              <div style={{
                display: 'flex', alignItems: 'center', gap: 8, padding: '8px 10px', borderRadius: 8, fontSize: 13,
                background: dragging ? 'rgba(37,99,235,0.15)' : 'rgba(139,92,246,0.06)',
                border: `1px solid ${dragging ? 'var(--text-accent, #2563eb)' : 'var(--border)'}`,
              }}>
                <span style={{ color: 'var(--text-muted)', fontSize: 11, width: 16 }}>{idx + 1}</span>
                <span {...handleProps} style={{ ...handleProps.style, color: 'var(--text-muted)' }} aria-hidden>⠿</span>
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
          }} />
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
                      style={{ display: 'flex', alignItems: 'center', gap: 8, justifyContent: 'flex-start', justifySelf: 'start', fontSize: 12 }}
                      onClick={() => enable(opt.code)}
                    >
                      <Favicon domain={opt.domain} size={16} fallback={<span aria-hidden>🎬</span>} />
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
