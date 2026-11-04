import { useState, useEffect, useRef } from 'react'
import type { PasoSubida, UploadJob, UploadJobLog, UploadProgressPhase } from '../types/api'
import { getUploadJobLogs } from '../api/uploads'
import { aplicarLineas, ultimaSecuenciaDe } from '../utils/registroSubida'
import { estadoDePaso } from '../utils/pasosSubida'
import { posterUrl } from '../utils/libraryItem'
import { formatDate, parseServerDate } from '../utils/format'
import { segundosDeFase } from '../utils/lineaDeTiempo'
import { InfoIcon } from './InfoIcon'
import { SeedingBloque } from './SaludSeeding'
import { StatsTrackerBloque } from './StatsTracker'
import type { SeedingEstado } from '../hooks/useSeeding'
import { DetailPoster, DetailHero, DetailTitle, DetailTitleText } from './DetailCard'
import { ResultadoSubida, type Consulta } from './detalle-subida/ResultadoSubida'
import { DondeSeFueElTiempo } from './detalle-subida/DondeSeFueElTiempo'
import { RemuxTable } from './asistente/RemuxTable'
import { EpisodeAccordionRow } from './asistente/Capitulos'
import { formatSecondsHM } from '../utils/uploadStatus'
import { useRefrescoPorAvisos, AVISOS_SUBIDA, AVISOS_SUBIDA_PROGRESO } from '../hooks/useRefrescoPorAvisos'
import { IconoDesplegar, IconoTipo } from './Iconos'
import { Modal } from './Modal'

