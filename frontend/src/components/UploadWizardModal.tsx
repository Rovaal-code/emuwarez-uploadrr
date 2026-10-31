import { useState, useEffect, useCallback, useRef } from 'react'
import type { EmuSource, EmuProvider, NomenclatureFields, FieldsPreviewResult, TrackRemuxPreview, TrackRemuxOverride, TrackRemuxTrack, SourceComparison } from '../api/nomenclature'
import {
  getEmuSources,
  getEmuProviders,
  getNomenclatureFields,
  previewNomenclatureFields,
  saveNomenclatureFields,
  previewTrackRemux,
} from '../api/nomenclature'
import {
  queueUpload, getExistingJobForItem,
  runUploadChecks, getUploadChecksProgress, type UploadChecksResult, type UploadCheck,
} from '../api/uploads'
import { getLibrary, getMediaInfoReport, suggestProvider } from '../api/library'
import type { MediaInfoReport } from '../api/library'
import { CheckStatusIcon } from './DetailCard'
import { SourceComparisonModal } from './SourceComparisonModal'
import {
  previewSeasonPack, getSeasonPlanProgress, getSeasonEpisodeNames, cancelSeasonPackPreview,
  getSeasonEpisodeMediaInfo, getSeasonEpisodeRemuxPreview, previewSeasonPackFields,
  type SeasonPlanProgress, type SeasonEpisodeName, type SeasonEpisodeMediaInfo, type SeasonEpisodeRemux,
} from '../api/seasonPack'
import type { LibraryItemResponse, SeasonPackPlanResponse, UploadJob } from '../types/api'
import { isSeasonReady, seasonNotReadyReason, episodeNotReadyReason, listDisplayTitle } from '../utils/libraryItem'
import { InfoIcon } from './InfoIcon'
import { FitText, FitTextPair } from './FitText'
import { Tooltip, useTooltip } from './Tooltip'
import { ACTIVE_JOB_STATUSES, statusLabel } from '../utils/uploadStatus'
import { seguirProgreso } from '../api/eventos'
import { fetchSettings } from '../api/settings'
import { AVISO_MODO_PISTAS, normalizarModo, renombra, tocaElFichero } from '../utils/modoPistas'
import {
  SIN_SELECCION, seleccionUnica, seleccionTemporadas, seleccionCapitulos,
  colaTemporadas, colaCapitulos, esTanda, mismaSeleccion, conObjetivo,
  cacheCubre, conAjustes, peticionCubre, type Seleccion, type Ajustes,
} from '../utils/seleccionSubida'
import { IconoAviso } from './Iconos'
import { Modal } from './Modal'

// Unified "Subir" wizard (replaces the separate Nomenclatura + Campos + Subir
// buttons). For a Series/Season it first asks which season (and episode, or the
// whole season) to target; then Step 1 generates the eMuwarez nomenclature —
// Spanish title + year from Radarr/Sonarr, Source/Provider from the filename,
// the rest from mediainfo — as editable boxes with a live preview of the final
// torrent name; Step 2 runs the pre-upload checks and, once confirmed, QUEUES
// the upload (services/upload_queue.py runs integrity/nomenclature/remux/start
// server-side after a grace period) and hands off to Subidas — nothing here
// applies nomenclature or starts Uploadrr directly anymore.
const PROVIDER_SOURCES = new Set(['WEB-DL'])

interface Props {
  item: LibraryItemResponse
  onClose: () => void
  onDone?: () => void
  // Switches the app to the Subidas tab right after queueing — same
  // onNavigate(page) callback AppShell hands its pages.
  onNavigate?: (page: string) => void
  // Optional pre-selection (e.g. from a request's scope): season number and,
  // for a single episode, its episode number. Used to auto-fill step 0.
  preselect?: { season?: number | null; episode?: number | null }
  // La petición desde la que se abrió, si fue así: todo lo que se suba aquí la
  // cubre, y Subidas lo enseña.
  requestId?: number
  // Only true when opened from a series' own dedicated Biblioteca page — the
  // one place multi-season selection is offered (never from the Biblioteca
  // list/table, never from a season's own page).
}

const labelStyle: React.CSSProperties = {
  fontSize: 12, color: 'var(--text-muted)', marginBottom: 4, display: 'block',
}

const thStyle: React.CSSProperties = {
  textAlign: 'left', padding: '8px 10px', fontWeight: 600, color: 'var(--text-muted)',
  position: 'sticky', top: 0, background: 'var(--bg-surface)',
}
const TRACK_TYPE_LABEL: Record<string, string> = { video: 'Vídeo', audio: 'Audio', subtitles: 'Subs' }

// Shown in place of a table whose data isn't loaded yet, so a slow fetch (e.g.
// mkvmerge/MediaInfo reading a real file over a remote mount) never looks like
// the UI has frozen — always show a spinner instead of a blank area.
function TableLoadingSpinner({ label = 'Cargando…' }: { label?: string }) {
  return (
    <div style={{ padding: '28px 0', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10 }}>
      <span className="spinner" style={{ width: 24, height: 24, borderWidth: 3 }} />
      <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>{label}</span>
    </div>
  )
}

// Same order run_upload_checks() runs them in (services/upload_checks.py) —
// used to name the check currently in flight ("Comprobando si es
// accesible…") while its own result hasn't landed yet, since liveChecks only
// grows with COMPLETED checks: its length is the index of the one running now.
// Accessibility/integrity are no longer checked here — they're checked for
// real once the upload is queued (services/upload_queue.py's
// "verificacion_presubida" stage, which already runs MediaInfo/mkvmerge on
// the file for the nomenclature/remux steps), so a failure lands with a specific reason
// instead of duplicating that work upfront.
// A season target collapses "renameable" into one "season_pack" check
// (run_upload_checks' season branch — see upload_checks.py).
const CHECK_STEP_ORDER = ['renameable', 'output', 'qbittorrent', 'imghosts', 'emuwarez']
const CHECK_STEP_ORDER_SEASON = ['season_pack', 'output', 'qbittorrent', 'imghosts', 'emuwarez']
const CHECK_STEP_PENDING_LABEL: Record<string, string> = {
  renameable: 'Comprobando si se puede renombrar…',
  season_pack: 'Comprobando el pack de temporada…',
  output: 'Comprobando el directorio de salida…',
  qbittorrent: 'Comprobando la conexión con qBittorrent…',
  imghosts: 'Comprobando el repositorio de imágenes…',
  emuwarez: 'Comprobando la conexión con eMuwarez…',
}

