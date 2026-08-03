import { useState, useEffect, useRef } from 'react'
import type { UploadJob, UploadJobLog, UploadProgressPhase } from '../types/api'
import { getUploadJobLogs } from '../api/uploads'
import { posterUrl } from '../utils/libraryItem'
import { formatDate, formatDateTimeSeconds, parseServerDate } from '../utils/format'
import { InfoIcon } from './InfoIcon'
import { StatusBadge } from './StatusBadge'
import { ServiceLabel } from './ServiceIcon'
import {
  Card, FieldRow, DetailPoster, ValueChip, ValueIcon, DETAIL_CARD_HEIGHT, DetailHero, DetailTitle, DetailTitleText,
  StatusCardIcon, ClockCardIcon, UploadButtonIcon, LibraryButtonIcon, RetryButtonIcon, CancelButtonIcon, DeleteButtonIcon,
  TypeValueIcon, CalendarValueIcon, ProgressValueIcon,
  NomenclatureValueIcon, AudioCodecValueIcon, ChecksValueIcon, LogsValueIcon,
} from './DetailCard'
import { RemuxTable, EpisodeAccordionRow } from './UploadWizardModal'
import {
  UPLOAD_TYPE_LABEL, STATUS_CLASS, statusLabel, phaseLabel, currentPhaseInfo, progressCounter, formatElapsed, queuedWaitText, useTicker, formatSecondsHM,
} from '../utils/uploadStatus'
import { useRefrescoPorAvisos, AVISOS_SUBIDA, AVISOS_SUBIDA_PROGRESO } from '../hooks/useRefrescoPorAvisos'

