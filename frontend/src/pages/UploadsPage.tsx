import { useState, useEffect, useMemo, useRef, Fragment } from 'react'
import { getUploads, countUploads, getUploadJob, startUploadJob, retryUploadJobQueued, cancelUploadJob } from '../api/uploads'
import { useInstancias } from '../hooks/useInstancias'
import { ApiClientError } from '../api/client'
import type { UploadJob, InstanceSafeResponse } from '../types/api'
import { EmptyState, FilaVacia } from '../components/EmptyState'
import { LoadingState } from '../components/LoadingState'
import { ErrorState } from '../components/ErrorState'
import { HeaderFilter } from '../components/HeaderFilter'
import { UploadJobDetailPage } from '../components/UploadJobDetailPage'
import { DeleteUploadModal } from '../components/DeleteUploadModal'
import { PeticionDeSubida } from '../components/PeticionDeSubida'
import { ServiceLabel } from '../components/ServiceIcon'
import { CancelButtonIcon, RetryButtonIcon, DeleteButtonIcon, ExternalLinkButtonIcon, ValueChip, PlainValue, TypeValueIcon } from '../components/DetailCard'
import { useTooltip } from '../components/Tooltip'
import { formatDateTimeSeconds } from '../utils/format'
import { posterUrl, buildDeepLink } from '../utils/libraryItem'
import { getDetailIdFromPath, pushDetailPath, closeDetailPath } from '../utils/detailUrl'
import { hayMasPorCargar } from '../utils/paginarSubidas'
import {
  UPLOAD_TYPE_LABEL, STATUS_CLASS, statusLabel, phaseLabel, currentPhaseInfo,
  progressCounter, queuedWaitText,
} from '../utils/uploadStatus'
import { useRefrescoPorAvisos, AVISOS_SUBIDA, AVISOS_SUBIDA_PROGRESO } from '../hooks/useRefrescoPorAvisos'
import { useAlSalir, useSeccionVisible } from '../context/SeccionVisible'
import { IconoSubida, IconoTipo } from '../components/Iconos'
import { Modal } from '../components/Modal'

// Backend-real gates — mirror cancel_upload_job()/queue_retry_for_job() in
// services/upload_execution.py / upload_queue.py exactly, so the button is
// only enabled when the action would actually succeed.
//
// 'preparing' SÍ entra: no se interrumpe a media faena (puede estar
// renombrando o remuxeando), pero se marca y el trabajo se rinde en el
// siguiente punto limpio. Excluirlo dejaba un agujero real: si la aplicación
// se paraba durante esa fase, el job se quedaba en 'preparing' para siempre y
// no había ningún botón capaz de tocarlo.
// Reintentar excludes 'completed' on purpose: retrying an already-successful
// upload isn't supported server-side.
const CANCELLABLE_STATUSES = new Set(['staging', 'queued', 'running', 'preparing'])
const RETRYABLE_STATUSES = new Set(['failed', 'cancelled'])
// Borrar solo lo terminado (mirror de delete_upload_job). 'completed' entra
// porque borrar el registro de una subida que salió bien no deshace nada: el
// torrent ya está en eMuwarez y el archivo sigue en su sitio; lo que se borra
// es el historial de esta aplicación.
const DELETABLE_STATUSES = new Set(['failed', 'cancelled', 'completed'])

const CONFIRMATION_TOKEN = 'INICIAR_UPLOADRR'

// Only real upload states — a job now only exists once the user uploads, so
// the preparatory "ready"/"blocked" states no longer appear here. 'preparing'
// isn't offered as its own filter option — it displays as "Subiendo" same as
// 'running' (see STATUS_LABEL), and the "Subiendo" filter option matches both.
const STATUS_OPTIONS = ['', 'staging', 'queued', 'running', 'completed', 'failed', 'cancelled']
// Preparatory states never represent a real upload — hide any stale leftovers.
const HIDDEN_STATES = new Set(['draft', 'preflight', 'blocked', 'ready', 'config_staging'])

// Cuántas subidas se piden de una vez, y cuántas como mucho (el máximo que acepta GET /uploads). Pasado el
// límite, «Cargar más» pide otra tanda: la lista es siempre las más recientes, sin huecos.
const PAGINA = 100
const MAX_LIMITE = 2000

// "Orden: Estado" ordenaba por el CÓDIGO interno, no por lo que se ve, y salía
// una secuencia sin sentido para nadie: Cancelado, Completado, Fallido, En
// cola, Subiendo, Preparando. Se ordena por el ciclo de vida de una subida, que
// además dice más que el alfabético: lo que está en marcha arriba y lo
// terminado abajo (auditoría de tablas).
const ORDEN_DE_ESTADO = ['staging', 'queued', 'preparing', 'running', 'completed', 'failed', 'cancelled']
const ordenDeEstado = (estado?: string | null): number => {
  const i = ORDEN_DE_ESTADO.indexOf(estado ?? '')
  return i === -1 ? ORDEN_DE_ESTADO.length : i    // lo desconocido, al final
}

