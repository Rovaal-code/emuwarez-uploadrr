import type { MediaInfoReport } from '../../api/library'
import { IconoAviso } from '../Iconos'
import { InfoIcon } from '../InfoIcon'
import { Tooltip } from '../Tooltip'

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
    return <p className="text-warning asist-t12 asist-m0"><IconoAviso /> {report.message}</p>
  }
  return (
    <div className="detail-card asist-tabla-caja asist-tabla-caja-mediainfo">
      <table className="asist-tabla asist-tabla-mediainfo">
        <colgroup>
          <col />
          <col />
          <col />
        </colgroup>
        <thead>
          <tr>
            <th className="asist-th">Campo</th>
            <th className="asist-th">MediaInfo</th>
            <th className="asist-th">eMuwarez</th>
          </tr>
        </thead>
        <tbody>
          {report.rows.map((r, i) => {
            const isSourceRow = r.field === 'Source'
            return (
              <tr key={i} className="asist-fila">
                <td className="asist-celda-mi asist-negrita">
                  <span className="asist-fila-info">
                    {r.field}
                    {r.help && <InfoIcon text={r.help} />}
                  </span>
                </td>
                <td className="asist-celda-mi asist-mono text-muted asist-romper">
                  {isSourceRow && onSourceToolClick ? (
                    <Tooltip content="Ver comparación del source">
                      <button type="button" className="source-bitrate-link" onClick={onSourceToolClick}>
                        {r.mediainfo}
                      </button>
                    </Tooltip>
                  ) : r.mediainfo}
                </td>
                <td className="asist-celda-mi asist-mono asist-romper">{r.emu}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
