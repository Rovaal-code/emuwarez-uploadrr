import { useState, useEffect } from 'react'
import { getEmuComparison, type EmuComparison } from '../api/library'
import { formatBytes } from '../utils/format'

// Detail-card comparison: your copy vs every eMuwarez torrent that matches this
// movie/season, plus the summary of what you'd add ("Aportes"). Only rendered
// for movies and seasons — series is a rollup (drill into seasons), episodes
// roll into their season.
export function EmuComparisonSection({ itemId }: { itemId: number }) {
  const [data, setData] = useState<EmuComparison | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let alive = true
    setLoading(true)
    getEmuComparison(itemId)
      .then(d => { if (alive) setData(d) })
      .catch(() => { if (alive) setData(null) })
      .finally(() => { if (alive) setLoading(false) })
    return () => { alive = false }
  }, [itemId])

  if (loading) {
    return <Panel><span style={{ color: 'var(--text-muted)', fontSize: 13 }}>Cargando comparación…</span></Panel>
  }
  if (!data || !data.available) {
    return (
      <Panel>
        <span style={{ color: 'var(--text-muted)', fontSize: 13 }}>
          {data?.message ?? 'Sincroniza con eMuwarez para ver la comparación.'}
        </span>
      </Panel>
    )
  }

  const notInCatalog = data.in_catalog === 0 || data.matches.length === 0
  const aportes = data.aportes ?? []
  const mine = data.mine

  return (
    <Panel>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14, flexWrap: 'wrap' }}>
        {notInCatalog ? (
          <span style={{ fontWeight: 600, color: '#22c55e' }}>🟢 No está en eMuwarez — contenido nuevo</span>
        ) : aportes.length > 0 ? (
          <>
            <span style={{ fontWeight: 600 }}>Ya está en eMuwarez, pero aportas:</span>
            {aportes.map((a, i) => (
              <span key={i} style={chipStyle}>{a.detail}</span>
            ))}
          </>
        ) : (
          <span style={{ fontWeight: 600, color: 'var(--text-secondary)' }}>⚪ Ya está en eMuwarez con igual o mejor calidad</span>
        )}
      </div>

      {!notInCatalog && (
        <div style={{ overflowX: 'auto' }}>
          <table className="data-table" style={{ fontSize: 12.5 }}>
            <thead>
              <tr>
                <th></th>
                <th>Resolución</th>
                <th>Source</th>
                <th>Códec</th>
                <th>Español</th>
                <th>Tamaño</th>
                <th>Nombre</th>
              </tr>
            </thead>
            <tbody>
              {mine && (
                <tr style={{ background: 'rgba(34,197,94,0.06)' }}>
                  <td style={{ fontWeight: 600, whiteSpace: 'nowrap' }}>Tu copia</td>
                  <td>{mine.resolution || '–'}</td>
                  <td>{mine.source || '–'}</td>
                  <td>{mine.codec || '–'}</td>
                  <td>{mine.has_es ? 'Sí' : '–'}</td>
                  <td style={{ whiteSpace: 'nowrap' }}>{formatBytes(mine.size)}</td>
                  <td style={{ color: 'var(--text-muted)' }}>—</td>
                </tr>
              )}
              {data.matches.map((m, i) => (
                <tr key={i}>
                  <td style={{ color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>eMuwarez</td>
                  <td>{m.resolution || '–'}</td>
                  <td>{m.source || '–'}</td>
                  <td>{m.codec || '–'}</td>
                  <td>{m.has_spanish === 1 ? 'Sí' : m.has_spanish === 0 ? 'No' : '?'}</td>
                  <td style={{ whiteSpace: 'nowrap' }}>{formatBytes(m.size)}</td>
                  <td style={{ maxWidth: 320, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: 'var(--text-secondary)' }} title={m.name}>{m.name}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 10 }}>
        El idioma español se deduce del nombre del torrent (eMuwarez no expone un campo de idioma); "?" = desconocido.
      </div>
    </Panel>
  )
}

const chipStyle: React.CSSProperties = {
  fontSize: 11.5, padding: '2px 8px', borderRadius: 4, whiteSpace: 'nowrap',
  background: 'rgba(34,197,94,0.14)', color: '#22c55e', border: '1px solid rgba(34,197,94,0.3)',
}

function Panel({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ marginTop: 28 }}>
      <div style={{ fontSize: 13, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em', color: 'var(--text-secondary)', marginBottom: 12 }}>
        Comparación con eMuwarez
      </div>
      <div style={{ padding: '16px 18px', background: 'rgba(255,255,255,0.03)', borderRadius: 10, border: '1px solid var(--border)' }}>
        {children}
      </div>
    </div>
  )
}
