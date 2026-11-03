import { useState, useEffect, useCallback, useRef } from 'react'
import { getDashboardSummary, getDashboardActivity, getDashboardRecommendations, type DashboardRecommendationItem } from '../api/dashboard'
import { getUploads } from '../api/uploads'
import { getRequests } from '../api/requests'
import { fetchSettings, type SettingsData } from '../api/settings'
import { getInstances } from '../api/instances'
import type { InstanceSafeResponse } from '../types/api'
import type { DashboardSummaryResponse, DashboardActivityResponse, RequestItemResponse, UploadJob } from '../types/api'
import { CarrilPeticionesListas, CARRIL_LISTAS_MAX, LISTA_PARA_SUBIR } from '../components/CarrilPeticionesListas'
import { StatCard } from '../components/StatCard'
import { SyncCard } from '../components/SyncCard'
import { CuentaEmu } from '../components/CuentaEmu'
import { useSync } from '../context/SyncContext'
import { EmptyState } from '../components/EmptyState'
import { LoadingState } from '../components/LoadingState'
import { ErrorState } from '../components/ErrorState'
import { StatusBadge } from '../components/StatusBadge'
import { ServiceLabel, ServiceIcon } from '../components/ServiceIcon'
import { Favicon, domainOf } from '../components/Favicon'
import { UploadWizardModal } from '../components/UploadWizardModal'
import { RequestFormModal } from '../components/RequestFormModal'
import { useTooltip, HoverTitle } from '../components/Tooltip'
import { getLibraryItem } from '../api/library'
import type { LibraryItemResponse } from '../types/api'
import { formatBytes, formatDate, formatItemType, formatNumero, timeAgo } from '../utils/format'
import { posterUrl, buildDeepLink } from '../utils/libraryItem'
import { ValueChip, ValueIcon, SizeValueIcon, TypeValueIcon, DetailTitleText } from '../components/DetailCard'

// The recommendations item doesn't carry the configured instance name
// (unlike a full LibraryItemResponse), only the raw instance_type — capitalize
// it for display so it reads the same as the Biblioteca list's Origen column.
const INSTANCE_TYPE_LABEL: Record<string, string> = { radarr: 'Radarr', sonarr: 'Sonarr' }

// Same look and behaviour as the Biblioteca list's own Origen column
// (ValueChip + hover-link + ServiceLabel) — extracted so the per-item
// useTooltip() call stays valid despite living inside a table .map().
function RecOriginCell({ item, instances }: { item: DashboardRecommendationItem; instances: InstanceSafeResponse[] }) {
  const deepLink = buildDeepLink(item, instances)
  const label = INSTANCE_TYPE_LABEL[item.instance_type ?? ''] ?? item.instance_type ?? ''
  const { triggerProps, tooltipNode } = useTooltip(deepLink ? `Abrir en ${label}` : null)
  if (!item.instance_type) return <span className="panel-atenuado">—</span>
  return (
    <ValueChip linkable={!!deepLink}>
      {deepLink
        ? <a className="hover-link" href={deepLink} target="_blank" rel="noreferrer" onClick={e => e.stopPropagation()} {...triggerProps}><ServiceLabel type={item.instance_type} label={label} size={13} />{tooltipNode}</a>
        : <ServiceLabel type={item.instance_type} label={label} size={13} />}
    </ValueChip>
  )
}
import {
  STATUS_CLASS, ACTIVE_JOB_STATUSES, statusLabel, phaseLabel, currentPhaseInfo,
  progressCounter, queuedWaitText, formatSecondsHM, useTicker,
} from '../utils/uploadStatus'
import { useRefrescoPorAvisos, AVISOS_SUBIDA, AVISOS_SUBIDA_PROGRESO } from '../hooks/useRefrescoPorAvisos'
import { queSalieron, soloVivas, idsDe, ultimasTerminadas, ESPERA_MS, DESVANECER_MS } from '../utils/despedidaSubidas'
import { useSeccionVisible } from '../context/SeccionVisible'
import { EMU_URL } from '../constants/emu'
import { IconoEstrella, IconoLista, IconoPelicula, IconoSerie, IconoSubida, IconoTipo } from '../components/Iconos'

// Phase 11G — "Recomendaciones" groups, in the order they appear. The content
// name always links to its Biblioteca detail; the "Acción" button is
// group-specific: view the existing request, upload, or create a request.
type RecAction = 'view-request' | 'upload' | 'request'
const REC_GROUP_META: Record<number, {
  category: string
  action: RecAction; actionLabel: string
  className: string
}> = {
  1: { category: 'Petición compatible',
       action: 'view-request', actionLabel: 'Ver petición', className: 'panel-cat-1' },
  2: { category: 'Contenido único',
       action: 'upload', actionLabel: 'Subir a eMuwarez', className: 'panel-cat-2' },
  3: { category: 'Faltante',
       action: 'request', actionLabel: 'Petición a eMuwarez', className: 'panel-cat-3' },
}

