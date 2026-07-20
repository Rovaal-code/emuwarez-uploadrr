import { useState, useEffect } from 'react'
import { getEmuComparison, type EmuComparison } from '../api/library'
import { formatBytes } from '../utils/format'
import { InfoIcon } from './InfoIcon'

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
  // You only have a real copy to compare if the file is on disk. For a
  // "Faltante" item there's nothing local, so the "Tu copia" row is hidden and
  // the verdict changes accordingly.
  const hasLocal = data.mine_available ?? (mine?.size != null)

  // If your copy matches a candidate on EVERY visible field (resolution,
  // source, codec, Spanish, size), it's presumed to come from eMuwarez — show
  // that candidate's name on the "Tu copia" row.
  const norm = (v?: string | null) => (v ?? '').trim().toLowerCase()
  const matchedCandidate = mine
    ? data.matches.find(m =>
        norm(m.resolution) === norm(mine.resolution) &&
        norm(m.source) === norm(mine.source) &&
        norm(m.codec) === norm(mine.codec) &&
        (m.has_spanish === 1) === !!mine.has_es &&
        mine.size != null && m.size != null && formatBytes(mine.size) === formatBytes(m.size),
      )
    : null

  return (
    <Panel>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14, flexWrap: 'wrap' }}>
        {!hasLocal ? (
          notInCatalog ? (
            <span style={{ fontWeight: 600, color: 'var(--text-secondary)' }}>No lo tienes descargado y no está en eMuwarez todavía</span>
          ) : (
            <span style={{ fontWeight: 600, color: '#60a5fa' }}>Está en eMuwarez, pero aún no lo tienes descargado</span>
          )
        ) : notInCatalog ? (
          <span style={{ fontWeight: 600, color: '#22c55e' }}>No está en eMuwarez · Contenido único</span>
        ) : data.only_episodes ? (
          <span style={{ fontWeight: 600, color: '#eab308' }}>
            Los capítulos ya están en eMuwarez (sueltos), no hay season pack{' '}
            {data.have_all_episodes
              ? '· tienes todos, podrías aportar el pack de temporada.'
              : '(podrías aportar el pack si tienes todos).'}
          </span>
        ) : aportes.length > 0 ? (
          <>
            <span style={{ fontWeight: 600 }}>Ya está en eMuwarez, pero aportas:</span>
            {aportes.map((a, i) => (
              <span key={i} style={chipStyle}>{a.detail}</span>
            ))}
          </>
        ) : (
          <span style={{ fontWeight: 600, color: 'var(--text-secondary)' }}>Ya está en eMuwarez con igual o mejor calidad</span>
        )}
      </div>

      {!notInCatalog && (
        <div style={{ overflowX: 'auto' }}>
          <table className="data-table" style={{ fontSize: 12.5 }}>
            <thead>
              <tr>
                <th>Contenido</th>
                <th>Resolución</th>
                <th>Source</th>
                <th>Códec</th>
                <th><span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>Español <InfoIcon text="El idioma español se deduce del nombre del torrent; «?» = desconocido." /></span></th>
                <th>Tamaño</th>
                <th><span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>Nombre del Torrent <InfoIcon text="Si todos los campos coinciden con algún candidato, se presupone que tu copia proviene de eMuwarez." /></span></th>
              </tr>
            </thead>
            <tbody>
              {mine && hasLocal && (
                <tr style={{ background: 'rgba(34,197,94,0.06)' }}>
                  <td style={{ fontWeight: 600, whiteSpace: 'nowrap' }}>Tu copia</td>
                  <td>{mine.resolution || '–'}</td>
                  <td>{mine.source || '–'}</td>
                  <td>{mine.codec || '–'}</td>
                  <td>{mine.has_es ? 'Sí' : '–'}</td>
                  <td style={{ whiteSpace: 'nowrap' }}>{formatBytes(mine.size)}</td>
                  {matchedCandidate ? (
                    <td style={{ maxWidth: 320, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: 'var(--text-secondary)' }} title={matchedCandidate.name}>{matchedCandidate.name}</td>
                  ) : (
                    <td style={{ color: 'var(--text-muted)' }}>—</td>
                  )}
                </tr>
              )}
              {data.matches.map((m, i) => (
                <tr key={i} style={m === matchedCandidate ? { background: 'rgba(59,130,246,0.08)' } : undefined}>
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
