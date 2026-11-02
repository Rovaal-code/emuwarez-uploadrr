import { useState } from 'react'
import type { SourceComparison, SourceEngineResult } from '../api/nomenclature'
import { InfoIcon } from './InfoIcon'
import { Tooltip } from './Tooltip'
import { IconoAviso } from './Iconos'
import { formatNumero } from '../utils/format'
import { Modal } from './Modal'

// Shared by the manual wizard's Source field: both the icon button and the
// blinking value inside "Ver MediaInfo". Same modal and same detail-toggle
// semantics for both entry points, instead of each re-implementing its own.
// Shown next to every "Internal Source Tool" column header, with the same
// wording everywhere so it doesn't read as two different explanations of the
// same thing.
export const INTERNAL_SOURCE_TOOL_INFO =
  'Herramienta interna que calcula el source de un vídeo analizando el archivo real. Todavía está en desarrollo y puede ser inexacta.'

// Source comparison — same table look as the rest of the wizard's tables, one
// column per origin, single data row (there's only one Source field).
function SourceCompareTable({ comparison, onShowEngineDetail }: { comparison: SourceComparison; onShowEngineDetail?: () => void }) {
  return (
    <div className="detail-card comp-caja">
      <table className="comp-tabla-fuente">
        <thead>
          <tr>
            <th className="comp-th">Nombre del archivo</th>
            <th className="comp-th">Radarr/Sonarr</th>
            <th className="comp-th">Internal Source Tool <InfoIcon text={INTERNAL_SOURCE_TOOL_INFO} /></th>
          </tr>
        </thead>
        <tbody>
          <tr className="comp-fila-borde">
            <td className="comp-celda-mono">{comparison.from_name || '—'}</td>
            <td className="comp-celda-mono">{comparison.from_radarr || '—'}</td>
            <td className="comp-celda-mono">
              {onShowEngineDetail && comparison.from_mediainfo ? (
                <Tooltip content="Ver comparación detallada">
                  <button
                    type="button"
                    className={`source-bitrate-link${comparison.agree === false ? ' badge-blink' : ''}`}
                    onClick={onShowEngineDetail}
                  >
                    {comparison.from_mediainfo}
                  </button>
                </Tooltip>
              ) : (comparison.from_mediainfo || '—')}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  )
}

const CERTAINTY_COLOR: Record<string, string> = { alto: 'var(--color-available)', medio: 'var(--color-req-pending)', bajo: 'var(--color-error)' }

// Spanish display names for the Internal Source Tool's evidence feature
// keys (the `feature` field itself stays the internal snake_case id — this
// is presentation-only). The full reasoning for each one is in its own
// per-row explanation, shown via the "?" InfoIcon, not in the label itself.
const EVIDENCE_LABELS: Record<string, string> = {
  single_file_container: 'Archivo único (no disco completo)',
  container_format: 'Formato del contenedor',
  fragmented_mp4: 'MP4 fragmentado',
  chapter_count: 'Capítulos',
  resolution_sd: 'Resolución SD',
  resolution_uhd: 'Resolución UHD',
  scan_type: 'Tipo de escaneo',
  hdr_or_dv: 'HDR / Dolby Vision',
  video_codec: 'Códec de vídeo',
  x264_bluray_compat: 'Flag bluray_compat (x264)',
  bits_per_pixel_per_frame: 'Bitrate normalizado',
  video_share_of_file: 'Proporción de vídeo en el archivo',
  lossless_audio_tracks: 'Audio sin pérdida',
  premium_object_audio: 'Audio Atmos / DTS:X',
  eac3_ddplus_audio: 'Audio E-AC-3 / DD+',
  broadcast_audio_at_sd: 'Audio de emisión en SD',
  pgs_subtitles: 'Subtítulos PGS',
  vobsub_subtitles: 'Subtítulos VobSub',
  text_only_subtitles: 'Solo subtítulos de texto',
  subtitle_language_breadth: 'Nº de idiomas de subtítulos',
  video_transcode_probability: 'Probabilidad de recodificación',
  disc_tier_encoder_fingerprint: 'Huella de encoder en un remux/disco',
  fast_effort_preset_signature: 'Perfil de codificación rápido/de bajo esfuerzo',
  screen_capture_probability: 'Probabilidad de captura de pantalla',
  sampled_bitrate_variability: 'Variabilidad de bitrate (muestreo)',
  sampled_gop_length: 'Duración de GOP (muestreo)',
}

