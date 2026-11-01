import type { TrackRemuxOverride, TrackRemuxPreview, TrackRemuxTrack } from '../../api/nomenclature'
import { AVISO_MODO_PISTAS, normalizarModo } from '../../utils/modoPistas'
import { IconoAviso } from '../Iconos'
import { thStyle } from './constantes'

const TRACK_TYPE_LABEL: Record<string, string> = { video: 'Vídeo', audio: 'Audio', subtitles: 'Subs' }

// Fuses a remux plan's base tracks with the user's manual edits — same
// merge RemuxTable renders inline, extracted so doUpload() can send the
// exact same "effective" table as remux_snapshot (see queueUpload()) instead
// of duplicating this logic and risking it drifting from what's on screen.
export function mergeRemuxTracks(
  plan: TrackRemuxPreview,
  edits?: Record<number, TrackRemuxOverride>,
): TrackRemuxTrack[] {
  return (plan.ordered_tracks ?? []).map(t => {
    const edit = edits?.[t.id]
    if (!edit) return t
    return {
      ...t,
      new_name: edit.new_name ?? t.new_name,
      default_after: edit.default_after ?? t.default_after,
    }
  })
}

/**
 * Dice, junto al título de "Ver Pistas", qué se va a hacer con las pistas.
 *
 * Sale SIEMPRE, no solo cuando algo está apagado. Antes solo avisaba de que la
 * ordenación estaba desactivada, y con cuatro estados posibles callarse en los
 * demás deja adivinando: la tabla puede enseñar las pistas en su orden actual
 * porque es el que van a conservar, o los nombres actuales porque no se van a
 * cambiar, y nada distinguía eso de "ya estaban bien".
 *
 * Sin `track_mode` no se pinta nada: significa que el plan no llegó a
 * calcularse (falta mkvmerge, archivo inaccesible) y ahí no se sabe en qué
 * modo se habría trabajado.
 */
export function AvisoModoPistas({ plan }: { plan?: { track_mode?: string } | null }) {
  if (!plan?.track_mode) return null
  const aviso = AVISO_MODO_PISTAS[normalizarModo(plan.track_mode)]
  const color = aviso.tono === 'info' ? 'var(--color-info)' : aviso.tono === 'aviso' ? 'var(--color-warning)' : 'var(--color-error)'
  return (
    <span style={{
      fontSize: 11, fontWeight: 500, color,
      background: `color-mix(in srgb, ${color} 14%, transparent)`, border: `1px solid color-mix(in srgb, ${color} 35%, transparent)`,
      borderRadius: 4, padding: '2px 8px',
    }}>
      {aviso.texto}
    </span>
  )
}

// Track reorder/rename table — the single-file "Ver Pistas" card renders it
// editable (inputs); the season target's per-episode accordion renders it
// read-only (editable=false — no manual per-track overrides for seasons).
export function RemuxTable({ plan, editable, nameEditable, edits, onEdit, onIdioma }: {
  plan: TrackRemuxPreview
  /** Si se puede tocar la casilla "Predet.". */
  editable: boolean
  /** Si se puede escribir en "Nombre nuevo". Va aparte de `editable` porque
   *  son ajustes distintos: con "Solo reordenar" la aplicación sigue marcando
   *  la pista predeterminada (y tú puedes cambiar cuál), pero los nombres se
   *  quedan como están y ofrecer escribirlos sería mentir. Sin pasarlo,
   *  acompaña a `editable`, que es lo que hace el acordeón de temporada. */
  nameEditable?: boolean
  edits?: Record<number, TrackRemuxOverride>
  onEdit?: (trackId: number, patch: TrackRemuxOverride) => void
  /** Elegir el idioma de una pista de audio que no trae ninguno. */
  onIdioma?: (trackId: number, code: string) => void
}) {
  return (
    <>
      {plan.errors?.map((e, i) => (
        <p key={i} className="text-error" style={{ fontSize: 12, marginTop: 10 }}>✗ {e}</p>
      ))}
      {plan.warnings?.map((w, i) => (
        <p key={i} className="text-warning" style={{ fontSize: 12, marginTop: 10 }}><IconoAviso /> {w}</p>
      ))}
      {plan.ordered_tracks && plan.ordered_tracks.length > 0 && (
        <div className="detail-card" style={{ marginTop: 12, maxHeight: 260, overflow: 'auto', borderRadius: 8 }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12.5, tableLayout: 'fixed' }}>
            <colgroup>
              <col style={{ width: '10%' }} />
              <col style={{ width: '10%' }} />
              <col style={{ width: '25%' }} />
              <col style={{ width: '38%' }} />
              <col style={{ width: '17%' }} />
            </colgroup>
            <thead>
              <tr>
                <th style={thStyle}>Tipo</th>
                <th style={thStyle}>Idioma</th>
                <th style={thStyle}>Nombre actual</th>
                <th style={thStyle}>Nombre nuevo</th>
                <th style={thStyle}>Predet.</th>
              </tr>
            </thead>
            <tbody>
              {mergeRemuxTracks(plan, edits).map(t => {
                const effectiveName = t.new_name
                const effectiveDefault = t.default_after
                return (
                  <tr key={t.id} style={{ borderTop: '1px solid var(--border)' }}>
                    <td style={{ padding: '6px 10px', color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>{TRACK_TYPE_LABEL[t.type] ?? t.type}</td>
                    {/* El BCP-47 cuando lo hay: es lo único que distingue el
                        valenciano del catalán ("cat" vs "ca-valencia") y el
                        latino del castellano. Enseñando solo `language`, esta
                        columna decía "cat" para una pista en valenciano. */}
                    <td style={{ padding: '6px 10px', fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>
                      {t.sin_idioma && onIdioma && plan.idiomas_elegibles?.length ? (
                        <select
                          className="form-input form-select"
                          style={{ fontSize: 12, padding: '4px 6px' }}
                          value={edits?.[t.id]?.language ?? t.language_after ?? ''}
                          onChange={e => onIdioma(t.id, e.target.value)}
                        >
                          <option value="">— Sin idioma —</option>
                          {plan.idiomas_elegibles.map(o => <option key={o.code} value={o.code}>{o.label}</option>)}
                        </select>
                      ) : (t.language_ietf || t.language || '—')}
                    </td>
                    <td style={{ padding: '6px 10px', color: 'var(--text-muted)', wordBreak: 'break-word' }}>{t.current_name || '—'}</td>
                    <td style={{ padding: '5px 8px' }}>
                      {(nameEditable ?? editable) ? (
                        <input
                          className="form-input"
                          style={{ fontSize: 12, padding: '4px 6px' }}
                          value={effectiveName}
                          onChange={e => onEdit?.(t.id, { new_name: e.target.value })}
                        />
                      ) : (
                        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }}>{effectiveName}</span>
                      )}
                    </td>
                    <td style={{ padding: '6px 10px', textAlign: 'center' }}>
                      {t.type === 'video' ? (
                        <span style={{ color: 'var(--text-muted)' }}>—</span>
                      ) : editable ? (
                        <input
                          type="checkbox"
                          checked={effectiveDefault}
                          onChange={e => onEdit?.(t.id, { default_after: e.target.checked })}
                        />
                      ) : (
                        <span>{effectiveDefault ? '✓' : '—'}</span>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </>
  )
}