// task_runs.name is the internal task key (services/scheduler.py's
// TASK_LIBRARY_SYNC/TASK_EMU_SYNC) — same human names Ajustes → Tareas
// programadas already shows for these same keys (services/scheduler.py's
// DEFAULT_TASKS). Unknown/future keys just fall back to the raw key, que es
// lo que pasó al añadir "check-version": salía en crudo. Lo vigila ahora
// tests/test_copias_frontend.py.
const TASK_NAME_LABEL: Record<string, string> = {
  'sync-library': 'Sincronizar bibliotecas',
  'vigilar-instancias': 'Vigilar instancias',
  'check-version': 'Comprobar versión',
  'sync-emu-requests': 'Sincronizar peticiones eMuwarez',
  'sync-emu-catalog': 'Sincronizar catálogo eMuwarez',
  'backup-config': 'Copia de seguridad',
  'mantenimiento': 'Mantenimiento',
}
function taskNameLabel(name: string): string {
  return TASK_NAME_LABEL[name] || name
}

// One row of the "Conexiones" card: icon + label + status badge. Only
// actually-configured connections are rendered, so the badge reads
// "Configurado" (or the instance's last test status when available).
function ConnRow({ icon, label, href, badge = 'Configurado', tone = 'ok' }: {
  icon: React.ReactNode; label: string; href?: string | null; badge?: string; tone?: 'ok' | 'warn' | 'error'
}) {
  const cls = tone === 'error' ? 'status-error' : tone === 'warn' ? 'status-partial' : 'status-available'
  const { triggerProps, tooltipNode } = useTooltip(href ? `Abrir ${label}` : null)
  const inner = (
    <>
      <span className="panel-conn-icono">{icon}</span>
      <span className="panel-conn-etiqueta">{label}</span>
    </>
  )
  return (
    <div className="panel-conn-fila">
      {href
        ? <a className="hover-link panel-conn-info" href={href} target="_blank" rel="noreferrer" {...triggerProps}>{inner}{tooltipNode}</a>
        : <div className="panel-conn-info">{inner}</div>}
      <span className={`badge ${cls}`}>{badge}</span>
    </div>
  )
}

// Una fila de "Actividad de subida": entera es un enlace al detalle de la
// subida en Subidas. Lleva su propio reloj para que el tiempo corra sin
// repintar el Panel entero cada segundo.
function FilaSubida({ job, yendose = false, compacta = false, onOpen }: {
  job: UploadJob; yendose?: boolean; compacta?: boolean; onOpen: (jobId: number) => void
}) {
  useTicker(ACTIVE_JOB_STATUSES.has(job.status))
  const isPreparingOrRunning = job.status === 'preparing' || job.status === 'running'
  const phaseInfo = isPreparingOrRunning ? currentPhaseInfo(job) : null
  const phaseLabelText = phaseInfo?.label ?? (isPreparingOrRunning ? phaseLabel(job.progress_phase) : null)
  // Total time since the job started (not just this sub-phase) — the
  // number that actually answers "how long has this been going".
  const totalElapsedText = isPreparingOrRunning ? progressCounter(job) : null
  const terminada = !ACTIVE_JOB_STATUSES.has(job.status)
  // El global que ya calcula el backend (uploadrr_progress.PHASES
  // pondera cada fase); se acota por si llega algo raro.
  const globalPct = Math.min(100, Math.max(0, Math.round(job.progress?.global_pct ?? 0)))
  return (
    // Terminada, se queda quieta ESPERA_MS y luego se va poco a
    // poco. Las que se despiden van al final de la lista, así
    // que al desaparecer no mueven de sitio a las de arriba.
    // En línea solo la duración, que es una constante del código.
    <HoverTitle className={`upload-row${yendose ? ' panel-fila-saliendo' : ''}`} tip="Ver detalle de la subida" onClick={() => onOpen(job.id!)}
      style={{ transition: `opacity ${DESVANECER_MS}ms ease-out` }}>
      {/* 36x54: el texto de la derecha ocupa unos 55 px (título 16,
          estado 17, barra con su % 11 y los huecos), así que el póster tiene
          que ser al menos eso para que la fila no crezca por debajo
          de él. Las recientes, sin barra, van al tamaño de Recomendaciones. */}
      <div className={`poster-thumb panel-poster${compacta ? ' panel-poster-peq' : ''}`}>
        {job.poster_url ? (
          <img
            src={posterUrl(job.poster_url, 'w154')}
            alt=""
            loading="lazy"
            className="panel-poster-img"
            onError={e => { (e.currentTarget as HTMLImageElement).style.display = 'none' }}
          />
        ) : (
          <span className="panel-poster-icono">
            <IconoTipo serie={job.media_type === 'series' || job.media_type === 'episode'} />
          </span>
        )}
      </div>
      <div className="panel-fila-texto">
        <div className="panel-fila-titulo">
          <span className="upload-row-title">{job.title ?? `Job #${job.id}`}</span>
          {(totalElapsedText || terminada) && (
            <span className="panel-fila-tiempo">
              {totalElapsedText ?? timeAgo(job.finished_at ?? job.updated_at)}
            </span>
          )}
        </div>
        <div className="panel-fila-estado">
          <div className="panel-fila-badges">
            <span className={`${STATUS_CLASS[job.status] || 'badge req-unknown'}${isPreparingOrRunning ? ' badge-blink' : ''}`}>{statusLabel(job.status)}</span>
            {job.status === 'queued' && (
              <span className="panel-fila-nota">{queuedWaitText(job)}</span>
            )}
            {isPreparingOrRunning && (
              <span className="panel-fila-fase">
                <span className="panel-fila-fase-texto">{phaseLabelText}</span>
                {phaseInfo?.counterText && <span className="panel-fila-contador">{phaseInfo.counterText}</span>}
                <span className="spinner panel-spinner-10" />
              </span>
            )}
            {terminada && job.duration_seconds != null && (
              <span className="panel-fila-duracion">en {formatSecondsHM(job.duration_seconds)}</span>
            )}
          </div>
          {/* Progreso global, en la misma barra fina que usa el resto
              del Panel, con su porcentaje al lado. Solo mientras trabaja: en
              cola no hay nada que medir todavía, y terminada la barra no dice
              nada que el estado no diga ya. */}
          {isPreparingOrRunning && (
            <div className="panel-fila-progreso">
              <div className="progress-bar panel-fila-barra">
                {/* En línea: el avance es un valor calculado. */}
                <div className="progress-fill" style={{ transform: `scaleX(${globalPct / 100})` }} />
              </div>
              <span className="panel-fila-pct">{globalPct}%</span>
            </div>
          )}
        </div>
      </div>
    </HoverTitle>
  )
}

