import { useState, useEffect, useCallback, useRef } from 'react'
import { getDashboardSummary, getDashboardRecommendations, type DashboardRecommendationItem } from '../api/dashboard'
import { getUploadJob, getUploads } from '../api/uploads'
import { ACTIVE_JOB_STATUSES } from '../utils/uploadStatus'
import { fetchSettings } from '../api/settings'
import { getVersionInfo } from '../api/maintenance'
import { getLibraryItem } from '../api/library'
import { suscribirse } from '../api/eventos'
import type { DashboardSummaryResponse, LibraryItemResponse, UploadJob } from '../types/api'
import { SyncCard } from '../components/SyncCard'
import { CuentaEmu } from '../components/CuentaEmu'
import { useSync } from '../context/SyncContext'
import { LoadingState } from '../components/LoadingState'
import { ErrorState } from '../components/ErrorState'
import { UploadWizardModal } from '../components/UploadWizardModal'
import { RequestFormModal } from '../components/RequestFormModal'
import { CarrilListo, type SeleccionCarril } from '../components/hoy/CarrilListo'
import { SubidaPorLotesModal } from '../components/lote/SubidaPorLotesModal'
import { useSeleccionLote } from '../hooks/useSeleccionLote'
import { MAX_ELEMENTOS_LOTE, claveDelPanel, entradaDelPanel, type EntradaLote } from '../utils/lote'
import { CarrilEnCurso } from '../components/hoy/CarrilEnCurso'
import { BandaAtencion } from '../components/hoy/BandaAtencion'
import { Franja } from '../components/hoy/Franja'
import { useRefrescoPorAvisos, AVISOS_SUBIDA, AVISOS_SUBIDA_PROGRESO } from '../hooks/useRefrescoPorAvisos'
import { queSalieron, soloVivas, idsDe, ultimasTerminadas, ESPERA_MS, DESVANECER_MS } from '../utils/despedidaSubidas'
import {
  avisosDeAtencion, fallidasRecientes, lineaSincronizacion, ordenarEnCurso, repartirRecomendaciones,
} from '../utils/hoy'
import { useAlSalir, useSeccionVisible } from '../context/SeccionVisible'

// La versión publicada se mira como mucho una vez por hora (el servidor tampoco pregunta más a menudo).
const VERSION_CADA_MS = 3_600_000

interface DashboardPageProps {
  onNavigate?: (page: string) => void
}