// Líneas del registro que se piden al abrir «Actividad», y las que se guardan como mucho en pantalla.
const LINEAS_INICIALES = 2000
const LINEAS_MAX = 5000

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
    <div className={fill ? 'dsub-panel dsub-panel-llena' : 'dsub-panel'}>
      <h2 className="dsub-panel-titulo">
        {collapsible ? (
          <button type="button" className="dsub-panel-boton" aria-expanded={open} onClick={() => setExpanded(e => !e)}>
            <IconoDesplegar abierto={open} size={12} />
            {title}
          </button>
        ) : title}
        {help && <InfoIcon text={help} />}
        {loading && <span className="spinner dsub-spinner-13" />}
        {live && <span className="dsub-en-directo">(en directo)</span>}
      </h2>
      {open && (
        <div
          className={fill ? 'detail-card dsub-caja dsub-panel-llena' : 'detail-card dsub-caja'}
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
const INTERNAL_TITLE_TOOLTIP = 'Es el nombre del torrent sin acentos y con puntos: también es el título interno, el que se graba dentro del propio contenedor .mkv.'

function GeneratingSpinner({ text }: { text: string }) {
  return (
    <span className="dsub-generando">
      <span className="spinner dsub-spinner-12" />
      {text}
    </span>
  )
}

function NomenclatureSection({ snapshot, mediaType, isStaging }: { snapshot: UploadJob['nomenclature_snapshot']; mediaType?: string | null; isStaging?: boolean }) {
  if (!snapshot && isStaging) {
    return <GeneratingSpinner text="Generando nomenclatura para eMuwarez…" />
  }
  const data = (snapshot ?? {}) as Record<string, unknown>
  const name = snapshot?.proposed_torrent_name || snapshot?.proposed_filename || snapshot?.proposed_title || null
  const fileName = snapshot?.proposed_filename || name
  const rows = NOMENCLATURE_FIELD_ROWS.filter(r => !mediaType || !r.hideFor?.includes(mediaType))

  return (
    <>
      <div className="dsub-scroll-x">
        <table className="data-table dsub-tabla">
          <thead>
            <tr><th>Campo</th><th>Valor</th></tr>
          </thead>
          <tbody>
            {rows.map(r => {
              const value = data[r.key]
              return (
                <tr key={r.key}>
                  <td className="dsub-b600">{r.label}</td>
                  <td className="dsub-mono">{value != null && value !== '' ? String(value) : '—'}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      <div className="dsub-bloques">
        <div>
          <div className="dsub-etiqueta">
            Nombre del torrent
          </div>
          <div className="dsub-valor-mono">{name || '—'}</div>
        </div>
        <div>
          <div className="dsub-etiqueta dsub-etiqueta-info">
            {INTERNAL_TITLE_LABEL_TEXT}
            <InfoIcon text={INTERNAL_TITLE_TOOLTIP} />
          </div>
          <div className="dsub-valor-mono">{fileName || '—'}</div>
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
      <div className="dsub-scroll-x">
        <table className="data-table dsub-tabla">
          <thead>
            <tr>{REMUX_COLUMNS.map(c => <th key={c}>{c}</th>)}</tr>
          </thead>
          <tbody>
            {REMUX_TEMPLATE_ROWS.map(r => (
              <tr key={r.type} className="dsub-fila-plantilla">
                <td>{r.type}</td>
                <td>—</td>
                <td>—</td>
                <td>—</td>
                <td className="dsub-centro">—</td>
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
  if (snapshot?.omitida) return <p className="form-hint">No se han tocado las pistas ({snapshot.omitida}).</p>
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
            {ep.omitida
              ? <p className="form-hint">No se han tocado las pistas ({ep.omitida}).</p>
              : <RemuxTable plan={{ status: 'applied', ordered_tracks: ep.ordered_tracks ?? [], errors: [], warnings: [] }} editable={false} />}
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
      <GeneratingSpinner text="Esperando a la nomenclatura de eMuwarez…" />
    )
  }

  return (
    <div className="dsub-scroll-x">
      <table className="data-table dsub-tabla">
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
                      className={`${CHECK_STATUS_BADGE[c.status] || 'badge status-unknown'} dsub-badge-chico${c.status === 'fail' ? ' badge-blink' : ''}`}
                    >
                      {CHECK_STATUS_TEXT[c.status] || c.status}
                    </span>
                  ) : (
                    <span className="badge status-unknown dsub-badge-chico">Pendiente</span>
                  )}
                </td>
                <td className="dsub-muted">
                  {c ? [c.label, c.message].filter(Boolean).join(': ') : '—'}
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
  const secs = segundosDeFase(startedAt, finishedAt, fallbackEnd)
  return secs == null ? '—' : formatSecondsHM(secs)
}

const JOB_TERMINAL_PHASE_STATUS: Record<string, string> = { failed: 'failed', cancelled: 'cancelled' }

// Percentage + a bar, same look as the topbar's own sync progress
// (.sync-chip-bar/.sync-chip-bar-fill) — the bar fills the rest of the
// (wide) Progreso column instead of the topbar's own fixed 140px.
function ProgressCell({ pct, bold }: { pct: number; bold?: boolean }) {
  return (
    <div className="dsub-progreso">
      <span className={bold ? 'dsub-progreso-pct dsub-progreso-pct-negrita' : 'dsub-progreso-pct'}>{pct}%</span>
      <div className="sync-chip-bar dsub-barra">
        <div className="sync-chip-bar-fill" style={{ transform: `scaleX(${pct / 100})` }} />
      </div>
    </div>
  )
}

// Los pasos con nombre de la subida y cuál se paró (los manda el servidor: services/subida_pasos.py).
function PasosDeSubida({ pasos }: { pasos: PasoSubida[] }) {
  return (
    <ol aria-label="Pasos de la subida" className="dsub-pasos">
      {pasos.map((p, i) => {
        const e = estadoDePaso(p)
        return (
          <li key={p.clave} title={e.texto} aria-label={`${p.nombre}: ${e.texto}`} className={`dsub-paso dsub-paso-${e.clave}`}>
            <span aria-hidden="true">{e.simbolo}</span>
            <span>{i + 1}. {p.nombre}</span>
            {p.subpasos && p.subpasos.length > 0 && (
              <span className="dsub-subpasos">
                ({p.subpasos.map(sp => `${sp.nombre.toLowerCase()} ${sp.hecho ? '✓' : '○'}`).join(' · ')})
              </span>
            )}
          </li>
        )
      })}
    </ol>
  )
}

function PhasesSection({ phases, globalPct, job }: { phases: UploadProgressPhase[]; globalPct: number; job: UploadJob }) {
  // If the job itself has stopped (failed/cancelled) but a phase snapshot was
  // never updated past "running" (e.g. mkvmerge's timeout kills the job
  // without touching progress_json), show that phase as failed/cancelled
  // too instead of leaving it looking like it's still going.
  const overrideStatus = JOB_TERMINAL_PHASE_STATUS[job.status]
  return (
    <div className="dsub-fases-scroll">
      <table className="data-table dsub-tabla dsub-tabla-fija">
        <colgroup>
          <col className="dsub-col-34" />
          <col className="dsub-col-200" />
          <col className="dsub-col-90" />
          <col className="dsub-col-360" />
          <col className="dsub-col-143" />
          <col className="dsub-col-143" />
          <col className="dsub-col-75" />
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
              <td className="dsub-muted dsub-num">{i + 1}</td>
              <td>{p.label}</td>
              <td>
                <span
                  className={`${PHASE_STATUS_BADGE[status] || 'badge status-unknown'} dsub-badge-chico${status === 'failed' ? ' badge-blink' : ''}`}
                >
                  {PHASE_STATUS_TEXT[status] || status}
                </span>
              </td>
              <td><ProgressCell pct={p.pct} /></td>
              <td className="dsub-fecha">{p.started_at ? formatDate(p.started_at) : '—'}</td>
              <td className="dsub-fecha">{p.finished_at ? formatDate(p.finished_at) : (overrideStatus ? formatDate(job.finished_at) : '—')}</td>
              <td className="dsub-num">{formatPhaseDuration(p.started_at, p.finished_at, overrideStatus ? job.finished_at : null)}</td>
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
          <tr className="sticky-footer-row dsub-total">
            <td />
            <td className="dsub-b700" colSpan={2}>Progreso global</td>
            <td><ProgressCell pct={globalPct} bold /></td>
            <td className="dsub-fecha dsub-b700">{formatDate(job.started_at ?? job.created_at ?? null)}</td>
            <td className="dsub-fecha dsub-b700">{job.finished_at ? formatDate(job.finished_at) : '—'}</td>
            <td className="dsub-num dsub-b700">{formatPhaseDuration(job.started_at ?? job.created_at, job.finished_at)}</td>
          </tr>
        </tbody>
      </table>
    </div>
  )
}

export function UploadJobDetailPage({ job, onBack, onStart, onRetry, onCancel, onDelete, onOpenLibraryItem, seeding, retryError }: {
  job: UploadJob
  onBack: () => void
  onStart: (job: UploadJob) => void
  onRetry: (job: UploadJob, desdeElPrincipio?: boolean) => void
  onCancel: (jobId: number) => void
  onDelete: (job: UploadJob) => void
  onOpenLibraryItem?: (id: number) => void
  seeding: SeedingEstado
  retryError?: string | null
}) {
  const jobId = job.id!
  const isRunning = job.status === 'running'
  const isQueued = job.status === 'queued'
  const isPreparing = job.status === 'preparing'
  const isStaging = job.status === 'staging'
  const completada = job.status === 'completed'
  const progressIsActive = isQueued || isPreparing || isRunning

  // Nomenclatura, pistas, verificación y registro se abren en un modal desde el bloque de resultado.
  const [showNomenclatura, setShowNomenclatura] = useState(false)
  const [showRemux, setShowRemux] = useState(false)
  const [showChecks, setShowChecks] = useState(false)
  const [showActividad, setShowActividad] = useState(false)
  const abrirConsulta = (c: Consulta) => {
    if (c === 'nomenclatura') setShowNomenclatura(true)
    else if (c === 'remux') setShowRemux(true)
    else if (c === 'checks') setShowChecks(true)
    else setShowActividad(true)
  }

  // El registro solo se pide con «Actividad» abierta: las últimas líneas al abrir y luego solo las posteriores a la
  // última que se tiene (`sequence`). Antes se bajaba entero cada segundo de una subida, aunque nadie lo mirara.
  const [logs, setLogs] = useState<UploadJobLog[]>([])
  const [logsTotal, setLogsTotal] = useState(0)
  const [loadingLogs, setLoadingLogs] = useState(true)
  const actividadAbierta = useRef(false)
  actividadAbierta.current = showActividad
  const ultimaSecuencia = useRef(0)
  // Solo la respuesta de la última petición se aplica: una lenta que llegue tarde no pisa a otra más nueva.
  const logsSeq = useRef(0)
  const loadLogs = async () => {
    if (!actividadAbierta.current) return
    const seq = ++logsSeq.current
    const desde = ultimaSecuencia.current
    try {
      const r = desde > 0
        ? await getUploadJobLogs(jobId, LINEAS_MAX, 0, false, desde)
        : await getUploadJobLogs(jobId, LINEAS_INICIALES, 0, true)
      if (seq !== logsSeq.current) return
      setLogsTotal(r.total)
      ultimaSecuencia.current = ultimaSecuenciaDe(r.logs, desde)
      setLogs(prev => aplicarLineas(prev, r.logs, desde, LINEAS_MAX))
    } catch { /* ignore */ } finally { if (seq === logsSeq.current) setLoadingLogs(false) }
  }
  useEffect(() => {
    ultimaSecuencia.current = 0
    logsSeq.current++   // lo que esté en vuelo ya no vale
    setLogs([])
    setLogsTotal(0)
    if (!showActividad) return
    setLoadingLogs(true)
    loadLogs()
    // eslint-disable-next-line react-hooks/exhaustive-deps -- solo al cambiar de subida o al abrir Actividad; loadLogs se recrea en cada pintado
  }, [jobId, showActividad])
  // El registro se recarga cuando el servidor avisa de que hay líneas nuevas.
  // El aviso NO trae las líneas —el proceso escupe cientos por segundo— y va
  // agrupado a una vez por segundo en el servidor: solo dice que las hay. El
  // sondeo de 2 s queda de red de seguridad para cuando el canal está caído.
  useRefrescoPorAvisos([...AVISOS_SUBIDA, 'subida-log'], loadLogs, {
    soloVisible: AVISOS_SUBIDA_PROGRESO,
    cadaSinCanal: 2000,
    activo: showActividad && (isRunning || isPreparing || isStaging),
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
  const mediaIcon = <IconoTipo serie={job.media_type === 'series' || job.media_type === 'episode'} />

  const pasosDeSubida = !isStaging && job.pasos && job.pasos.length > 0 ? <PasosDeSubida pasos={job.pasos} /> : null
  const fases = <PhasesSection phases={progress?.phases?.length ? progress.phases : DEFAULT_PHASES} globalPct={progress?.global_pct ?? 0} job={job} />

  return (
    <div className="dsub-pagina">
      <div className="dsub-cabecera">
      <DetailHero backdropUrl={job.backdrop_url}>
      <div className="dsub-barra-sup">
        <button className="btn btn-ghost btn-sm" onClick={onBack}>Volver a Subidas</button>
      </div>

      <div className="dsub-titulo-caja">
        <DetailTitle>
          <h1 className="dsub-h1"><DetailTitleText title={job.display_title || job.title || `Job ${jobId}`} /></h1>
          {isRunning && <span className="dsub-en-vivo">● en vivo</span>}
        </DetailTitle>
      </div>

      <div className="dsub-cuerpo">
        <DetailPoster url={job.poster_url ? posterUrl(job.poster_url, 'w500') : null} alt={job.title || `Job ${jobId}`} fallbackIcon={mediaIcon} />

        <div className="dsub-columna">
          <ResultadoSubida
            job={job} seeding={seeding} retryError={retryError}
            onStart={onStart} onRetry={onRetry} onCancel={onCancel} onDelete={onDelete}
            onOpenLibraryItem={onOpenLibraryItem} onConsulta={abrirConsulta}
          />
          {completada ? <DondeSeFueElTiempo job={job} /> : pasosDeSubida}
        </div>
      </div>
      </DetailHero>
      </div>

      <SeedingBloque job={job} seeding={seeding} />
      <StatsTrackerBloque job={job} />

      {completada ? (
        // Terminada, las fases ya no son la noticia: quedan a un clic.
        <Panel title="Ver todas las fases" collapsible>
          {pasosDeSubida}
          {fases}
        </Panel>
      ) : (
        <Panel
          title="Progreso de la subida" loading={progressIsActive} fill
          help="Cada fase por la que pasa la subida (comprobación de integridad, nomenclatura, remux, subida a eMuwarez…), con su estado, cuándo empezó y terminó, y el porcentaje global de la subida completa."
        >
          {isStaging ? <GeneratingSpinner text="Esperando a que termine la verificación previa…" /> : fases}
        </Panel>
      )}

      {showNomenclatura && (
        <Modal titulo="Nomenclatura" onClose={() => setShowNomenclatura(false)} className="modal-wide dsub-modal-720">
          <div className="modal-body">
            <NomenclatureSection snapshot={job.nomenclature_snapshot} mediaType={job.media_type} isStaging={isStaging} />
          </div>
        </Modal>
      )}

      {showRemux && (
        <Modal titulo="Reordenación/Renombrado" onClose={() => setShowRemux(false)} className="modal-wide dsub-modal-780">
          <div className="modal-body">
            <RemuxSection snapshot={job.remux_snapshot} isStaging={isStaging} />
          </div>
        </Modal>
      )}

      {showChecks && (
        <Modal titulo="Verificación pre-subida" onClose={() => setShowChecks(false)} className="modal-wide dsub-modal-720">
          <div className="modal-body">
            <ChecksSection
              snapshot={job.checks_snapshot}
              mediaType={job.media_type}
              isActive={isQueued || isPreparing || isRunning || isStaging}
            />
          </div>
        </Modal>
      )}

      {showActividad && (
        <Modal titulo={<>Actividad{isRunning ? ' (en directo)' : ''}</>} onClose={() => setShowActividad(false)} className="modal-wide dsub-modal-680">
          <div className="modal-body">
            {logsTotal > logs.length && (
              <p className="dsub-log-resumen">
                Mostrando las últimas {logs.length} de {logsTotal} líneas.
              </p>
            )}
            <pre ref={logsBoxRef} className="dsub-log">
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
        </Modal>
      )}
    </div>
  )
}
