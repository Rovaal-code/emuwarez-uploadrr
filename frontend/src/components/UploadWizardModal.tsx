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
  previewSeasonPack, getSeasonPlanProgress, getSeasonEpisodeNames,
  getSeasonEpisodeMediaInfo, getSeasonEpisodeRemuxPreview, previewSeasonPackFields,
  type SeasonPlanProgress, type SeasonEpisodeName, type SeasonEpisodeMediaInfo, type SeasonEpisodeRemux,
} from '../api/seasonPack'
import type { LibraryItemResponse, SeasonPackPlanResponse, UploadJob } from '../types/api'
import { isSeasonReady, seasonNotReadyReason } from '../utils/libraryItem'
import { InfoIcon } from './InfoIcon'
import { AutoUploadSourceGate } from './AutoUploadSourceGate'
import { FitText, FitTextPair } from './FitText'
import { Tooltip, useTooltip } from './Tooltip'
import { ACTIVE_JOB_STATUSES, statusLabel } from '../utils/uploadStatus'

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
const WHOLE_SEASON = 'WHOLE_SEASON'

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
  // Only true when opened from a series' own dedicated Biblioteca page — the
  // one place multi-season selection is offered (never from the Biblioteca
  // list/table, never from a season's own page).
  multiSeason?: boolean
}

const labelStyle: React.CSSProperties = {
  fontSize: 11, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 4, display: 'block',
}

