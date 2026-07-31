import { useState } from 'react'
import type { SourceComparison, SourceEngineResult } from '../api/nomenclature'
import { InfoIcon } from './InfoIcon'
import { Tooltip } from './Tooltip'

// Shared by the manual wizard's Source field: both the icon button and the
// blinking value inside "Ver MediaInfo". Same modal and same detail-toggle
// semantics for both entry points, instead of each re-implementing its own.
const thStyle: React.CSSProperties = {
  textAlign: 'left', padding: '8px 10px', fontWeight: 600, color: 'var(--text-muted)',
  position: 'sticky', top: 0, background: 'var(--bg-surface, #0f1420)',
}

// Shown next to every "Internal Source Tool" column header, with the same
// wording everywhere so it doesn't read as two different explanations of the
// same thing.
export const INTERNAL_SOURCE_TOOL_INFO =
  'Herramienta interna que calcula el source de un vídeo analizando el archivo real. Todavía está en desarrollo y puede ser inexacta.'

// Source comparison — same table look as the rest of the wizard's tables, one
// column per origin, single data row (there's only one Source field).
function SourceCompareTable({ comparison, onShowEngineDetail }: { comparison: SourceComparison; onShowEngineDetail?: () => void }) {
  return (
    <div className="detail-card" style={{ borderRadius: 8 }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12.5, tableLayout: 'fixed' }}>
        <thead>
          <tr>
            <th style={thStyle}>Nombre del archivo</th>
            <th style={thStyle}>Radarr/Sonarr</th>
            <th style={thStyle}>Internal Source Tool <InfoIcon text={INTERNAL_SOURCE_TOOL_INFO} /></th>
          </tr>
        </thead>
        <tbody>
          <tr style={{ borderTop: '1px solid var(--border)' }}>
            <td style={{ padding: '7px 12px', fontFamily: 'monospace' }}>{comparison.from_name || '—'}</td>
            <td style={{ padding: '7px 12px', fontFamily: 'monospace' }}>{comparison.from_radarr || '—'}</td>
            <td style={{ padding: '7px 12px', fontFamily: 'monospace' }}>
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

const CERTAINTY_COLOR: Record<string, string> = { alto: '#22c55e', medio: '#eab308', bajo: '#ef4444' }

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
    <div style={{ marginTop: 14 }}>
      <div className="detail-card" style={{ borderRadius: 8, padding: '12px 14px', marginBottom: 12 }}>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px 20px', fontSize: 12.5 }}>
          <span>Source estimado: <strong>{prediction.label}</strong></span>
          <span>Confianza: <strong>{(prediction.confidence_score * 100).toFixed(1)}%</strong></span>
          <span>Segundo candidato: <strong>{prediction.runner_up}</strong> ({(prediction.runner_up_score * 100).toFixed(1)}%)</span>
          <span>Margen: <strong>{(prediction.margin * 100).toFixed(1)} pts</strong></span>
          <span>Nivel de evidencia: <strong style={{ color: certaintyColor }}>{prediction.certainty}</strong></span>
          <span>Tiempo de análisis: <strong>{(performance.duration_ms / 1000).toFixed(1)}s</strong></span>
        </div>
        <p style={{ fontSize: 12.5, color: 'var(--text-secondary)', margin: '10px 0 0' }}>{explanation.winner}</p>
        <p style={{ fontSize: 12.5, color: 'var(--text-secondary)', margin: '6px 0 0' }}>{explanation.winner_vs_runner_up}</p>
        {contradictions.length > 0 && (
          <div style={{ marginTop: 8 }}>
            <span style={{ fontSize: 11, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>Contradicciones detectadas</span>
            {contradictions.map((c, i) => (
              <p key={i} style={{ fontSize: 12, color: '#eab308', margin: '4px 0 0' }}>⚠ {c}</p>
            ))}
          </div>
        )}
      </div>

      <div className="detail-card" style={{ borderRadius: 8, overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11.5, minWidth: 820 }}>
          <thead>
            <tr>
              <th style={{ ...thStyle, minWidth: 160 }}>Evidencia</th>
              {orderedLabels.map(label => (
                <th key={label} style={{
                  ...thStyle, textAlign: 'right', minWidth: 68,
                  color: label === prediction.label ? '#22c55e' : thStyle.color,
                }}>
                  {label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {evidence.map((ev, i) => (
              <tr key={i} style={{ borderTop: '1px solid var(--border)' }}>
                <td style={{ padding: '6px 10px' }}>
                  <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
                    {EVIDENCE_LABELS[ev.feature] ?? ev.feature}
                    <InfoIcon text={ev.explanation} />
                  </span>
                </td>
                {orderedLabels.map(label => {
                  const v = ev.contributions[label]
                  return (
                    <td key={label} style={{
                      padding: '6px 10px', textAlign: 'right', fontFamily: 'monospace',
                      color: !v ? 'var(--text-muted)' : v > 0 ? '#4ade80' : '#f87171',
                      background: label === prediction.label ? 'rgba(34,197,94,0.06)' : undefined,
                    }}>
                      {v ? (v > 0 ? `+${v.toFixed(1)}` : v.toFixed(1)) : '0'}
                    </td>
                  )
                })}
              </tr>
            ))}
            <tr style={{ borderTop: '2px solid var(--border-hover)', fontWeight: 700 }}>
              <td style={{ padding: '7px 10px' }}>SCORE TOTAL</td>
              {ranking.map(c => (
                <td key={c.label} style={{
                  padding: '7px 10px', textAlign: 'right', fontFamily: 'monospace',
                  color: c.label === prediction.label ? '#22c55e' : undefined,
                  background: c.label === prediction.label ? 'rgba(34,197,94,0.1)' : undefined,
                }}>
                  {c.raw_score.toFixed(1)}
                </td>
              ))}
            </tr>
            <tr>
              <td style={{ padding: '5px 10px', fontSize: 11, color: 'var(--text-muted)' }}>Confianza normalizada</td>
              {ranking.map(c => (
                <td key={c.label} style={{
                  padding: '5px 10px', textAlign: 'right', fontFamily: 'monospace', fontSize: 11,
                  color: c.label === prediction.label ? '#22c55e' : 'var(--text-muted)',
                }}>
                  {(c.normalized_score * 100).toFixed(1)}%
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
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-panel modal-wide" onClick={e => e.stopPropagation()} style={{ maxWidth: showDetail && comparison.engine ? 980 : 620 }}>
        <div className="modal-header">
          <h2 className="modal-title">Comparación del Source</h2>
          <button className="modal-close" onClick={onClose}>✕</button>
        </div>
        <div className="modal-body">
          <SourceCompareTable
            comparison={comparison}
            onShowEngineDetail={comparison.engine ? () => setShowDetail(true) : undefined}
          />
          {showDetail && comparison.engine && !comparison.engine.error && (
            <SourceEngineDetail result={comparison.engine} />
          )}
        </div>
      </div>
    </div>
  )
}