function StartModal({ job, onClose, onDone }: { job: UploadJob; onClose: () => void; onDone: () => void }) {
  const [confirm, setConfirm] = useState('')
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const jobId = job.id!

  const handleDryRun = async () => {
    setLoading(true); setError(null); setMessage(null)
    try {
      const r = await startUploadJob(jobId, { dry_run: true, start: false, confirmation: null })
      setMessage(r.command_preview ? `Comando previsto:\n${r.command_preview}` : r.message || 'Dry-run completado.')
    } catch (e: unknown) { setError(e instanceof Error ? e.message : 'Error.') }
    finally { setLoading(false) }
  }

  const handleStart = async () => {
    if (confirm !== CONFIRMATION_TOKEN) return
    setLoading(true); setError(null); setMessage(null)
    try {
      const r = await startUploadJob(jobId, { dry_run: false, start: true, confirmation: CONFIRMATION_TOKEN })
      setMessage(r.message || 'Uploadrr iniciado.')
      onDone()
    } catch (e: unknown) { setError(e instanceof Error ? e.message : 'Error al iniciar.') }
    finally { setLoading(false) }
  }

  return (
    <Modal titulo={<>Iniciar Uploadrr: job {jobId}</>} onClose={onClose} style={{ maxWidth: 560 }}>
      <div className="modal-body">
        <p style={{ marginBottom: 8 }}><strong>{job.title || '—'}</strong></p>
        <div style={{ padding: '10px 14px', background: 'color-mix(in srgb, var(--color-error) 8%, transparent)', borderRadius: 6, border: '1px solid color-mix(in srgb, var(--color-error) 20%, transparent)', marginBottom: 12 }}>
          <ul style={{ margin: 0, paddingLeft: 18, fontSize: '0.83rem', lineHeight: 1.6 }}>
            <li>Esta acción puede publicar/subir contenido a eMuwarez.</li>
            <li>No se crearán peticiones automáticamente.</li>
            <li>No se modificará el archivo original ni el título MKV.</li>
          </ul>
        </div>
        <label style={{ display: 'block', marginBottom: 6, fontSize: '0.83rem' }}>
          Escribe <strong>{CONFIRMATION_TOKEN}</strong> para confirmar:
        </label>
        <input type="text" value={confirm} onChange={e => setConfirm(e.target.value)} placeholder={CONFIRMATION_TOKEN}
          style={{ width: '100%', padding: '6px 10px', background: 'color-mix(in srgb, var(--overlay-light) 8%, transparent)', border: `1px solid ${confirm === CONFIRMATION_TOKEN ? 'var(--color-available-soft)' : 'color-mix(in srgb, var(--overlay-light) 15%, transparent)'}`, borderRadius: 4, color: 'inherit', fontFamily: 'var(--font-mono)', fontSize: '0.9rem', boxSizing: 'border-box' }} />
        {message && <pre style={{ marginTop: 12, fontSize: '0.78rem', whiteSpace: 'pre-wrap', background: 'color-mix(in srgb, var(--overlay-dark) 20%, transparent)', padding: 8, borderRadius: 4 }}>{message}</pre>}
        {error && <p className="error-text" style={{ marginTop: 8 }}>{error}</p>}
      </div>
      <div className="detail-panel__actions" style={{ padding: '10px 16px', gap: 8, display: 'flex' }}>
        <button className="btn btn-secondary" onClick={handleDryRun} disabled={loading}>Dry-run</button>
        <button className="btn btn-primary" onClick={handleStart} disabled={confirm !== CONFIRMATION_TOKEN || loading}>{loading ? 'Iniciando…' : 'Iniciar subida'}</button>
        <button className="btn btn-secondary" onClick={onClose}>Cerrar</button>
      </div>
    </Modal>
  )
}