// El Panel: lo que se puede subir ahora y lo que está subiéndose, una banda con lo que hay que mirar y debajo cinco números.
export function DashboardPage({ onNavigate }: DashboardPageProps = {}) {
  // Abrir una ficha o una subida: se apunta el id y se cambia de sección; el destino lo recoge al entrar.
  const abrirFicha = (item: DashboardRecommendationItem) => {
    try { sessionStorage.setItem('emuwarez_open_library_item', String(item.id)) } catch { /* ignore */ }
    onNavigate?.('library')
  }
  const abrirPeticion = (item: DashboardRecommendationItem) => {
    if (item.rec_request_id == null) return
    try { sessionStorage.setItem('emuwarez_open_request', String(item.rec_request_id)) } catch { /* ignore */ }
    onNavigate?.('requests')
  }
  const goToUpload = (jobId: number) => {
    try { sessionStorage.setItem('emuwarez_open_upload', String(jobId)) } catch { /* ignore */ }
    onNavigate?.('uploads')
  }

  // Volver al Panel no vuelve a enseñar "Cargando Panel…": la sección no se
  // desmonta al cambiar de pestaña, se queda montada y oculta (ver AppShell).
  // Esto solo corre la PRIMERA vez que se entra.
  const [summary, setSummary] = useState<DashboardSummaryResponse | null>(null)
  const [recommendations, setRecommendations] = useState<DashboardRecommendationItem[]>([])
  const [activeUploads, setActiveUploads] = useState<UploadJob[]>([])
  const [versionNueva, setVersionNueva] = useState<string | null>(null)
  const [recsError, setRecsError] = useState<string | null>(null)
  const [loadingData, setLoadingData] = useState(true)
  const [dataError, setDataError] = useState<string | null>(null)
  const [wizardItem, setWizardItem] = useState<LibraryItemResponse | null>(null)
  const [wizardPreselect, setWizardPreselect] = useState<{ season?: number | null; episode?: number | null } | undefined>(undefined)
  const [wizardRequestId, setWizardRequestId] = useState<number | undefined>(undefined)
  const [requestItem, setRequestItem] = useState<LibraryItemResponse | null>(null)
  // Si ya se está pidiendo un contenido para abrir el asistente o el formulario (no se desactivan los botones: el que
  // se pulsó perdería el foco y el cierre del modal no sabría a dónde devolverlo), y por qué falló la última vez.
  const abriendo = useRef(false)
  const [errorAccion, setErrorAccion] = useState<string | null>(null)
  // «Subir seleccionadas»: el botón «Seleccionar» pone casillas en las filas de «Listo para subir» (peticiones y
  // otras ideas, no faltantes). Lo marcado se limpia al salir del Panel (la sección se queda montada y se recarga
  // sola) y al encolar el lote.
  const [modoSeleccion, setModoSeleccion] = useState(false)
  const {
    total: totalSeleccion, lleno: loteLleno, alternar: alternarLote, limpiar: limpiarLote, tiene: marcada,
    vigente: seleccionVigente,
  } = useSeleccionLote<DashboardRecommendationItem, string>(MAX_ELEMENTOS_LOTE, claveDelPanel)
  const [loteAbierto, setLoteAbierto] = useState<EntradaLote[] | null>(null)
  // Cada salida del Panel lo sube: un «Subir seleccionadas» que aún esperaba sus fichas no abre el lote al volver.
  const salidas = useRef(0)
  useAlSalir(() => {
    salidas.current++
    limpiarLote()
    setModoSeleccion(false)
    setLoteAbierto(null)
  })
  // Una sincronización que termina, o volver a la pestaña, sube `lastInvalidatedAt` y recarga lo cargado. El mensaje
  // de que terminó sale en la barra de arriba (ver SyncProgressBanner), no aquí.
  const { lastInvalidatedAt } = useSync()

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
  // completa o el refresco propio de "En curso". Si cada una lo
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
    return vivas
  }, [])

  // Lo que se pinta: primero las vivas y detrás las que se van. En ese orden
  // porque al quitarse una no mueve de sitio a las de arriba.
  const filasDeSubida = [
    ...ordenarEnCurso(activeUploads).map(job => ({ job, yendose: false })),
    ...despidiendose,
  ]

  // "En curso" se refresca aparte del Panel, por el aviso del servidor (con el sondeo de 2,5 s de red
  // de seguridad), y es la única que pide las subidas. Con un número de orden por petición: una respuesta lenta
  // que llegara tarde repondría el estado de antes (la barra iba hacia atrás y una subida acabada reaparecía viva).
  // Sin las preparatorias, que no ocupan sitio, y con 100.
  const subidasSeq = useRef(0)
  const loadActiveUploads = useCallback(async () => {
    const seq = ++subidasSeq.current
    try {
      // Las 100 más nuevas no bastan con lotes grandes: con más de 100 vivas, la que sube (la más vieja) se caía de
      // «En curso», y al fallar no salía en «Necesita atención». Las vivas y las fallidas se piden aparte y se juntan
      // con las recientes.
      const [recientes, vivas, fallidas] = await Promise.all([
        getUploads({ hide_preparatory: true, limit: 100 }),
        getUploads({ status: [...ACTIVE_JOB_STATUSES].join(','), limit: 500 }),
        getUploads({ status: 'failed', hide_preparatory: true, limit: 50 }),
      ])
      const todas: UploadJob[] = []
      const enLista = new Set<number | undefined>()
      for (const j of [...recientes, ...vivas, ...fallidas]) {
        if (!enLista.has(j.id)) { enLista.add(j.id); todas.push(j) }
      }
      // Una viva vieja que acaba de completarse o cancelarse no sale en ninguna: se pide sola, para que se despida
      // con su estado final. Una borrada da 404 y se deja ir.
      const perdidas = [...vivasAntes.current].filter(id => !enLista.has(id)).slice(0, MAX_ELEMENTOS_LOTE)
      const finales = await Promise.allSettled(perdidas.map(id => getUploadJob(id)))
      for (const r of finales) if (r.status === 'fulfilled') todas.push(r.value)
      if (seq === subidasSeq.current) registrarSubidas(todas)
    } catch { /* ignore — next tick retries */ }
  }, [registrarSubidas])

  // Las subidas se piden aquí solo la primera vez: de ahí en adelante las
  // refresca el aviso del servidor, sin esperar a que dé la vuelta el Panel.
  const subidasPedidas = useRef(false)
  const versionMirada = useRef(0)

  const loadData = useCallback(async () => {
    if (!subidasPedidas.current) {
      subidasPedidas.current = true
      void loadActiveUploads()
    }
    setLoadingData(true)
    setDataError(null)
    // Settings first, so "Listo para subir" honours the configured limit.
    const cfg = await fetchSettings().catch(() => null)
    const recentLimit = cfg?.recent_activity_limit ?? 100
    // Promise.allSettled never rejects — each branch's own status carries
    // its outcome, so failures are handled per-item below, not via catch.
    const [s, la] = await Promise.allSettled([
      getDashboardSummary(),
      getDashboardRecommendations(recentLimit),
    ])
    if (s.status === 'fulfilled') setSummary(s.value)
    else {
      setDataError('No se pudieron cargar los datos del dashboard')
    }
    if (la.status === 'fulfilled') { setRecommendations(la.value.items); setRecsError(null) }
    else setRecsError('No se pudieron cargar las peticiones y recomendaciones. Se vuelve a intentar sola cada 15 segundos.')
    setLoadingData(false)

    if (Date.now() - versionMirada.current > VERSION_CADA_MS) {
      versionMirada.current = Date.now()
      getVersionInfo().then(
        v => setVersionNueva(v.estado === 'hay_novedad' ? (v.ultima.version ?? 'nueva') : null),
        () => { /* sin manifiesto no hay aviso */ })
    }
  }, [loadActiveUploads])

  useEffect(() => { loadData() }, [loadData])

  // Reload the dashboard data whenever any global sync finishes.
  // Recarga en cuanto algo cambia, se esté viendo esta sección o no: los avisos
  // que suben esta marca son raros (una sincronización, una tarea), así que
  // mantenerlas todas al día cuesta poco y a cambio cambiar de pestaña enseña
  // lo actual y no lo actual tras un parpadeo.
  useEffect(() => { if (lastInvalidatedAt) loadData() }, [lastInvalidatedAt, loadData])

  // Red de seguridad del Panel entero (resumen/recomendaciones). Solo
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
  // Cuando termina una tarea programada (la vigilancia de instancias cada 5 min, una sincronización) cambia lo que
  // dice «Necesita atención» y la hora de la última sincronización. Solo escucha: el sondeo de arriba ya es la red.
  useEffect(() => suscribirse('tarea-terminada', () => { void loadData() }), [loadData])

  if (loadingData && !summary) return <LoadingState label="Cargando Panel…" />
  if (!summary) return <ErrorState message={dataError ?? 'No se pudieron cargar los datos del dashboard'} onRetry={loadData} />

  const s = summary
  const reparto = repartirRecomendaciones(recommendations)
  // Las que aún se despiden salen arriba, no se repiten en «Recientes».
  const recientes = ultimasTerminadas(todasLasSubidas, idsDe(despidiendose.map(d => d.job)))
  const avisos = avisosDeAtencion({
    instancias: s.instancias_caidas ?? [],
    fallidas: fallidasRecientes(todasLasSubidas, idsDe(despidiendose.map(d => d.job))),
    versionNueva,
  })

  // «Subir» de una petición: el asistente se abre sobre la fila a la que se refiere (la temporada o el capítulo, no la
  // serie), con su selección y la petición, igual que desde Peticiones; lo que se suba la cubre.
  // «Subir» de un contenido único: el asistente sobre su ficha. «Pedir»: el formulario de petición.
  const abrir = async (item: DashboardRecommendationItem, como: 'peticion' | 'unico' | 'pedir') => {
    if (abriendo.current) return
    abriendo.current = true
    setErrorAccion(null)
    try {
      const libItem = await getLibraryItem(como === 'peticion' ? (item.library_target_id ?? item.id) : item.id)
      if (como === 'pedir') setRequestItem(libItem)
      else {
        setWizardPreselect(como === 'peticion'
          ? { season: item.season_number, episode: item.item_type === 'episode' ? item.episode_number : null }
          : undefined)
        setWizardRequestId(como === 'peticion' ? (item.rec_request_id ?? undefined) : undefined)
        setWizardItem(libItem)
      }
    } catch {
      setErrorAccion('No se pudo abrir ese contenido: puede que ya no esté en la biblioteca tras la última sincronización.')
    } finally {
      abriendo.current = false
    }
  }

  // «Subir seleccionadas»: la fila real de cada una (como «Subir»: la temporada o el capítulo de la petición) y el
  // modal de «Subir por lotes» con su petición y su alcance. Las que ya no están se dicen y el resto sigue.
  const subirSeleccionadas = async () => {
    if (abriendo.current) return
    abriendo.current = true
    setErrorAccion(null)
    try {
      const fichas = new Map<number, Promise<LibraryItemResponse>>()
      const fichaDe = (id: number) => {
        if (!fichas.has(id)) fichas.set(id, getLibraryItem(id))
        return fichas.get(id)!
      }
      const salidasAntes = salidas.current
      // Si lo marcado cambia mientras se piden las fichas, se prepara otra vez con lo de ahora (las ya pedidas no se
      // repiten); salir de la página lo deja.
      let marcadas = seleccionVigente()
      let filas: DashboardRecommendationItem[]
      let resultados: PromiseSettledResult<LibraryItemResponse>[]
      for (;;) {
        filas = [...marcadas.values()]
        resultados = await Promise.allSettled(filas.map(f => fichaDe(f.library_target_id ?? f.id)))
        if (salidas.current !== salidasAntes) return
        const ahora = seleccionVigente()
        if (ahora === marcadas) break
        marcadas = ahora
      }
      const entradas: EntradaLote[] = []
      const perdidas: string[] = []
      resultados.forEach((r, i) => {
        if (r.status === 'fulfilled') entradas.push(entradaDelPanel(filas[i], r.value))
        else perdidas.push(`«${filas[i].content_name}»`)
      })
      if (perdidas.length > 0) {
        setErrorAccion(perdidas.length === 1
          ? `No se pudo abrir ${perdidas[0]}: puede que ya no esté en la biblioteca tras la última sincronización.`
          : `No se pudieron abrir ${perdidas.join(', ')}: puede que ya no estén en la biblioteca tras la última sincronización.`)
      }
      if (entradas.length > 0) setLoteAbierto(entradas)
    } finally {
      abriendo.current = false
    }
  }
  const seleccionCarril: SeleccionCarril = {
    activa: modoSeleccion,
    onAlternarModo: () => {
      if (modoSeleccion) limpiarLote()
      setModoSeleccion(m => !m)
    },
    tiene: marcada, alternar: alternarLote, lleno: loteLleno, total: totalSeleccion,
    onSubir: subirSeleccionadas, onLimpiar: limpiarLote,
  }

  return (
    <div className="panel-pagina">
      {wizardItem && (
        <UploadWizardModal item={wizardItem} preselect={wizardPreselect} requestId={wizardRequestId}
          onClose={() => setWizardItem(null)} onDone={() => { loadData(); loadActiveUploads() }} onNavigate={onNavigate} />
      )}
      {requestItem && (
        <RequestFormModal item={requestItem} onClose={() => setRequestItem(null)} />
      )}
      {loteAbierto && (
        <SubidaPorLotesModal
          entradas={loteAbierto}
          onClose={() => setLoteAbierto(null)}
          onDone={() => { limpiarLote(); setModoSeleccion(false); loadData(); loadActiveUploads() }}
          onNavigate={onNavigate}
        />
      )}

      <div className="page-header panel-cabecera">
        <h1 className="page-title">Panel</h1>
        <CuentaEmu />
        <div className="panel-sincronizar">
          <SyncCard />
          <div className="panel-sincronizacion">
            {lineaSincronizacion(s.last_sync_at, s.next_sync_at).split(' · ').map((parte, i) => (
              <span key={i}>{i > 0 && <span className="solo-lector"> · </span>}{parte}</span>
            ))}
          </div>
        </div>
      </div>

      {errorAccion && <div className="panel-error-accion" role="alert">{errorAccion}</div>}

      {/* Los dos carriles llenan el alto que sobra (la página no se desplaza); cada uno se desplaza por dentro. */}
      <div className="panel-carriles">
        <CarrilListo recomendaciones={reparto} error={recsError} onReintentar={loadData}
          onSubir={item => abrir(item, 'peticion')} onVerPeticion={abrirPeticion} onVerFicha={abrirFicha}
          onSubirUnico={item => abrir(item, 'unico')} onPedir={item => abrir(item, 'pedir')} seleccion={seleccionCarril} />
        <CarrilEnCurso filas={filasDeSubida} recientes={recientes} onOpen={goToUpload} onVerTodas={() => onNavigate?.('uploads')} />
      </div>

      <BandaAtencion avisos={avisos} onVerSubida={goToUpload} onVerSubidas={() => onNavigate?.('uploads')} onVerVersion={() => onNavigate?.('settings')} />

      <Franja resumen={s} />
    </div>
  )
}