// Dedicated page for one upload job (replaces the old JobProgressPanel modal)
// — same Radarr/Sonarr-style layout LibraryDetailPage/RequestDetailPage use:
// back button, poster + title + action buttons, a Field grid, and — where
// Biblioteca puts its comparison table — the job's own nomenclature/remux/
// phase-progress breakdown instead, in the same Panel visual format
// EmuComparisonSection/RequestDetailPage's "Petición vs. tu biblioteca" use
// (uppercase section title + bordered/padded box). Tables always show their
// header shell, even with no data yet, rather than a "no data" paragraph.
function Panel({ title, live, loading, help, collapsible, defaultExpanded = false, fill, children }: {
  title: string
  live?: boolean
  // Shown as a spinning icon at the RIGHT edge of the header, visible even
  // while collapsed — lets the user tell which section is currently being
  // worked on (staging's nomenclature -> remux -> checks sub-steps, or the
  // real upload pipeline once queued) without opening anything.
  loading?: boolean
  help?: string
  collapsible?: boolean
  defaultExpanded?: boolean
  // Fills the remaining vertical space below it and lets its content scroll
  // internally — same fill+internal-scroll pattern LibraryChildrenSection
  // uses for Temporadas/Capítulos, so this section's table never grows the
  // whole page and its bottom edge keeps the page's usual bottom margin.
  fill?: boolean
  children: React.ReactNode
}) {
  const [expanded, setExpanded] = useState(defaultExpanded)
  const open = !collapsible || expanded
  return (
    <div style={{ marginTop: 28, ...(fill ? { flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' } : {}) }}>
      <div
        onClick={collapsible ? () => setExpanded(e => !e) : undefined}
        style={{
          // Same size as Biblioteca's Temporadas/Capítulos section titles
          // (LibraryChildrenSection) — this is now the only other "fixed,
          // always-expanded section title" in the app, so they should read
          // the same size at a glance.
          fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em',
          color: 'var(--text-secondary)', marginBottom: 12, display: 'flex', alignItems: 'center', gap: 6,
          cursor: collapsible ? 'pointer' : undefined, userSelect: collapsible ? 'none' : undefined,
          flexShrink: 0,
        }}
      >
        {collapsible && (
          <span style={{ display: 'inline-flex', fontSize: 10, transform: open ? 'rotate(90deg)' : 'none', transition: 'transform 0.15s' }}>▶</span>
        )}
        {title}
        {help && <span onClick={e => e.stopPropagation()}><InfoIcon text={help} /></span>}
        {loading && <span className="spinner" style={{ width: 13, height: 13, borderWidth: 2 }} />}
        {live && <span style={{ color: '#22c55e', fontWeight: 400, textTransform: 'none', letterSpacing: 0 }}>(en directo)</span>}
      </div>
      {open && (
        <div
          className="detail-card"
          style={{
            padding: '16px 18px', borderRadius: 10,
            ...(fill ? { flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' } : {}),
          }}
        >
          {children}
        </div>
      )}
    </div>
  )
}

const NOMENCLATURE_FIELD_ROWS: { key: string; label: string; hideFor?: string[] }[] = [
  { key: 'proposed_title', label: 'Título propuesto' },
  { key: 'series_title', label: 'Serie', hideFor: ['movie'] },
  { key: 'year', label: 'Año' },
  { key: 'season_number', label: 'Temporada', hideFor: ['movie'] },
  { key: 'resolution', label: 'Resolución' },
  { key: 'source', label: 'Source' },
  { key: 'provider_final', label: 'Proveedor' },
  { key: 'video_codec', label: 'Códec de vídeo' },
  { key: 'audio_summary', label: 'Audio' },
  { key: 'subtitle_summary', label: 'Subtítulos' },
  { key: 'release_tag', label: 'Tag' },
]

// Same label/tooltip UploadWizardModal's INTERNAL_TITLE_LABEL uses — kept in
// sync manually since this page and the wizard don't share a components file.
const INTERNAL_TITLE_LABEL_TEXT = 'Título del archivo'
const INTERNAL_TITLE_TOOLTIP = 'Es el mismo texto que el nombre del torrent: también es el título interno, el que se graba dentro del propio contenedor .mkv.'

function GeneratingSpinner({ text }: { text: string }) {
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, color: 'var(--text-muted)', fontSize: 13, padding: '2px 0' }}>
      <span className="spinner" style={{ width: 12, height: 12, borderWidth: 2 }} />
      {text}
    </span>
  )
}

function NomenclatureSection({ snapshot, mediaType, isStaging }: { snapshot: UploadJob['nomenclature_snapshot']; mediaType?: string | null; isStaging?: boolean }) {
  if (!snapshot && isStaging) {
    return <GeneratingSpinner text="Generando nomenclatura para eMuwarez…" />
  }
  const data = (snapshot ?? {}) as Record<string, unknown>
  const name = snapshot?.proposed_filename || snapshot?.proposed_title || null
  const rows = NOMENCLATURE_FIELD_ROWS.filter(r => !mediaType || !r.hideFor?.includes(mediaType))

  return (
    <>
      <div style={{ overflowX: 'auto' }}>
        <table className="data-table" style={{ fontSize: 12.5 }}>
          <thead>
            <tr><th>Campo</th><th>Valor</th></tr>
          </thead>
          <tbody>
            {rows.map(r => {
              const value = data[r.key]
              return (
                <tr key={r.key}>
                  <td style={{ fontWeight: 600 }}>{r.label}</td>
                  <td style={{ fontFamily: 'monospace' }}>{value != null && value !== '' ? String(value) : '–'}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      <div style={{ marginTop: 14, display: 'grid', gap: 10 }}>
        <div>
          <div style={{ fontSize: 11, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 3 }}>
            Nombre del torrent
          </div>
          <div style={{ fontFamily: 'monospace', fontSize: 13, wordBreak: 'break-all' }}>{name || '–'}</div>
        </div>
        <div>
          <div style={{ fontSize: 11, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 3, display: 'flex', alignItems: 'center', gap: 5 }}>
            {INTERNAL_TITLE_LABEL_TEXT}
            <InfoIcon text={INTERNAL_TITLE_TOOLTIP} />
          </div>
          <div style={{ fontFamily: 'monospace', fontSize: 13, wordBreak: 'break-all' }}>{name || '–'}</div>
        </div>
      </div>
    </>
  )
}

const REMUX_COLUMNS = ['Tipo', 'Idioma', 'Nombre actual', 'Nombre nuevo', 'Predet.']

// Placeholder rows shown before the real remux plan exists — the exact track
// COUNT isn't knowable ahead of time (a file might have 3 audio tracks or
// none), but every remuxed file has at most one of each of these three KINDS
// of track, so one representative row per kind still gives a real preview of
// the table's shape instead of just an empty message.
const REMUX_TEMPLATE_ROWS: { type: string }[] = [
  { type: 'Vídeo' }, { type: 'Audio' }, { type: 'Subs' },
]

function EmptyRemuxShell() {
  return (
    <>
      <div style={{ overflowX: 'auto' }}>
        <table className="data-table" style={{ fontSize: 12.5 }}>
          <thead>
            <tr>{REMUX_COLUMNS.map(c => <th key={c}>{c}</th>)}</tr>
          </thead>
          <tbody>
            {REMUX_TEMPLATE_ROWS.map(r => (
              <tr key={r.type} style={{ opacity: 0.5, fontStyle: 'italic' }}>
                <td>{r.type}</td>
                <td>–</td>
                <td>–</td>
                <td>–</td>
                <td style={{ textAlign: 'center' }}>–</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  )
}

function RemuxSection({ snapshot, isStaging }: { snapshot: UploadJob['remux_snapshot']; isStaging?: boolean }) {
  const [expanded, setExpanded] = useState<Record<number, boolean>>({})
  if (!snapshot || (!snapshot.ordered_tracks?.length && !snapshot.episodes?.length)) {
    if (isStaging) return <GeneratingSpinner text="Generando reordenación de pistas…" />
    return <EmptyRemuxShell />
  }
  if (snapshot.episodes?.length) {
    return (
      <>
        {snapshot.episodes.map(ep => (
          <EpisodeAccordionRow
            key={ep.episode_id}
            episodeNumber={ep.episode_number}
            title={ep.title}
            expanded={!!expanded[ep.episode_id]}
            onToggle={() => setExpanded(e => ({ ...e, [ep.episode_id]: !e[ep.episode_id] }))}
          >
            <RemuxTable plan={{ status: 'applied', ordered_tracks: ep.ordered_tracks ?? [], errors: [], warnings: [] }} editable={false} />
          </EpisodeAccordionRow>
        ))}
      </>
    )
  }
  return <RemuxTable plan={{ status: 'applied', ordered_tracks: snapshot.ordered_tracks ?? [], errors: [], warnings: [] }} editable={false} />
}

// Static topic per check id — matches services/upload_checks.py's CHECK
// ids exactly (renameable for a single file, season_pack for a season pack,
// then output/qbittorrent/imghosts/emuwarez shared by both).
const CHECK_TOPICS: { id: string; label: string }[] = [
  { id: 'renameable', label: 'Renombrado' },
  { id: 'season_pack', label: 'Pack de temporada' },
  { id: 'output', label: 'Directorio de salida' },
  { id: 'qbittorrent', label: 'qBittorrent' },
  { id: 'imghosts', label: 'Repositorio de imágenes' },
  { id: 'emuwarez', label: 'Conexión con eMuwarez' },
]

function checkTopicsFor(mediaType?: string | null): { id: string; label: string }[] {
  const isSeason = mediaType === 'season'
  return CHECK_TOPICS.filter(t => {
    if (t.id === 'renameable') return !isSeason
    if (t.id === 'season_pack') return isSeason
    return true
  })
}

const CHECK_STATUS_BADGE: Record<string, string> = {
  ok: 'badge status-available',
  fail: 'badge status-error',
  skip: 'badge status-unknown',
}
const CHECK_STATUS_TEXT: Record<string, string> = { ok: 'OK', fail: 'Error', skip: 'Omitida' }

function ChecksSection({ snapshot, mediaType, isActive }: {
  snapshot: UploadJob['checks_snapshot']
  mediaType?: string | null
  isActive: boolean
}) {
  const topics = checkTopicsFor(mediaType)
  const byId = new Map((snapshot?.checks ?? []).map(c => [c.id, c]))

  if (!snapshot && isActive) {
    return (
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, color: 'var(--text-muted)', fontSize: 13, padding: '2px 0' }}>
        <span className="spinner" style={{ width: 12, height: 12, borderWidth: 2 }} />
        Esperando a la nomenclatura de eMuwarez…
      </span>
    )
  }

  return (
    <div style={{ overflowX: 'auto' }}>
      <table className="data-table" style={{ fontSize: 12.5 }}>
        <thead><tr><th>Comprobación</th><th>Estado</th><th>Detalle</th></tr></thead>
        <tbody>
          {topics.map(t => {
            const c = byId.get(t.id)
            return (
              <tr key={t.id}>
                <td>{t.label}</td>
                <td>
                  {c ? (
                    <span
                      className={`${CHECK_STATUS_BADGE[c.status] || 'badge status-unknown'}${c.status === 'fail' ? ' badge-blink' : ''}`}
                      style={{ fontSize: '0.72rem' }}
                    >
                      {CHECK_STATUS_TEXT[c.status] || c.status}
                    </span>
                  ) : (
                    <span className="badge status-unknown" style={{ fontSize: '0.72rem' }}>Pendiente</span>
                  )}
                </td>
                <td style={{ color: 'var(--text-muted)' }}>
                  {c ? [c.label, c.message].filter(Boolean).join(': ') : '–'}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

const PHASE_STATUS_BADGE: Record<string, string> = {
  done: 'badge status-available',
  running: 'badge status-queued',
  pending: 'badge status-unknown',
  failed: 'badge status-error',
  cancelled: 'badge status-unknown',
}
const PHASE_STATUS_TEXT: Record<string, string> = {
  done: 'Completada',
  running: 'En curso',
  pending: 'Pendiente',
  failed: 'Fallida',
  cancelled: 'Cancelada',
}

// Fixed pipeline stages (mirrors services/uploadrr_progress.py's PHASES) —
// shown as an all-pending shell before the job has any real progress_json
// yet. Uploadrr-EMU's own internal phases (queue -> ... -> uploading to
// eMuwarez) are each their own row, not collapsed into one "Subiendo" bucket.
const DEFAULT_PHASES: UploadProgressPhase[] = [
  { key: 'nomenclature', label: 'Aplicación de nomenclatura', status: 'pending', pct: 0 },
  { key: 'remux', label: 'Reordenación o renombrado de pistas', status: 'pending', pct: 0 },
  { key: 'verificacion_presubida', label: 'Inicio de Uploadrr', status: 'pending', pct: 0 },
  { key: 'screenshots', label: 'Generación y subida de capturas', status: 'pending', pct: 0 },
  { key: 'hash_torrent', label: 'Cálculo de hash del torrent', status: 'pending', pct: 0 },
  { key: 'uploading_emu', label: 'Subida a eMuwarez', status: 'pending', pct: 0 },
  { key: 'qbittorrent_add', label: 'Subida a qBittorrent', status: 'pending', pct: 0 },
]

// Not a live per-second ticker — matches formatElapsed's convention
// elsewhere on this page: recomputed from Date.now() on every render (i.e.
// every poll refresh), not animated in between. `fallbackEnd` freezes a
// phase's duration at the job's own finished_at when the phase itself never
// got a finished_at (e.g. it was mid-run when the whole job died) — without
// it, a stuck "running" phase's duration keeps counting up from Date.now()
// forever, long after the job itself has stopped.
function formatPhaseDuration(startedAt?: string | null, finishedAt?: string | null, fallbackEnd?: string | null): string {
  if (!startedAt) return '–'
  const start = parseServerDate(startedAt).getTime()
  const endSource = finishedAt ?? fallbackEnd
  const end = endSource ? parseServerDate(endSource).getTime() : Date.now()
  const secs = Math.max(0, Math.round((end - start) / 1000))
  return formatSecondsHM(secs)
}

const JOB_TERMINAL_PHASE_STATUS: Record<string, string> = { failed: 'failed', cancelled: 'cancelled' }

// Percentage + a bar, same look as the topbar's own sync progress
// (.sync-chip-bar/.sync-chip-bar-fill) — the bar fills the rest of the
// (wide) Progreso column instead of the topbar's own fixed 140px.
function ProgressCell({ pct, bold }: { pct: number; bold?: boolean }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
      <span style={{ fontWeight: bold ? 700 : undefined, fontVariantNumeric: 'tabular-nums', flexShrink: 0 }}>{pct}%</span>
      <div className="sync-chip-bar" style={{ width: 'auto', flex: 1 }}>
        <div className="sync-chip-bar-fill" style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}

function PhasesSection({ phases, globalPct, job }: { phases: UploadProgressPhase[]; globalPct: number; job: UploadJob }) {
  // If the job itself has stopped (failed/cancelled) but a phase snapshot was
  // never updated past "running" (e.g. mkvmerge's timeout kills the job
  // without touching progress_json), show that phase as failed/cancelled
  // too instead of leaving it looking like it's still going.
  const overrideStatus = JOB_TERMINAL_PHASE_STATUS[job.status]
  return (
    <div style={{ overflow: 'auto', flex: 1, minHeight: 0 }}>
      <table className="data-table" style={{ fontSize: 12.5, tableLayout: 'fixed' }}>
        <colgroup>
          <col style={{ width: 34 }} />
          <col style={{ width: 200 }} />
          <col style={{ width: 90 }} />
          <col style={{ width: 360 }} />
          <col style={{ width: 143 }} />
          <col style={{ width: 143 }} />
          <col style={{ width: 75 }} />
        </colgroup>
        <thead>
          <tr>
            <th>#</th><th>Fase</th><th>Estado</th><th>Progreso</th>
            <th>Creado</th><th>Finalizado</th><th>Duración</th>
          </tr>
        </thead>
        <tbody>
          {phases.map((p, i) => {
            const status = (p.status === 'running' && overrideStatus) ? overrideStatus : p.status
            return (
            <tr key={p.key}>
              <td style={{ color: 'var(--text-muted)', fontVariantNumeric: 'tabular-nums' }}>{i + 1}</td>
              <td>{p.label}</td>
              <td>
                <span
                  className={`${PHASE_STATUS_BADGE[status] || 'badge status-unknown'}${status === 'failed' ? ' badge-blink' : ''}`}
                  style={{ fontSize: '0.72rem' }}
                >
                  {PHASE_STATUS_TEXT[status] || status}
                </span>
              </td>
              <td><ProgressCell pct={p.pct} /></td>
              <td style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{p.started_at ? formatDate(p.started_at) : '–'}</td>
              <td style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{p.finished_at ? formatDate(p.finished_at) : (overrideStatus ? formatDate(job.finished_at) : '–')}</td>
              <td style={{ fontVariantNumeric: 'tabular-nums' }}>{formatPhaseDuration(p.started_at, p.finished_at, overrideStatus ? job.finished_at : null)}</td>
            </tr>
            )
          })}
          {/* Fila fija al pie (.sticky-footer-row en components.css): el
              progreso del job entero, siempre visible al fondo del área de
              scroll en vez de tener que bajar por todas las fases para verlo,
              igual que la cabecera se queda pegada arriba.

              Sí, el campo "Progreso" de la tarjeta Tiempos da el mismo
              número, y por eso se quitó en su día (489b422). Vuelve porque
              allí es un número suelto y aquí está en su contexto: alineado
              con las columnas de inicio, fin y duración de las fases que lo
              componen. */}
          <tr className="sticky-footer-row" style={{ borderTop: '2px solid var(--border)' }}>
            <td />
            <td style={{ fontWeight: 700 }} colSpan={2}>Progreso global</td>
            <td><ProgressCell pct={globalPct} bold /></td>
            <td style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', fontWeight: 700 }}>{formatDate(job.started_at ?? job.created_at ?? null)}</td>
            <td style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', fontWeight: 700 }}>{job.finished_at ? formatDate(job.finished_at) : '–'}</td>
            <td style={{ fontVariantNumeric: 'tabular-nums', fontWeight: 700 }}>{formatPhaseDuration(job.started_at ?? job.created_at, job.finished_at)}</td>
          </tr>
        </tbody>
      </table>
    </div>
  )
}

export function UploadJobDetailPage({ job, onBack, onStart, onRetry, onCancel, onDelete, onOpenLibraryItem, retryError }: {
  job: UploadJob
  onBack: () => void
  onStart: (job: UploadJob) => void
  onRetry: (job: UploadJob) => void
  onCancel: (jobId: number) => void
  onDelete: (job: UploadJob) => void
  onOpenLibraryItem?: (id: number) => void
  retryError?: string | null
}) {
  const jobId = job.id!
  const isRunning = job.status === 'running'
  const isQueued = job.status === 'queued'
  const isPreparing = job.status === 'preparing'
  const isStaging = job.status === 'staging'
  const canCancel = isRunning || isQueued || isStaging
  // Mirrors the backend's delete_upload_job() gate exactly: only a terminal,
  // dead-end job (never running/queued/staging, nothing left to interrupt).
  const canDelete = job.status === 'failed' || job.status === 'cancelled'
  // Which section is currently "working" — staging advances through its own
  // sub-steps (stage: nomenclature -> remux -> checks) one snapshot at a
  // time; once queued, "Progreso de la subida" covers everything else until
  // the upload finishes (its own phase table already breaks that down).
  const stagingLoadingNomenclature = isStaging && job.stage === 'nomenclature'
  const stagingLoadingRemux = isStaging && job.stage === 'remux'
  const stagingLoadingChecks = isStaging && job.stage === 'checks'
  const progressIsActive = isQueued || isPreparing || isRunning
  // The Progreso field's own icon: a live spinner while genuinely doing
  // something (staging included, unlike progressIsActive above which only
  // covers the panel below it), the plain pulse icon once there's nothing
  // left to show progress of.
  const progressValueLoading = isStaging || isQueued || isPreparing || isRunning
  useTicker(isQueued)

  // The 4 sections that used to be their own collapsible Panel below now
  // live as mini-card fields in "Estado de la subida" (same visual pattern
  // as Proveedor/Origen) — clicking one opens its content in a modal instead
  // of expanding an accordion. "Progreso de la subida" stays its own
  // always-expanded section (see the Panel usage further down, now with no
  // `collapsible` prop at all).
  const [showNomenclatura, setShowNomenclatura] = useState(false)
  const [showRemux, setShowRemux] = useState(false)
  const [showChecks, setShowChecks] = useState(false)
  const [showActividad, setShowActividad] = useState(false)
  const checksReady = job.checks_snapshot?.ready
  const checksFailed = job.checks_snapshot != null && checksReady === false
  const checksLabel = !job.checks_snapshot ? 'Pendiente' : checksReady ? 'OK' : 'Error'

  const [logs, setLogs] = useState<UploadJobLog[]>([])
  const [loadingLogs, setLoadingLogs] = useState(true)
  const loadLogs = async () => {
    try {
      // tail=true + a very high limit: effectively the WHOLE log, not just a
      // window of it — a season with many episodes (real Uploadrr-EMU
      // output per chapter) can easily produce many thousands of lines, and
      // a small fixed limit (previously 300) silently hid everything before
      // the last window, with no way to see full activity for that upload.
      const r = await getUploadJobLogs(jobId, 100000, 0, true)
      setLogs([...r.logs].sort((a, b) => a.created_at.localeCompare(b.created_at)))
    } catch { /* ignore */ } finally { setLoadingLogs(false) }
  }
  useEffect(() => { loadLogs(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [jobId])
  // El registro se recarga cuando el servidor avisa de que hay líneas nuevas.
  // El aviso NO trae las líneas —el proceso escupe cientos por segundo— y va
  // agrupado a una vez por segundo en el servidor: solo dice que las hay. El
  // sondeo de 2 s queda de red de seguridad para cuando el canal está caído.
  useRefrescoPorAvisos([...AVISOS_SUBIDA, 'subida-log'], loadLogs, {
    soloVisible: AVISOS_SUBIDA_PROGRESO,
    cadaSinCanal: 2000,
    activo: isRunning || isPreparing || isStaging,
    // Con varias subidas a la vez, el detalle de una no se recarga porque otra
    // distinta esté avanzando.
    filtro: aviso => aviso.job_id === jobId,
  })
  // No artificial cap here: `logs` is already the last 300 lines (tail=true
  // above). Slicing further to a small window (e.g. -40) used to discard
  // everything older every 2s poll, even though the scrollable <pre> below
  // has room to show much more — the user just couldn't scroll back to it.
  const logsBoxRef = useRef<HTMLPreElement | null>(null)
  useEffect(() => {
    const el = logsBoxRef.current
    if (!el) return
    // Only auto-follow the tail if the user hasn't scrolled up to read
    // history — otherwise a live-updating job would keep yanking them back
    // to the bottom every 2s.
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 40
    if (atBottom) el.scrollTop = el.scrollHeight
  }, [logs])

  const progress = job.progress
  const mediaEmoji = job.media_type === 'series' || job.media_type === 'episode' ? '📺' : '🎬'

  return (
    <div style={{ width: '100%', height: '100%', minHeight: 0, display: 'flex', flexDirection: 'column' }}>
      <div style={{ flexShrink: 0 }}>
      <DetailHero backdropUrl={job.backdrop_url}>
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 16, flexWrap: 'wrap', marginBottom: 16 }}>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <button className="btn btn-ghost btn-sm" onClick={onBack}>← Volver a Subidas</button>
        </div>
        <div style={{ display: 'flex', gap: 8, flexShrink: 0, flexWrap: 'wrap' }}>
          {job.library_item_id != null && (
            <button className="btn btn-primary btn-sm" onClick={() => onOpenLibraryItem?.(job.library_item_id!)}><LibraryButtonIcon /> Ver en Biblioteca</button>
          )}
          {job.status === 'ready' && <button className="btn btn-primary btn-sm" onClick={() => onStart(job)}><UploadButtonIcon /> Iniciar subida</button>}
          {['failed', 'cancelled'].includes(job.status) && <button className="btn btn-primary btn-sm" onClick={() => onRetry(job)}><RetryButtonIcon /> Reintentar</button>}
          {canCancel && <button className="btn btn-danger btn-sm" onClick={() => onCancel(jobId)}><CancelButtonIcon /> Cancelar</button>}
          {canDelete && <button className="btn btn-danger btn-sm" onClick={() => onDelete(job)}><DeleteButtonIcon /> Borrar</button>}
        </div>
      </div>

      <div style={{ marginBottom: 20 }}>
        <DetailTitle>
          <DetailTitleText title={job.display_title || job.title || `Job ${jobId}`} />
          {isRunning && <span style={{ fontSize: 11, color: '#22c55e' }}>● en vivo</span>}
        </DetailTitle>
      </div>

      <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap', alignItems: 'flex-start' }}>
        <DetailPoster url={job.poster_url ? posterUrl(job.poster_url, 'w500') : null} alt={job.title || `Job ${jobId}`} fallbackEmoji={mediaEmoji} />

        <div style={{ flex: 1, minWidth: 300 }}>
          {retryError && (
            <div style={{ padding: '8px 12px', background: 'rgba(248,113,113,0.1)', border: '1px solid rgba(248,113,113,0.3)', borderRadius: 6, fontSize: 12.5, color: '#fca5a5', marginBottom: 16 }}>
              {retryError}
            </div>
          )}

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 16, minHeight: DETAIL_CARD_HEIGHT }}>
            <Card title="Estado de la subida" icon={<StatusCardIcon />}>
              <FieldRow label="Estado"><span className={STATUS_CLASS[job.status] || 'badge req-unknown'}>{statusLabel(job.status)}</span></FieldRow>
              <FieldRow label="Tipo">
                <ValueChip><ValueIcon><TypeValueIcon /></ValueIcon><span className="txt">{UPLOAD_TYPE_LABEL[job.media_type ?? ''] ?? '–'}</span></ValueChip>
              </FieldRow>
              <FieldRow label="Origen">
                {job.instance_type
                  ? <ValueChip><ServiceLabel type={job.instance_type} label={job.instance_name ?? job.instance_type} size={15} /></ValueChip>
                  : <span className="muted">–</span>}
              </FieldRow>
              <FieldRow label="Petición"><StatusBadge status={job.request_status || 'Sin petición'} type="request" /></FieldRow>
              <FieldRow label="Nomenclatura" help="Los campos que componen el nombre final del torrent, del archivo y de su título interno.">
                <ValueChip as="button" linkable onClick={() => setShowNomenclatura(true)} title="Ver nomenclatura">
                  {stagingLoadingNomenclature
                    ? <span className="spinner" style={{ width: 14, height: 14, borderWidth: 2, flexShrink: 0 }} />
                    : <ValueIcon><NomenclatureValueIcon /></ValueIcon>}
                  <span className="txt">{job.nomenclature_snapshot ? 'Ver' : 'Pendiente'}</span>
                </ValueChip>
              </FieldRow>
              <FieldRow label="Reordenación/Renombrado" help="Antes de subir se hace un remux para reordenar las pistas de audio y subtítulos y ponerles el nombre adecuado, siguiendo la prioridad de idioma: Español (Castellano) → Català → Inglés → el resto.">
                <ValueChip as="button" linkable onClick={() => setShowRemux(true)} title="Ver reordenación de pistas">
                  {stagingLoadingRemux
                    ? <span className="spinner" style={{ width: 14, height: 14, borderWidth: 2, flexShrink: 0 }} />
                    : <ValueIcon><AudioCodecValueIcon /></ValueIcon>}
                  <span className="txt">{job.remux_snapshot ? 'Ver' : 'Pendiente'}</span>
                </ValueChip>
              </FieldRow>
              <FieldRow label="Verificación pre-subida" help="Las comprobaciones que se hacen antes de subir: que el archivo se pueda renombrar o enlazar, que el directorio de salida sea escribible, y que qBittorrent, el repositorio de imágenes y eMuwarez estén disponibles. Si alguna falla (no las que se omiten), la subida no continúa.">
                <ValueChip as="button" linkable blink={checksFailed ? 'alert' : undefined} onClick={() => setShowChecks(true)} title="Ver verificación pre-subida">
                  {stagingLoadingChecks
                    ? <span className="spinner" style={{ width: 14, height: 14, borderWidth: 2, flexShrink: 0 }} />
                    : <ValueIcon><ChecksValueIcon /></ValueIcon>}
                  <span className="txt">{checksLabel}</span>
                </ValueChip>
              </FieldRow>
              <FieldRow label="Actividad" help="El registro de lo que va haciendo la subida en tiempo real: si se ha cancelado, si ha dado error en alguna fase y por qué, o si se ha completado con éxito.">
                <ValueChip as="button" linkable blink={isRunning ? 'live' : undefined} onClick={() => setShowActividad(true)} title="Ver registro de actividad">
                  <ValueIcon><LogsValueIcon /></ValueIcon>
                  <span className="txt">Ver Logs</span>
                </ValueChip>
              </FieldRow>
            </Card>

            <Card title="Tiempos" icon={<ClockCardIcon />}>
              <FieldRow label="Progreso">
                <ValueChip>
                  {progressValueLoading
                    ? <span className="spinner" style={{ width: 14, height: 14, borderWidth: 2, flexShrink: 0 }} />
                    : <ValueIcon><ProgressValueIcon /></ValueIcon>}
                  <span className="txt">
                    {isStaging
                      ? 'Generando nomenclatura'
                      : isQueued
                      ? `En cola · ${queuedWaitText(job)}`
                      : (job.status === 'preparing' || job.status === 'running')
                      ? (() => {
                          const info = currentPhaseInfo(job)
                          const label = info?.label ?? phaseLabel(job.progress_phase)
                          const counter = info?.counterText ? ` (${info.counterText})` : ''
                          const elapsed = progressCounter(job)
                          return `${label}${counter}${elapsed ? ` · ${elapsed}` : ''}`
                        })()
                      : '–'}
                  </span>
                </ValueChip>
              </FieldRow>
              <FieldRow label="Creado">
                <ValueChip><ValueIcon><CalendarValueIcon /></ValueIcon><span className="txt">{formatDateTimeSeconds(job.created_at ?? null)}</span></ValueChip>
              </FieldRow>
              <FieldRow label="Finalizado">
                <ValueChip><ValueIcon><CalendarValueIcon /></ValueIcon><span className="txt">{formatDateTimeSeconds(job.finished_at ?? null)}</span></ValueChip>
              </FieldRow>
              <FieldRow label="Duración">
                <ValueChip><ValueIcon><ClockCardIcon /></ValueIcon><span className="txt">{formatElapsed(job)}</span></ValueChip>
              </FieldRow>
              <FieldRow label="Reintentos">
                <ValueChip><ValueIcon><RetryButtonIcon /></ValueIcon><span className="txt">{(job.retry_count ?? 0) > 0 ? `x${job.retry_count}` : '–'}</span></ValueChip>
              </FieldRow>
            </Card>
          </div>
        </div>
      </div>
      </DetailHero>
      </div>

      {/* Only "Progreso de la subida" keeps its own always-expanded section —
          no `collapsible` prop at all, same fixed pattern Temporadas/
          Capítulos use in Biblioteca (LibraryChildrenSection). The other 4
          (Nomenclatura, Reordenación/Renombrado, Verificación pre-subida,
          Actividad) moved into "Estado de la subida" above as mini-card
          fields — each opens its own modal below instead. */}
      <Panel
        title="Progreso de la subida" loading={progressIsActive} fill
        help="Cada fase por la que pasa la subida (comprobación de integridad, nomenclatura, remux, subida a eMuwarez…), con su estado, cuándo empezó y terminó, y el porcentaje global de la subida completa."
      >
        {isStaging ? (
          <GeneratingSpinner text="Esperando a que termine la verificación previa…" />
        ) : (
          <PhasesSection phases={progress?.phases?.length ? progress.phases : DEFAULT_PHASES} globalPct={progress?.global_pct ?? 0} job={job} />
        )}
      </Panel>

      {showNomenclatura && (
        <div className="modal-overlay" onClick={() => setShowNomenclatura(false)}>
          <div className="modal-panel modal-wide" onClick={e => e.stopPropagation()} style={{ maxWidth: 720 }}>
            <div className="modal-header">
              <h2 className="modal-title">Nomenclatura</h2>
              <button className="modal-close" onClick={() => setShowNomenclatura(false)}>✕</button>
            </div>
            <div className="modal-body">
              <NomenclatureSection snapshot={job.nomenclature_snapshot} mediaType={job.media_type} isStaging={isStaging} />
            </div>
          </div>
        </div>
      )}

      {showRemux && (
        <div className="modal-overlay" onClick={() => setShowRemux(false)}>
          <div className="modal-panel modal-wide" onClick={e => e.stopPropagation()} style={{ maxWidth: 780 }}>
            <div className="modal-header">
              <h2 className="modal-title">Reordenación/Renombrado</h2>
              <button className="modal-close" onClick={() => setShowRemux(false)}>✕</button>
            </div>
            <div className="modal-body">
              <RemuxSection snapshot={job.remux_snapshot} isStaging={isStaging} />
            </div>
          </div>
        </div>
      )}

      {showChecks && (
        <div className="modal-overlay" onClick={() => setShowChecks(false)}>
          <div className="modal-panel modal-wide" onClick={e => e.stopPropagation()} style={{ maxWidth: 720 }}>
            <div className="modal-header">
              <h2 className="modal-title">Verificación pre-subida</h2>
              <button className="modal-close" onClick={() => setShowChecks(false)}>✕</button>
            </div>
            <div className="modal-body">
              <ChecksSection
                snapshot={job.checks_snapshot}
                mediaType={job.media_type}
                isActive={isQueued || isPreparing || isRunning || isStaging}
              />
            </div>
          </div>
        </div>
      )}

      {showActividad && (
        <div className="modal-overlay" onClick={() => setShowActividad(false)}>
          <div className="modal-panel modal-wide" onClick={e => e.stopPropagation()} style={{ maxWidth: 680 }}>
            <div className="modal-header">
              <h2 className="modal-title">Actividad{isRunning ? ' (en directo)' : ''}</h2>
              <button className="modal-close" onClick={() => setShowActividad(false)}>✕</button>
            </div>
            <div className="modal-body">
              <pre ref={logsBoxRef} style={{ margin: 0, maxHeight: 420, overflowY: 'auto', fontSize: '0.76rem', lineHeight: 1.5, whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>
                {loadingLogs ? 'Cargando…' : logs.length === 0 ? 'Sin actividad registrada todavía.' : logs.map(log => {
                  // created_at is stored/sent in UTC — naively slicing the raw
                  // string (the old approach) showed the UTC hour verbatim,
                  // disagreeing with Creado/Finalizado above (which DO convert
                  // to the browser's local time via parseServerDate).
                  const ts = parseServerDate(log.created_at).toLocaleTimeString('es-ES', {
                    hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
                  })
                  return `[${ts}] ${log.message}\n`
                })}
              </pre>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
