import { useState, useEffect } from 'react'
import { createPortal } from 'react-dom'
import { getEmuComparison, type EmuComparison } from '../api/library'
import { formatBytes } from '../utils/format'
import { InfoIcon } from './InfoIcon'
import { useTooltip } from './Tooltip'
import {
  ValueChip, TechChip, ResolutionValueIcon, SourceValueIcon,
  VideoCodecValueIcon, LanguageValueIcon, SizeValueIcon,
} from './DetailCard'
import { ServiceIcon } from './ServiceIcon'

// Three-state summary shown in the "eMuwarez" field chip (Información
// técnica card) — collapses EmuComparison's several branches (not in
// catalog, only-loose-episodes, aportes, exact match) down to the three
// words the user actually wants to see at a glance.
export type EmuFieldStatus = 'si' | 'no' | 'aportas'

function summarize(data: EmuComparison | null): EmuFieldStatus | null {
  if (!data || !data.available) return null
  const notInCatalog = data.in_catalog === 0 || data.matches.length === 0
  if (notInCatalog) return 'no'
  if (data.only_episodes) return data.have_all_episodes ? 'aportas' : 'si'
  if ((data.aportes ?? []).length > 0) return 'aportas'
  return 'si'
}

const STATUS_LABEL: Record<EmuFieldStatus, string> = { si: 'Sí', no: 'No', aportas: 'Aportas' }

// The "eMuwarez" field in Información técnica — fetches the comparison
// itself (same call EmuComparisonContent's data comes from) and shows a
// three-state chip (Sí/No/Aportas). Blinks green whenever there's something
// actionable (not in the catalog, or you'd contribute something new) — a
// plain "Sí" (already there, nothing better to add) stays the normal static
// blue border every other linkable field chip uses.
export function EmuFieldChip({ itemId }: { itemId: number }) {
  const [data, setData] = useState<EmuComparison | null>(null)
  const [loading, setLoading] = useState(true)
  const [showModal, setShowModal] = useState(false)

  useEffect(() => {
    let alive = true
    setLoading(true)
    getEmuComparison(itemId)
      .then(d => { if (alive) setData(d) })
      .catch(() => { if (alive) setData(null) })
      .finally(() => { if (alive) setLoading(false) })
    return () => { alive = false }
  }, [itemId])

  const status = summarize(data)

  if (loading || status === null) {
    return <span className="muted">–</span>
  }

  const blink = (status === 'no' || status === 'aportas') ? 'new' : undefined

  return (
    <>
      <ValueChip as="button" linkable blink={blink} onClick={() => setShowModal(true)} title="Ver comparación con eMuwarez">
        <span className="brand-icon" style={{ display: 'inline-flex' }}>
          <ServiceIcon type="emu" size={15} />
        </span>
        <span className="txt">{STATUS_LABEL[status]}</span>
      </ValueChip>
      {showModal && createPortal(
        <div className="modal-overlay" onClick={() => setShowModal(false)}>
          <div className="modal-panel modal-wide" onClick={e => e.stopPropagation()} style={{ maxWidth: '95vw', width: 'max-content' }}>
            <div className="modal-header">
              <h2 className="modal-title">Comparación con eMuwarez</h2>
              <button className="modal-close" onClick={() => setShowModal(false)}>✕</button>
            </div>
            <div className="modal-body">
              <EmuComparisonContent data={data} />
            </div>
          </div>
        </div>,
        document.body,
      )}
    </>
  )
}