// One table row — used both for the latest attempt in a retry chain (normal
// row) and for its older attempts (indented/muted, revealed by expanding the
// Reintentos toggle). `retryToggle` is only passed on the latest-attempt row.
function JobRow({ job, instances, onOpen, indent, retryToggle, onCancel, onRetry, onDelete }: {
  job: UploadJob
  instances: InstanceSafeResponse[]
  onOpen: () => void
  indent?: boolean
  retryToggle?: { count: number; expanded: boolean; onClick: () => void }
  onCancel: (jobId: number) => void
  onDelete: (job: UploadJob) => void
  onRetry: (job: UploadJob) => void
}) {
  const canCancel = CANCELLABLE_STATUSES.has(job.status)
  const canDelete = DELETABLE_STATUSES.has(job.status)
  const canRetry = RETRYABLE_STATUSES.has(job.status)
  const isPreparingOrRunning = job.status === 'preparing' || job.status === 'running'
  const phaseInfo = isPreparingOrRunning ? currentPhaseInfo(job) : null
  const phaseLabelText = phaseInfo?.label ?? (isPreparingOrRunning ? phaseLabel(job.progress_phase) : null)
  const phaseElapsedText = isPreparingOrRunning ? progressCounter(job) : null
  const deepLink = buildDeepLink(job, instances)
  const { triggerProps: titleTip, tooltipNode: titleTooltip } = useTooltip('Ver progreso / detalle')
  const { triggerProps: emuTip, tooltipNode: emuTooltip } = useTooltip(job.result_url ? 'Ver en eMuwarez' : null)
  const { triggerProps: originTip, tooltipNode: originTooltip } = useTooltip(deepLink ? `Abrir en ${job.instance_name ?? job.instance_type}` : null)
  const retryToggleTip = useTooltip(retryToggle ? (retryToggle.expanded ? 'Ocultar intentos anteriores' : 'Ver intentos anteriores') : null)
  const retryBtnTip = useTooltip(canRetry ? 'Reintentar subida' : 'Solo se puede reintentar una subida cancelada o fallida')
  const deleteBtnTip = useTooltip(canDelete
    ? ((job.retry_count ?? 0) > 0
        ? 'Borrar esta subida del historial, con todos sus intentos'
        : 'Borrar esta subida del historial')
    : 'Solo se puede borrar una subida terminada: completada, cancelada o fallida')
  const cancelBtnTip = useTooltip(canCancel ? 'Cancelar subida' : 'Solo se puede cancelar mientras está preparando, en cola o subiendo')
  return (
    <tr style={indent ? { opacity: 0.65 } : undefined}>
      <td style={{ maxWidth: 360 }}>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center', minWidth: 0, paddingLeft: indent ? 24 : undefined }}>
          <div className="poster-thumb" style={{ width: 28, height: 42, borderRadius: 4, overflow: 'hidden', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
            {job.poster_url ? (
              <img
                src={posterUrl(job.poster_url, 'w154')}
                alt=""
                loading="lazy"
                style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                onError={e => { (e.currentTarget as HTMLImageElement).style.display = 'none' }}
              />
            ) : (
              <span style={{ fontSize: 14, opacity: 0.35 }}>
                <IconoTipo serie={job.media_type === 'series' || job.media_type === 'episode'} />
              </span>
            )}
          </div>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 4, minWidth: 0 }}>
            {indent && <span style={{ color: 'var(--text-muted)', flexShrink: 0 }}>↳</span>}
            <span
              className="lib-title-link"
              style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', minWidth: 0 }}
              onClick={onOpen}
              {...titleTip}
            >
              {job.title || '—'}
              {titleTooltip}
            </span>
            {job.year ? <span style={{ fontSize: 11, color: 'var(--text-muted)', flexShrink: 0 }}>({job.year})</span> : null}
            {job.result_url && (
              <a className="hover-link" href={job.result_url} target="_blank" rel="noreferrer" onClick={e => e.stopPropagation()}
                style={{ display: 'inline-flex', flexShrink: 0, alignSelf: 'center' }} aria-label="Ver en eMuwarez" {...emuTip}>
                <ExternalLinkButtonIcon />
                {emuTooltip}
              </a>
            )}
          </div>
        </div>
      </td>
      <td style={{ whiteSpace: 'nowrap' }}>
        {job.media_type
          ? <PlainValue icon={<TypeValueIcon />}>{UPLOAD_TYPE_LABEL[job.media_type] ?? job.media_type}</PlainValue>
          : <span style={{ color: 'var(--text-muted)' }}>—</span>}
      </td>
      <td style={{ whiteSpace: 'nowrap' }}>
        {job.instance_type
          ? (
            deepLink
              ? <ValueChip linkable><a className="hover-link" href={deepLink} target="_blank" rel="noreferrer" onClick={e => e.stopPropagation()} {...originTip}><ServiceLabel type={job.instance_type} label={job.instance_name ?? job.instance_type} size={14} />{originTooltip}</a></ValueChip>
              : <ServiceLabel type={job.instance_type} label={job.instance_name ?? job.instance_type} size={14} />
          )
          : <span style={{ color: 'var(--text-muted)' }}>—</span>}
      </td>
      <td className="col-prioridad-baja" style={{ whiteSpace: 'nowrap', maxWidth: 240 }}>
        <PeticionDeSubida job={job} />
      </td>
      <td>
        {job.status === 'queued' ? (
          <span className="badge status-queued">En cola</span>
        ) : (job.status === 'preparing' || job.status === 'running' || job.status === 'failed') ? (
          <span className={`${STATUS_CLASS[job.status] || 'badge req-unknown'} badge-blink`}>
            {statusLabel(job.status)}
          </span>
        ) : (
          <span className={STATUS_CLASS[job.status] || 'badge req-unknown'}>
            {statusLabel(job.status)}
          </span>
        )}
      </td>
      <td style={{ whiteSpace: 'nowrap' }}>
        {job.status === 'staging' ? (
          <span className="badge status-queued" style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
            <span className="spinner" style={{ width: 10, height: 10, borderWidth: 2 }} />
            Generando nomenclatura
          </span>
        ) : job.status === 'queued' ? (
          <span className="badge status-queued" style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
            <span className="spinner" style={{ width: 10, height: 10, borderWidth: 2 }} />
            {queuedWaitText(job)}
          </span>
        ) : (job.status === 'preparing' || job.status === 'running') ? (
          <span className="badge status-queued" style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
            <span className="spinner" style={{ width: 10, height: 10, borderWidth: 2 }} />
            {phaseLabelText}{phaseInfo?.counterText ? ` (${phaseInfo.counterText})` : ''}{phaseElapsedText ? ` · ${phaseElapsedText}` : ''}
          </span>
        ) : '—'}
      </td>
      <td style={{ fontSize: 11, color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>{formatDateTimeSeconds(job.created_at ?? null)}</td>
      <td style={{ fontSize: 11, color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>{formatDateTimeSeconds(job.finished_at ?? null)}</td>
      <td className="col-prioridad-baja" style={{ fontSize: 12, color: 'var(--text-muted)' }}>
        {job.duration_seconds != null ? `${job.duration_seconds}s` : '—'}
      </td>
      <td style={{ fontSize: 12, color: 'var(--text-muted)' }}>
        {retryToggle ? (
          <span
            className="lib-title-link"
            onClick={retryToggle.onClick}
            style={{ display: 'inline-flex', alignItems: 'center', gap: 3 }}
            {...retryToggleTip.triggerProps}
          >
            x{job.retry_count} <span style={{ fontSize: 10 }}>{retryToggle.expanded ? '▾' : '▸'}</span>
            {retryToggleTip.tooltipNode}
          </span>
        ) : (job.retry_count ?? 0) > 0 ? `x${job.retry_count}` : '—'}
      </td>
      <td className="col-actions">
        <div style={{ display: 'flex', gap: 6 }}>
          <button
            type="button"
            className="btn btn-primary btn-sm"
            disabled={!canRetry}
            onClick={() => onRetry(job)}
            {...retryBtnTip.triggerProps}
          >
            <RetryButtonIcon /> Reintentar
            {retryBtnTip.tooltipNode}
          </button>
          <button
            type="button"
            className="btn btn-danger btn-sm"
            disabled={!canCancel}
            onClick={() => onCancel(job.id!)}
            {...cancelBtnTip.triggerProps}
          >
            <CancelButtonIcon /> Cancelar
            {cancelBtnTip.tooltipNode}
          </button>
          <button
            type="button"
            className="btn btn-danger btn-sm"
            disabled={!canDelete}
            onClick={() => onDelete(job)}
            {...deleteBtnTip.triggerProps}
          >
            <DeleteButtonIcon /> Borrar
            {deleteBtnTip.tooltipNode}
          </button>
        </div>
      </td>
    </tr>
  )
}

export function UploadsPage({ onNavigate }: { onNavigate?: (page: string) => void } = {}) {
  const [jobs, setJobs] = useState<UploadJob[]>([])
  // Only needed to build the Origen deep link (same as Biblioteca's own column).
  const instances = useInstancias()
  // Volver aquí no vuelve a enseñar "Cargando…" ni reinicia los filtros: la
  // sección no se desmonta al cambiar de pestaña, se queda montada y oculta
  // (ver AppShell). Esto solo corre la PRIMERA vez que se entra.
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [statusFilter, setStatusFilter] = useState('')
  const [search, setSearch] = useState('')
  const [sortBy, setSortBy] = useState('created_desc')
  const [typeFilter, setTypeFilter] = useState('')
  const [selectedJobId, setSelectedJobId] = useState<number | null>(null)
  // Cuántas se piden (las más recientes), cuántas hay en total con el filtro de estado, y si ya llegó la primera
  // respuesta (hasta entonces «no está en la lista» no quiere decir nada).
  const [limite, setLimite] = useState(PAGINA)
  const [total, setTotal] = useState<number | null>(null)
  const [cargado, setCargado] = useState(false)

  // Keeps /uploads/:id in sync with whichever job's detail page is open.
  function openUpload(id: number) {
    pushDetailPath('uploads', id)
    setSelectedJobId(id)
  }
  function closeUpload() {
    closeDetailPath('uploads')
    setSelectedJobId(null)
  }
  const [startJob, setStartJob] = useState<UploadJob | null>(null)
  const [deleteJob, setDeleteJob] = useState<UploadJob | null>(null)
  // Retry chains: which terminal (latest-attempt) job ids currently have
  // their older attempts expanded below them.
  const [expandedChains, setExpandedChains] = useState<Set<number>>(new Set())

  // Guards against out-of-order responses: the 2.5s background poll (below)
  // and an explicit load() (e.g. right after deleting a job) can both be
  // in-flight at once, and network timing doesn't guarantee the one that
  // started first also RESOLVES first. Without this, a slower poll that
  // started before a delete can resolve after it and overwrite `jobs` with
  // stale pre-delete data — the deleted job "comes back" until the next
  // refresh. Only ever apply the response from the most recently ISSUED call.
  const loadSeqRef = useRef(0)
  const load = async (opts?: { silent?: boolean }) => {
    if (!opts?.silent) { setLoading(true); setError(null) }
    const seq = ++loadSeqRef.current
    try {
      // The "Subiendo" filter option (value 'running') must also catch
      // 'preparing' jobs — they display identically as "Subiendo" now (see
      // STATUS_LABEL) — so the server filters on both, before paginating and counting.
      const filtros = { status: statusFilter === 'running' ? 'running,preparing' : statusFilter || undefined, hide_preparatory: true }
      // Si falla solo el recuento, la lista se enseña igual y el total queda sin conocer.
      const [data, cuantas] = await Promise.all([
        getUploads({ ...filtros, limit: limite }),
        countUploads(filtros).catch(() => null),
      ])
      if (seq === loadSeqRef.current) {
        setJobs(data)
        setTotal(cuantas)
        setCargado(true)
        setError(null)
      }
    } catch {
      if (!opts?.silent) setError('Error al cargar los trabajos de subida.')
    }
    finally { if (!opts?.silent) setLoading(false) }
  }

  useEffect(() => { load() }, [statusFilter, limite])

  // Opened from the dashboard "Actividad de subida" (clicking a title): pick
  // up the stashed job id once the list has loaded and show its detail page.
  //
  // Depende de `cargado` y de `seVe`: la sección ya no se levanta de cero en
  // cada visita, así que sin eso solo se recogía el salto si los datos
  // llegaban justo después (ver context/SeccionVisible). Se abre aunque no esté
  // en la lista (una antigua): la ficha la pide por su id.
  const subidasALaVista = useSeccionVisible()
  useEffect(() => {
    if (!subidasALaVista || !cargado) return
    let pending: string | null = null
    try { pending = sessionStorage.getItem('emuwarez_open_upload') } catch { /* ignore */ }
    if (!pending) return
    try { sessionStorage.removeItem('emuwarez_open_upload') } catch { /* ignore */ }
    openUpload(Number(pending))
  }, [cargado, subidasALaVista])

  function quitarFiltros() {
    setSearch('')
    setStatusFilter(''); setTypeFilter('')
  }
  const filtrando = !!(search || statusFilter || typeFilter)
  // Las que faltan por cargar (sin total conocido, si la lista llena el límite pedido). La búsqueda por título y el
  // filtro de tipo miran solo las cargadas.
  const hayMas = hayMasPorCargar(total, jobs.length, limite, MAX_LIMITE)
  const cargarMas = () => setLimite(l => Math.min(l + PAGINA, MAX_LIMITE))
  // Al salir, de vuelta a la tabla sin filtros y con el orden por defecto.
  useAlSalir(() => {
    closeUpload()
    quitarFiltros()
    setSortBy('created_desc')
  })

  // Deep link: /uploads/:id — resolve straight from the URL. selectedJob's
  // own `jobs.find(...)` gracefully returns undefined until `jobs` finishes
  // loading, so this doesn't need to wait on it like the sessionStorage
  // hand-off above does. On mount this only OPENS (never force-closes on a
  // bare /uploads) — the sessionStorage/CustomEvent hand-offs above land on a
  // bare /uploads path themselves and may resolve the same tick, so
  // unconditionally clearing here on mount would win the race and wipe out
  // whatever they just opened. Closing on a bare path is left to real
  // back/forward navigation (popstate), which happens well after mount.
  useEffect(() => {
    const id = getDetailIdFromPath('uploads')
    if (id != null) setSelectedJobId(id)

    const onPopState = () => setSelectedJobId(getDetailIdFromPath('uploads'))
    window.addEventListener('popstate', onPopState)
    return () => window.removeEventListener('popstate', onPopState)
  }, [])

  // Same hand-off, but live — the sessionStorage read above only re-checks
  // when `jobs` changes, so clicking a notification while Subidas is
  // ALREADY the open page (no reload, `jobs` unchanged) would otherwise do
  // nothing. NotificationBell dispatches this same-tick, in addition to
  // stashing sessionStorage for the cross-page case.
  useEffect(() => {
    const onOpenUpload = (e: Event) => {
      const id = (e as CustomEvent<number>).detail
      if (id == null) return
      try { sessionStorage.removeItem('emuwarez_open_upload') } catch { /* ignore */ }
      openUpload(id)
    }
    window.addEventListener('emuwarez:open-upload', onOpenUpload)
    return () => window.removeEventListener('emuwarez:open-upload', onOpenUpload)
  }, [])

  // Mientras haya algún trabajo vivo (staging/queued/preparing/running), la
  // tabla se mantiene al día. Ahora lo hace el aviso del servidor, y el sondeo
  // de 2,5 s queda de red de seguridad para cuando el canal está caído.
  const hasLiveJob = jobs.some(j => j.status === 'running' || j.status === 'preparing' || j.status === 'queued' || j.status === 'staging')
  // La cadencia depende de si hay algo en marcha, pero el sondeo NO se apaga
  // del todo: es la red de seguridad de la que dependía enterarse de una
  // subida nueva cuando el aviso se perdía, y apagarla dejaba la tabla clavada
  // hasta recargar la página. Mirando y sin nada vivo, preguntar una vez cada
  // 30 s no se nota.
  useRefrescoPorAvisos(AVISOS_SUBIDA, () => load({ silent: true }),
    { cadaSinCanal: hasLiveJob ? 2500 : 30_000, soloVisible: AVISOS_SUBIDA_PROGRESO })

  // Cancelar mientras se preparan ficheros no interrumpe nada a media faena,
  // así que se avisa antes: lo que pasa de verdad no es obvio desde el botón.
  const [confirmCancel, setConfirmCancel] = useState<UploadJob | null>(null)
  const handleCancel = async (jobId: number) => {
    const job = jobs.find(j => j.id === jobId)
    if (job?.status === 'preparing') { setConfirmCancel(job); return }
    await doCancel(jobId)
  }
  const doCancel = async (jobId: number) => {
    setConfirmCancel(null)
    try { await cancelUploadJob(jobId); await load() } catch { /* ignore */ }
  }

  // Sin confirmación: reintentar solo crea un trabajo nuevo en cola (el mismo camino que
  // «Subir a eMuwarez») y no toca el original, fallido o cancelado. Salta a la ficha del
  // trabajo nuevo para ver su progreso en el momento. Los errores se enseñan, no se tragan:
  // un fallo silencioso aquí parecía un botón que no hacía nada.
  const [retryError, setRetryError] = useState<string | null>(null)
  const handleRetryQueued = async (job: UploadJob) => {
    setRetryError(null)
    try {
      const r = await retryUploadJobQueued(job.id!)
      await load()
      if (r.job?.id != null) openUpload(r.job.id)
    } catch (e: unknown) {
      setRetryError(e instanceof Error ? e.message : 'No se pudo reintentar la subida.')
    }
  }

  // Same sessionStorage handoff RequestsPage uses to open a specific
  // library item's detail page in Biblioteca.
  const goToLibraryItem = (id: number) => {
    try { sessionStorage.setItem('emuwarez_open_library_item', String(id)) } catch { /* ignore */ }
    onNavigate?.('library')
  }

  // Retry chains: a job created via "Reintentar" points back at the job it
  // retried (retry_of_job_id), and the original is never touched — so a
  // retried item would otherwise show up twice (or more) as unrelated-
  // looking rows. Only the LATEST attempt in each chain (the one nothing
  // else retries) shows as a normal row; its older attempts are reachable
  // by expanding the Reintentos cell instead of cluttering the main list.
  const jobById = useMemo(() => new Map(jobs.map(j => [j.id!, j])), [jobs])
  const hasNewerRetry = useMemo(() => {
    const s = new Set<number>()
    for (const j of jobs) if (j.retry_of_job_id != null) s.add(j.retry_of_job_id)
    return s
  }, [jobs])
  const ancestorsOf = (job: UploadJob): UploadJob[] => {
    const chain: UploadJob[] = []
    let cur = job.retry_of_job_id != null ? jobById.get(job.retry_of_job_id) : undefined
    while (cur) {
      chain.push(cur)
      cur = cur.retry_of_job_id != null ? jobById.get(cur.retry_of_job_id) : undefined
    }
    return chain // most recent ancestor first, original last
  }
  const toggleChain = (jobId: number) => {
    setExpandedChains(prev => {
      const next = new Set(prev)
      if (next.has(jobId)) next.delete(jobId); else next.add(jobId)
      return next
    })
  }

  // Client-side filter + sort over the loaded jobs (status stays server-side).
  const visibleJobs = useMemo(() => {
    const q = search.trim().toLowerCase()
    const out = jobs.filter(j => {
      if (HIDDEN_STATES.has(j.status)) return false
      if (hasNewerRetry.has(j.id!)) return false // shown nested under its retry instead
      const titleOk = !q || (j.title || '').toLowerCase().includes(q)
      const typeOk = !typeFilter || j.media_type === typeFilter
      return titleOk && typeOk
    })
    const dt = (s?: string | null) => (s ? new Date(s).getTime() : 0)
    out.sort((a, b) => {
      switch (sortBy) {
        case 'created_asc': return dt(a.created_at) - dt(b.created_at)
        case 'title': return (a.title || '').localeCompare(b.title || '')
        case 'status': return ordenDeEstado(a.status) - ordenDeEstado(b.status)
        case 'duration_desc': return (b.duration_seconds ?? -1) - (a.duration_seconds ?? -1)
        default: return dt(b.created_at) - dt(a.created_at) // created_desc
      }
    })
    return out
  }, [jobs, search, sortBy, typeFilter, hasNewerRetry])

  // La de la lista o, si es más antigua que las cargadas (enlace /uploads/123, notificación, Panel), la pedida por su id.
  const [jobSuelto, setJobSuelto] = useState<UploadJob | null>(null)
  const enLista = selectedJobId != null ? jobs.find(j => j.id === selectedJobId) : undefined
  // Depende de si está en la lista, no de la lista entera: cada recarga la sustituye y cancelaría la petición en vuelo.
  const seleccionadaEnLista = enLista != null
  useEffect(() => {
    if (selectedJobId == null || !cargado) return
    if (seleccionadaEnLista) { setJobSuelto(null); return }
    let alive = true
    getUploadJob(selectedJobId)
      .then(j => { if (alive) setJobSuelto(j) })
      .catch(e => {
        // Ya no existe (la borraron): fuera de una ficha vacía.
        if (alive && e instanceof ApiClientError && e.status === 404) closeUpload()
      })
    return () => { alive = false }
  }, [selectedJobId, cargado, seleccionadaEnLista])
  const selectedJob = enLista ?? (jobSuelto?.id === selectedJobId ? jobSuelto : undefined)

  // The list row (above) never carries display_title — only the single-job
  // GET computes the canonical "Serie (Año)"-style title, to avoid a
  // parent-walk query per list row — so fetch it once per selection and
  // merge just that field into the (still live-polled) list-derived job,
  // instead of replacing it outright and losing further progress updates.
  const [selectedTitle, setSelectedTitle] = useState<{ id: number; display_title: string | null } | null>(null)
  useEffect(() => {
    if (selectedJobId == null) { setSelectedTitle(null); return }
    let alive = true
    getUploadJob(selectedJobId).then(j => { if (alive) setSelectedTitle({ id: selectedJobId, display_title: j.display_title ?? null }) }).catch(() => {})
    return () => { alive = false }
  }, [selectedJobId])
  const selectedJobWithTitle = selectedJob && selectedTitle && selectedTitle.id === selectedJob.id
    ? { ...selectedJob, display_title: selectedTitle.display_title }
    : selectedJob

  const modals = (
    <>
      {confirmCancel && (
        <Modal titulo="Cancelar una subida que se está preparando" onClose={() => setConfirmCancel(null)} style={{ maxWidth: 520 }}>
          <div className="modal-body">
            <p style={{ fontSize: 13, marginTop: 0 }}>
              <strong>«{confirmCancel.title}»</strong> está preparando ficheros: puede estar renombrando
              o reordenando pistas. Eso no se puede interrumpir a mitad sin dejar un archivo a medias.
            </p>
            <p style={{ fontSize: 13 }}>
              Se marcará como <strong>cancelada</strong> y se detendrá al terminar el paso en curso, no
              al instante. Si el proceso ya no existe (por ejemplo, porque se paró la aplicación), queda
              cancelada directamente.
            </p>
            <p style={{ fontSize: 13, color: 'var(--text-muted)' }}>
              En ambos casos podrás <strong>reintentarla</strong> después. Revisa el archivo antes de
              hacerlo, por si quedó algo a medio renombrar.
            </p>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 16 }}>
              <button className="btn btn-secondary" type="button" onClick={() => setConfirmCancel(null)}>
                Dejarla seguir
              </button>
              <button className="btn btn-primary" type="button" onClick={() => doCancel(confirmCancel.id!)}>
                Cancelar la subida
              </button>
            </div>
          </div>
        </Modal>
      )}
      {startJob && <StartModal job={startJob} onClose={() => setStartJob(null)} onDone={() => { setStartJob(null); load() }} />}
      {deleteJob && (
        <DeleteUploadModal
          job={deleteJob}
          onClose={() => setDeleteJob(null)}
          onDeleted={() => { setDeleteJob(null); closeUpload(); load() }}
        />
      )}
    </>
  )

  // Dedicated detail page — shown in place of the list when a job is
  // selected, instead of the old JobProgressPanel modal.
  if (selectedJobWithTitle) {
    return (
      <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
        <UploadJobDetailPage
          job={selectedJobWithTitle}
          onBack={closeUpload}
          onStart={j => setStartJob(j)}
          onRetry={j => handleRetryQueued(j)}
          onCancel={id => handleCancel(id)}
          onDelete={j => setDeleteJob(j)}
          onOpenLibraryItem={goToLibraryItem}
          retryError={retryError}
        />
        {modals}
      </div>
    )
  }

  return (
    <div data-tour="uploads-content" style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      {modals}

      <div className="page-header" style={{ flexShrink: 0 }}>
        <div>
          <div className="page-title">Subidas</div>
          <div className="page-subtitle">
            {visibleJobs.length} subidas{total != null && jobs.length < total ? ` · ${jobs.length} de ${total} cargadas` : ''}
          </div>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          {hasLiveJob && <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>● actualizando en vivo</span>}
        </div>
      </div>

      <div className="filters-bar" style={{ flexShrink: 0 }}>
        <input
          className="form-input"
          placeholder="Buscar título…"
          value={search}
          onChange={e => setSearch(e.target.value)}
          style={{ width: 160 }}
        />
        <select className="form-input form-select" value={sortBy} onChange={e => setSortBy(e.target.value)}>
          <option value="created_desc">Orden: Reciente primero</option>
          <option value="created_asc">Orden: Antiguo primero</option>
          <option value="title">Orden: Título (A-Z)</option>
          <option value="status">Orden: Estado</option>
          <option value="duration_desc">Orden: Duración</option>
        </select>
      </div>

      {/* Ver RequestsPage: solo bloquea si no hay nada que enseñar todavía. */}
      {loading && jobs.length === 0 && !filtrando ? <LoadingState label="Cargando Subidas…" /> : error ? <ErrorState message={error} onRetry={load} /> : jobs.length === 0 && !filtrando ? (
        <EmptyState icon={<IconoSubida />} title="No hay trabajos de subida." body="Usa el botón 'Subir' desde Biblioteca para generar un preflight." />
      ) : (
        <div className="activity-section" style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', marginBottom: 0 }}>
          <div style={{ overflow: 'auto', flex: 1, minHeight: 0 }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th style={{ width: '100%' }}>Título</th>
                  <th><HeaderFilter label="Tipo" value={typeFilter} onChange={setTypeFilter} options={[
                    { value: '', label: 'Todos' }, { value: 'movie', label: 'Película' }, { value: 'series', label: 'Serie' }, { value: 'season', label: 'Temporada' }, { value: 'episode', label: 'Episodio' },
                  ]} /></th>
                  <th>Origen</th>
                  <th className="col-prioridad-baja">Petición</th>
                  <th><HeaderFilter label="Estado" value={statusFilter} onChange={setStatusFilter} options={[
                    { value: '', label: 'Todos' }, ...STATUS_OPTIONS.filter(Boolean).map(s => ({ value: s, label: statusLabel(s) })),
                  ]} /></th>
                  <th>Progreso</th>
                  <th>Creado</th>
                  <th>Finalizado</th>
                  <th className="col-prioridad-baja">Duración</th>
                  <th>Reintentos</th>
                  <th className="col-actions" style={{ width: '1%' }}>Acciones</th>
                </tr>
              </thead>
              {visibleJobs.length === 0 && filtrando && (
                <FilaVacia
                  columnas={11}
                  icon={<IconoSubida />}
                  title="Sin resultados"
                  body={hayMas
                    ? 'No hay subidas cargadas que coincidan con los filtros. Quedan más sin cargar.'
                    : 'No hay subidas que coincidan con los filtros.'}
                  action={
                    <div style={{ display: 'flex', gap: 8, justifyContent: 'center' }}>
                      <button className="btn btn-primary btn-sm" onClick={quitarFiltros}>Quitar filtros</button>
                      {hayMas && <button className="btn btn-secondary btn-sm" onClick={cargarMas}>Cargar más</button>}
                    </div>
                  }
                />
              )}
              <tbody>
                {visibleJobs.map(job => {
                  const ancestors = ancestorsOf(job)
                  const expanded = expandedChains.has(job.id!)
                  return (
                    <Fragment key={job.id}>
                      <JobRow
                        job={job}
                        instances={instances}
                        onOpen={() => openUpload(job.id!)}
                        retryToggle={ancestors.length > 0 ? { count: ancestors.length, expanded, onClick: () => toggleChain(job.id!) } : undefined}
                        onCancel={handleCancel}
                        onDelete={setDeleteJob}
                        onRetry={handleRetryQueued}
                      />
                      {expanded && ancestors.map(a => (
                        <JobRow key={a.id} job={a} instances={instances} indent onOpen={() => openUpload(a.id!)} onCancel={handleCancel} onRetry={handleRetryQueued} onDelete={setDeleteJob} />
                      ))}
                    </Fragment>
                  )
                })}
              </tbody>
            </table>
          </div>
          {hayMas && (
            <div style={{ flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 12, padding: '10px 0' }}>
              <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                {total != null ? `${jobs.length} de ${total} subidas cargadas` : `${jobs.length} subidas cargadas`}
              </span>
              <button type="button" className="btn btn-secondary btn-sm" onClick={cargarMas}>Cargar más</button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