// Full Internal Source Tool breakdown, shown below the plain 3-column
// comparison inside the same "Comparación del Source" modal — same
// detail-card/thStyle/monospace language as every other table in the wizard,
// just with 9 candidate columns instead of 1. Never shown if the engine
// couldn't run (comparison.engine is null) — the plain table above still
// works standalone in that case.
function SourceEngineDetail({ result }: { result: SourceEngineResult }) {
  const { prediction, ranking, evidence, explanation, contradictions, performance } = result
  const certaintyColor = CERTAINTY_COLOR[prediction.certainty] ?? 'var(--text-accent)'
  const orderedLabels = ranking.map(r => r.label)

  return (
    <div className="comp-detalle">
      <div className="detail-card comp-caja-resumen">
        <div className="comp-resumen">
          <span>Source estimado: <strong>{prediction.label}</strong></span>
          <span>Confianza: <strong>{formatNumero(prediction.confidence_score * 100, 1)}%</strong></span>
          <span>Segundo candidato: <strong>{prediction.runner_up}</strong> ({formatNumero(prediction.runner_up_score * 100, 1)}%)</span>
          <span>Margen: <strong>{formatNumero(prediction.margin * 100, 1)} pts</strong></span>
          {/* En línea: el color sale del nivel de certeza (valor calculado). */}
          <span>Nivel de evidencia: <strong style={{ color: certaintyColor }}>{prediction.certainty}</strong></span>
          <span>Tiempo de análisis: <strong>{formatNumero(performance.duration_ms / 1000, 1)}s</strong></span>
        </div>
        <p className="comp-explicacion">{explanation.winner}</p>
        <p className="comp-explicacion comp-segunda">{explanation.winner_vs_runner_up}</p>
        {contradictions.length > 0 && (
          <div className="comp-contradicciones">
            <span className="comp-contradicciones-titulo">Contradicciones detectadas</span>
            {contradictions.map((c, i) => (
              <p key={i} className="comp-contradiccion"><IconoAviso /> {c}</p>
            ))}
          </div>
        )}
      </div>

      <div className="detail-card comp-caja-scroll">
        <table className="comp-tabla-evidencia">
          <thead>
            <tr>
              <th className="comp-th comp-th-evidencia">Evidencia</th>
              {orderedLabels.map(label => (
                <th key={label} className={`comp-th comp-th-etiqueta${label === prediction.label ? ' comp-th-ganadora' : ''}`}>
                  {label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {evidence.map((ev, i) => (
              <tr key={i} className="comp-fila-borde">
                <td className="comp-celda-evidencia">
                  <span className="comp-etiqueta-evidencia">
                    {EVIDENCE_LABELS[ev.feature] ?? ev.feature}
                    <InfoIcon text={ev.explanation} />
                  </span>
                </td>
                {orderedLabels.map(label => {
                  const v = ev.contributions[label]
                  return (
                    <td key={label} className={`comp-celda-valor ${!v ? 'comp-nulo' : v > 0 ? 'comp-positivo' : 'comp-negativo'}${label === prediction.label ? ' comp-ganadora' : ''}`}>
                      {v ? (v > 0 ? `+${formatNumero(v, 1)}` : formatNumero(v, 1)) : '0'}
                    </td>
                  )
                })}
              </tr>
            ))}
            <tr className="comp-fila-total">
              <td className="comp-celda-total">SCORE TOTAL</td>
              {ranking.map(c => (
                <td key={c.label} className={`comp-celda-total comp-valor${c.label === prediction.label ? ' comp-ganadora' : ''}`}>
                  {formatNumero(c.raw_score, 1)}
                </td>
              ))}
            </tr>
            <tr>
              <td className="comp-celda-confianza">Confianza normalizada</td>
              {ranking.map(c => (
                <td key={c.label} className={`comp-celda-confianza comp-valor${c.label === prediction.label ? ' comp-ganadora' : ''}`}>
                  {formatNumero(c.normalized_score * 100, 1)}%
                </td>
              ))}
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  )
}

// Full modal: the plain 3-column table always shows; the 9-candidate detail
// breakdown only shows once `showDetail` is true — either because the caller
// opened it that way (`initialShowDetail`, e.g. clicking the blinking
// Internal Source Tool value directly) or because the user clicked that same
// value from inside the plain table after opening via the narrower icon
// button (see UploadWizardModal's Source field).
export function SourceComparisonModal({ comparison, initialShowDetail = false, onClose }: {
  comparison: SourceComparison
  initialShowDetail?: boolean
  onClose: () => void
}) {
  const [showDetail, setShowDetail] = useState(initialShowDetail)
  return (
    <Modal titulo="Comparación del Source" onClose={onClose} className={`modal-wide ${showDetail && comparison.engine ? 'comp-modal-fuente-detalle' : 'comp-modal-fuente'}`}>
      <div className="modal-body">
        <SourceCompareTable
          comparison={comparison}
          onShowEngineDetail={comparison.engine ? () => setShowDetail(true) : undefined}
        />
        {showDetail && comparison.engine && !comparison.engine.error && (
          <SourceEngineDetail result={comparison.engine} />
        )}
      </div>
    </Modal>
  )
}
