import type { MediaInfoReport } from '../../api/library'
import { IconoAviso } from '../Iconos'
import { InfoIcon } from '../InfoIcon'
import { Tooltip } from '../Tooltip'
import { thStyle } from './constantes'

// MediaInfo field/value table — shared by the single-file "Ver MediaInfo"
// card and the season target's per-episode accordion. `onSourceToolClick`
// (only wired from the single-file card, which has the comparison data) makes
// the Source row's "MediaInfo" cell — the internal source-detection tool's own
// output — clickable, opening the Source comparison modal; styled with the
// same `.source-bitrate-link` white-to-blue color sweep already used inside
// that modal for the "from_mediainfo" value linking to the bitrate table, so
// both blinking links read as the same affordance.
export function MediaInfoTable({ report, onSourceToolClick }: {
  report: MediaInfoReport
  onSourceToolClick?: () => void
}) {
  if (!report.available) {
    return <p className="text-warning" style={{ fontSize: 12, margin: 0 }}><IconoAviso /> {report.message}</p>
  }
  return (
    <div className="detail-card" style={{ maxHeight: 420, overflow: 'auto', borderRadius: 8 }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12.5, tableLayout: 'fixed' }}>
        <colgroup>
          <col style={{ width: '22%' }} />
          <col style={{ width: '39%' }} />
          <col style={{ width: '39%' }} />
        </colgroup>
        <thead>
          <tr>
            <th style={thStyle}>Campo</th>
            <th style={thStyle}>MediaInfo</th>
            <th style={thStyle}>eMuwarez</th>
          </tr>
        </thead>
        <tbody>
          {report.rows.map((r, i) => {
            const isSourceRow = r.field === 'Source'
            return (
              <tr key={i} style={{ borderTop: '1px solid var(--border)' }}>
                <td style={{ padding: '7px 12px', fontWeight: 600 }}>
                  <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
                    {r.field}
                    {r.help && <InfoIcon text={r.help} />}
                  </span>
                </td>
                <td style={{ padding: '7px 12px', fontFamily: 'var(--font-mono)', color: 'var(--text-muted)', wordBreak: 'break-word' }}>
                  {isSourceRow && onSourceToolClick ? (
                    <Tooltip content="Ver comparación del source">
                      <button type="button" className="source-bitrate-link" onClick={onSourceToolClick}>
                        {r.mediainfo}
                      </button>
                    </Tooltip>
                  ) : r.mediainfo}
                </td>
                <td style={{ padding: '7px 12px', fontFamily: 'var(--font-mono)', wordBreak: 'break-word' }}>{r.emu}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