// Panel HUD stat-card icons — large, single-purpose per metric (matches the
// approved holographic reference; other pages' StatCard usage is unaffected
// since the `icon` prop only renders inside `.panel-hud`'s CSS scope).
function svgIcon(d: React.ReactNode) {
  // strokeLinecap="round" is what makes ICON_MISSING's "M12 17h.01" trick (a
  // near-zero-length segment, the standard way to draw the exclamation
  // mark's dot) actually render as a dot instead of vanishing — without it
  // the default "butt" cap draws nothing for a zero-length line.
  return <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">{d}</svg>
}
const ICON_LIBRARY = svgIcon(<><ellipse cx="12" cy="5" rx="8" ry="3" /><path d="M4 5v6c0 1.7 3.6 3 8 3s8-1.3 8-3V5" /><path d="M4 11v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6" /></>)
const ICON_AVAILABLE = svgIcon(<><path d="M21 15V6a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v9" /><path d="M2 15h20l-2 5H4l-2-5z" /></>)
const ICON_MISSING = svgIcon(<><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z" /><path d="M12 9v4M12 17h.01" /></>)
const ICON_UNIQUE = svgIcon(<><path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M18.4 5.6l-2.1 2.1M7.7 16.3l-2.1 2.1" /><circle cx="12" cy="12" r="3.2" /></>)
const ICON_UPLOADS = svgIcon(<path d="M12 19V5M5 12l7-7 7 7" />)
const ICON_REQUESTS = svgIcon(<><rect x="9" y="3" width="6" height="4" rx="1" /><path d="M9 12h6M9 16h4" /></>)
const ICON_COMPATIBLE = svgIcon(<><circle cx="12" cy="12" r="9" /><path d="M8.5 12.3l2.3 2.3 4.7-4.7" /></>)
const ICON_PARTIAL = svgIcon(<><circle cx="12" cy="12" r="9" /><path d="M12 3a9 9 0 0 1 0 18z" fill="currentColor" stroke="none" /></>)
const ICON_RECLAIMED = svgIcon(<><path d="M5 21V4" /><path d="M5 4h13l-3.2 4.2L18 12.5H5" /></>)
const ICON_MINE = svgIcon(<><path d="M22 2 11 13" /><path d="M22 2 15 22l-4-9-9-4 20-7z" /></>)

interface DashboardPageProps {
  onNavigate?: (page: string) => void
}

export function DashboardPage({ onNavigate }: DashboardPageProps = {}) {
  // Open a recommendation's target: group 1 → its eMuwarez request (Peticiones
  // tab), groups 2 & 3 → the content's own detail page (Biblioteca tab). Both
  // stash an id that the destination page reads on mount.
  // The content name always opens its own Biblioteca detail page (all groups).
  const openLibraryDetail = (item: DashboardRecommendationItem) => {
    try { sessionStorage.setItem('emuwarez_open_library_item', String(item.id)) } catch { /* ignore */ }
    onNavigate?.('library')
  }

  // A row of "Actividad de subida" → same stash-and-navigate handoff, opening
  // that job's own detail page in Subidas.
  const goToUpload = (jobId: number) => {
    try { sessionStorage.setItem('emuwarez_open_upload', String(jobId)) } catch { /* ignore */ }
    onNavigate?.('uploads')
  }

  // Una petición, en su ficha de Peticiones: la de una recomendación y la del
  // carril de listas para subir, por el mismo camino que la campana.
  const openRequest = (requestId: number) => {
    try { sessionStorage.setItem('emuwarez_open_request', String(requestId)) } catch { /* ignore */ }
    onNavigate?.('requests')
  }

  // "Acción" column, group-specific: group 1 → open the existing request;
  // group 2 → open the upload wizard; group 3 → open the request form. Groups
  // 2 & 3 fetch the full library item first.
  const handleRecAction = async (item: DashboardRecommendationItem) => {
    const meta = REC_GROUP_META[item.rec_group] ?? REC_GROUP_META[2]
    if (meta.action === 'view-request') {
      if (item.rec_request_id != null) openRequest(item.rec_request_id)
      return
    }
    try {
      const libItem = await getLibraryItem(item.id)
      if (meta.action === 'request') setRequestItem(libItem)
      else { setWizardPreselect(undefined); setWizardItem(libItem) }
    } catch { /* ignore — the content may have vanished since the last sync */ }
  }

  // Volver al Panel no vuelve a enseñar "Cargando Panel…": la sección no se
  // desmonta al cambiar de pestaña, se queda montada y oculta (ver AppShell).
  // Esto solo corre la PRIMERA vez que se entra.
  const [summary, setSummary] = useState<DashboardSummaryResponse | null>(null)
  const [taskActivity, setTaskActivity] = useState<DashboardActivityResponse | null>(null)
  const [recommendations, setRecommendations] = useState<DashboardRecommendationItem[]>([])
  const [activeUploads, setActiveUploads] = useState<UploadJob[]>([])
  const [connSettings, setConnSettings] = useState<SettingsData | null>(null)
  const [connInstances, setConnInstances] = useState<InstanceSafeResponse[]>([])
  const [loadingData, setLoadingData] = useState(true)
  const [dataError, setDataError] = useState<string | null>(null)
  const [wizardItem, setWizardItem] = useState<LibraryItemResponse | null>(null)
  const [wizardPreselect, setWizardPreselect] = useState<{ season?: number | null; episode?: number | null } | undefined>(undefined)
  const [requestItem, setRequestItem] = useState<LibraryItemResponse | null>(null)
  // Global sync state (shared with Biblioteca/Peticiones and the progress
  // banner). `lastInvalidatedAt` triggers a data reload when what's loaded
  // stops being valid — una sincronización que termina, o volver a la pestaña
  // — the completion message itself is shown centrally in the topbar (see
  // SyncProgressBanner), not duplicated here.
  const { lastInvalidatedAt } = useSync()

  // Carril «Peticiones listas para subir»: las de más recompensa primero (el
  // orden y el tope, del servidor) y cuántas listas hay en total. Va con el
  // resto del Panel (loadData: al terminar una sincronización, al volver a la
  // pestaña y en la red de seguridad) y además cuando termina una subida. Con
  // número de orden, como las subidas: una respuesta vieja no pisa una nueva.
  const [carril, setCarril] = useState<{ items: RequestItemResponse[]; total: number }>({ items: [], total: 0 })
  const carrilSeq = useRef(0)
  const loadCarril = useCallback(async () => {
    const seq = ++carrilSeq.current
    try {
      const r = await getRequests({ readiness: [LISTA_PARA_SUBIR], sort: 'points_desc', limit: CARRIL_LISTAS_MAX })
      if (seq === carrilSeq.current) setCarril({ items: r.items, total: r.total })
    } catch { /* se queda lo que había; la siguiente vuelta lo reintenta */ }
  }, [])

  // Toda la respuesta, para sacar de ella las que han terminado hace poco.
  const [todasLasSubidas, setTodasLasSubidas] = useState<UploadJob[]>([])

  // Las que acaban de terminar se quedan con su estado final y luego se
  // desvanecen (ver utils/despedidaSubidas). Aparte de `activeUploads` porque
  // ya no están vivas: no cuentan para el sondeo ni para el tic del reloj.
  const [despidiendose, setDespidiendose] = useState<{ job: UploadJob; yendose: boolean }[]>([])
  const vivasAntes = useRef<Set<number>>(new Set())
  const relojes = useRef<ReturnType<typeof setTimeout>[]>([])
  useEffect(() => () => { relojes.current.forEach(clearTimeout) }, [])

  // La ÚNICA puerta por la que entran las subidas al Panel, la traiga la carga
  // completa o el refresco propio de "Actividad de subida". Si cada una lo
  // hiciera por su cuenta, según por dónde llegara la noticia la fila se
  // despediría o no.
  const registrarSubidas = useCallback((todas: UploadJob[]): UploadJob[] => {
    const vivas = soloVivas(todas)
    const idsVivas = idsDe(vivas)
    const salieron = queSalieron(todas, vivasAntes.current)
    vivasAntes.current = idsVivas
    setActiveUploads(vivas)
    setTodasLasSubidas(todas)

    setDespidiendose(prev => {
      // Una que vuelve a estar viva (la reintentaste) deja de despedirse.
      const siguen = prev.filter(
        d => !idsVivas.has(d.job.id!) && !salieron.some(s => s.id === d.job.id))
      if (!salieron.length && siguen.length === prev.length) return prev   // nada que cambiar
      return [...siguen, ...salieron.map(job => ({ job, yendose: false }))]
    })
    for (const job of salieron) {
      relojes.current.push(setTimeout(() => setDespidiendose(
        prev => prev.map(d => (d.job.id === job.id ? { ...d, yendose: true } : d))), ESPERA_MS))
      relojes.current.push(setTimeout(() => setDespidiendose(
        prev => prev.filter(d => d.job.id !== job.id)), ESPERA_MS + DESVANECER_MS))
    }
    // Una subida que termina puede haber sido la de una petición del carril.
    if (salieron.length) void loadCarril()
    return vivas
  }, [loadCarril])

  // Lo que se pinta: primero las vivas y detrás las que se van. En ese orden
  // porque al quitarse una no mueve de sitio a las de arriba.
  const filasDeSubida = [
    ...activeUploads.map(job => ({ job, yendose: false })),
    ...despidiendose,
  ]
  // Debajo, las últimas terminadas: una subida fallida sigue a la vista cuando
  // acaba su despedida, y la tarjeta no se queda vacía entre subida y subida.
  const recientes = ultimasTerminadas(todasLasSubidas, idsDe(despidiendose.map(d => d.job)))

  // "Actividad de subida" se refresca aparte del Panel, por el aviso del servidor (con el sondeo de 2,5 s de red
  // de seguridad), y es la única que pide las subidas. Con un número de orden por petición: una respuesta lenta
  // que llegara tarde repondría el estado de antes (la barra iba hacia atrás y una subida acabada reaparecía viva).
  // Sin las preparatorias, que no ocupan sitio, y con 100.
  const subidasSeq = useRef(0)
  const loadActiveUploads = useCallback(async () => {
    const seq = ++subidasSeq.current
    try {
      const todas = await getUploads({ hide_preparatory: true, limit: 100 })
      if (seq === subidasSeq.current) registrarSubidas(todas)
    } catch { /* ignore — next tick retries */ }
  }, [registrarSubidas])

  // Las subidas se piden aquí solo la primera vez: de ahí en adelante las
  // refresca el aviso del servidor, sin esperar a que dé la vuelta el Panel.
  const subidasPedidas = useRef(false)

  const loadData = useCallback(async () => {
    if (!subidasPedidas.current) {
      subidasPedidas.current = true
      void loadActiveUploads()
    }
    setLoadingData(true)
    setDataError(null)
    // Settings first, so "Recomendaciones" honours the configured limit.
    const cfg = await fetchSettings().catch(() => null)
    if (cfg) setConnSettings(cfg)
    // Se espera con el resto, no por su cuenta: su valor entra en la caché, y
    // guardarlo vacío haría parpadear "Conexiones" al volver al Panel.
    const instancias = await getInstances().catch(() => [] as InstanceSafeResponse[])
    setConnInstances(instancias)
    const recentLimit = cfg?.recent_activity_limit ?? 100
    // Promise.allSettled never rejects — each branch's own status carries
    // its outcome, so failures are handled per-item below, not via catch.
    const [s, a, la] = await Promise.allSettled([
      getDashboardSummary(),
      getDashboardActivity(),
      getDashboardRecommendations(recentLimit),
      // A la vez que el resto, para que el carril salga en el mismo pintado.
      loadCarril(),
    ])
    if (s.status === 'fulfilled') setSummary(s.value)
    else {
      setDataError('No se pudieron cargar los datos del dashboard')
    }
    if (a.status === 'fulfilled') setTaskActivity(a.value)
    if (la.status === 'fulfilled') setRecommendations(la.value.items)
    setLoadingData(false)
  }, [loadActiveUploads, loadCarril])

  useEffect(() => { loadData() }, [loadData])

  // Reload the dashboard data whenever any global sync finishes.
  // Recarga en cuanto algo cambia, se esté viendo esta sección o no: los avisos
  // que suben esta marca son raros (una sincronización, una tarea), así que
  // mantenerlas todas al día cuesta poco y a cambio cambiar de pestaña enseña
  // lo actual y no lo actual tras un parpadeo.
  useEffect(() => { if (lastInvalidatedAt) loadData() }, [lastInvalidatedAt, loadData])

  // Red de seguridad del Panel entero (resumen/recomendaciones/tareas). Solo
  // mientras se ve: la sección se queda montada al cambiar de pestaña, así que
  // sin esta condición seguiría preguntando cada 15 s para nadie.
  //
  // Encadenado: la siguiente vuelta se programa cuando acaba la anterior. Con
  // un temporizador fijo, mientras una sincronización tenía bloqueada la base
  // se acumulaban peticiones sin terminar.
  const panelALaVista = useSeccionVisible()
  useEffect(() => {
    if (!panelALaVista) return
    let vivo = true
    let t: ReturnType<typeof setTimeout>
    const vuelta = async () => {
      try { await loadData() } finally { if (vivo) t = setTimeout(vuelta, 15000) }
    }
    t = setTimeout(vuelta, 15000)
    return () => { vivo = false; clearTimeout(t) }
  }, [loadData, panelALaVista])

  const hasLiveUpload = activeUploads.length > 0
  // Ver UploadsPage: la cadencia depende de si hay algo vivo, pero el sondeo
  // no se apaga — es la red de seguridad por si se pierde un aviso.
  useRefrescoPorAvisos(AVISOS_SUBIDA, loadActiveUploads,
    { cadaSinCanal: hasLiveUpload ? 2500 : 30_000, soloVisible: AVISOS_SUBIDA_PROGRESO })

  if (loadingData && !summary) return <LoadingState label="Cargando Panel…" />
  if (!summary) return <ErrorState message={dataError ?? 'No se pudieron cargar los datos del dashboard'} onRetry={loadData} />

  const s = summary
  const taskRuns = (taskActivity?.items ?? []).slice(0, 50)

  return (
    <div className="panel-pagina">
      {wizardItem && (
        <UploadWizardModal item={wizardItem} preselect={wizardPreselect} onClose={() => setWizardItem(null)} onDone={() => { loadData(); loadActiveUploads() }} onNavigate={onNavigate} />
      )}
      {requestItem && (
        <RequestFormModal item={requestItem} onClose={() => setRequestItem(null)} />
      )}

      <div className="page-header panel-cabecera">
        <div>
          <div className="page-title">Panel</div>
        </div>
        <CuentaEmu />
        <SyncCard />
      </div>

      {/* Lo primero, porque es lo que se hace: qué petición lista para subir
          paga más. Una sola fila; sin ninguna lista no ocupa nada. */}
      <CarrilPeticionesListas items={carril.items} total={carril.total} onOpen={openRequest} />

      {/* Main grid — fills the remaining height exactly (flex:1, minHeight:0)
          so the page itself never scrolls; each panel below keeps its own
          internal scroll via its inner `overflow: auto` div. */}
      <div className="dashboard-grid panel-rejilla">
        {/* Left column — "Actividad reciente" (50vh) with "Últimas tareas
            ejecutadas" (25vh) stacked under it, so tasks sits parallel to the
            "Conexiones" card in the right column. */}
        <div className="panel-columna">
          <div data-tour="dashboard-recommendations" className="activity-section panel-bloque panel-grande">
            <div className="section-header">
              <div className="section-title">Recomendaciones</div>
            </div>
            {recommendations.length === 0 ? (
              <EmptyState
                icon={<IconoEstrella />}
                title="No hay recomendaciones todavía"
                body="Sincroniza tu biblioteca, eMuwarez y las peticiones para ver aquí qué subir o pedir."
              />
            ) : (
              <div className="panel-tabla-scroll">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Título</th>
                      <th>Tipo</th>
                      <th>Origen</th>
                      <th>Categoría</th>
                      <th>Tamaño</th>
                      <th className="col-actions">Acción</th>
                    </tr>
                  </thead>
                  <tbody>
                    {recommendations.map(item => {
                      const meta = REC_GROUP_META[item.rec_group] ?? REC_GROUP_META[2]
                      return (
                      <tr key={`${item.rec_group}-${item.rec_request_id ?? item.id}`}>
                        <td>
                          <div className="panel-rec-titulo">
                            <div className="poster-thumb panel-poster panel-poster-peq">
                              {item.poster_url ? (
                                <img
                                  src={posterUrl(item.poster_url, 'w154')}
                                  alt=""
                                  loading="lazy"
                                  className="panel-poster-img"
                                  onError={e => { (e.currentTarget as HTMLImageElement).style.display = 'none' }}
                                />
                              ) : (
                                <span className="panel-poster-icono">
                                  <IconoTipo serie={item.item_type === 'series' || item.item_type === 'season' || item.item_type === 'episode'} />
                                </span>
                              )}
                            </div>
                            <HoverTitle className="hover-link panel-rec-nombre" onClick={() => openLibraryDetail(item)} tip="Ver ficha del contenido"><DetailTitleText title={item.content_name} /></HoverTitle>
                          </div>
                        </td>
                        <td className="panel-nowrap">
                          <ValueChip><ValueIcon><TypeValueIcon /></ValueIcon><span className="txt">{formatItemType(item.item_type)}</span></ValueChip>
                        </td>
                        <td className="panel-nowrap"><RecOriginCell item={item} instances={connInstances} /></td>
                        <td>
                          <span className={`badge ${meta.className}`}>{meta.category}</span>
                        </td>
                        <td className="panel-nowrap">
                          {item.size_bytes
                            ? <ValueChip><ValueIcon><SizeValueIcon /></ValueIcon><span className="txt">{formatBytes(item.size_bytes)}</span></ValueChip>
                            : <span className="panel-atenuado">—</span>}
                        </td>
                        <td className="col-actions">
                          <button className="btn btn-primary btn-sm" onClick={() => handleRecAction(item)}>
                            {meta.actionLabel}
                          </button>
                        </td>
                      </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* Últimas tareas ejecutadas — parallel to "Conexiones" on the right. */}
          <div data-tour="dashboard-tasks" className="activity-section panel-bloque panel-chico">
            <div className="section-header">
              <div className="section-title">Últimas tareas ejecutadas</div>
            </div>
            {taskRuns.length === 0 ? (
              <EmptyState
                icon={<IconoLista />}
                title="No hay tareas ejecutadas todavía"
                body="Las sincronizaciones automáticas y manuales aparecerán aquí."
              />
            ) : (
              <div className="panel-tabla-scroll">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Tarea</th>
                      <th>Estado</th>
                      <th>Resumen</th>
                      <th>Iniciada</th>
                      <th>Finalizada</th>
                    </tr>
                  </thead>
                  <tbody>
                    {taskRuns.map(item => (
                      <tr key={item.id}>
                        <td>{taskNameLabel(item.name)}</td>
                        <td>
                          <StatusBadge status={item.status ?? ''} type="task" />
                        </td>
                        <td className="panel-tarea-resumen">{item.summary ?? '—'}</td>
                        <td className="panel-tarea-fecha">{formatDate(item.started_at)}</td>
                        <td className="panel-tarea-fecha">{formatDate(item.finished_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>

        {/* Right — Actividad de subida: real running upload jobs, honest data only,
            and the last few that finished below them. Stretches to the full
            height of "Actividad reciente" on its left. */}
        <div className="panel-columna">
          <div data-tour="dashboard-uploads" className="upload-panel panel-bloque panel-grande">
            <div className="section-header">
              <div className="section-title">Actividad de subida</div>
              <span className="panel-ver-todas">
                <HoverTitle as="span" className="hover-link" onClick={() => onNavigate?.('uploads')} tip="Abrir Subidas">Ver todas</HoverTitle>
              </span>
            </div>
            <div className="upload-panel-body">
              {filasDeSubida.length === 0 && recientes.length === 0 ? (
                <EmptyState
                  icon={<IconoSubida />}
                  title="No hay subidas en curso"
                  body="Sube contenido desde Biblioteca o una recomendación para verlo aquí, con su progreso en vivo."
                />
              ) : (
                <>
                  {filasDeSubida.length === 0
                    ? <div className="panel-sin-subidas">No hay subidas en curso.</div>
                    : filasDeSubida.map(({ job, yendose }) => <FilaSubida key={job.id} job={job} yendose={yendose} onOpen={goToUpload} />)}
                  {recientes.length > 0 && (
                    <>
                      <div className="upload-panel-group">Recientes</div>
                      {recientes.map(job => <FilaSubida key={job.id} job={job} compacta onOpen={goToUpload} />)}
                    </>
                  )}
                </>
              )}
            </div>
          </div>

          {/* Estado de conexiones — misma altura que "Últimas tareas ejecutadas" */}
          <div data-tour="dashboard-connections" className="upload-panel panel-bloque panel-chico">
            <div className="section-header">
              <div className="section-title">Conexiones</div>
            </div>
            <div className="panel-conexiones-cuerpo">
              {(() => {
                const rows: React.ReactNode[] = []
                const qbitUrl = connSettings?.qbit_url
                  ? connSettings.qbit_url
                  : null
                // Radarr/Sonarr instances (each configured one, with its icon).
                for (const inst of connInstances) {
                  rows.push(
                    <ConnRow key={`inst-${inst.id}`} icon={<ServiceIcon type={inst.type === 'sonarr' ? 'sonarr' : 'radarr'} size={16} />}
                      label={inst.name} href={inst.url} />
                  )
                }
                if (connSettings?.emu_api_key_configured)
                  rows.push(<ConnRow key="emu" icon={<ServiceIcon type="emu" size={16} />} label="API eMuwarez" href={EMU_URL} />)
                if (connSettings?.tmdb_api_key_configured)
                  rows.push(<ConnRow key="tmdb" icon={<ServiceIcon type="tmdb" size={16} />} label="API TMDb" href="https://www.themoviedb.org" />)
                if (connSettings?.qbit_configured)
                  rows.push(<ConnRow key="qbit" icon={<ServiceIcon type="qbittorrent" size={16} />} label="qBittorrent" href={qbitUrl} />)
                // Image hosts: imgbox is always the default fallback, plus enabled ones.
                const imgIds = Array.from(new Set(['imgbox', ...(connSettings?.image_hosts_enabled ?? [])]))
                for (const id of imgIds) {
                  const meta = connSettings?.image_hosts_available?.find(h => h.id === id)
                  rows.push(<ConnRow key={`img-${id}`} icon={<Favicon domain={domainOf(meta?.url)} size={16} background="var(--overlay-light)" fallback={<ServiceIcon type="imghost" size={16} />} />}
                    label={meta?.label ?? id} href={meta?.url} />)
                }
                if (connSettings?.notify_discord_webhook_configured)
                  rows.push(<ConnRow key="discord" icon={<ServiceIcon type="discord" size={16} />} label="Bot de Discord" />)
                if (connSettings?.notify_telegram_bot_token_configured)
                  rows.push(<ConnRow key="telegram" icon={<ServiceIcon type="telegram" size={16} />} label="Bot de Telegram" />)
                return rows.length ? rows : <div className="panel-sin-conexiones">Sin conexiones configuradas todavía.</div>
              })()}
            </div>
          </div>
        </div>
      </div>

      {/* Las cifras van al final, no al principio: lo primero que se ve ahora
          es la cuadrícula principal (Recomendaciones, Actividad de subida...),
          que es lo que de verdad se usa. El color de la cifra solo marca un
          estado (disponible, faltante, compatible, parcial); el resto va en
          el color del texto. */}
      <div data-tour="dashboard-stats">
      <div className="stat-cards-row panel-cifras-fijas">
        <StatCard
          icon={ICON_LIBRARY}
          label="Biblioteca sincronizada"
          value={s.library_total}
          info="Total de películas y episodios importados desde tus instancias de Radarr y Sonarr."
        >
          <div className="panel-sub-lista panel-sub-scroll">
            <div className="stat-card-sub-row">
              <ServiceLabel type="radarr" label={`Radarr: ${formatNumero(s.radarr_items)}`} size={13} />
            </div>
            <div className="stat-card-sub-row">
              <ServiceLabel type="sonarr" label={`Sonarr: ${formatNumero(s.sonarr_items)}`} size={13} />
            </div>
          </div>
        </StatCard>

        <StatCard
          icon={ICON_AVAILABLE}
          label="Disponibles"
          value={s.available}
          accentColor="var(--color-available)"
          info="Contenido cuyo archivo está presente en disco, listo para comparar o subir."
        />

        <StatCard
          icon={ICON_MISSING}
          label="Faltantes"
          value={s.missing}
          accentColor="var(--color-missing)"
          info="Contenido que Radarr/Sonarr conocen pero cuyo archivo aún no está en disco (falta, en cola o con error)."
        />

        <StatCard
          icon={ICON_UNIQUE}
          label="Contenido único"
          value={s.unique_content ?? 0}
          info="Contenido disponible que aún no está en eMuwarez: las películas, las temporadas completas de series o documentales y sus capítulos. Son tus oportunidades de subida."
        >
          <div className="panel-sub-lista">
            <div className="stat-card-sub-row"><IconoPelicula /> {formatNumero(s.unique_movies ?? 0)} películas</div>
            <div className="stat-card-sub-row"><IconoSerie /> {formatNumero(s.unique_seasons ?? 0)} temporadas, {formatNumero(s.unique_episodes ?? 0)} capítulos</div>
          </div>
        </StatCard>

        <StatCard
          icon={ICON_UPLOADS}
          label="Tus subidas"
          value={s.uploads_completed ?? 0}
          info="Número de subidas a eMuwarez que has completado con Uploadrr."
        />
      </div>

      {/* eMuwarez requests — cards + a "Sincronizar peticiones" button below.
          20px bottom margin = the flex gap between the activity panels and
          their lower cards, so spacing above and below each panel matches. */}
      <div className="panel-cifras-peticiones">
        <div className="stat-cards-row">
          <StatCard
            icon={ICON_REQUESTS}
            label="Peticiones eMuwarez"
            value={s.requests_total ?? 0}
            info="Total de peticiones activas descargadas de eMuwarez."
          />
          <StatCard
            icon={ICON_COMPATIBLE}
            label="Peticiones compatibles"
            value={s.requests_compatible ?? 0}
            accentColor="var(--color-available)"
            info="Peticiones cuya mejor coincidencia en tu biblioteca cumple resolución y source: quizás puedas cubrirlas."
          />
          <StatCard
            icon={ICON_PARTIAL}
            label="Peticiones parciales"
            value={s.requests_partial ?? 0}
            accentColor="var(--color-warning)"
            info="Peticiones cuya mejor coincidencia cumple solo parte de lo pedido (resolución o source, pero no ambos)."
          />
          <StatCard
            icon={ICON_RECLAIMED}
            label="Peticiones reclamadas"
            value={s.requests_reclaimed ?? 0}
            info="Peticiones ya Reclamadas en eMuwarez, tuyas y de otros: es el total. En Peticiones, cada una dice si la reclamaste tú, la reclamó otro usuario o eMuwarez no indica quién."
          />
          <StatCard
            icon={ICON_MINE}
            label="Mis peticiones"
            value={s.requests_mine ?? 0}
            info="Peticiones creadas por tu propio usuario de eMuwarez (según el nombre configurado en Ajustes)."
          />
        </div>
      </div>
      </div>
    </div>
  )
}
