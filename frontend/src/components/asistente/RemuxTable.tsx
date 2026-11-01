import type { TrackRemuxOverride, TrackRemuxPreview, TrackRemuxTrack } from '../../api/nomenclature'
import { AVISO_MODO_PISTAS, normalizarModo } from '../../utils/modoPistas'
import { IconoAviso } from '../Iconos'

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
  const tono = aviso.tono === 'info' ? 'asist-tono-info' : aviso.tono === 'aviso' ? 'asist-tono-aviso' : 'asist-tono-error'
  return (
    <span className={`asist-modo-pistas ${tono}`}>
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
        <p key={i} className="text-error asist-aviso-linea">✗ {e}</p>
      ))}
      {plan.warnings?.map((w, i) => (
        <p key={i} className="text-warning asist-aviso-linea"><IconoAviso /> {w}</p>
      ))}
      {plan.ordered_tracks && plan.ordered_tracks.length > 0 && (
        <div className="detail-card asist-tabla-caja asist-tabla-caja-pistas">
          <table className="asist-tabla asist-tabla-pistas">
            <colgroup>
              <col />
              <col />
              <col />
              <col />
              <col />
            </colgroup>
            <thead>
              <tr>
                <th className="asist-th">Tipo</th>
                <th className="asist-th">Idioma</th>
                <th className="asist-th">Nombre actual</th>
                <th className="asist-th">Nombre nuevo</th>
                <th className="asist-th">Predet.</th>
              </tr>
            </thead>
            <tbody>
              {mergeRemuxTracks(plan, edits).map(t => {
                const effectiveName = t.new_name
                const effectiveDefault = t.default_after
                return (
                  <tr key={t.id} className="asist-fila">
                    <td className="asist-celda-pista text-muted asist-sin-salto">{TRACK_TYPE_LABEL[t.type] ?? t.type}</td>
                    {/* El BCP-47 cuando lo hay: es lo único que distingue el
                        valenciano del catalán ("cat" vs "ca-valencia") y el
                        latino del castellano. Enseñando solo `language`, esta
                        columna decía "cat" para una pista en valenciano. */}
                    <td className="asist-celda-pista asist-mono asist-color-secundario">
                      {t.sin_idioma && onIdioma && plan.idiomas_elegibles?.length ? (
                        <select
                          className="form-input form-select asist-input-chico"
                          value={edits?.[t.id]?.language ?? t.language_after ?? ''}
                          onChange={e => onIdioma(t.id, e.target.value)}
                        >
                          <option value="">— Sin idioma —</option>
                          {plan.idiomas_elegibles.map(o => <option key={o.code} value={o.code}>{o.label}</option>)}
                        </select>
                      ) : (t.language_ietf || t.language || '—')}
                    </td>
                    <td className="asist-celda-pista text-muted asist-romper">{t.current_name || '—'}</td>
                    <td className="asist-celda-pista-campo">
                      {(nameEditable ?? editable) ? (
                        <input
                          className="form-input asist-input-chico"
                          value={effectiveName}
                          onChange={e => onEdit?.(t.id, { new_name: e.target.value })}
                        />
                      ) : (
                        <span className="asist-mono-12">{effectiveName}</span>
                      )}
                    </td>
                    <td className="asist-celda-pista asist-centrado">
                      {t.type === 'video' ? (
                        <span className="text-muted">—</span>
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