// Detail-card comparison content: your copy vs every eMuwarez torrent that
// matches this movie/season, plus the summary of what you'd add ("Aportes").
// Pure — takes already-fetched data, no fetch of its own (EmuFieldChip above
// owns that) — so it can be dropped into a modal without a second request.
export function EmuComparisonContent({ data }: { data: EmuComparison | null }) {
  const notInCatalog = !!data && (data.in_catalog === 0 || data.matches.length === 0)
  const aportes = data?.aportes ?? []
  const mine = data?.mine
  // You only have a real copy to compare if the file is on disk. For a
  // "Faltante" item there's nothing local, so the "Tu copia" row is hidden and
  // the verdict changes accordingly.
  const hasLocal = data?.mine_available ?? (mine?.size != null)

  // If your copy matches a candidate on EVERY visible field (resolution,
  // source, codec, Spanish, size), it's presumed to come from eMuwarez — show
  // that candidate's name on the "Tu copia" row.
  const norm = (v?: string | null) => (v ?? '').trim().toLowerCase()
  const matchedCandidate = mine
    ? data?.matches.find(m =>
        norm(m.resolution) === norm(mine.resolution) &&
        norm(m.source) === norm(mine.source) &&
        norm(m.codec) === norm(mine.codec) &&
        (m.has_spanish === 1) === !!mine.has_es &&
        mine.size != null && m.size != null && formatBytes(mine.size) === formatBytes(m.size),
      )
    : null
  const matchedNameTip = useTooltip(matchedCandidate?.name ?? null)

  if (!data || !data.available) {
    return (
      <span style={{ color: 'var(--text-muted)', fontSize: 13 }}>
        {data?.message ?? 'Sincroniza con eMuwarez para ver la comparación.'}
      </span>
    )
  }

  return (
    <>
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
          <table className="data-table" style={{ fontSize: 12.5, width: 'calc(100% - 1px)' }}>
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
                  <td style={{ whiteSpace: 'nowrap' }}><TechChip icon={ResolutionValueIcon} value={mine.resolution} /></td>
                  <td style={{ whiteSpace: 'nowrap' }}><TechChip icon={SourceValueIcon} value={mine.source} /></td>
                  <td style={{ whiteSpace: 'nowrap' }}><TechChip icon={VideoCodecValueIcon} value={mine.codec} /></td>
                  <td style={{ whiteSpace: 'nowrap' }}><TechChip icon={LanguageValueIcon} value={mine.has_es ? 'Sí' : null} /></td>
                  <td style={{ whiteSpace: 'nowrap' }}><TechChip icon={SizeValueIcon} value={formatBytes(mine.size)} /></td>
                  {matchedCandidate ? (
                    <td
                      style={{ maxWidth: 1000, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: 'var(--text-secondary)', textAlign: 'left' }}
                      {...matchedNameTip.triggerProps}
                    >
                      {matchedCandidate.name}
                      {matchedNameTip.tooltipNode}
                    </td>
                  ) : (
                    <td style={{ color: 'var(--text-muted)' }}>—</td>
                  )}
                </tr>
              )}
              {data.matches.map((m, i) => (
                <tr key={i} style={m === matchedCandidate ? { background: 'rgba(59,130,246,0.08)' } : undefined}>
                  <td style={{ color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>eMuwarez</td>
                  <td style={{ whiteSpace: 'nowrap' }}><TechChip icon={ResolutionValueIcon} value={m.resolution} /></td>
                  <td style={{ whiteSpace: 'nowrap' }}><TechChip icon={SourceValueIcon} value={m.source} /></td>
                  <td style={{ whiteSpace: 'nowrap' }}><TechChip icon={VideoCodecValueIcon} value={m.codec} /></td>
                  <td style={{ whiteSpace: 'nowrap' }}><TechChip icon={LanguageValueIcon} value={m.has_spanish === 1 ? 'Sí' : m.has_spanish === 0 ? 'No' : '?'} /></td>
                  <td style={{ whiteSpace: 'nowrap' }}><TechChip icon={SizeValueIcon} value={formatBytes(m.size)} /></td>
                  <TorrentNameCell name={m.name} />
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  )
}

function TorrentNameCell({ name }: { name: string | null | undefined }) {
  const { triggerProps, tooltipNode } = useTooltip(name ?? null)
  return (
    <td
      style={{ maxWidth: 1000, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: 'var(--text-secondary)', textAlign: 'left' }}
      {...triggerProps}
    >
      {name}
      {tooltipNode}
    </td>
  )
}

const chipStyle: React.CSSProperties = {
  fontSize: 11.5, padding: '2px 8px', borderRadius: 4, whiteSpace: 'nowrap',
  background: 'rgba(34,197,94,0.14)', color: '#22c55e', border: '1px solid rgba(34,197,94,0.3)',
}