const thStyle: React.CSSProperties = {
  textAlign: 'left', padding: '8px 10px', fontWeight: 600, color: 'var(--text-muted)',
  position: 'sticky', top: 0, background: 'var(--bg-surface, #0f1420)',
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
    return <p className="text-warning" style={{ fontSize: 12, margin: 0 }}>⚠ {report.message}</p>
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
                <td style={{ padding: '7px 12px', fontFamily: 'monospace', color: 'var(--text-muted)', wordBreak: 'break-word' }}>
                  {isSourceRow && onSourceToolClick ? (
                    <Tooltip content="Ver comparación del source">
                      <button type="button" className="source-bitrate-link" onClick={onSourceToolClick}>
                        {r.mediainfo}
                      </button>
                    </Tooltip>
                  ) : r.mediainfo}
                </td>
                <td style={{ padding: '7px 12px', fontFamily: 'monospace', wordBreak: 'break-word' }}>{r.emu}</td>
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

// Track reorder/rename table — the single-file "Ver Remux" card renders it
// editable (inputs); the season target's per-episode accordion renders it
// read-only (editable=false — no manual per-track overrides for seasons).
export function RemuxTable({ plan, editable, edits, onEdit }: {
  plan: TrackRemuxPreview
  editable: boolean
  edits?: Record<number, TrackRemuxOverride>
  onEdit?: (trackId: number, patch: TrackRemuxOverride) => void
}) {
  return (
    <>
      {plan.errors?.map((e, i) => (
        <p key={i} className="text-error" style={{ fontSize: 12, marginTop: 10 }}>✗ {e}</p>
      ))}
      {plan.warnings?.map((w, i) => (
        <p key={i} className="text-warning" style={{ fontSize: 12, marginTop: 10 }}>⚠ {w}</p>
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
                    <td style={{ padding: '6px 10px', fontFamily: 'monospace', color: 'var(--text-secondary)' }}>{t.language || '—'}</td>
                    <td style={{ padding: '6px 10px', color: 'var(--text-muted)', wordBreak: 'break-word' }}>{t.current_name || '—'}</td>
                    <td style={{ padding: '5px 8px' }}>
                      {editable ? (
                        <input
                          className="form-input"
                          style={{ fontSize: 12, padding: '4px 6px' }}
                          value={effectiveName}
                          onChange={e => onEdit?.(t.id, { new_name: e.target.value })}
                        />
                      ) : (
                        <span style={{ fontFamily: 'monospace', fontSize: 12 }}>{effectiveName}</span>
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
          width: '100%', textAlign: 'left', padding: '8px 12px', background: 'rgba(255,255,255,0.03)',
          border: 'none', cursor: 'pointer', display: 'flex', justifyContent: 'space-between',
          alignItems: 'center', gap: 8, color: 'inherit', fontSize: 13,
        }}
        {...triggerProps}
      >
        <span style={{ minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {episodeNumber != null ? `E${String(episodeNumber).padStart(2, '0')} — ` : ''}{title}
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
  tag: 'El tag de tu grupo de subida, configurado en Ajustes.',
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
    <InfoIcon text="Es el mismo texto que el nombre del torrent: también es el título interno, el que se graba dentro del propio contenedor .mkv." />
  </span>
)

export function UploadWizardModal({ item, onClose, onDone, onNavigate, preselect, multiSeason }: Props) {
  const isSeries = item.item_type === 'series'
  const isSeason = item.item_type === 'season'
  const needsSelection = isSeries || isSeason
  const allowMultiSeason = !!multiSeason && isSeries

  // Manual/Automático choice, made up front — gates everything else. null
  // shows the chooser screen; nothing below runs until one is picked.
  const [mode, setMode] = useState<'manual' | 'auto' | null>(null)

  // Multi-season selection (series' own dedicated page only): a checklist
  // instead of the single season/episode dropdowns. `seasonQueue` holds the
  // remaining season ids to process — for Manual, doUpload() pops the next
  // one and loops the wizard instead of closing; for Automático, all of them
  // are queued in one go with no wizard involved from here on.
  const [multiSelected, setMultiSelected] = useState<Set<number>>(new Set())
  const [seasonQueue, setSeasonQueue] = useState<number[]>([])

  // The item the nomenclature actually runs on: a movie/episode directly, a
  // season row for a whole-season pack, or an episode picked from a series.
  const [targetId, setTargetId] = useState<number | null>(needsSelection ? null : item.id)
  // Whether targetId resolves to a whole season (pack) rather than one file —
  // known at selection time (confirmSelection), drives an entirely different
  // Step 1 (plan preview instead of per-file nomenclature fields), but the
  // rest of the wizard (checks/queue) needs no branching at all.
  const [targetIsSeason, setTargetIsSeason] = useState(false)
  const [step, setStep] = useState<0 | 1 | 2>(needsSelection ? 0 : 1)

  // Step 0 — series/season selection
  const [seasons, setSeasons] = useState<LibraryItemResponse[]>([])
  const [episodes, setEpisodes] = useState<LibraryItemResponse[]>([])
  const [selSeasonId, setSelSeasonId] = useState<number | ''>(isSeason ? item.id : '')
  // A season opened directly defaults to its whole-season pack pre-selected.
  const [selEpisode, setSelEpisode] = useState<string>(isSeason ? WHOLE_SEASON : '')  // episode id or WHOLE_SEASON
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
  const [titleWarning, setTitleWarning] = useState<string | null>(null)
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

  // Season target — per-episode MediaInfo/Remux (accordion, one entry per
  // episode), replacing the single-file "Ver MediaInfo"/"Ver Remux" cards.
  const [seasonMi, setSeasonMi] = useState<SeasonEpisodeMediaInfo[] | null>(null)
  const [seasonMiLoading, setSeasonMiLoading] = useState(false)
  const [seasonMiError, setSeasonMiError] = useState<string | null>(null)
  const [expandedMiEp, setExpandedMiEp] = useState<number | null>(null)

  const [seasonRemux, setSeasonRemux] = useState<SeasonEpisodeRemux[] | null>(null)
  const [seasonRemuxLoading, setSeasonRemuxLoading] = useState(false)
  const [seasonRemuxError, setSeasonRemuxError] = useState<string | null>(null)
  const [expandedRemuxEp, setExpandedRemuxEp] = useState<number | null>(null)

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
    const poll = window.setInterval(async () => {
      try {
        const p = await getUploadChecksProgress(targetId)
        setLiveChecks(p.checks)
      } catch { /* transient poll failure — next tick retries */ }
    }, 400)
    try { setChecks(await runUploadChecks(targetId)) }
    catch { setChecks(null) }
    finally {
      window.clearInterval(poll)
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
          // Preselect the requested season (its episodes load via the effect below).
          if (preselect?.season != null) {
            const s = r.items.find(x => x.season_number === preselect.season)
            if (s) setSelSeasonId(s.id)
          }
        } else {
          const r = await getLibrary({ parent_id: item.id, type: 'episode', limit: 500 })
          setEpisodes(r.items)
          if (preselect?.episode != null) {
            const e = r.items.find(x => x.episode_number === preselect.episode)
            if (e) setSelEpisode(String(e.id))
          }
        }
      } catch (e: unknown) {
        setSelError(e instanceof Error ? e.message : 'Error cargando temporadas')
      }
    }
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [item.id, isSeries, needsSelection])

  // When a season is picked (series flow), load its episodes.
  useEffect(() => {
    if (!isSeries || selSeasonId === '') return
    getLibrary({ parent_id: Number(selSeasonId), type: 'episode', limit: 500 })
      .then(r => {
        setEpisodes(r.items)
        // Preselect the requested episode, or the whole-season pack when the
        // request's scope is the season (not a single episode).
        if (preselect?.episode != null) {
          const e = r.items.find(x => x.episode_number === preselect.episode)
          setSelEpisode(e ? String(e.id) : WHOLE_SEASON)
        } else if (preselect?.season != null) {
          setSelEpisode(WHOLE_SEASON)
        } else {
          setSelEpisode('')
        }
      })
      .catch(() => setEpisodes([]))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isSeries, selSeasonId])

  const confirmSelection = () => {
    setSelError(null)
    if (selEpisode === WHOLE_SEASON) {
      const seasonId = isSeason ? item.id : Number(selSeasonId)
      if (!seasonId) { setSelError('Selecciona una temporada'); return }
      setTargetId(seasonId)
      setTargetIsSeason(true)
    } else if (selEpisode) {
      setTargetId(Number(selEpisode))
      setTargetIsSeason(false)
    } else {
      setSelError('Selecciona un episodio o "Temporada entera"')
      return
    }
    // For Automático the target resolving is enough — rendering switches to
    // <AutoUploadSourceGate>, step 1's UI never renders.
    if (mode === 'manual') setStep(1)
  }

  const toggleMultiSeason = (seasonId: number) => {
    setMultiSelected(prev => {
      const next = new Set(prev)
      if (next.has(seasonId)) next.delete(seasonId); else next.add(seasonId)
      return next
    })
  }

  const confirmMultiSelection = () => {
    setSelError(null)
    if (multiSelected.size === 0) { setSelError('Selecciona al menos una temporada'); return }
    const ids = seasons.filter(s => multiSelected.has(s.id)).map(s => s.id)
    setSeasonQueue(ids)
    if (mode === 'manual') {
      setTargetId(ids[0])
      setTargetIsSeason(true)
      setStep(1)
    }
    // For Automático, setting seasonQueue above is enough — it switches the
    // render to <AutoUploadSourceGate>, which checks + queues each season
    // sequentially (source-disparity gate per season, see that component).
  }

  // "Ya existe una subida" precheck — only relevant for the manual flow (the
  // Automático path chains onto it silently server-side either way, see
  // ACTIVE_JOB_STATUSES/_find_latest_job_for_item in upload_queue.py).
  const [existingJob, setExistingJob] = useState<UploadJob | null>(null)
  useEffect(() => {
    if (mode !== 'manual' || targetId == null) { setExistingJob(null); return }
    let alive = true
    getExistingJobForItem(targetId).then(j => { if (alive) setExistingJob(j) }).catch(() => { if (alive) setExistingJob(null) })
    return () => { alive = false }
  }, [mode, targetId])
  const existingJobBlocking = !!existingJob && ACTIVE_JOB_STATUSES.has(existingJob.status)

  // --- Step 1: load nomenclature for the resolved target ---
  const loadFields = useCallback(async () => {
    if (targetId == null) return
    setLoading(true); setError(null)
    try {
      const [srcResp, prvResp, fieldsResp] = await Promise.all([
        getEmuSources(), getEmuProviders(), getNomenclatureFields(targetId),
      ])
      setSources(srcResp.sources)
      setProviders(prvResp.providers)
      // File not accessible / MediaInfo unavailable → block: show the error and
      // don't render a (bogus, incomplete) name.
      if (fieldsResp.blocked) {
        setError(fieldsResp.error || 'No se puede generar la nomenclatura.')
        setFields({})
        setInitialTag('')
        return
      }
      setFields(fieldsResp.fields || {})
      setInitialTag(fieldsResp.fields?.tag || 'EMUWAREZ')
      setTitleWarning(fieldsResp.title_warning ?? null)
      setSourceWarning(fieldsResp.source_warning ?? null)
      setSourceComparison(fieldsResp.source_comparison ?? null)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Error cargando la nomenclatura')
    } finally {
      setLoading(false)
    }
  }, [targetId])

  useEffect(() => { if (step === 1 && !targetIsSeason) loadFields() }, [step, targetIsSeason, loadFields])

  // --- Step 1 (season target): build the pack plan, polling progress while
  // it's in flight (real work per episode — build_nomenclature_proposal()).
  const loadSeasonPlan = useCallback(async () => {
    if (targetId == null) return
    setSeasonPlanLoading(true); setSeasonPlanError(null)
    setSeasonProgress({ done: 0, total: 0, current_title: null })
    setSeasonTitlePreview(null)
    const poll = window.setInterval(async () => {
      try { setSeasonProgress(await getSeasonPlanProgress(targetId)) } catch { /* transient poll failure — next tick retries */ }
    }, 400)
    try {
      const [plan, srcResp, prvResp] = await Promise.all([
        previewSeasonPack(targetId), getEmuSources(), getEmuProviders(),
      ])
      setSeasonPlan(plan)
      setSources(srcResp.sources)
      setProviders(prvResp.providers)
      // Source/Proveedor/Tag now editable (same dropdowns a movie/episode
      // shows) — seed `fields` from the pack's own resolved values so
      // setField('source'|'provider'|'tag', ...) below works the same way.
      // `season_episode` deliberately left unset (a season pack has no
      // single SxxExx, unlike one episode).
      setFields({
        title: plan.series_title ?? undefined,
        year: plan.year != null ? String(plan.year) : undefined,
        resolution: plan.resolution ?? undefined,
        source: plan.source ?? undefined,
        provider: plan.provider ?? undefined,
        video_codec: plan.video_codec ?? undefined,
        audio_summary: plan.audio_summary ?? undefined,
        subs: plan.subtitle_summary ?? undefined,
        tag: plan.release_tag ?? undefined,
      })
      setInitialTag(plan.release_tag || 'EMUWAREZ')
      setSourceComparison(plan.source_comparison ?? null)
      if (plan.status !== 'valid') setSeasonPlanError(plan.errors.join(' '))
    } catch (e: unknown) {
      setSeasonPlan(null)
      setSeasonPlanError(e instanceof Error ? e.message : 'Error preparando la temporada')
    } finally {
      window.clearInterval(poll)
      setSeasonPlanLoading(false)
    }
  }, [targetId])

  useEffect(() => { if (step === 1 && targetIsSeason) loadSeasonPlan() }, [step, targetIsSeason, loadSeasonPlan])

  const loadSeasonNames = useCallback(async () => {
    if (targetId == null) return
    setSeasonNamesLoading(true)
    try {
      const overrides = { source: fields.source, provider: fields.provider, tag: fields.tag }
      setSeasonNames((await getSeasonEpisodeNames(targetId, overrides)).episodes)
    }
    catch { setSeasonNames(null) }
    finally { setSeasonNamesLoading(false) }
  }, [targetId, fields.source, fields.provider, fields.tag])

  const loadSeasonMi = useCallback(async () => {
    if (targetId == null) return
    setSeasonMiLoading(true); setSeasonMiError(null)
    try { setSeasonMi((await getSeasonEpisodeMediaInfo(targetId)).episodes) }
    catch (e: unknown) { setSeasonMi(null); setSeasonMiError(e instanceof Error ? e.message : 'Error cargando MediaInfo') }
    finally { setSeasonMiLoading(false) }
  }, [targetId])

  const loadSeasonRemux = useCallback(async () => {
    if (targetId == null) return
    setSeasonRemuxLoading(true); setSeasonRemuxError(null)
    try { setSeasonRemux((await getSeasonEpisodeRemuxPreview(targetId)).episodes) }
    catch (e: unknown) { setSeasonRemux(null); setSeasonRemuxError(e instanceof Error ? e.message : 'Error calculando el remux') }
    finally { setSeasonRemuxLoading(false) }
  }, [targetId])

  // Reset all per-target state (both single-file and season) whenever the
  // resolved target changes — a different item means unrelated data.
  useEffect(() => {
    setMiReport(null); setMiError(null); setShowMiCard(false)
    setRemuxPreview(null); setRemuxError(null); setRemuxEdits({}); setShowRemuxCard(false)
    setSeasonPlan(null); setSeasonPlanError(null)
    setSeasonNames(null); setShowSeasonNamesCard(false)
    setSeasonMi(null); setSeasonMiError(null); setExpandedMiEp(null)
    setSeasonRemux(null); setSeasonRemuxError(null); setExpandedRemuxEp(null)
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
    if (targetId == null) return
    setMiLoading(true); setMiError(null); setMiReport(null)
    try {
      setMiReport(await getMediaInfoReport(targetId))
    } catch (e: unknown) {
      setMiError(e instanceof Error ? e.message : 'Error ejecutando MediaInfo')
    } finally {
      setMiLoading(false)
    }
  }

  const runTrackRemux = useCallback(async () => {
    if (targetId == null) return
    setRemuxLoading(true); setRemuxError(null); setRemuxEdits({})
    try {
      setRemuxPreview(await previewTrackRemux(targetId))
    } catch (e: unknown) {
      setRemuxPreview(null)
      setRemuxError(e instanceof Error ? e.message : 'Error calculando el remux de pistas')
    } finally {
      setRemuxLoading(false)
    }
  }, [targetId])

  // Prefetch the track remux plan IN PARALLEL with the nomenclature fields
  // (reading a real .mkv's tracks — mkvmerge -J — can be slow over a remote
  // mount) so it's usually already loaded (or well underway) by the time the
  // user opens "Ver Remux", instead of only starting the read on click.
  useEffect(() => { if (step === 1 && !targetIsSeason) runTrackRemux() }, [step, targetIsSeason, runTrackRemux])

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
    const t = setTimeout(async () => {
      try {
        const r = await previewSeasonPackFields(targetId, {
          title: fields.title, year: fields.year ? Number(fields.year) : null,
          season_number: item.season_number ?? null,
          resolution: fields.resolution, source: fields.source, provider: fields.provider,
          video_codec: fields.video_codec, audio_summary: fields.audio_summary,
          subtitle_summary: fields.subs, tag: fields.tag,
        })
        setSeasonTitlePreview(r.torrent_name)
      } catch { /* non-blocking */ }
    }, 400)
    return () => clearTimeout(t)
  }, [targetId, targetIsSeason, fields, item.season_number])

  const setField = (key: string, value: string | null) => {
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
    setPreparing(false)
    setStep(2)
    runChecks()
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
        ? { ordered_tracks: mergeRemuxTracks(remuxPreview, remuxEdits) }
        : null
      const r = await queueUpload(
        targetId, remuxEdits, checks, remuxSnapshot,
        targetIsSeason ? { source: fields.source, provider: fields.provider, tag: fields.tag } : undefined,
      )
      if (r.status !== 'queued' || !r.job?.id) {
        setUploadMsg(`✗ No se pudo encolar la subida (estado: ${r.status}). ${(r.errors || []).join(' ')}`)
        return
      }
      // Manual multi-temporada: en vez de cerrar, sigue con la siguiente
      // temporada de la cola — el wizard vuelve al paso 1 para ella.
      const remaining = seasonQueue.slice(1)
      if (remaining.length > 0) {
        setSeasonQueue(remaining)
        setTargetId(remaining[0])
        setTargetIsSeason(true)
        setChecks(null)
        setStep(1)
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

  // Step 0, single target — the original season/episode dropdowns, used
  // whenever multi-season selection isn't offered (movie/episode directly,
  // a season opened on its own, or a series opened from anywhere other than
  // its own dedicated Biblioteca page).
  const singleSelectionFields = (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px 16px' }}>
      {isSeries && (
        <label><span style={labelStyle}>Temporada</span>
          <select className="form-input form-select" value={selSeasonId} onChange={e => setSelSeasonId(e.target.value ? Number(e.target.value) : '')}>
            <option value="">— Seleccionar —</option>
            {seasons.map(s => <option key={s.id} value={s.id}>{s.title || `Temporada ${s.season_number}`}</option>)}
          </select>
        </label>
      )}
      <label><span style={labelStyle}>Episodio</span>
        <select className="form-input form-select" value={selEpisode} onChange={e => setSelEpisode(e.target.value)} disabled={isSeries && selSeasonId === ''}>
          <option value="">— Seleccionar —</option>
          <option value={WHOLE_SEASON}>★ Temporada entera</option>
          {episodes.map(ep => (
            <option key={ep.id} value={ep.id}>
              {ep.episode_number != null ? `E${String(ep.episode_number).padStart(2, '0')} — ` : ''}{ep.title}
            </option>
          ))}
        </select>
      </label>
    </div>
  )

  // Step 0, multi-season — only reachable when the wizard was opened from a
  // series' own dedicated Biblioteca page (allowMultiSeason).
  // Only a season with EVERY episode Disponible AND every episode agreeing
  // on codec/audio/idiomas/subs/resolución/source can go as a season pack
  // (build_season_pack_plan() blocks otherwise) — incomplete/inconsistent
  // ones are shown greyed out and unselectable instead of letting the user
  // pick one and fail later. isSeasonReady/seasonNotReadyReason (shared with
  // LibraryActionButtons' own "Subir" button) only know about the
  // consistency check; the "incomplete" message is layered on here.
  const seasonCardReason = (s: LibraryItemResponse) =>
    s.local_status !== 'Disponible'
      ? 'Temporada incompleta: no todos los capítulos están Disponibles.'
      : seasonNotReadyReason(s)
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
          const reason = seasonCardReason(s)
          const selected = multiSelected.has(s.id)
          const card = (
            <button
              type="button"
              disabled={!ready}
              onClick={() => toggleMultiSeason(s.id)}
              style={{
                width: '100%', padding: '16px 12px', borderRadius: 8, fontSize: 13, textAlign: 'center', cursor: ready ? 'pointer' : 'not-allowed',
                background: selected ? 'rgba(37,99,235,0.18)' : 'var(--bg-card)',
                border: `1px solid ${selected ? '#2563eb' : 'var(--border-input)'}`,
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
      background: existingJobBlocking ? 'rgba(248,113,113,0.1)' : 'rgba(59,130,246,0.1)',
      border: `1px solid ${existingJobBlocking ? 'rgba(248,113,113,0.3)' : 'rgba(59,130,246,0.3)'}`,
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
          <input className="form-input" value={fields.title || ''} disabled />
          {titleWarning && (
            <span style={{ display: 'block', marginTop: 4, fontSize: 11, color: '#f59e0b' }}>⚠ {titleWarning}</span>
          )}
        </label>
        <label><FieldLabel label="Año" info={FIELD_INFO.year} />
          <input className="form-input" value={fields.year || ''} disabled />
        </label>
        {fields.season_episode != null && (
          <label><FieldLabel label="Temporada / Episodio" info={FIELD_INFO.season_episode} />
            <input className="form-input" value={fields.season_episode || ''} onChange={e => setField('season_episode', e.target.value)} />
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
                    style={{ display: 'inline-flex', color: sourceComparison.agree ? 'var(--text-accent)' : '#eab308' }}
                  >
                    <svg width="34" height="34" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <rect x="2" y="5" width="20" height="14" rx="4" />
                      <path d="M10 9.3v5.4l5-2.7z" fill="currentColor" stroke="none" />
                    </svg>
                  </span>
                </button>
              </Tooltip>
            )}
          </div>
          {sourceWarning && (
            <span style={{ display: 'block', marginTop: 4, fontSize: 11, color: '#f59e0b' }}>⚠ {sourceWarning}</span>
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
            {Array.from(new Set([initialTag, 'EMUWAREZ'].filter(Boolean))).map(t => (
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
  const seasonFieldBox = (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px 16px' }}>
      <label><FieldLabel label="Título" info={FIELD_INFO.title} />
        <input className="form-input" value={seasonPlan?.series_title || ''} disabled />
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
                  style={{ display: 'inline-flex', color: sourceComparison.agree ? 'var(--text-accent)' : '#eab308' }}
                >
                  <svg width="34" height="34" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
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
          {Array.from(new Set([initialTag, 'EMUWAREZ'].filter(Boolean))).map(t => (
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
            onClick={() => { setShowSeasonNamesCard(true); if (!seasonNames && !seasonNamesLoading) loadSeasonNames() }}
          >
            Ver nombre de todos los capítulos
          </button>
        </div>
      )}
    </>
  )

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-panel modal-wide" onClick={e => e.stopPropagation()} style={{ maxWidth: 900 }}>
        <div className="modal-header">
          <h2 className="modal-title">Subir a eMuwarez — {item.title}</h2>
          <button className="modal-close" onClick={onClose}>✕</button>
        </div>

        {mode === null && (
          <div className="modal-body">
            <p className="text-muted" style={{ fontSize: 12, marginBottom: 16 }}>
              Elige cómo quieres subir <strong>{item.title}</strong> a eMuwarez.
            </p>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
              <button
                className="btn btn-secondary"
                style={{
                  padding: '14px 14px', textAlign: 'left', display: 'flex', flexDirection: 'column',
                  alignItems: 'flex-start', gap: 6, height: 'auto', width: '100%', minWidth: 0, whiteSpace: 'normal',
                }}
                onClick={() => setMode('manual')}
                type="button"
              >
                <span style={{ fontSize: 15, fontWeight: 700 }}>Manual</span>
                <span style={{ fontSize: 12, color: 'var(--text-muted)', fontWeight: 400, whiteSpace: 'normal' }}>
                  Revisa y ajusta la nomenclatura, el remux y las comprobaciones antes de confirmar.
                </span>
              </button>
              <button
                className="btn btn-secondary"
                style={{
                  padding: '14px 14px', textAlign: 'left', display: 'flex', flexDirection: 'column',
                  alignItems: 'flex-start', gap: 6, height: 'auto', width: '100%', minWidth: 0, whiteSpace: 'normal',
                }}
                onClick={() => setMode('auto')}
                type="button"
              >
                <span style={{ fontSize: 15, fontWeight: 700 }}>Automático</span>
                <span style={{ fontSize: 12, color: 'var(--text-muted)', fontWeight: 400, whiteSpace: 'normal' }}>
                  Se envía directamente a Subidas; la nomenclatura y las comprobaciones se generan solas.
                </span>
              </button>
            </div>
          </div>
        )}

        {mode === 'auto' && allowMultiSeason && seasonQueue.length === 0 && (
          <div className="modal-body">
            {multiSeasonChecklist}
            {selError && <p className="text-error" style={{ marginTop: 10 }}>{selError}</p>}
            <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 16 }}>
              <button className="btn btn-secondary" onClick={() => setMode(null)} type="button">← Volver</button>
              <button className="btn btn-primary" onClick={confirmMultiSelection} type="button">Continuar →</button>
            </div>
          </div>
        )}

        {mode === 'auto' && allowMultiSeason && seasonQueue.length > 0 && (
          <AutoUploadSourceGate targetIds={seasonQueue} onNavigate={onNavigate} onClose={onClose} onDone={onDone} />
        )}

        {mode === 'auto' && !allowMultiSeason && needsSelection && targetId == null && (
          <div className="modal-body">
            <p className="text-muted" style={{ fontSize: 12, marginBottom: 12 }}>
              Elige qué subir de <strong>{item.title}</strong>: un episodio concreto, o la temporada entera.
            </p>
            {singleSelectionFields}
            {selError && <p className="text-error" style={{ marginTop: 10 }}>{selError}</p>}
            <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 16 }}>
              <button className="btn btn-secondary" onClick={() => setMode(null)} type="button">← Volver</button>
              <button className="btn btn-primary" onClick={confirmSelection} type="button">Continuar →</button>
            </div>
          </div>
        )}

        {mode === 'auto' && !allowMultiSeason && targetId != null && (
          <AutoUploadSourceGate targetIds={[targetId]} onNavigate={onNavigate} onClose={onClose} onDone={onDone} />
        )}

        {mode === 'manual' && (
        <div style={{ display: 'flex', gap: 8, padding: '0 20px', marginTop: 8, fontSize: 12, flexWrap: 'wrap' }}>
          {needsSelection && <><span style={{ fontWeight: step === 0 ? 700 : 400, color: step === 0 ? 'var(--text)' : 'var(--text-muted)' }}>0. Selección</span><span style={{ color: 'var(--text-muted)' }}>→</span></>}
          <span style={{ fontWeight: step === 1 ? 700 : 400, color: step === 1 ? 'var(--text)' : 'var(--text-muted)' }}>1. Nomenclatura</span>
          <span style={{ color: 'var(--text-muted)' }}>→</span>
          <span style={{ fontWeight: step === 2 ? 700 : 400, color: step === 2 ? 'var(--text)' : 'var(--text-muted)' }}>2. Subida a eMuwarez</span>
        </div>
        )}

        {mode === 'manual' && step === 0 && (
          <div className="modal-body">
            <p className="text-muted" style={{ fontSize: 12, marginBottom: 12 }}>
              {allowMultiSeason
                ? <>Elige qué temporada(s) de <strong>{item.title}</strong> subir.</>
                : <>Elige qué subir de <strong>{item.title}</strong>: un episodio concreto, o la temporada entera.</>}
            </p>
            {allowMultiSeason ? multiSeasonChecklist : singleSelectionFields}
            {selError && <p className="text-error" style={{ marginTop: 10 }}>{selError}</p>}
            <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 16 }}>
              <button className="btn btn-secondary" onClick={() => setMode(null)} type="button">← Volver</button>
              <button className="btn btn-primary" onClick={allowMultiSeason ? confirmMultiSelection : confirmSelection} type="button">Continuar →</button>
            </div>
          </div>
        )}

        {mode === 'manual' && step === 1 && targetIsSeason && (
          <div className="modal-body">
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
                <p className="text-error" style={{ marginTop: 0, marginBottom: 10 }}>⚠ {seasonPlanError}</p>
                <button className="btn btn-secondary btn-sm" type="button" onClick={loadSeasonPlan}>↻ Reintentar</button>
              </div>
            )}
            {!seasonPlanLoading && !seasonPlanError && seasonPlan && (
              <>
                <p className="text-muted" style={{ fontSize: 12, marginBottom: 12 }}>
                  Se sube como un único pack de temporada. Todos los capítulos deben tener el mismo códec
                  de audio/vídeo, los mismos idiomas de audio/subtítulos, la misma resolución y source —
                  estos campos confirman que todos coinciden; no son editables para una temporada.
                </p>
                {seasonFieldBox}
                {seasonSummaryBox}

                <div style={{ marginTop: 20, paddingTop: 16, borderTop: '1px solid var(--border)' }}>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
                    <div>
                      <div style={{ fontSize: 13, fontWeight: 600 }}>MediaInfo y Remux de los capítulos</div>
                      <div className="text-muted" style={{ fontSize: 11, marginTop: 2 }}>
                        Un capítulo por fila, expandible — cada uno con su propio detalle de MediaInfo y su
                        propio plan de reordenación/renombrado de pistas (sin edición manual para temporadas).
                      </div>
                    </div>
                    <div style={{ display: 'flex', gap: 8, flexShrink: 0 }}>
                      <button className="btn btn-primary" onClick={() => { setShowMiCard(true); if (!seasonMi && !seasonMiLoading) loadSeasonMi() }} disabled={targetId == null}>
                        Ver MediaInfo
                      </button>
                      <button className="btn btn-primary" onClick={() => { setShowRemuxCard(true); if (!seasonRemux && !seasonRemuxLoading) loadSeasonRemux() }} disabled={targetId == null}>
                        Ver Remux
                      </button>
                    </div>
                  </div>
                </div>

                {showMiCard && (
                  <div className="modal-overlay" onClick={() => setShowMiCard(false)}>
                    <div className="modal-panel modal-wide" onClick={e => e.stopPropagation()} style={{ maxWidth: 900 }}>
                      <div className="modal-header">
                        <h2 className="modal-title">MediaInfo de los capítulos</h2>
                        <button className="modal-close" onClick={() => setShowMiCard(false)}>✕</button>
                      </div>
                      <div className="modal-body">
                        {seasonMiLoading && !seasonMi && <TableLoadingSpinner label="Leyendo MediaInfo de cada capítulo…" />}
                        {seasonMiError && !seasonMiLoading && (
                          <>
                            <p className="text-error" style={{ fontSize: 12, marginTop: 0, marginBottom: 10 }}>✗ {seasonMiError}</p>
                            <button className="btn btn-secondary btn-sm" type="button" onClick={loadSeasonMi}>↻ Reintentar</button>
                          </>
                        )}
                        {seasonMi?.map(ep => (
                          <EpisodeAccordionRow
                            key={ep.episode_id}
                            episodeNumber={ep.episode_number}
                            title={episodeOnlyTitle(ep.title)}
                            expanded={expandedMiEp === ep.episode_id}
                            onToggle={() => setExpandedMiEp(expandedMiEp === ep.episode_id ? null : ep.episode_id)}
                          >
                            <MediaInfoTable
                              report={ep.report}
                              onSourceToolClick={ep.source_comparison ? () => {
                                setSourceComparison(ep.source_comparison!)
                                setShowEngineDetail(true)
                                setShowSourceCompare(true)
                              } : undefined}
                            />
                          </EpisodeAccordionRow>
                        ))}
                      </div>
                    </div>
                  </div>
                )}
                {showSourceCompare && sourceComparison && (
                  <SourceComparisonModal
                    comparison={sourceComparison}
                    initialShowDetail={showEngineDetail}
                    onClose={() => setShowSourceCompare(false)}
                  />
                )}

                {showRemuxCard && (
                  <div className="modal-overlay" onClick={() => setShowRemuxCard(false)}>
                    <div className="modal-panel modal-wide" onClick={e => e.stopPropagation()} style={{ maxWidth: 780 }}>
                      <div className="modal-header">
                        <h2 className="modal-title">Ordenación y Nombre de las Pistas por Capítulo</h2>
                        <button className="modal-close" onClick={() => setShowRemuxCard(false)}>✕</button>
                      </div>
                      <div className="modal-body">
                        {seasonRemuxLoading && !seasonRemux && <TableLoadingSpinner label="Calculando el remux de cada capítulo…" />}
                        {seasonRemuxError && !seasonRemuxLoading && (
                          <>
                            <p className="text-error" style={{ fontSize: 12, marginTop: 0, marginBottom: 10 }}>✗ {seasonRemuxError}</p>
                            <button className="btn btn-secondary btn-sm" type="button" onClick={loadSeasonRemux}>↻ Reintentar</button>
                          </>
                        )}
                        {seasonRemux?.map(ep => (
                          <EpisodeAccordionRow
                            key={ep.episode_id}
                            episodeNumber={ep.episode_number}
                            title={episodeOnlyTitle(ep.title)}
                            expanded={expandedRemuxEp === ep.episode_id}
                            onToggle={() => setExpandedRemuxEp(expandedRemuxEp === ep.episode_id ? null : ep.episode_id)}
                          >
                            <RemuxTable plan={ep.plan} editable={false} />
                          </EpisodeAccordionRow>
                        ))}
                      </div>
                    </div>
                  </div>
                )}

                {showSeasonNamesCard && (
                  <div className="modal-overlay" onClick={() => setShowSeasonNamesCard(false)}>
                    <div className="modal-panel modal-wide" onClick={e => e.stopPropagation()} style={{ maxWidth: 900 }}>
                      <div className="modal-header">
                        <h2 className="modal-title">Nombre de todos los capítulos</h2>
                        <button className="modal-close" onClick={() => setShowSeasonNamesCard(false)}>✕</button>
                      </div>
                      <div className="modal-body">
                        {seasonNamesLoading && !seasonNames && <TableLoadingSpinner label="Generando el nombre de cada capítulo…" />}
                        {seasonNames?.map(ep => (
                          <div key={ep.episode_id} style={{ marginBottom: 14, paddingBottom: 14, borderBottom: '1px solid var(--border)' }}>
                            <div style={{ ...labelStyle, marginBottom: 6 }}>
                              {ep.episode_number != null ? `E${String(ep.episode_number).padStart(2, '0')} — ` : ''}{ep.title}
                            </div>
                            {ep.error ? (
                              <p className="text-error" style={{ fontSize: 12, margin: 0 }}>✗ {ep.error}</p>
                            ) : (
                              <FitTextPair
                                min={9}
                                items={[
                                  { label: 'Nombre del torrent', text: ep.torrent_name || '–', labelStyle: { ...labelStyle, fontSize: 10 } },
                                  { label: INTERNAL_TITLE_LABEL, text: ep.internal_mkv_title || '–', labelStyle: { ...labelStyle, fontSize: 10 } },
                                ]}
                              />
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                )}

                <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 16 }}>
                  {needsSelection
                    ? <button className="btn btn-secondary" onClick={() => setStep(0)}>← Selección</button>
                    : <span />}
                  <button className="btn btn-primary" onClick={goToUpload} disabled={preparing || seasonPlan.status !== 'valid' || existingJobBlocking}>
                    {preparing ? 'Preparando…' : 'Continuar →'}
                  </button>
                </div>
              </>
            )}
          </div>
        )}

        {mode === 'manual' && step === 1 && !targetIsSeason && (
          <div className="modal-body">
            {existingJobNotice}
            {loading && (
              <div style={{ padding: '36px 0', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 12 }}>
                <span className="spinner" style={{ width: 28, height: 28, borderWidth: 3 }} />
                <div style={{ fontSize: 15, fontWeight: 600 }}>Generando Nomenclatura para eMuwarez…</div>
              </div>
            )}
            {error && !loading && (
              <div style={{ padding: '20px 0' }}>
                <p className="text-error" style={{ marginTop: 0, marginBottom: 10 }}>⚠ {error}</p>
                <button className="btn btn-secondary btn-sm" type="button" onClick={loadFields}>↻ Reintentar</button>
              </div>
            )}
            {!loading && !error && (
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
                      <div style={{ fontSize: 13, fontWeight: 600 }}>MediaInfo y Remux del archivo</div>
                      <div className="text-muted" style={{ fontSize: 11, marginTop: 2 }}>
                        Ver Remux: muestra la reordenación y el nombre de las pistas de vídeo/audio/subtítulos del contenido (editable).
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
                        onClick={() => { setShowRemuxCard(true); if (!remuxPreview && !remuxLoading) runTrackRemux() }}
                        disabled={targetId == null}
                      >
                        Ver Remux
                      </button>
                    </div>
                  </div>
                </div>

                {showMiCard && (
                  <div className="modal-overlay" onClick={() => setShowMiCard(false)}>
                    <div className="modal-panel modal-wide" onClick={e => e.stopPropagation()} style={{ maxWidth: 900 }}>
                      <div className="modal-header">
                        <h2 className="modal-title">MediaInfo del archivo</h2>
                        <button className="modal-close" onClick={() => setShowMiCard(false)}>✕</button>
                      </div>
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
                    </div>
                  </div>
                )}

                {showRemuxCard && (
                  <div className="modal-overlay" onClick={() => setShowRemuxCard(false)}>
                    <div className="modal-panel modal-wide" onClick={e => e.stopPropagation()} style={{ maxWidth: 780 }}>
                      <div className="modal-header">
                        <h2 className="modal-title">Ordenación y Nombre de las Pistas</h2>
                        <button className="modal-close" onClick={() => setShowRemuxCard(false)}>✕</button>
                      </div>
                      <div className="modal-body">
                        {remuxLoading && !remuxPreview && <TableLoadingSpinner label="Cargando pistas del archivo…" />}
                        {remuxError && !remuxLoading && (
                          <>
                            <p className="text-error" style={{ fontSize: 12, marginTop: 0, marginBottom: 10 }}>✗ {remuxError}</p>
                            <button className="btn btn-secondary btn-sm" type="button" onClick={runTrackRemux}>↻ Reintentar</button>
                          </>
                        )}
                        {remuxPreview && <RemuxTable plan={remuxPreview} editable edits={remuxEdits} onEdit={setRemuxEdit} />}
                      </div>
                    </div>
                  </div>
                )}

                <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 16 }}>
                  {needsSelection
                    ? <button className="btn btn-secondary" onClick={() => setStep(0)}>← Selección</button>
                    : <span />}
                  <button className="btn btn-primary" onClick={goToUpload} disabled={preparing || !preview || existingJobBlocking}>
                    {preparing ? 'Preparando…' : 'Continuar →'}
                  </button>
                </div>
              </>
            )}
          </div>
        )}

        {mode === 'manual' && step === 2 && (
          <div className="modal-body">
            <div className="detail-card" style={{ marginBottom: 14, padding: '12px 14px', borderRadius: 8 }}>
              {targetIsSeason ? (
                <>
                  <div style={labelStyle}>Nombre final del torrent (pack de temporada)</div>
                  <FitText min={9} text={seasonPlan?.season_pack_title || '–'} />
                </>
              ) : (
                <FitTextPair
                  min={9}
                  items={[
                    { label: 'Nombre final del torrent', text: preview?.torrent_name || '–', labelStyle },
                    { label: INTERNAL_TITLE_LABEL, text: preview?.internal_mkv_title || '–', labelStyle },
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
                <div style={{ marginTop: 14, fontWeight: 600, color: checks.ready ? '#22c55e' : '#ef4444' }}>
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
                background: uploadMsg.startsWith('✗') ? 'rgba(239,68,68,0.12)' : 'rgba(34,197,94,0.12)',
                border: `1px solid ${uploadMsg.startsWith('✗') ? 'rgba(239,68,68,0.35)' : 'rgba(34,197,94,0.35)'}`,
                color: uploadMsg.startsWith('✗') ? '#fca5a5' : '#86efac',
              }}>{uploadMsg}</p>
            )}

            <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 16 }}>
              <button className="btn btn-secondary" onClick={() => setStep(1)} disabled={uploading}>← Volver</button>
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
      </div>
    </div>
  )
}