// MediaInfo field/value table — shared by the single-file "Ver MediaInfo"
// card and the season target's per-episode accordion. `onSourceToolClick`
// (only wired from the single-file card, which has the comparison data) makes
// the Source row's "MediaInfo" cell — the internal source-detection tool's own
// output — clickable, opening the Source comparison modal; styled with the
// same `.source-bitrate-link` white-to-blue color sweep already used inside
// that modal for the "from_mediainfo" value linking to the bitrate table, so
// both blinking links read as the same affordance.
function MediaInfoTable({ report, onSourceToolClick }: {
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
function AvisoModoPistas({ plan }: { plan?: { track_mode?: string } | null }) {
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
export function RemuxTable({ plan, editable, nameEditable, edits, onEdit }: {
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
                      {t.language_ietf || t.language || '—'}
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

// library_items.title for an episode is built (integrations/sonarr.py's
// episode_to_library_item) as "{Serie} SxxExx - {título del capítulo}" —
// needed for Biblioteca's own listing, but redundant inside a season
// target's own MediaInfo/Remux accordion (EpisodeAccordionRow already
// prepends "Exx — " itself, and you're already looking at that one
// season). Strips everything up to and including the first " - ", keeping
// only the episode's own title; falls back to the full string if there's
// no " - " at all (an episode with no per-episode title in Sonarr).
function episodeOnlyTitle(fullTitle?: string | null): string | undefined {
  if (!fullTitle) return fullTitle ?? undefined
  const idx = fullTitle.indexOf(' - ')
  return idx === -1 ? fullTitle : fullTitle.slice(idx + 3)
}

// One collapsible episode row — used by the season target's MediaInfo/Remux
// accordions (one entry per episode instead of a single-file table).
// El desplegable con el que se elige capítulo dentro de una tarjeta de
// temporada (MediaInfo, Remux, nombres). Se oculta si solo hay uno: un
// desplegable de una sola opción no navega a ningún sitio.
function EpisodePicker<T extends { episode_id: number; display_title?: string | null; title?: string | null }>(
  { episodes, currentId, onChange }: { episodes: T[]; currentId: number; onChange: (id: number) => void },
) {
  if (episodes.length <= 1) return null
  return (
    <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 12 }}>
      <select
        className="form-input form-select" style={{ width: 'auto' }}
        value={currentId} onChange={e => onChange(Number(e.target.value))}
      >
        {episodes.map(ep => (
          <option key={ep.episode_id} value={ep.episode_id}>
            {ep.display_title ?? episodeOnlyTitle(ep.title)}
          </option>
        ))}
      </select>
    </div>
  )
}

export function EpisodeAccordionRow({ episodeNumber, title, expanded, onToggle, children }: {
  episodeNumber?: number | null
  title?: string | null
  expanded: boolean
  onToggle: () => void
  children: React.ReactNode
}) {
  const { triggerProps, tooltipNode } = useTooltip(title ?? null)
  return (
    <div style={{ border: '1px solid var(--border)', borderRadius: 8, marginBottom: 8, overflow: 'hidden' }}>
      <button
        type="button"
        onClick={onToggle}
        style={{
          width: '100%', textAlign: 'left', padding: '8px 12px', background: 'color-mix(in srgb, var(--overlay-light) 3%, transparent)',
          border: 'none', cursor: 'pointer', display: 'flex', justifyContent: 'space-between',
          alignItems: 'center', gap: 8, color: 'inherit', fontSize: 13,
        }}
        {...triggerProps}
      >
        <span style={{ minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {episodeNumber != null ? `E${String(episodeNumber).padStart(2, '0')}: ` : ''}{title}
        </span>
        <span style={{ color: 'var(--text-muted)', fontSize: 11, flexShrink: 0 }}>{expanded ? '▲' : '▼'}</span>
        {tooltipNode}
      </button>
      {expanded && <div style={{ padding: 10 }}>{children}</div>}
    </div>
  )
}

// Status ring for one check: thin track + glowing ring + glyph, same visual
// language as the sidebar's CPU/RAM gauges (see SystemStatusPanel.tsx) —
// replaces the 🟢🟡🔴 emoji, which didn't match the rest of the UI's icon set.
// One check's icon + label + message — used for the final full list once the
// run is done.
function CheckRow({ c }: { c: UploadCheck }) {
  return (
    <div style={{ display: 'flex', gap: 8, alignItems: 'flex-start', padding: '3px 0' }}>
      <span style={{ marginTop: 2 }}><CheckStatusIcon status={c.status} /></span>
      <div style={{ minWidth: 0 }}>
        <div style={{ fontSize: 13 }}>{c.label}</div>
        {c.message && <div style={{ fontSize: 11, color: 'var(--text-muted)', wordBreak: 'break-all', marginTop: 2, marginBottom: 4 }}>{c.message}</div>}
      </div>
    </div>
  )
}

// Field label + an info "?" explaining where the field's data comes from.
function FieldLabel({ label, info }: { label: string; info?: React.ReactNode }) {
  return (
    <span style={{ ...labelStyle, display: 'inline-flex', alignItems: 'center', gap: 5 }}>
      {label}{info && <InfoIcon text={info} />}
    </span>
  )
}

// Where each nomenclature field comes from (shown in the "?" tooltips).
const FIELD_INFO = {
  title: 'Viene de Radarr/Sonarr y se traduce al español con TMDb.',
  year: 'Viene de Radarr/Sonarr.',
  season_episode: 'Temporada/episodio del release (SxxExx).',
  resolution: 'Viene de Radarr/Sonarr. El botón «Ver MediaInfo» muestra la del archivo real.',
  source: 'Prioridad: 1) nombre del archivo, 2) Radarr/Sonarr, 3) estimado con MediaInfo por bitrate (tamaño/duración) si ninguno de los dos anteriores da un source válido.',
  provider: 'Sale del nombre del archivo. Si no lo trae y el source es WEB-DL, se sugiere con TMDb (suscripción antes que alquiler, según tu prioridad).',
  video_codec: 'Se lee con MediaInfo del archivo real.',
  audio: 'Se lee con MediaInfo del archivo real (por pista).',
  subs: 'Se genera con MediaInfo del archivo real: «SUBS» si tiene pistas de subtítulos.',
  tag: 'Por defecto, el grupo de release del archivo (columna Grupo de Biblioteca); si no lo tiene, el de Ajustes. Puedes elegir otro de los guardados.',
}

// Monospace one-liner (torrent name / internal title) that shrinks its font so
// the whole string fits the card width instead of wrapping onto two lines.
// Placeholder shown while the torrent name / ficha title is still being
// generated (the preview arrives a moment after opening), so the box is never
// empty first.
function GeneratingHint() {
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, color: 'var(--text-muted)', fontSize: 13, padding: '2px 0' }}>
      <span className="spinner" style={{ width: 12, height: 12, borderWidth: 2 }} /> Generando…
    </span>
  )
}

// Same value as the torrent name, just also used as the .mkv container's own
// title tag — one label reused everywhere this pairing shows up (single-file
// preview, season episode accordion, step 2 confirmation).
const INTERNAL_TITLE_LABEL = (
  <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
    Título del archivo
    <InfoIcon text="Es el nombre del torrent sin acentos y con puntos: también es el título interno, el que se graba dentro del propio contenedor .mkv." />
  </span>
)

export function UploadWizardModal({ item, onClose: onCloseProp, onDone, onNavigate, preselect, requestId }: Props) {
  const isSeries = item.item_type === 'series'
  const isSeason = item.item_type === 'season'
  const needsSelection = isSeries || isSeason
  // Una serie SIEMPRE significa elegir temporadas. Esto dependía de una
  // propiedad `multiSeason` que solo pasaba Biblioteca, así que la misma serie
  // abierta desde Peticiones o desde el Panel caía en los desplegables
  // antiguos de Temporada/Episodio. Y la propiedad ya era redundante: sus dos
  // llamantes la calculaban como item_type === 'series'.
  const allowMultiSeason = isSeries


  // Multi-season selection (a series): a checklist of seasons. The seasons
  // chosen go to the queue in `seleccion` — for Manual, step 1 shows a
  // season-switcher dropdown to review/edit each one's nomenclature (their
  // Source/Proveedor/Tag edits kept in ajustesPorId below, restored when
  // switching back), and step 2 becomes a single "Subir todas" that checks +
  // queues each one in turn, skipping a failed check instead of blocking the
  // rest.
  const [multiSelected, setMultiSelected] = useState<Set<number>>(new Set())
  // Lo que se sube, en un solo valor: un elemento, una cola de temporadas o una
  // de capítulos. Todo lo que cuelga de ello se descarta junto al cambiarlo
  // (elegirSeleccion), así dos colas no pueden convivir.
  const [seleccion, setSeleccion] = useState<Seleccion>(needsSelection ? SIN_SELECCION : seleccionUnica(item.id))
  const targetId = seleccion.objetivo
  const targetIsSeason = seleccion.esTemporada
  const seasonQueue = colaTemporadas(seleccion)
  const episodeQueue = colaCapitulos(seleccion)
  // Source/Proveedor/Tag/Título editados por elemento (temporada o capítulo),
  // por id — persisten al cambiar en el desplegable (loadSeasonPlan los
  // pisaría con lo autodetectado cada vez que vuelves).
  const [ajustesPorId, setAjustesPorId] = useState<Map<number, Ajustes>>(new Map())
  // De quién son los campos que hay ahora en `fields`: no se apuntan como
  // ajustes de otro elemento mientras este aún carga.
  const camposDe = useRef<number | null>(null)
  // El objetivo vigente: la respuesta lenta de otro elemento no pisa lo que
  // hay en pantalla.
  const objetivoActual = useRef(targetId)
  objetivoActual.current = targetId

  // Season upload mode. A season that can't ship as a PACK (episodes disagree
  // on codec/audio/resolution, or it's incomplete) can still have its episodes
  // uploaded one by one: those rules exist because a pack carries a single
  // release name for everything inside it, and an individual episode carries
  // its own, which can state its own codec and audio truthfully.
  const [seasonUploadMode, setSeasonUploadMode] = useState<'whole' | 'episodes' | null>(null)
  const [episodeSelected, setEpisodeSelected] = useState<Set<number>>(new Set())
  // Nomenclature is generated for EVERY selected episode up front, not lazily
  // as the user switches between them: it's real work per episode, and doing
  // it on switch made the dropdown feel broken (a spinner every time you moved)
  // and hid failures until you happened to land on the broken one. Same shape
  // as the season pack's own "Comprobando N de M capítulos…".
  const [episodeFieldsById, setEpisodeFieldsById] = useState<Map<number, Awaited<ReturnType<typeof getNomenclatureFields>>>>(new Map())
  // Paso 2 con varios elementos elegidos. Las comprobaciones del ENTORNO
  // (directorio de salida, qBittorrent, hosts de imágenes, eMuwarez) se piden
  // UNA vez para toda la tanda: con 30 capítulos, preguntarle 30 veces a
  // eMuwarez si está vivo no aporta nada y multiplica por 30 la espera. Las
  // del CONTENIDO sí van una por elemento, porque dependen del fichero.
  const [batchEnvChecks, setBatchEnvChecks] = useState<UploadChecksResult | null>(null)
  const [batchContentChecks, setBatchContentChecks] = useState<Map<number, UploadChecksResult>>(new Map())
  const [batchChecksLoading, setBatchChecksLoading] = useState(false)
  const [batchChecksIndex, setBatchChecksIndex] = useState(0)
  // Cuál se está mirando en el desplegable de arriba a la derecha.
  const [batchViewId, setBatchViewId] = useState<number | null>(null)
  const [episodePrepIndex, setEpisodePrepIndex] = useState(0)
  const [episodePrepping, setEpisodePrepping] = useState(false)
  // The one Título the whole batch shares (see setField). Null until the user
  // actually picks one, so each item keeps its own auto-resolved title before
  // that.
  const [sharedTitle, setSharedTitle] = useState<string | null>(null)
  // "Subir todas" (multi-season) batch state.
  const [batchPhase, setBatchPhase] = useState<'idle' | 'processing' | 'done'>('idle')
  const [batchIndex, setBatchIndex] = useState(0)
  const [batchResults, setBatchResults] = useState<{ seasonId: number; title: string; status: 'queued' | 'failed'; reason?: string }[]>([])

  // targetId (el elemento sobre el que corre la nomenclatura: una película o
  // un capítulo, la fila de una temporada para el pack) y targetIsSeason (si
  // es un pack y no un fichero: cambia por completo el paso 1) salen de
  // `seleccion`, arriba.
  const [step, setStep] = useState<0 | 1 | 2>(needsSelection ? 0 : 1)

  // Step 0 — series/season selection
  const [seasons, setSeasons] = useState<LibraryItemResponse[]>([])
  const [episodes, setEpisodes] = useState<LibraryItemResponse[]>([])
  const [selError, setSelError] = useState<string | null>(null)

  // Step 1 — nomenclature fields
  const [sources, setSources] = useState<EmuSource[]>([])
  const [providers, setProviders] = useState<EmuProvider[]>([])
  const [fields, setFields] = useState<NomenclatureFields>({})
  // Tag becomes a locked dropdown (Título/Año/Resolución/Códec/Audio/Subs are
  // also locked) — this captures the resolved value at load time so the
  // dropdown always offers it as an option alongside the "EMUWAREZ" fallback,
  // even after the user picks the other one.
  const [initialTag, setInitialTag] = useState('')
  // Los grupos de subida guardados en Configuración, para el desplegable de Tag.
  const [gruposDeSubida, setGruposDeSubida] = useState<string[]>([])
  useEffect(() => {
    fetchSettings().then(s => setGruposDeSubida(s.upload_tags ?? [])).catch(() => { /* quedan los de siempre */ })
  }, [])
  const opcionesTag = Array.from(new Set([fields.tag, initialTag, ...(gruposDeSubida.length ? gruposDeSubida : ['EMUWAREZ'])].filter(Boolean))) as string[]
  const [titleWarning, setTitleWarning] = useState<string | null>(null)
  const [titleOptions, setTitleOptions] = useState<{ value: string; kind: string; label: string }[]>([])
  const [sourceWarning, setSourceWarning] = useState<string | null>(null)
  const [sourceComparison, setSourceComparison] = useState<SourceComparison | null>(null)
  const [showSourceCompare, setShowSourceCompare] = useState(false)
  // The detailed 9-candidate engine breakdown (SourceEngineDetail) only
  // shows when the modal was opened from the blinking Internal Source Tool
  // value inside "Ver MediaInfo" — the plain badge next to the Source field
  // below opens the same modal for the simpler name/Radarr/MediaInfo
  // 3-way check, without the extended breakdown.
  const [showEngineDetail, setShowEngineDetail] = useState(false)
  const [preview, setPreview] = useState<FieldsPreviewResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Step 1 — on-demand MediaInfo report (only runs when the button is clicked)
  const [miReport, setMiReport] = useState<MediaInfoReport | null>(null)
  const [miLoading, setMiLoading] = useState(false)
  const [miError, setMiError] = useState<string | null>(null)
  const [showMiCard, setShowMiCard] = useState(false)

  // Step 1 — on-demand track remux preview (reorder + rename audio/subs/video),
  // editable by hand; applied automatically as part of "Subir" (see doUpload).
  const [remuxPreview, setRemuxPreview] = useState<TrackRemuxPreview | null>(null)
  const [remuxLoading, setRemuxLoading] = useState(false)
  const [remuxError, setRemuxError] = useState<string | null>(null)
  const [remuxEdits, setRemuxEdits] = useState<Record<number, TrackRemuxOverride>>({})
  const [showRemuxCard, setShowRemuxCard] = useState(false)

  // Step 1 (season target only) — the pack plan: consistency across
  // episodes, completeness, and the single pack torrent name. Built with a
  // live "N de M capítulos" counter (real work per episode server-side).
  const [seasonPlan, setSeasonPlan] = useState<SeasonPackPlanResponse | null>(null)
  const [seasonPlanLoading, setSeasonPlanLoading] = useState(false)
  // Which season (if any) has a plan being built right now, so closing the
  // wizard can tell the server to stop. A ref, not state: the close handler
  // must read the value at the moment of the click, not the one captured when
  // it was last rendered.
  const buildingPlanFor = useRef<number | null>(null)
  // Cuenta las cargas de plan: la respuesta de una temporada ya abandonada no pisa la actual.
  const planPedido = useRef(0)
  // Lo que ya se cargó en el paso 1. Volver al 1 (desde el 2, o desde el 0 con
  // lo mismo elegido) no recarga: pisaba lo elegido (título, fuente, etiqueta, pistas).
  const cargadoPara = useRef<string | null>(null)
  const objetivo = `${targetIsSeason ? 's' : 'e'}${targetId}`
  const [seasonPlanError, setSeasonPlanError] = useState<string | null>(null)
  const [seasonProgress, setSeasonProgress] = useState<SeasonPlanProgress>({ done: 0, total: 0, current_title: null })
  // Live-recomputed pack title while editing Source/Proveedor/Tag (null
  // until the first edit-triggered recompute lands — seasonPlan's own
  // season_pack_title covers display until then).
  const [seasonTitlePreview, setSeasonTitlePreview] = useState<string | null>(null)

  // Season target — per-episode final names ("Ver nombre de todos los
  // capítulos"), on demand.
  const [seasonNames, setSeasonNames] = useState<SeasonEpisodeName[] | null>(null)
  const [seasonNamesLoading, setSeasonNamesLoading] = useState(false)
  const [showSeasonNamesCard, setShowSeasonNamesCard] = useState(false)
  // Capítulo elegido dentro de "Ver nombre de todos los capítulos": se navega
  // con un desplegable, igual que Ver MediaInfo, en vez de una lista de 25
  // bloques uno debajo de otro.
  const [seasonNamesEpisodeId, setSeasonNamesEpisodeId] = useState<number | null>(null)

  // Season target — per-episode MediaInfo/Remux (accordion, one entry per
  // episode), replacing the single-file "Ver MediaInfo"/"Ver Pistas" cards.
  const [seasonMi, setSeasonMi] = useState<SeasonEpisodeMediaInfo[] | null>(null)
  const [seasonMiLoading, setSeasonMiLoading] = useState(false)
  const [seasonMiError, setSeasonMiError] = useState<string | null>(null)
  // Capítulo que se está viendo dentro de la tarjeta: se navega con un
  // desplegable, igual que "Ver nombre de todos los capítulos", en vez de una
  // lista de 25 acordeones que obliga a bajar buscando el que interesa.
  const [miEpisodeId, setMiEpisodeId] = useState<number | null>(null)

  const [seasonRemux, setSeasonRemux] = useState<SeasonEpisodeRemux[] | null>(null)
  const [seasonRemuxLoading, setSeasonRemuxLoading] = useState(false)
  const [seasonRemuxError, setSeasonRemuxError] = useState<string | null>(null)
  const [remuxEpisodeId, setRemuxEpisodeId] = useState<number | null>(null)

  // Step 1 — automatic TMDB provider detection for WEB-DL with no provider.
  const [detectingProvider, setDetectingProvider] = useState(false)
  // Which target we've already fired the TMDB detection for — guarantees at
  // most ONE TMDB call per resolved item while this wizard stays open.
  const detectedTargetRef = useRef<number | null>(null)

  // Step 2 — checks + (on upload) apply + preflight + start
  const [preparing, setPreparing] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [uploadMsg, setUploadMsg] = useState<string | null>(null)
  const [checks, setChecks] = useState<UploadChecksResult | null>(null)
  const [checksLoading, setChecksLoading] = useState(false)
  // Checks landing one at a time while the run (POST, ~30s of real network
  // calls) is in flight — polled separately so the UI can reveal each one as
  // it actually completes instead of sitting on a static spinner.
  const [liveChecks, setLiveChecks] = useState<UploadCheck[]>([])

  const runChecks = useCallback(async () => {
    if (targetId == null) return
    setChecksLoading(true)
    setLiveChecks([])
    const pedir = async () => {
      try {
        const p = await getUploadChecksProgress(targetId)
        setLiveChecks(p.checks)
      } catch { /* fallo pasajero — el siguiente aviso o tic reintenta */ }
    }
    const dejarDeSeguir = seguirProgreso(
      'comprobaciones-progreso', a => a.item_id === targetId, pedir, 400)
    try { setChecks(await runUploadChecks(targetId)) }
    catch { setChecks(null) }
    finally {
      dejarDeSeguir()
      setChecksLoading(false)
      setLiveChecks([])
    }
  }, [targetId])

  // --- Step 0: load seasons (series) or episodes (season) ---
  useEffect(() => {
    if (!needsSelection) return
    const load = async () => {
      try {
        if (isSeries) {
          const r = await getLibrary({ parent_id: item.id, type: 'season', limit: 500 })
          setSeasons(r.items)
          // La temporada de la petición, ya marcada si se puede subir.
          if (preselect?.season != null) {
            const s = r.items.find(x => x.season_number === preselect.season)
            if (s && isSeasonReady(s)) setMultiSelected(new Set([s.id]))
          }
        } else {
          const r = await getLibrary({ parent_id: item.id, type: 'episode', limit: 500 })
          setEpisodes(r.items)
          // Lo que pide la petición, ya elegido: el capítulo si es de un
          // capítulo, y si no el pack de la temporada.
          if (preselect?.episode != null) {
            const e = r.items.find(x => x.episode_number === preselect.episode)
            if (e && !episodeNotReadyReason(e)) {
              setSeasonUploadMode('episodes')
              setEpisodeSelected(new Set([e.id]))
            }
          } else if (preselect?.season != null && !seasonNotReadyReason(item)) {
            setSeasonUploadMode('whole')
          }
        }
      } catch (e: unknown) {
        setSelError(e instanceof Error ? e.message : 'Error cargando temporadas')
      }
    }
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [item.id, isSeries, needsSelection])

  // La tanda activa: capítulos sueltos o temporadas, nunca las dos.
  const batchIsEpisodes = episodeQueue.length > 1
  const batchQueue = batchIsEpisodes ? episodeQueue : seasonQueue
  const batchItemTitle = (id: number) => {
    const row = (batchIsEpisodes ? episodes : seasons).find(x => x.id === id)
    return row ? listDisplayTitle(row) : `#${id}`
  }
  // Contenido + entorno reconstruye exactamente la pasada completa de siempre
  // (fijado por tests/test_upload_checks.py), así que el snapshot que se
  // guarda con el job es el mismo que antes.
  const mergedChecksFor = (id: number): UploadChecksResult | null => {
    const content = batchContentChecks.get(id)
    if (!content || !batchEnvChecks) return null
    return {
      checks: [...content.checks, ...batchEnvChecks.checks],
      ready: content.ready && batchEnvChecks.ready,
    }
  }

  // Al entrar en el paso 2 con varios elegidos: el entorno una vez, el
  // contenido uno a uno. Se guardan para que "Subir todos" no las repita y
  // para que el desplegable pueda enseñar las de cualquiera sin volver a
  // pedirlas.
  useEffect(() => {
    if (step !== 2 || batchQueue.length <= 1 || batchPhase !== 'idle') return
    if (batchChecksLoading || (batchEnvChecks && cacheCubre(batchQueue, batchContentChecks))) return
    let alive = true
    const run = async () => {
      setBatchChecksLoading(true)
      setBatchChecksIndex(0)
      try {
        // El item_id da igual para las de entorno, pero el endpoint lo pide.
        const env = await runUploadChecks(batchQueue[0], 'environment')
        if (!alive) return
        setBatchEnvChecks(env)
        const acc = new Map<number, UploadChecksResult>()
        for (let i = 0; i < batchQueue.length; i++) {
          if (!alive) return
          setBatchChecksIndex(i)
          acc.set(batchQueue[i], await runUploadChecks(batchQueue[i], 'content'))
          setBatchContentChecks(new Map(acc))
        }
        if (alive) setBatchViewId(prev => prev ?? batchQueue[0])
      } finally {
        if (alive) setBatchChecksLoading(false)
      }
    }
    run()
    return () => { alive = false; setBatchChecksLoading(false) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step, batchQueue.length, batchPhase])

  const eligibleEpisodes = episodes.filter(ep => !episodeNotReadyReason(ep))
  const allEligibleSelected = eligibleEpisodes.length > 0
    && eligibleEpisodes.every(ep => episodeSelected.has(ep.id))

  const toggleEpisode = (episodeId: number) => {
    setEpisodeSelected(prev => {
      const next = new Set(prev)
      if (next.has(episodeId)) next.delete(episodeId); else next.add(episodeId)
      return next
    })
  }

  // Only ever touches the eligible ones — "seleccionar todos" must not appear
  // to tick a card the user can't actually upload.
  const toggleAllEpisodes = () => {
    setEpisodeSelected(allEligibleSelected ? new Set() : new Set(eligibleEpisodes.map(ep => ep.id)))
  }

  // Un único sitio donde cambia lo que se sube. Si es otra cosa que antes se
  // descarta todo lo que colgaba de lo anterior (ajustes, caché de
  // nomenclatura, comprobaciones de la tanda); si es lo mismo (volver al paso 0
  // y pulsar Continuar) se conserva lo cargado y editado.
  const elegirSeleccion = (nueva: Seleccion) => {
    setSelError(null)
    if (!mismaSeleccion(seleccion, nueva)) {
      setSeleccion(nueva)
      setAjustesPorId(new Map())
      setEpisodeFieldsById(new Map())
      setBatchEnvChecks(null); setBatchContentChecks(new Map()); setBatchViewId(null)
      setBatchPhase('idle'); setBatchResults([])
      camposDe.current = null
      cargadoPara.current = null
    }
    setStep(1)
  }

  const confirmSeasonWhole = () => elegirSeleccion(seleccionUnica(item.id, true))

  const confirmEpisodeSelection = () => {
    if (episodeSelected.size === 0) { setSelError('Selecciona al menos un capítulo'); return }
    elegirSeleccion(seleccionCapitulos(episodes.filter(ep => episodeSelected.has(ep.id)).map(ep => ep.id)))
  }

  const toggleMultiSeason = (seasonId: number) => {
    setMultiSelected(prev => {
      const next = new Set(prev)
      if (next.has(seasonId)) next.delete(seasonId); else next.add(seasonId)
      return next
    })
  }

  const confirmMultiSelection = () => {
    if (multiSelected.size === 0) { setSelError('Selecciona al menos una temporada'); return }
    elegirSeleccion(seleccionTemporadas(seasons.filter(s => multiSelected.has(s.id)).map(s => s.id)))
  }

  // Lo editado en `fields` ahora mismo, tal como se guarda por elemento.
  const ajustesDeFields = (): Ajustes =>
    ({ source: fields.source, provider: fields.provider, tag: fields.tag, title: fields.title })
  const bancarAjustes = (id: number | null) => {
    const dueno = camposDe.current
    const ajustes = ajustesDeFields()
    setAjustesPorId(prev => conAjustes(prev, id, dueno, ajustes))
  }

  // Cambiar de temporada o capítulo en el desplegable del paso 1: antes de
  // irse se apuntan los ajustes del que sale (solo ocupa `fields` hasta
  // entonces), si de verdad son suyos.
  const cambiarElemento = (id: number) => {
    if (targetId != null && targetId !== id) bancarAjustes(targetId)
    setSeleccion(prev => conObjetivo(prev, id))
  }

  // "Ya existe una subida" precheck (ACTIVE_JOB_STATUSES /
  // _find_latest_job_for_item en upload_queue.py).
  const [existingJob, setExistingJob] = useState<UploadJob | null>(null)
  useEffect(() => {
    if (targetId == null) { setExistingJob(null); return }
    let alive = true
    getExistingJobForItem(targetId).then(j => { if (alive) setExistingJob(j) }).catch(() => { if (alive) setExistingJob(null) })
    return () => { alive = false }
  }, [targetId])
  const existingJobBlocking = !!existingJob && ACTIVE_JOB_STATUSES.has(existingJob.status)

  // Shared by the single-target load and the multi-episode cache, so both
  // paths put exactly the same things on screen.
  const applyFieldsResponse = useCallback((
    resp: Awaited<ReturnType<typeof getNomenclatureFields>>,
    saved: Ajustes | undefined,
    id: number,
  ) => {
    camposDe.current = id
    if (resp.blocked) {
      setError(resp.error || 'No se puede generar la nomenclatura.')
      setFields({})
      setInitialTag('')
      return
    }
    setError(null)
    // Restore this item's own previously-edited values instead of falling back
    // to what the backend auto-detected.
    setFields({
      ...(resp.fields || {}),
      ...(saved?.source !== undefined && saved.source !== null ? { source: saved.source } : {}),
      ...(saved?.provider !== undefined && saved.provider !== null ? { provider: saved.provider } : {}),
      ...(saved?.tag ? { tag: saved.tag } : {}),
      ...(sharedTitle ? { title: sharedTitle } : saved?.title ? { title: saved.title } : {}),
    })
    setInitialTag(saved?.tag || resp.fields?.tag || 'EMUWAREZ')
    setTitleWarning(resp.title_warning ?? null)
    setTitleOptions(resp.title_options ?? [])
    setSourceWarning(resp.source_warning ?? null)
    setSourceComparison(resp.source_comparison ?? null)
  }, [sharedTitle])

  // --- Step 1: load nomenclature for the resolved target ---
  const loadFields = useCallback(async () => {
    const id = targetId
    if (id == null) return
    setLoading(true); setError(null)
    try {
      const [srcResp, prvResp, fieldsResp] = await Promise.all([
        getEmuSources(), getEmuProviders(), getNomenclatureFields(id),
      ])
      if (objetivoActual.current !== id) return
      setSources(srcResp.sources)
      setProviders(prvResp.providers)
      applyFieldsResponse(fieldsResp, ajustesPorId.get(id), id)
    } catch (e: unknown) {
      if (objetivoActual.current === id) setError(e instanceof Error ? e.message : 'Error cargando la nomenclatura')
    } finally {
      if (objetivoActual.current === id) setLoading(false)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [targetId])   // NOT ajustesPorId: it changes on every switch, and
                   // depending on it would reload the fields on top of the
                   // edits it was just asked to restore.

  // Single target: load it. Multi-episode: the prefetch below owns it, so this
  // must not also fire and race with it.
  useEffect(() => {
    if (step === 1 && cargadoPara.current !== objetivo && !targetIsSeason && episodeQueue.length <= 1) loadFields()
  }, [step, objetivo, targetIsSeason, episodeQueue.length, loadFields])

  // Multi-episode: generate the nomenclature for every selected episode in one
  // pass, reporting which one it's on, and cache the results so switching
  // between them afterwards is instant.
  useEffect(() => {
    if (step !== 1 || targetIsSeason || episodeQueue.length <= 1) return
    if (cacheCubre(episodeQueue, episodeFieldsById)) return
    let alive = true
    const run = async () => {
      setEpisodePrepping(true); setEpisodePrepIndex(0); setError(null)
      try {
        const [srcResp, prvResp] = await Promise.all([getEmuSources(), getEmuProviders()])
        if (!alive) return
        setSources(srcResp.sources)
        setProviders(prvResp.providers)
        const cache = new Map<number, Awaited<ReturnType<typeof getNomenclatureFields>>>()
        for (let i = 0; i < episodeQueue.length; i++) {
          if (!alive) return
          setEpisodePrepIndex(i)
          try {
            cache.set(episodeQueue[i], await getNomenclatureFields(episodeQueue[i]))
          } catch (e: unknown) {
            // One episode failing must not sink the rest — it surfaces as its
            // own blocked entry when the user lands on it.
            cache.set(episodeQueue[i], {
              fields: {}, torrent_name: '', internal_mkv_title: '',
              blocked: true,
              error: e instanceof Error ? e.message : 'Error generando la nomenclatura',
            })
          }
        }
        if (!alive) return
        setEpisodeFieldsById(cache)
        const first = cache.get(episodeQueue[0])
        if (first) applyFieldsResponse(first, ajustesPorId.get(episodeQueue[0]), episodeQueue[0])
      } finally {
        if (alive) setEpisodePrepping(false)
      }
    }
    run()
    return () => { alive = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step, targetIsSeason, episodeQueue])

  // Switching between already-generated episodes reads the cache — no refetch.
  useEffect(() => {
    if (step !== 1 || targetIsSeason || targetId == null) return
    if (episodeQueue.length <= 1 || episodePrepping) return
    const cached = episodeFieldsById.get(targetId)
    if (cached) applyFieldsResponse(cached, ajustesPorId.get(targetId), targetId)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [targetId, episodePrepping])

  // --- Step 1 (season target): build the pack plan, polling progress while
  // it's in flight (real work per episode — build_nomenclature_proposal()).
  const loadSeasonPlan = useCallback(async () => {
    if (targetId == null) return
    const pedido = ++planPedido.current
    setSeasonPlanLoading(true); setSeasonPlanError(null)
    buildingPlanFor.current = targetId
    setSeasonProgress({ done: 0, total: 0, current_title: null })
    setSeasonTitlePreview(null)
    const pedirPlan = async () => {
      try { setSeasonProgress(await getSeasonPlanProgress(targetId)) } catch { /* fallo pasajero */ }
    }
    const dejarDeSeguirPlan = seguirProgreso(
      'plan-temporada-progreso', a => a.season_id === targetId, pedirPlan, 400)
    try {
      const [plan, srcResp, prvResp] = await Promise.all([
        previewSeasonPack(targetId), getEmuSources(), getEmuProviders(),
      ])
      if (pedido !== planPedido.current) return
      setSeasonPlan(plan)
      setSources(srcResp.sources)
      setProviders(prvResp.providers)
      // Source/Proveedor/Tag now editable (same dropdowns a movie/episode
      // shows) — seed `fields` from the pack's own resolved values so
      // setField('source'|'provider'|'tag', ...) below works the same way.
      // `season_episode` deliberately left unset (a season pack has no
      // single SxxExx, unlike one episode).
      // Multi-season: restore this season's own previously-edited Source/
      // Proveedor/Tag (if the user already visited it via the dropdown and
      // changed something) instead of always falling back to the plan's own
      // auto-detected values.
      const saved = ajustesPorId.get(targetId)
      camposDe.current = targetId
      setFields({
        title: sharedTitle ?? saved?.title ?? plan.series_title ?? undefined,
        year: plan.year != null ? String(plan.year) : undefined,
        resolution: plan.resolution ?? undefined,
        source: saved?.source ?? plan.source ?? undefined,
        provider: saved?.provider ?? plan.provider ?? undefined,
        video_codec: plan.video_codec ?? undefined,
        audio_summary: plan.audio_summary ?? undefined,
        subs: plan.subtitle_summary ?? undefined,
        tag: saved?.tag ?? plan.release_tag ?? undefined,
      })
      setInitialTag(saved?.tag || plan.release_tag || 'EMUWAREZ')
      setSourceComparison(plan.source_comparison ?? null)
      // 'cancelled' isn't a failure: the user closed the wizard mid-build and
      // the server stopped. Showing it as an error would flash a red message
      // over a modal that's already going away.
      if (plan.status !== 'valid' && plan.status !== 'cancelled') {
        setSeasonPlanError(plan.errors.join(' '))
      }
    } catch (e: unknown) {
      if (pedido !== planPedido.current) return
      setSeasonPlan(null)
      setSeasonPlanError(e instanceof Error ? e.message : 'Error preparando la temporada')
    } finally {
      dejarDeSeguirPlan()
      if (pedido === planPedido.current) {
        buildingPlanFor.current = null
        setSeasonPlanLoading(false)
      }
    }
  }, [targetId, ajustesPorId])

  // Closing the wizard while a season plan is being built has to stop the
  // server too: it runs one real nomenclature proposal per episode, so a 24
  // episode season kept the CPU busy long after the modal was gone. Wraps
  // EVERY exit (the ✕, the overlay click, Cancelar) — they all called onClose
  // directly before.
  const onClose = useCallback(() => {
    const seasonId = buildingPlanFor.current
    if (seasonId != null) {
      buildingPlanFor.current = null
      void cancelSeasonPackPreview(seasonId)
    }
    onCloseProp()
  }, [onCloseProp])
  // Lo que cierra el Modal (✕, Escape, clic fuera): no mientras se encola, que
  // el bucle seguiría sin que se viera el resultado ni se fuera a Subidas.
  const ocupado = uploading || batchPhase === 'processing'
  const cerrarModal = () => { if (!ocupado) onClose() }

  useEffect(() => {
    if (step === 1 && cargadoPara.current !== objetivo && targetIsSeason) loadSeasonPlan()
  }, [step, objetivo, targetIsSeason, loadSeasonPlan])

  // Las cargas siguientes no tocan nada si, al llegar la respuesta, el
  // objetivo ya es otro: era la de un elemento que ya no se está viendo.
  const loadSeasonNames = useCallback(async () => {
    const id = targetId
    if (id == null) return
    setSeasonNamesLoading(true)
    try {
      const overrides = { source: fields.source, provider: fields.provider, tag: fields.tag }
      const r = await getSeasonEpisodeNames(id, overrides)
      if (objetivoActual.current === id) setSeasonNames(r.episodes)
    }
    catch { if (objetivoActual.current === id) setSeasonNames(null) }
    finally { if (objetivoActual.current === id) setSeasonNamesLoading(false) }
  }, [targetId, fields.source, fields.provider, fields.tag])

  const loadSeasonMi = useCallback(async () => {
    const id = targetId
    if (id == null) return
    setSeasonMiLoading(true); setSeasonMiError(null)
    try {
      const r = await getSeasonEpisodeMediaInfo(id)
      if (objetivoActual.current === id) setSeasonMi(r.episodes)
    }
    catch (e: unknown) {
      if (objetivoActual.current === id) { setSeasonMi(null); setSeasonMiError(e instanceof Error ? e.message : 'Error cargando MediaInfo') }
    }
    finally { if (objetivoActual.current === id) setSeasonMiLoading(false) }
  }, [targetId])

  const loadSeasonRemux = useCallback(async () => {
    const id = targetId
    if (id == null) return
    setSeasonRemuxLoading(true); setSeasonRemuxError(null)
    try {
      const r = await getSeasonEpisodeRemuxPreview(id)
      if (objetivoActual.current === id) setSeasonRemux(r.episodes)
    }
    catch (e: unknown) {
      if (objetivoActual.current === id) { setSeasonRemux(null); setSeasonRemuxError(e instanceof Error ? e.message : 'Error calculando el remux') }
    }
    finally { if (objetivoActual.current === id) setSeasonRemuxLoading(false) }
  }, [targetId])

  // Reset all per-target state (both single-file and season) whenever the
  // resolved target changes — a different item means unrelated data.
  useEffect(() => {
    setMiReport(null); setMiError(null); setShowMiCard(false); setMiLoading(false)
    // Otro contenido, otras pistas: las ediciones a mano no se arrastran, que
    // haría que un capítulo heredara los nombres que escribiste para el
    // anterior sin decírtelo.
    setRemuxPreview(null); setRemuxError(null); setRemuxEdits({}); setShowRemuxCard(false); setRemuxLoading(false)
    setSeasonPlan(null); setSeasonPlanError(null)
    setSeasonNames(null); setShowSeasonNamesCard(false); setSeasonNamesLoading(false)
    setSeasonMi(null); setSeasonMiError(null); setMiEpisodeId(null); setSeasonMiLoading(false)
    setSeasonRemux(null); setSeasonRemuxError(null); setRemuxEpisodeId(null); setSeasonRemuxLoading(false)
  }, [targetId])

  // Season target: invalidate the cached per-episode names list whenever
  // Source/Proveedor/Tag change, so a stale (pre-edit) list isn't shown next
  // time "Ver nombre de todos los capítulos" is reopened — it must always
  // reflect the same override the season pack's own title uses.
  useEffect(() => {
    if (!targetIsSeason) return
    setSeasonNames(null)
  }, [targetIsSeason, fields.source, fields.provider, fields.tag])

  // Auto-detect the provider via TMDB when Source is WEB-DL and none was
  // detected from the filename. Debounced 500ms and fired at most once per
  // resolved target, so clicking "Subir" never triggers a burst of TMDB calls.
  useEffect(() => {
    if (targetIsSeason) return
    if (targetId == null || loading) return
    if (!PROVIDER_SOURCES.has(fields.source || '')) return
    if (fields.provider) return                       // already have one
    if (detectedTargetRef.current === targetId) return // already tried this item
    const t = setTimeout(async () => {
      detectedTargetRef.current = targetId            // lock before the call
      setDetectingProvider(true)
      try {
        const res = await suggestProvider(targetId)
        if (res.suggested) setField('provider', res.suggested)
      } catch { /* non-blocking — leave "Sin provider" */ }
      finally { setDetectingProvider(false) }
    }, 500)
    return () => clearTimeout(t)
  }, [targetId, targetIsSeason, loading, fields.source, fields.provider])

  const runMediaInfo = async () => {
    const id = targetId
    if (id == null) return
    setMiLoading(true); setMiError(null); setMiReport(null)
    try {
      const r = await getMediaInfoReport(id)
      if (objetivoActual.current === id) setMiReport(r)
    } catch (e: unknown) {
      if (objetivoActual.current === id) setMiError(e instanceof Error ? e.message : 'Error ejecutando MediaInfo')
    } finally {
      if (objetivoActual.current === id) setMiLoading(false)
    }
  }

  const runTrackRemux = useCallback(async () => {
    const id = targetId
    if (id == null) return
    setRemuxLoading(true); setRemuxError(null); setRemuxEdits({})
    try {
      const r = await previewTrackRemux(id)
      if (objetivoActual.current === id) setRemuxPreview(r)
    } catch (e: unknown) {
      if (objetivoActual.current === id) {
        setRemuxPreview(null)
        setRemuxError(e instanceof Error ? e.message : 'Error calculando el remux de pistas')
      }
    } finally {
      if (objetivoActual.current === id) setRemuxLoading(false)
    }
  }, [targetId])

  // Prefetch the track remux plan IN PARALLEL with the nomenclature fields
  // (reading a real .mkv's tracks — mkvmerge -J — can be slow over a remote
  // mount) so it's usually already loaded (or well underway) by the time the
  // user opens "Ver Pistas", instead of only starting the read on click.
  useEffect(() => {
    if (step === 1 && cargadoPara.current !== objetivo && !targetIsSeason) runTrackRemux()
  }, [step, objetivo, targetIsSeason, runTrackRemux])

  // Después de los efectos de carga, para que aún vean lo cargado antes.
  useEffect(() => { if (step === 1) cargadoPara.current = objetivo }, [step, objetivo])

  // Lo que el usuario haya escrito a mano en la tabla. No hace falta filtrarlo
  // por el modo: la columna solo es editable si el modo renombra, y el
  // servidor descarta las ediciones igualmente cuando no
  // (mkv_remux.py::apply_remux), que es lo que cubre el caso de cambiar el
  // ajuste con un trabajo ya encolado.
  const edicionesFinales = (): Record<number, TrackRemuxOverride> => remuxEdits

  const setRemuxEdit = (trackId: number, patch: TrackRemuxOverride) => {
    setRemuxEdits(prev => ({ ...prev, [trackId]: { ...prev[trackId], ...patch } }))
  }

  // Debounced live preview of the final torrent name + internal title.
  useEffect(() => {
    if (targetIsSeason) return
    if (targetId == null || !Object.keys(fields).length) return
    const t = setTimeout(async () => {
      try { setPreview(await previewNomenclatureFields(targetId, fields)) } catch { /* non-blocking */ }
    }, 400)
    return () => clearTimeout(t)
  }, [targetId, targetIsSeason, fields])

  // Season target: same debounced live recompute, but cheap (no disk/DB
  // work — just the title string, given the pack's own already-loaded base
  // values plus whatever Source/Proveedor/Tag the user is editing).
  useEffect(() => {
    if (!targetIsSeason) return
    if (targetId == null || !Object.keys(fields).length) return
    // '' = recalculando o sin título: nunca se enseña el de antes de editar.
    let vigente = true
    setSeasonTitlePreview('')
    const t = setTimeout(async () => {
      try {
        const r = await previewSeasonPackFields(targetId, {
          title: fields.title, year: fields.year ? Number(fields.year) : null,
          // seasonPlan?.season_number, NOT item.season_number — a season
          // opened from its series' own ficha (single or multi-season
          // picker) has `item` = the series, which has no season_number of
          // its own. Using it unconditionally silently dropped the "Sxx"
          // from the live-recomputed title in that case (regression: made
          // the title look like it was for the whole series).
          season_number: seasonPlan?.season_number ?? null,
          resolution: fields.resolution, source: fields.source, provider: fields.provider,
          video_codec: fields.video_codec, audio_summary: fields.audio_summary,
          subtitle_summary: fields.subs, tag: fields.tag,
          // El CUSTOM lo decide el plan comparando capítulos; editar
          // Source/Proveedor/Tag no lo cambia, pero hay que reenviarlo o el
          // título recalculado lo perdería.
          custom: seasonPlan?.custom ?? false,
        })
        if (vigente) setSeasonTitlePreview(r.torrent_name)
      } catch { /* non-blocking */ }
    }, 400)
    return () => { vigente = false; clearTimeout(t) }
  }, [targetId, targetIsSeason, fields, seasonPlan?.season_number, seasonPlan?.custom])

  const setField = (key: string, value: string | null) => {
    // Título is a property of the SERIES, so it is shared by every item in a
    // multi-episode or multi-season batch: picking it on episode 5 has to show
    // up on episode 1 too, and go up with all of them. Everything else
    // (Source, Proveedor, Tag) belongs to the individual file.
    if (key === 'title') setSharedTitle(value)
    setFields(prev => {
      const updated = { ...prev, [key]: value }
      if (key === 'source' && !PROVIDER_SOURCES.has(value || '')) updated.provider = null
      return updated
    })
  }

  const sourceRequiresProvider = PROVIDER_SOURCES.has(fields.source || '')

  // Entering step 2 only stores the edited fields and runs the read-only
  // checks. It does NOT apply the nomenclature nor create an upload job — a job
  // must only appear in "Subidas" once the user actually uploads.
  const goToUpload = async () => {
    if (targetId == null) return
    setPreparing(true); setUploadMsg(null)
    // saveNomenclatureFields persists into nomenclature_proposals, keyed by
    // a single library item — a season pack has no proposal row of its own
    // (source/provider/tag edits there flow through queueUpload's own
    // seasonOverrides param instead, applied uniformly across episodes).
    if (!targetIsSeason) {
      try { await saveNomenclatureFields(targetId, fields) } catch { /* non-blocking */ }
    }
    // Tanda: persist whichever item is still active when leaving step 1 —
    // "Subir todas" reads every OTHER item's edits from this same cache, but
    // the active one's latest edits only ever live in `fields`.
    if (esTanda(seleccion)) bancarAjustes(targetId)
    setPreparing(false)
    setStep(2)
    setBatchPhase('idle'); setBatchResults([])
    // "Subir todos" runs its own per-item checks — no single-target check to
    // kick off here.
    if (!esTanda(seleccion)) runChecks()
  }

  const canUpload = !!checks?.ready
  const uploadBtnTip = useTooltip(canUpload ? null : 'Alguna comprobación ha fallado o aún está en curso')
  // Queues the upload and hands off to Subidas immediately — nomenclature
  // rename, track remux, and the actual Uploadrr start all run server-side
  // afterwards (services/upload_queue.py), against the SAME job the user
  // lands on, with a grace period the user can still cancel from there.
  const doUpload = async () => {
    if (targetId == null || !canUpload) return
    setUploading(true); setUploadMsg(null)
    try {
      await saveNomenclatureFields(targetId, fields)
      const remuxSnapshot = remuxPreview
        ? { ordered_tracks: mergeRemuxTracks(remuxPreview, edicionesFinales()) }
        : null
      const r = await queueUpload(
        targetId, edicionesFinales(), checks, remuxSnapshot,
        targetIsSeason
          ? { source: fields.source, provider: fields.provider, tag: fields.tag, title: fields.title }
          : undefined,
        requestId,
      )
      if (r.status !== 'queued' || !r.job?.id) {
        setUploadMsg(`✗ No se pudo encolar la subida (estado: ${r.status}). ${(r.errors || []).join(' ')}`)
        return
      }
      onDone?.()
      onNavigate?.('uploads')
      onClose()
    } catch (e: unknown) {
      setUploadMsg(`✗ ${e instanceof Error ? e.message : 'Error encolando la subida'}`)
    } finally {
      setUploading(false)
    }
  }

  // Multi-season "Subir todas": checks + queues each chosen season in turn,
  // using whichever season is still active in `fields` for its own edits and
  // ajustesPorId for every other one already reviewed via the
  // dropdown. A season that fails its own check is skipped (not counted,
  // reason recorded) — the rest still go through, per explicit confirmation
  // this shouldn't block on one bad season.
  const uploadAllSeasons = async () => {
    const overridesMap = conAjustes(ajustesPorId, targetId, camposDe.current, ajustesDeFields())
    // Título is a property of the SERIES, and every season in this batch
    // belongs to the same one — so the pick applies to all of them, including
    // seasons the user never opened via the dropdown. Without this, choosing
    // the original title would silently upload season 1 as "The Tudors" and
    // the rest as "Los Tudor".
    const batchTitle = sharedTitle ?? fields.title
    if (batchTitle) {
      for (const seasonId of seasonQueue) {
        overridesMap.set(seasonId, { ...(overridesMap.get(seasonId) ?? {}), title: batchTitle })
      }
    }

    setBatchPhase('processing'); setBatchIndex(0); setBatchResults([])
    const results: typeof batchResults = []
    for (let i = 0; i < seasonQueue.length; i++) {
      const seasonId = seasonQueue[i]
      setBatchIndex(i)
      const s = seasons.find(x => x.id === seasonId)
      const title = s?.title || `Temporada ${s?.season_number ?? seasonId}`
      try {
        // Ya comprobado al entrar en el paso 2: el contenido de cada
        // temporada una vez, y el entorno una sola vez para toda la tanda. Si
        // por lo que sea no está cacheado, se hace la pasada completa.
        const checksResult = mergedChecksFor(seasonId) ?? await runUploadChecks(seasonId)
        if (!checksResult.ready) {
          const reason = checksResult.checks.find(c => c.status === 'fail')?.message || 'Alguna comprobación falló'
          results.push({ seasonId, title, status: 'failed', reason })
          continue
        }
        const r = await queueUpload(seasonId, undefined, checksResult, null, overridesMap.get(seasonId), s && peticionCubre(preselect, s) ? requestId : undefined)
        if (r.status !== 'queued' || !r.job?.id) {
          results.push({ seasonId, title, status: 'failed', reason: (r.errors || []).join(' ') || 'No se pudo encolar' })
        } else {
          results.push({ seasonId, title, status: 'queued' })
        }
      } catch (e: unknown) {
        results.push({ seasonId, title, status: 'failed', reason: e instanceof Error ? e.message : 'Error inesperado' })
      }
    }
    setBatchResults(results)
    setBatchPhase('done')
  }

  // Step 0 for a SEASON: pick how to upload it before picking what. The whole
  // pack and the per-episode selection answer to different rules, so they are
  // two cards and not two entries of one dropdown — only one of them can be
  // unavailable, and it needs room to say why.
  const seasonPackReason = seasonNotReadyReason(item)
  const seasonModeSelection = (
    <>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
        {([
          {
            key: 'whole' as const,
            title: 'Temporada entera',
            body: 'Un único release con todos los capítulos. Exige tenerlos todos, que coincidan en resolución y códec de vídeo, y que todos tengan audio en castellano o, si está en otro idioma, al menos subtítulos en castellano.',
            reason: seasonPackReason,
          },
          {
            key: 'episodes' as const,
            title: 'Selección de capítulos',
            body: 'Cada capítulo se sube por separado, con su propia nomenclatura, así que pueden diferir en resolución, códec o audio. Cada uno sigue necesitando audio en castellano o, si está en otro idioma, al menos subtítulos en castellano.',
            reason: eligibleEpisodes.length === 0
              ? 'Ningún capítulo de esta temporada cumple las condiciones de subida.'
              : null,
          },
        ]).map(m => {
          const enabled = !m.reason
          const selected = seasonUploadMode === m.key
          // Tarjeta seleccionable: el mismo control que usa el resto del
          // asistente para una elección de este tipo. Añade el resaltado del
          // elegido (se queda en pantalla tras pulsarlo) y el atenuado cuando
          // un modo no está disponible.
          const card = (
            <button
              className="btn btn-secondary"
              type="button"
              disabled={!enabled}
              onClick={() => setSeasonUploadMode(m.key)}
              style={{
                padding: '14px 14px', textAlign: 'left', display: 'flex', flexDirection: 'column',
                alignItems: 'flex-start', gap: 6, height: 'auto', width: '100%', minWidth: 0, whiteSpace: 'normal',
                cursor: enabled ? 'pointer' : 'not-allowed',
                opacity: enabled ? 1 : 0.45,
                ...(selected ? { background: 'color-mix(in srgb, var(--color-primary) 18%, transparent)', borderColor: 'var(--color-primary)' } : {}),
              }}
            >
              <span style={{ fontSize: 15, fontWeight: 700 }}>{m.title}</span>
              <span style={{ fontSize: 12, color: 'var(--text-muted)', fontWeight: 400, whiteSpace: 'normal' }}>{m.body}</span>
            </button>
          )
          return enabled
            ? <div key={m.key}>{card}</div>
            : <Tooltip key={m.key} content={m.reason} style={{ width: '100%' }}>{card}</Tooltip>
        })}
      </div>

      {seasonUploadMode === 'episodes' && (
        <div style={{ marginTop: 16 }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10, gap: 12, flexWrap: 'wrap' }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12.5, cursor: 'pointer' }}>
              <input type="checkbox" checked={allEligibleSelected} onChange={toggleAllEpisodes} />
              Seleccionar todos ({eligibleEpisodes.length})
            </label>
            <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
              {episodeSelected.size} seleccionado(s)
            </span>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(150px, 1fr))', gap: 10 }}>
            {episodes.map(ep => {
              const reason = episodeNotReadyReason(ep)
              const ready = !reason
              const selected = episodeSelected.has(ep.id)
              // Already on eMuwarez stays selectable on purpose: re-uploading a
              // better version is a legitimate thing to do, so it's a warning
              // and not a wall.
              const onEmu = ep.emu_in_catalog === 1
              const card = (
                <button
                  type="button"
                  disabled={!ready}
                  onClick={() => toggleEpisode(ep.id)}
                  style={{
                    width: '100%', padding: '12px 10px', borderRadius: 8, fontSize: 13, textAlign: 'center',
                    cursor: ready ? 'pointer' : 'not-allowed',
                    background: selected ? 'color-mix(in srgb, var(--color-primary) 18%, transparent)' : 'var(--bg-card)',
                    border: `1px solid ${selected ? 'var(--color-primary)' : 'var(--border-input)'}`,
                    color: 'var(--text-primary)', opacity: ready ? 1 : 0.45,
                    display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4, minWidth: 0,
                  }}
                >
                  {/* Truncated: an episode with no number falls back to its
                      title, and a long one would blow the grid cell out. */}
                  <span style={{
                    fontWeight: 600, maxWidth: '100%', overflow: 'hidden',
                    textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                  }}>
                    {ep.episode_number != null ? `E${String(ep.episode_number).padStart(2, '0')}` : ep.title}
                  </span>
                  {onEmu && (
                    <span style={{ fontSize: 11, color: 'var(--color-warning)' }}><IconoAviso /> ya en eMuwarez</span>
                  )}
                </button>
              )
              const tip = reason ?? (onEmu ? 'Ya existe en eMuwarez. Puedes subirlo igualmente (por ejemplo, una versión mejor).' : null)
              return tip
                ? <Tooltip key={ep.id} content={tip} style={{ width: '100%' }}>{card}</Tooltip>
                : <div key={ep.id}>{card}</div>
            })}
          </div>
        </div>
      )}
    </>
  )

  // Multi-episode "Subir todos": same shape as uploadAllSeasons, but an episode
  // carries its Título in its OWN nomenclature proposal (a season has none,
  // which is why that one travels as an override instead). And the save
  // endpoint rebuilds the whole proposal from what it's given rather than
  // merging, so each episode's current fields have to be read first and sent
  // back with the title swapped in — sending just the title would blank
  // everything else.
  const uploadAllEpisodes = async () => {
    const overridesMap = conAjustes(ajustesPorId, targetId, camposDe.current, ajustesDeFields())
    // Título belongs to the SERIES, so the pick applies to every episode in the
    // batch, including ones the user never opened via the dropdown.
    const batchTitle = sharedTitle ?? fields.title
    if (batchTitle) {
      for (const id of episodeQueue) {
        overridesMap.set(id, { ...(overridesMap.get(id) ?? {}), title: batchTitle })
      }
    }

    setBatchPhase('processing'); setBatchIndex(0); setBatchResults([])
    const results: typeof batchResults = []
    for (let i = 0; i < episodeQueue.length; i++) {
      const episodeId = episodeQueue[i]
      setBatchIndex(i)
      const ep = episodes.find(x => x.id === episodeId)
      const title = ep ? listDisplayTitle(ep) : `Capítulo ${episodeId}`
      try {
        const ov = overridesMap.get(episodeId)
        if (ov) {
          // Straight from the cache the step-1 pass already built — the save
          // endpoint rebuilds the whole proposal from what it's given rather
          // than merging, so it needs the episode's full field set, not just
          // the overridden bits.
          const current = episodeFieldsById.get(episodeId) ?? await getNomenclatureFields(episodeId)
          if (!current.blocked) {
            await saveNomenclatureFields(episodeId, {
              ...(current.fields || {}),
              ...(ov.source !== undefined && ov.source !== null ? { source: ov.source } : {}),
              ...(ov.provider !== undefined && ov.provider !== null ? { provider: ov.provider } : {}),
              ...(ov.tag ? { tag: ov.tag } : {}),
              ...(ov.title ? { title: ov.title } : {}),
            })
          }
        }
        // Igual que las temporadas: se reutiliza lo comprobado al entrar en
        // el paso 2 en vez de repetir las 4 de entorno por cada capítulo.
        const checksResult = mergedChecksFor(episodeId) ?? await runUploadChecks(episodeId)
        if (!checksResult.ready) {
          const reason = checksResult.checks.find(c => c.status === 'fail')?.message || 'Alguna comprobación falló'
          results.push({ seasonId: episodeId, title, status: 'failed', reason })
          continue
        }
        const r = await queueUpload(episodeId, undefined, checksResult, null, undefined, ep && peticionCubre(preselect, ep) ? requestId : undefined)
        if (r.status !== 'queued' || !r.job?.id) {
          results.push({ seasonId: episodeId, title, status: 'failed', reason: (r.errors || []).join(' ') || 'No se pudo encolar' })
        } else {
          results.push({ seasonId: episodeId, title, status: 'queued' })
        }
      } catch (e: unknown) {
        results.push({ seasonId: episodeId, title, status: 'failed', reason: e instanceof Error ? e.message : 'Error inesperado' })
      }
    }
    setBatchResults(results)
    setBatchPhase('done')
  }

  // Step 0 de una serie: la lista de temporadas a marcar.
  // Only a season with EVERY episode Disponible AND every episode agreeing
  // on codec/audio/idiomas/subs/resolución/source can go as a season pack
  // (build_season_pack_plan() blocks otherwise) — incomplete/inconsistent
  // ones are shown greyed out and unselectable instead of letting the user
  // pick one and fail later. isSeasonReady/seasonNotReadyReason (shared with
  // LibraryActionButtons' own "Subir" button) only know about the
  // consistency check; the "incomplete" message is layered on here.
  const selectableSeasons = seasons.filter(isSeasonReady)
  // The series' own name is redundant here (already the wizard's title) —
  // just the season part, e.g. "Temporada 1"/"Especiales".
  const seasonCardLabel = (s: LibraryItemResponse) => {
    const prefix = `${item.title} - `
    if (s.title?.startsWith(prefix)) return s.title.slice(prefix.length)
    return s.season_number === 0 ? 'Especiales' : `Temporada ${s.season_number}`
  }
  const multiSeasonChecklist = (
    <div>
      <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, marginBottom: 10 }}>
        <input
          type="checkbox"
          checked={selectableSeasons.length > 0 && multiSelected.size === selectableSeasons.length}
          onChange={e => setMultiSelected(e.target.checked ? new Set(selectableSeasons.map(s => s.id)) : new Set())}
        />
        Seleccionar todas
      </label>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(150px, 1fr))', gap: 10, maxHeight: 320, overflowY: 'auto' }}>
        {seasons.map(s => {
          const ready = isSeasonReady(s)
          const reason = seasonNotReadyReason(s)
          const selected = multiSelected.has(s.id)
          const card = (
            <button
              type="button"
              disabled={!ready}
              onClick={() => toggleMultiSeason(s.id)}
              style={{
                width: '100%', padding: '16px 12px', borderRadius: 8, fontSize: 13, textAlign: 'center', cursor: ready ? 'pointer' : 'not-allowed',
                background: selected ? 'color-mix(in srgb, var(--color-primary) 18%, transparent)' : 'var(--bg-card)',
                border: `1px solid ${selected ? 'var(--color-primary)' : 'var(--border-input)'}`,
                color: 'var(--text-primary)', opacity: ready ? 1 : 0.45,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}
            >
              <span style={{ fontWeight: 600 }}>{seasonCardLabel(s)}</span>
            </button>
          )
          return ready ? (
            <div key={s.id}>{card}</div>
          ) : (
            <Tooltip key={s.id} content={reason} style={{ width: '100%' }}>
              {card}
            </Tooltip>
          )
        })}
      </div>
    </div>
  )

  // "Ya existe una subida" — shown at the top of step 1 once the target
  // resolves. Never blocks continuing unless the existing job is still
  // active (queued/staging/preparing/running); a terminal one (Completado/
  // Fallido/Cancelado) just informs — the new job chains onto it either way
  // (services/upload_queue.py's _find_latest_job_for_item).
  const existingJobNotice = existingJob && (
    <div style={{
      marginBottom: 14, padding: '10px 14px', borderRadius: 8, fontSize: 12.5, display: 'flex',
      alignItems: 'center', gap: 10, flexWrap: 'wrap',
      background: existingJobBlocking ? 'color-mix(in srgb, var(--color-error-soft) 10%, transparent)' : 'color-mix(in srgb, var(--text-accent) 10%, transparent)',
      border: `1px solid ${existingJobBlocking ? 'color-mix(in srgb, var(--color-error-soft) 30%, transparent)' : 'color-mix(in srgb, var(--text-accent) 30%, transparent)'}`,
    }}>
      <span>
        {existingJobBlocking
          ? `Ya hay una subida en curso para este contenido (${statusLabel(existingJob.status)}). Espera a que termine o cancélala antes de continuar.`
          : `Ya existe este contenido (${statusLabel(existingJob.status)}) en Subidas. Si continúas, esta nueva subida se encadenará a su historial.`}
      </span>
    </div>
  )

  const fieldBox = (
    <>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px 16px' }}>
        <label><FieldLabel label="Título" info={FIELD_INFO.title} />
          {/* Spanish by default (it leads title_options), original as the
              alternative. Falls back to the old read-only input when the
              backend couldn't offer a choice at all, so the field never
              silently turns into an empty select. */}
          {titleOptions.length > 0 ? (
            <select
              className="form-input form-select"
              value={fields.title || ''}
              onChange={e => setField('title', e.target.value)}
              disabled={titleOptions.length < 2}
            >
              {titleOptions.map(o => (
                <option key={o.value} value={o.value}>{o.label}: {o.value}</option>
              ))}
            </select>
          ) : (
            <input className="form-input" value={fields.title || ''} disabled />
          )}
          {titleWarning && (
            <span style={{ display: 'block', marginTop: 4, fontSize: 11, color: 'var(--color-warning)' }}><IconoAviso /> {titleWarning}</span>
          )}
        </label>
        <label><FieldLabel label="Año" info={FIELD_INFO.year} />
          <input className="form-input" value={fields.year || ''} disabled />
        </label>
        {fields.season_episode != null && (
          <label><FieldLabel label="Temporada / Episodio" info={FIELD_INFO.season_episode} />
            {/* Read-only like every other derived field here (Año, Resolución,
                códecs): it comes straight from Sonarr's season/episode numbers
                for THIS file. Editing it let you name a file S03E07 when it is
                actually S01E02, and the upload renames the real file to
                whatever this says — a typo here mislabels the release and the
                file on disk. Only Source, Proveedor and Tag are meant to be
                editable, and those are genuine judgement calls. */}
            <input className="form-input" value={fields.season_episode || ''} disabled />
          </label>
        )}
        <label><FieldLabel label="Resolución" info={FIELD_INFO.resolution} />
          <input className="form-input" value={fields.resolution || ''} disabled />
        </label>
        <label><FieldLabel label="Source" info={FIELD_INFO.source} />
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <select className="form-input form-select" style={{ flex: 1 }} value={fields.source || ''} onChange={e => setField('source', e.target.value)}>
              <option value="">— Seleccionar —</option>
              {sources.map(s => <option key={s.code} value={s.code}>{s.label}</option>)}
            </select>
            {sourceComparison && (
              <Tooltip content={sourceComparison.agree
                ? 'Nombre, Radarr/Sonarr y MediaInfo coinciden en el source. Clic para ver el detalle.'
                : 'El source no coincide entre el nombre del archivo, Radarr/Sonarr y MediaInfo. Clic para comparar.'}>
                <button
                  type="button"
                  onClick={() => { setShowEngineDetail(false); setShowSourceCompare(v => !v) }}
                  style={{
                    display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                    width: 34, height: 34, background: 'none', border: 'none', cursor: 'pointer',
                    padding: 0, flexShrink: 0,
                  }}
                >
                  <span
                    className={sourceComparison.agree ? undefined : 'badge-blink'}
                    style={{ display: 'inline-flex', color: sourceComparison.agree ? 'var(--text-accent)' : 'var(--color-req-pending)' }}
                  >
                    <svg aria-hidden="true" width="34" height="34" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <rect x="2" y="5" width="20" height="14" rx="4" />
                      <path d="M10 9.3v5.4l5-2.7z" fill="currentColor" stroke="none" />
                    </svg>
                  </span>
                </button>
              </Tooltip>
            )}
          </div>
          {sourceWarning && (
            <span style={{ display: 'block', marginTop: 4, fontSize: 11, color: 'var(--color-warning)' }}><IconoAviso /> {sourceWarning}</span>
          )}
        </label>
        {showSourceCompare && sourceComparison && (
          <SourceComparisonModal
            comparison={sourceComparison}
            initialShowDetail={showEngineDetail}
            onClose={() => setShowSourceCompare(false)}
          />
        )}
        {sourceRequiresProvider && (
          <label><FieldLabel label="Proveedor" info={FIELD_INFO.provider} />
            {detectingProvider ? (
              <div className="form-input" style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--text-muted)' }}>
                <span className="spinner" style={{ width: 12, height: 12, borderWidth: 2 }} /> Detectando…
              </div>
            ) : (
              <select className="form-input form-select" value={fields.provider || ''} onChange={e => setField('provider', e.target.value || null)}>
                <option value="">— Sin proveedor —</option>
                {providers.map(p => <option key={p.code} value={p.code}>{p.name} ({p.code})</option>)}
              </select>
            )}
          </label>
        )}
        <label><FieldLabel label="Códec de vídeo" info={FIELD_INFO.video_codec} />
          <input className="form-input" value={fields.video_codec || ''} disabled />
        </label>
        <label><FieldLabel label="Audio" info={FIELD_INFO.audio} />
          <input className="form-input" value={fields.audio_summary || ''} disabled />
        </label>
        <label><FieldLabel label="Subtítulos" info={FIELD_INFO.subs} />
          <input className="form-input" value={fields.subs || ''} disabled />
        </label>
        <label><FieldLabel label="Tag" info={FIELD_INFO.tag} />
          <select className="form-input form-select" value={fields.tag || ''} onChange={e => setField('tag', e.target.value)}>
            {opcionesTag.map(t => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
        </label>
      </div>
      <div className="detail-card" style={{ marginTop: 16, padding: '12px 14px', borderRadius: 8 }}>
        {preview?.torrent_name && preview?.internal_mkv_title ? (
          <FitTextPair
            min={9}
            items={[
              { label: 'Nombre final del torrent (eMuwarez)', text: preview.torrent_name, labelStyle },
              { label: INTERNAL_TITLE_LABEL, text: preview.internal_mkv_title, labelStyle },
            ]}
          />
        ) : (
          <>
            <div style={labelStyle}>Nombre final del torrent (eMuwarez)</div>
            <GeneratingHint />
            <div style={{ ...labelStyle, marginTop: 10 }}>{INTERNAL_TITLE_LABEL}</div>
            <GeneratingHint />
          </>
        )}
      </div>
    </>
  )

  // Season target: same field-by-field confirmation grid a movie/episode
  // shows. Título/Año/Resolución/Códec/Audio/Subtítulos stay read-only (read
  // straight from the actual files — every episode already has to agree, or
  // build_season_pack_plan blocks otherwise). Source/Proveedor/Tag are
  // editable exactly like a movie/episode: applied uniformly across every
  // episode (source_override/provider_override/tag_override) instead of
  // being stuck with whatever the filename/Radarr-Sonarr happened to say —
  // the same kind of misdetection the Internal Source Tool exists to catch.
  const seasonTitleOptions = seasonPlan?.title_options ?? []

  const seasonFieldBox = (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px 16px' }}>
      <label><FieldLabel label="Título" info={FIELD_INFO.title} />
        {seasonTitleOptions.length > 0 ? (
          <select
            className="form-input form-select"
            value={fields.title || seasonPlan?.series_title || ''}
            onChange={e => setField('title', e.target.value)}
            disabled={seasonTitleOptions.length < 2}
          >
            {seasonTitleOptions.map(o => (
              <option key={o.value} value={o.value}>{o.label}: {o.value}</option>
            ))}
          </select>
        ) : (
          <input className="form-input" value={seasonPlan?.series_title || ''} disabled />
        )}
      </label>
      <label><FieldLabel label="Año" info={FIELD_INFO.year} />
        <input className="form-input" value={seasonPlan?.year ?? ''} disabled />
      </label>
      <label><FieldLabel label="Resolución" info={FIELD_INFO.resolution} />
        <input className="form-input" value={seasonPlan?.resolution || ''} disabled />
      </label>
      <label><FieldLabel label="Source" info={FIELD_INFO.source} />
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <select className="form-input form-select" style={{ flex: 1 }} value={fields.source || ''} onChange={e => setField('source', e.target.value)}>
            <option value="">— Seleccionar —</option>
            {sources.map(s => <option key={s.code} value={s.code}>{s.label}</option>)}
          </select>
          {sourceComparison && (
            <Tooltip content={sourceComparison.agree
              ? 'Nombre, Radarr/Sonarr y MediaInfo coinciden en el source (capítulo representativo). Clic para ver el detalle.'
              : 'El source no coincide entre el nombre del archivo, Radarr/Sonarr y MediaInfo (capítulo representativo). Clic para comparar.'}>
              <button
                type="button"
                onClick={() => { setShowEngineDetail(false); setShowSourceCompare(v => !v) }}
                style={{
                  display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                  width: 34, height: 34, background: 'none', border: 'none', cursor: 'pointer',
                  padding: 0, flexShrink: 0,
                }}
              >
                <span
                  className={sourceComparison.agree ? undefined : 'badge-blink'}
                  style={{ display: 'inline-flex', color: sourceComparison.agree ? 'var(--text-accent)' : 'var(--color-req-pending)' }}
                >
                  <svg aria-hidden="true" width="34" height="34" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <rect x="2" y="5" width="20" height="14" rx="4" />
                    <path d="M10 9.3v5.4l5-2.7z" fill="currentColor" stroke="none" />
                  </svg>
                </span>
              </button>
            </Tooltip>
          )}
        </div>
      </label>
      {showSourceCompare && sourceComparison && (
        <SourceComparisonModal
          comparison={sourceComparison}
          initialShowDetail={showEngineDetail}
          onClose={() => setShowSourceCompare(false)}
        />
      )}
      {sourceRequiresProvider && (
        <label><FieldLabel label="Proveedor" info={FIELD_INFO.provider} />
          <select className="form-input form-select" value={fields.provider || ''} onChange={e => setField('provider', e.target.value || null)}>
            <option value="">— Sin proveedor —</option>
            {providers.map(p => <option key={p.code} value={p.code}>{p.name} ({p.code})</option>)}
          </select>
        </label>
      )}
      <label><FieldLabel label="Códec de vídeo" info={FIELD_INFO.video_codec} />
        <input className="form-input" value={seasonPlan?.video_codec || ''} disabled />
      </label>
      <label><FieldLabel label="Audio" info={FIELD_INFO.audio} />
        <input className="form-input" value={seasonPlan?.audio_summary || ''} disabled />
      </label>
      <label><FieldLabel label="Subtítulos" info={FIELD_INFO.subs} />
        <input className="form-input" value={seasonPlan?.subtitle_summary || ''} disabled />
      </label>
      <label><FieldLabel label="Tag" info={FIELD_INFO.tag} />
        <select className="form-input form-select" value={fields.tag || ''} onChange={e => setField('tag', e.target.value)}>
          {opcionesTag.map(t => (
            <option key={t} value={t}>{t}</option>
          ))}
        </select>
      </label>
    </div>
  )

  // Just the single pack torrent name (no per-file "internal title" at
  // season level, see "Ver nombre de todos los capítulos" instead) plus a
  // summary of the episodes included.
  const seasonDisplayTitle = seasonTitlePreview ?? seasonPlan?.season_pack_title
  const seasonSummaryBox = (
    <>
      <div className="detail-card" style={{ marginTop: 16, padding: '12px 14px', borderRadius: 8 }}>
        {seasonDisplayTitle ? (
          <FitText min={9} text={seasonDisplayTitle} />
        ) : (
          <>
            <div style={labelStyle}>Nombre final del torrent (eMuwarez)</div>
            <GeneratingHint />
          </>
        )}
      </div>
      {seasonPlan?.status === 'valid' && (
        <div style={{ marginTop: 12, fontSize: 12, color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
          <span>✓ {seasonPlan.episodes.length} capítulo(s) listos, coherentes entre sí</span>
          <button
            className="btn btn-secondary btn-sm"
            type="button"
            onClick={() => { setShowSeasonNamesCard(true); setSeasonNamesEpisodeId(null); if (!seasonNames && !seasonNamesLoading) loadSeasonNames() }}
          >
            Ver nombre de todos los capítulos
          </button>
        </div>
      )}
    </>
  )

  return (
    <Modal titulo={item.title} onClose={cerrarModal} className="modal-wide" style={{ maxWidth: 900 }}>

      <div style={{ display: 'flex', gap: 8, padding: '0 20px', marginTop: 8, fontSize: 12, flexWrap: 'wrap' }}>
        {needsSelection && <><span style={{ fontWeight: step === 0 ? 700 : 400, color: step === 0 ? 'var(--text)' : 'var(--text-muted)' }}>0. Selección</span><span style={{ color: 'var(--text-muted)' }}>→</span></>}
        <span style={{ fontWeight: step === 1 ? 700 : 400, color: step === 1 ? 'var(--text)' : 'var(--text-muted)' }}>1. Nomenclatura</span>
        <span style={{ color: 'var(--text-muted)' }}>→</span>
        <span style={{ fontWeight: step === 2 ? 700 : 400, color: step === 2 ? 'var(--text)' : 'var(--text-muted)' }}>2. Subida a eMuwarez</span>
      </div>

      {step === 0 && (
        <div className="modal-body">
          <p className="text-muted" style={{ fontSize: 12, marginBottom: 12 }}>
            {allowMultiSeason
              ? <>Elige qué temporada(s) de <strong>{item.title}</strong> subir.</>
              : <>Elige cómo subir <strong>{item.title}</strong>.</>}
          </p>
          {allowMultiSeason ? multiSeasonChecklist : seasonModeSelection}
          {selError && <p className="text-error" style={{ marginTop: 10 }}>{selError}</p>}
          <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 16 }}>
            <button
              className="btn btn-primary"
              disabled={!allowMultiSeason && seasonUploadMode === null}
              onClick={
                allowMultiSeason ? confirmMultiSelection
                : seasonUploadMode === 'episodes' ? confirmEpisodeSelection : confirmSeasonWhole
              }
              type="button"
            >Continuar</button>
          </div>
        </div>
      )}

      {step === 1 && targetIsSeason && (
        <div className="modal-body">
          {seasonQueue.length > 1 && (
            <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 12 }}>
              <select
                className="form-input form-select" style={{ width: 'auto' }}
                value={targetId ?? ''} onChange={e => cambiarElemento(Number(e.target.value))}
                disabled={seasonPlanLoading}
              >
                {seasonQueue.map(id => {
                  const s = seasons.find(x => x.id === id)
                  return <option key={id} value={id}>{s?.title || `Temporada ${s?.season_number ?? id}`}</option>
                })}
              </select>
            </div>
          )}
          {existingJobNotice}
          {seasonPlanLoading && (
            <div style={{ padding: '36px 0', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 12 }}>
              <span className="spinner" style={{ width: 28, height: 28, borderWidth: 3 }} />
              <div style={{ fontSize: 15, fontWeight: 600 }}>
                {seasonProgress.total > 0
                  ? `Generando Nomenclatura para eMuwarez… (${seasonProgress.done} de ${seasonProgress.total} capítulos)`
                  : 'Generando Nomenclatura para eMuwarez…'}
              </div>
              {seasonProgress.current_title && (
                <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>{seasonProgress.current_title}</div>
              )}
            </div>
          )}
          {seasonPlanError && !seasonPlanLoading && (
            <div style={{ padding: '20px 0' }}>
              <p className="text-error" style={{ marginTop: 0, marginBottom: 10 }}><IconoAviso /> {seasonPlanError}</p>
              <button className="btn btn-secondary btn-sm" type="button" onClick={loadSeasonPlan}>↻ Reintentar</button>
            </div>
          )}
          {!seasonPlanLoading && !seasonPlanError && seasonPlan && (
            <>
              <p className="text-muted" style={{ fontSize: 12, marginBottom: 12 }}>
                Se sube como un único pack de temporada. Todos los capítulos deben tener el mismo códec
                de audio/vídeo, los mismos idiomas de audio/subtítulos, la misma resolución y source —
                estos campos confirman que todos coinciden. Source, Proveedor y Tag se pueden corregir
                a mano si el detectado no es correcto (se aplica a todos los capítulos por igual).
              </p>
              {seasonFieldBox}
              {seasonSummaryBox}

              <div style={{ marginTop: 20, paddingTop: 16, borderTop: '1px solid var(--border)' }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
                  <div>
                    <div style={{ fontSize: 13, fontWeight: 600 }}>MediaInfo y pistas de los capítulos</div>
                    <div className="text-muted" style={{ fontSize: 11, marginTop: 2 }}>
                      Se elige capítulo con un desplegable, cada uno con su propio detalle de MediaInfo y
                      su propio plan de reordenación/renombrado de pistas (sin edición manual para temporadas).
                    </div>
                  </div>
                  <div style={{ display: 'flex', gap: 8, flexShrink: 0 }}>
                    <button className="btn btn-primary" onClick={() => { setShowMiCard(true); if (!seasonMi && !seasonMiLoading) loadSeasonMi() }} disabled={targetId == null}>
                      Ver MediaInfo
                    </button>
                    <button className="btn btn-primary" onClick={() => { setShowRemuxCard(true); if (!seasonRemux && !seasonRemuxLoading) loadSeasonRemux() }} disabled={targetId == null}>
                      Ver Pistas
                    </button>
                  </div>
                </div>
              </div>

              {showMiCard && (
                <Modal titulo="MediaInfo de los capítulos" onClose={() => setShowMiCard(false)} className="modal-wide" style={{ maxWidth: 900 }}>
                  <div className="modal-body">
                    {seasonMiLoading && !seasonMi && <TableLoadingSpinner label="Leyendo MediaInfo de cada capítulo…" />}
                    {seasonMiError && !seasonMiLoading && (
                      <>
                        <p className="text-error" style={{ fontSize: 12, marginTop: 0, marginBottom: 10 }}>✗ {seasonMiError}</p>
                        <button className="btn btn-secondary btn-sm" type="button" onClick={loadSeasonMi}>↻ Reintentar</button>
                      </>
                    )}
                    {seasonMi && seasonMi.length > 0 && (() => {
                      const current = seasonMi.find(e => e.episode_id === miEpisodeId) ?? seasonMi[0]
                      return (
                        <>
                          <EpisodePicker episodes={seasonMi} currentId={current.episode_id} onChange={setMiEpisodeId} />
                          <MediaInfoTable
                            report={current.report}
                            onSourceToolClick={current.source_comparison ? () => {
                              setShowMiCard(false)
                              setSourceComparison(current.source_comparison!)
                              setShowEngineDetail(true)
                              setShowSourceCompare(true)
                            } : undefined}
                          />
                        </>
                      )
                    })()}
                  </div>
                </Modal>
              )}
              {showSourceCompare && sourceComparison && (
                <SourceComparisonModal
                  comparison={sourceComparison}
                  initialShowDetail={showEngineDetail}
                  onClose={() => setShowSourceCompare(false)}
                />
              )}

              {showRemuxCard && (
                <Modal
                  titulo={<>
                    Ordenación y Nombre de las Pistas por Capítulo
                    <AvisoModoPistas plan={seasonRemux?.[0]?.plan} />
                  </>}
                  onClose={() => setShowRemuxCard(false)}
                  className="modal-wide"
                  style={{ maxWidth: 780 }}
                  tituloStyle={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}
                >
                  <div className="modal-body">
                    {seasonRemuxLoading && !seasonRemux && <TableLoadingSpinner label="Calculando las pistas de cada capítulo…" />}
                    {seasonRemuxError && !seasonRemuxLoading && (
                      <>
                        <p className="text-error" style={{ fontSize: 12, marginTop: 0, marginBottom: 10 }}>✗ {seasonRemuxError}</p>
                        <button className="btn btn-secondary btn-sm" type="button" onClick={loadSeasonRemux}>↻ Reintentar</button>
                      </>
                    )}
                    {seasonRemux && seasonRemux.length > 0 && (() => {
                      const current = seasonRemux.find(e => e.episode_id === remuxEpisodeId) ?? seasonRemux[0]
                      return (
                        <>
                          <EpisodePicker episodes={seasonRemux} currentId={current.episode_id} onChange={setRemuxEpisodeId} />
                          <RemuxTable plan={current.plan} editable={false} />
                        </>
                      )
                    })()}
                  </div>
                </Modal>
              )}

              {showSeasonNamesCard && (
                <Modal titulo="Nombre de todos los capítulos" onClose={() => setShowSeasonNamesCard(false)} className="modal-wide" style={{ maxWidth: 900 }}>
                  <div className="modal-body">
                    {seasonNamesLoading && !seasonNames && <TableLoadingSpinner label="Generando el nombre de cada capítulo…" />}
                    {seasonNames && seasonNames.length > 0 && (() => {
                      const current = seasonNames.find(e => e.episode_id === seasonNamesEpisodeId) ?? seasonNames[0]
                      return (
                        <>
                          {seasonNames.length > 1 && (
                            <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 12 }}>
                              <select
                                className="form-input form-select" style={{ width: 'auto' }}
                                value={current.episode_id}
                                onChange={e => setSeasonNamesEpisodeId(Number(e.target.value))}
                              >
                                {seasonNames.map(ep => (
                                  <option key={ep.episode_id} value={ep.episode_id}>{ep.display_title}</option>
                                ))}
                              </select>
                            </div>
                          )}
                          {current.error ? (
                            <p className="text-error" style={{ fontSize: 12, margin: 0 }}>✗ {current.error}</p>
                          ) : (
                            <FitTextPair
                              min={9}
                              items={[
                                { label: 'Nombre del torrent', text: current.torrent_name || '—', labelStyle },
                                { label: INTERNAL_TITLE_LABEL, text: current.internal_mkv_title || '—', labelStyle },
                              ]}
                            />
                          )}
                        </>
                      )
                    })()}
                  </div>
                </Modal>
              )}

              <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 16 }}>
                {needsSelection
                  ? <button className="btn btn-secondary" onClick={() => setStep(0)}>Volver a la selección</button>
                  : <span />}
                <button className="btn btn-primary" onClick={goToUpload} disabled={preparing || seasonPlan.status !== 'valid' || existingJobBlocking}>
                  {preparing ? 'Preparando…' : 'Continuar'}
                </button>
              </div>
            </>
          )}
        </div>
      )}

      {step === 1 && !targetIsSeason && (
        <div className="modal-body">
          {episodeQueue.length > 1 && (
            <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 12 }}>
              <select
                className="form-input form-select" style={{ width: 'auto' }}
                value={targetId ?? ''} onChange={e => cambiarElemento(Number(e.target.value))}
                disabled={episodePrepping}
              >
                {/* Canonical "Serie (Año) - SxxExx", same format the rest
                    of the app uses for an episode. */}
                {episodeQueue.map(id => {
                  const ep = episodes.find(x => x.id === id)
                  return <option key={id} value={id}>{ep ? listDisplayTitle(ep) : id}</option>
                })}
              </select>
            </div>
          )}
          {existingJobNotice}
          {episodePrepping && (
            <div style={{ padding: '36px 0', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 12 }}>
              <span className="spinner" style={{ width: 28, height: 28, borderWidth: 3 }} />
              <div style={{ fontSize: 15, fontWeight: 600 }}>Generando Nomenclatura para eMuwarez…</div>
              <div style={{ fontSize: 12.5, color: 'var(--text-muted)' }}>
                Capítulo {Math.min(episodePrepIndex + 1, episodeQueue.length)} de {episodeQueue.length}
                {(() => {
                  const ep = episodes.find(x => x.id === episodeQueue[episodePrepIndex])
                  return ep ? `: ${listDisplayTitle(ep)}` : ''
                })()}
              </div>
            </div>
          )}
          {loading && !episodePrepping && (
            <div style={{ padding: '36px 0', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 12 }}>
              <span className="spinner" style={{ width: 28, height: 28, borderWidth: 3 }} />
              <div style={{ fontSize: 15, fontWeight: 600 }}>Generando Nomenclatura para eMuwarez…</div>
            </div>
          )}
          {error && !loading && !episodePrepping && (
            <div style={{ padding: '20px 0' }}>
              <p className="text-error" style={{ marginTop: 0, marginBottom: 10 }}><IconoAviso /> {error}</p>
              <button className="btn btn-secondary btn-sm" type="button" onClick={loadFields}>↻ Reintentar</button>
            </div>
          )}
          {!loading && !error && !episodePrepping && (
            <>
              <p className="text-muted" style={{ fontSize: 12, marginBottom: 12 }}>
                Los campos técnicos (audio por pista, códec, HDR/DV) se leen con MediaInfo del archivo
                real; el título/año vienen de Radarr/Sonarr y el Source/Provider del nombre del archivo.
                Puedes ajustar cualquier campo, o ver el detalle de MediaInfo abajo.
              </p>
              {fieldBox}

              <div style={{ marginTop: 20, paddingTop: 16, borderTop: '1px solid var(--border)' }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
                  <div>
                    <div style={{ fontSize: 13, fontWeight: 600 }}>MediaInfo y pistas del archivo</div>
                    <div className="text-muted" style={{ fontSize: 11, marginTop: 2 }}>
                      Ver Pistas: muestra la reordenación y el nombre de las pistas de vídeo/audio/subtítulos del contenido (editable).
                      <br />
                      Ver MediaInfo: muestra el detalle técnico real del archivo.
                    </div>
                  </div>
                  <div style={{ display: 'flex', gap: 8, flexShrink: 0 }}>
                    <button className="btn btn-primary" onClick={() => { runMediaInfo(); setShowMiCard(true) }} disabled={targetId == null}>
                      Ver MediaInfo
                    </button>
                    <button
                      className="btn btn-primary"
                      onClick={() => {
                        setShowRemuxCard(true)
                        if (!remuxPreview && !remuxLoading) runTrackRemux()
                      }}
                      disabled={targetId == null}
                    >
                      Ver Pistas
                    </button>
                  </div>
                </div>
              </div>

              {showMiCard && (
                <Modal titulo="MediaInfo del archivo" onClose={() => setShowMiCard(false)} className="modal-wide" style={{ maxWidth: 900 }}>
                  <div className="modal-body">
                    {miLoading && !miReport && <TableLoadingSpinner label="Cargando MediaInfo…" />}
                    {miError && !miLoading && (
                      <>
                        <p className="text-error" style={{ fontSize: 12, marginTop: 0, marginBottom: 10 }}>✗ {miError}</p>
                        <button className="btn btn-secondary btn-sm" type="button" onClick={runMediaInfo}>↻ Reintentar</button>
                      </>
                    )}
                    {miReport && (
                      <MediaInfoTable
                        report={miReport}
                        // Closes this card before opening the comparison one — both are
                        // modal-overlays at the same z-index, so having two open at once
                        // would bury the newly-opened one behind this still-open card.
                        onSourceToolClick={sourceComparison ? () => { setShowMiCard(false); setShowEngineDetail(true); setShowSourceCompare(true) } : undefined}
                      />
                    )}
                  </div>
                </Modal>
              )}

              {showRemuxCard && (
                <Modal
                  titulo={<>
                    Ordenación y Nombre de las Pistas
                    <AvisoModoPistas plan={remuxPreview} />
                  </>}
                  onClose={() => setShowRemuxCard(false)}
                  className="modal-wide"
                  style={{ maxWidth: 780 }}
                  tituloStyle={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}
                >
                  <div className="modal-body">
                    {remuxLoading && !remuxPreview && <TableLoadingSpinner label="Cargando pistas del archivo…" />}
                    {remuxError && !remuxLoading && (
                      <>
                        <p className="text-error" style={{ fontSize: 12, marginTop: 0, marginBottom: 10 }}>✗ {remuxError}</p>
                        <button className="btn btn-secondary btn-sm" type="button" onClick={runTrackRemux}>↻ Reintentar</button>
                      </>
                    )}
                    {/* Editable solo si el modo renombra: sin eso la
                        columna ofrece escribir un nombre que no se va a
                        aplicar. Lo decide Configuración → Otros, no una
                        casilla aquí: la casilla solo salía subiendo una
                        película o un capítulo suelto, nunca en una
                        temporada entera. */}
                    {remuxPreview && (
                      <RemuxTable
                        plan={remuxPreview}
                        editable={tocaElFichero(normalizarModo(remuxPreview.track_mode))}
                        nameEditable={renombra(normalizarModo(remuxPreview.track_mode))}
                        edits={remuxEdits}
                        onEdit={setRemuxEdit}
                      />
                    )}
                  </div>
                </Modal>
              )}

              <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 16 }}>
                {needsSelection
                  ? <button className="btn btn-secondary" onClick={() => setStep(0)}>Volver a la selección</button>
                  : <span />}
                <button className="btn btn-primary" onClick={goToUpload} disabled={preparing || !preview || existingJobBlocking}>
                  {preparing ? 'Preparando…' : 'Continuar'}
                </button>
              </div>
            </>
          )}
        </div>
      )}

      {/* Paso 2 con varios elegidos. Mismo aspecto que el de uno solo:
          tarjeta de comprobaciones y desplegable arriba a la derecha para
          recorrer los elementos, en vez del párrafo suelto de antes. */}
      {step === 2 && batchQueue.length > 1 && (
        <div className="modal-body">
          {batchPhase === 'idle' && (() => {
            const viewId = batchViewId ?? batchQueue[0]
            const contentChecks = batchContentChecks.get(viewId)
            const blocked = batchQueue.filter(id => batchContentChecks.get(id)?.ready === false)
            const envReady = batchEnvChecks?.ready !== false
            return (
              <>
                <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 12 }}>
                  <select
                    className="form-input form-select" style={{ width: 'auto' }}
                    value={viewId} onChange={e => setBatchViewId(Number(e.target.value))}
                  >
                    {batchQueue.map(id => {
                      const failed = batchContentChecks.get(id)?.ready === false
                      return <option key={id} value={id}>{failed ? '✗ ' : ''}{batchItemTitle(id)}</option>
                    })}
                  </select>
                </div>

                <div className="detail-card" style={{ padding: '12px 14px', borderRadius: 8 }}>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
                    <div style={labelStyle}>Comprobaciones previas</div>
                    {batchChecksLoading && <span className="spinner" style={{ width: 14, height: 14, borderWidth: 2 }} />}
                  </div>

                  {/* Las del elemento que estés mirando. */}
                  {contentChecks
                    ? contentChecks.checks.map(c => <CheckRow key={c.id} c={c} />)
                    : <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                        Comprobando {batchIsEpisodes ? 'capítulo' : 'temporada'} {Math.min(batchChecksIndex + 1, batchQueue.length)} de {batchQueue.length}…
                      </div>}

                  {/* Y las compartidas, hechas una sola vez para la tanda. */}
                  {batchEnvChecks && (
                    <>
                      <div style={{ ...labelStyle, marginTop: 14, marginBottom: 8 }}>
                        Comunes a {batchIsEpisodes ? 'todos los capítulos' : 'todas las temporadas'}
                      </div>
                      {batchEnvChecks.checks.map(c => <CheckRow key={c.id} c={c} />)}
                    </>
                  )}

                  {!batchChecksLoading && (
                    <div style={{ marginTop: 14, fontWeight: 600, color: blocked.length === 0 && envReady ? 'var(--color-available)' : 'var(--color-error)' }}>
                      {!envReady
                        ? '✗ La subida no se puede realizar'
                        : blocked.length === 0
                        ? `✓ Todo listo: ${batchQueue.length} ${batchIsEpisodes ? 'capítulos' : 'temporadas'}`
                        : `✗ ${blocked.length} de ${batchQueue.length} no se ${blocked.length === 1 ? 'puede' : 'pueden'} subir`}
                    </div>
                  )}
                </div>

                {/* Qué se va a saltar y por qué, antes de pulsar nada. */}
                {!batchChecksLoading && blocked.length > 0 && (
                  <div className="detail-card" style={{ padding: '12px 14px', borderRadius: 8, marginTop: 12 }}>
                    {blocked.map(id => (
                      <p key={id} style={{ fontSize: 12.5, margin: '4px 0', color: 'var(--color-error-pale)' }}>
                        ✗ {batchItemTitle(id)}: {batchContentChecks.get(id)?.checks.find(c => c.status === 'fail')?.message || 'Alguna comprobación falló'}
                      </p>
                    ))}
                    <p style={{ fontSize: 12, margin: '10px 0 0', color: 'var(--text-muted)' }}>
                      Se saltarán. El resto se subirá igualmente.
                    </p>
                  </div>
                )}

                <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 16 }}>
                  <button className="btn btn-secondary" onClick={() => setStep(1)} type="button">Volver</button>
                  <button
                    className="btn btn-primary"
                    onClick={batchIsEpisodes ? uploadAllEpisodes : uploadAllSeasons}
                    disabled={batchChecksLoading || !envReady || blocked.length === batchQueue.length}
                    type="button"
                  >
                    {batchIsEpisodes ? 'Subir todos' : 'Subir todas'}
                  </button>
                </div>
              </>
            )
          })()}
          {batchPhase === 'processing' && (
            <div style={{ padding: '20px 0', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 12 }}>
              <span className="spinner" style={{ width: 28, height: 28, borderWidth: 3 }} />
              <div style={{ fontSize: 14, fontWeight: 600 }}>
                Subiendo {batchIsEpisodes ? 'capítulo' : 'temporada'} {batchIndex + 1} de {batchQueue.length}
                {`: ${batchItemTitle(batchQueue[batchIndex])}`}
              </div>
            </div>
          )}
          {batchPhase === 'done' && (
            <>
              <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 12, textAlign: 'center' }}>
                {batchResults.filter(r => r.status === 'queued').length} de {batchResults.length} {batchIsEpisodes ? 'capítulo(s) encolado(s)' : 'temporada(s) encolada(s)'}
              </div>
              {batchResults.some(r => r.status === 'failed') && (
                <div className="detail-card" style={{ padding: '12px 14px', borderRadius: 8, marginBottom: 14 }}>
                  {batchResults.filter(r => r.status === 'failed').map(r => (
                    <p key={r.seasonId} style={{ fontSize: 12.5, margin: '4px 0', color: 'var(--color-error-pale)' }}>
                      ✗ {r.title}: {r.reason}
                    </p>
                  ))}
                </div>
              )}
              <div style={{ display: 'flex', justifyContent: 'center' }}>
                <button className="btn btn-primary" onClick={() => { onDone?.(); onNavigate?.('uploads'); onClose() }} type="button">
                  Ir a Subidas
                </button>
              </div>
            </>
          )}
        </div>
      )}


      {step === 2 && seasonQueue.length <= 1 && episodeQueue.length <= 1 && (
        <div className="modal-body">
          <div className="detail-card" style={{ marginBottom: 14, padding: '12px 14px', borderRadius: 8 }}>
            {targetIsSeason ? (
              <>
                <div style={labelStyle}>Nombre final del torrent (pack de temporada)</div>
                <FitText min={9} text={seasonDisplayTitle || '—'} />
              </>
            ) : (
              <FitTextPair
                min={9}
                items={[
                  { label: 'Nombre final del torrent', text: preview?.torrent_name || '—', labelStyle },
                  { label: INTERNAL_TITLE_LABEL, text: preview?.internal_mkv_title || '—', labelStyle },
                ]}
              />
            )}
          </div>

          {/* Pre-upload checks card */}
          <div className="detail-card" style={{ padding: '12px 14px', borderRadius: 8 }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
              <div style={labelStyle}>Comprobaciones previas</div>
              {checksLoading && <span className="spinner" style={{ width: 14, height: 14, borderWidth: 2 }} />}
            </div>
            {checksLoading ? (
              // Progressive reveal: one line naming whichever check is
              // currently running ("Comprobando si es accesible…"),
              // replacing itself as each one finishes and the next starts —
              // instead of a silent wait (the full run is real network
              // calls, ~30s). liveChecks only holds COMPLETED checks, so
              // its length is the index of the one in flight right now.
              <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                {CHECK_STEP_PENDING_LABEL[(targetIsSeason ? CHECK_STEP_ORDER_SEASON : CHECK_STEP_ORDER)[liveChecks.length]] ?? 'Finalizando comprobaciones…'}
              </div>
            ) : (
              checks?.checks.map(c => <CheckRow key={c.id} c={c} />)
            )}
            {!checksLoading && checks && (
              <div style={{ marginTop: 14, fontWeight: 600, color: checks.ready ? 'var(--color-available)' : 'var(--color-error)' }}>
                {checks.ready ? '✓ Todo listo para subir' : '✗ La subida no se puede realizar'}
              </div>
            )}
            {!checksLoading && (
              <button className="btn btn-secondary btn-sm" style={{ marginTop: 12, fontSize: 12 }} onClick={runChecks} type="button">
                ↻ Volver a comprobar
              </button>
            )}
          </div>

          {checks?.ready && (
            <p style={{ marginTop: 12, fontSize: 13 }}>
              ¿Seguro que quieres subir <strong>«{item.title}»</strong> a eMuwarez? Se iniciará la subida real.
            </p>
          )}
          {uploadMsg && (
            <p style={{
              fontSize: 13, marginTop: 8, padding: '8px 12px', borderRadius: 6, fontWeight: 500,
              background: uploadMsg.startsWith('✗') ? 'color-mix(in srgb, var(--color-error) 12%, transparent)' : 'color-mix(in srgb, var(--color-available) 12%, transparent)',
              border: `1px solid ${uploadMsg.startsWith('✗') ? 'color-mix(in srgb, var(--color-error) 35%, transparent)' : 'color-mix(in srgb, var(--color-available) 35%, transparent)'}`,
              color: uploadMsg.startsWith('✗') ? 'var(--color-error-pale)' : 'var(--color-available-pale)',
            }}>{uploadMsg}</p>
          )}

          <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 16 }}>
            <button className="btn btn-secondary" onClick={() => setStep(1)} disabled={uploading}>Volver</button>
            <button
              className="btn btn-primary"
              onClick={doUpload}
              disabled={!canUpload || uploading || checksLoading}
              {...uploadBtnTip.triggerProps}
            >
              {uploading ? 'Subiendo…' : 'Subir a eMuwarez'}
              {uploadBtnTip.tooltipNode}
            </button>
          </div>
        </div>
      )}
    </Modal>
  )
}
