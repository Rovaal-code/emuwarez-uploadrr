// Todo el estado y la lógica del asistente de subida; los pasos (Paso*.tsx)
// solo pintan lo que esto les da.
import { useState, useEffect, useCallback, useRef } from 'react'
import type { EmuSource, EmuProvider, NomenclatureFields, FieldsPreviewResult, TrackRemuxPreview, TrackRemuxOverride, SourceComparison } from '../../api/nomenclature'
import {
  getEmuSources,
  getEmuProviders,
  getNomenclatureFields,
  previewNomenclatureFields,
  saveNomenclatureFields,
  previewTrackRemux,
  applyTrackRemux,
} from '../../api/nomenclature'
import { queueUpload, getExistingJobForItem, runUploadChecks } from '../../api/uploads'
import { nuevoLoteId } from '../../utils/lote'
import { getLibrary, getMediaInfoReport, suggestProvider } from '../../api/library'
import type { MediaInfoReport } from '../../api/library'
import {
  previewSeasonPack, getSeasonPlanProgress, cancelSeasonPackPreview, previewSeasonPackFields, getSeasonPackAudio,
  type SeasonPlanProgress,
} from '../../api/seasonPack'
import type { LibraryItemResponse, SeasonPackPlanResponse, UploadJob } from '../../types/api'
import { isSeasonReady, seasonNotReadyReason, episodeNotReadyReason, listDisplayTitle } from '../../utils/libraryItem'
import { ACTIVE_JOB_STATUSES } from '../../utils/uploadStatus'
import { seguirProgreso } from '../../api/eventos'
import { fetchSettings } from '../../api/settings'
import { ajustesDeTemporada, proveedorParaServidor, type ProveedoresElegidos } from '../../utils/origenProveedor'
import {
  SIN_SELECCION, seleccionUnica, seleccionTemporadas, seleccionCapitulos,
  colaTemporadas, colaCapitulos, esTanda, mismaSeleccion, conObjetivo,
  cacheCubre, conAjustes, peticionCubre, type Seleccion, type Ajustes,
} from '../../utils/seleccionSubida'
import {
  SIN_IDIOMAS, conIdioma, idiomasDelServidor, idiomasParaServidor, type IdiomasPorPosicion,
} from '../../utils/idiomasPack'
import { avisoSourceVisible } from '../../utils/avisoSource'
import { PROVIDER_SOURCES } from './constantes'
import { mergeRemuxTracks } from './RemuxTable'
import { useComprobaciones, useComprobacionesTanda } from './useComprobaciones'
import { useDetallesTemporada } from './useDetallesTemporada'

export interface PropsAsistente {
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
}

export function useAsistente({ item, onClose: onCloseProp, onDone, onNavigate, preselect, requestId }: PropsAsistente) {
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
  // Proveedor elegido A MANO por temporada (campo Proveedor o selector del
  // conflicto). Va aparte de ajustesPorId, que guarda también el detectado:
  // solo este viaja como provider_override (ver ajustesDeTemporada).
  const [proveedorElegido, setProveedorElegido] = useState<ProveedoresElegidos>(new Map())
  const elegirProveedor = (id: number, valor: string | null) =>
    setProveedorElegido(prev => new Map(prev).set(id, valor))
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
  // El ajuste de pistas de Configuración: el Resumen lo dice en un pack y en una tanda, que no cargan las pistas.
  const [modoPistasAjuste, setModoPistasAjuste] = useState<string | undefined>()
  useEffect(() => {
    fetchSettings().then(s => {
      setGruposDeSubida(s.upload_tags ?? [])
      setModoPistasAjuste(s.remux_track_mode)
    }).catch(() => { /* quedan los de siempre */ })
  }, [])
  const opcionesTag = Array.from(new Set([fields.tag, initialTag, ...(gruposDeSubida.length ? gruposDeSubida : ['EMUWAREZ'])].filter(Boolean))) as string[]
  const [titleWarning, setTitleWarning] = useState<string | null>(null)
  const [titleOptions, setTitleOptions] = useState<{ value: string; kind: string; label: string }[]>([])
  const [sourceWarning, setSourceWarning] = useState<string | null>(null)
  const [audioWarning, setAudioWarning] = useState<string | null>(null)
  // MediaInfo apunta a otro source que el nombre o Radarr/Sonarr (lo redacta el servidor).
  const [sourceMismatch, setSourceMismatch] = useState<string | null>(null)
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
  // Para elegirIdioma: lo último elegido, y qué respuesta es la de la última elección.
  const edicionesActuales = useRef(remuxEdits)
  edicionesActuales.current = remuxEdits
  const versionIdioma = useRef(0)
  // Sube cada vez que cambian los datos del pack (idioma elegido, otro objetivo): una carga de nombres
  // o de pistas por capítulo pedida antes de eso llega con los datos viejos y no se aplica.
  const versionDatosPack = useRef(0)
  // Mientras se recalcula el nombre con el idioma elegido, Continuar y Subir esperan: si no, se
  // guardaría el nombre con el audio de antes y el remux aplicaría el idioma nuevo.
  const [recalculandoIdioma, setRecalculandoIdioma] = useState(false)
  // Cambiar de elemento invalida las respuestas pendientes del anterior, aunque se vuelva a él.
  // Los idiomas con los que el nombre se recalculó bien por última vez, por pista. Si un recálculo
  // falla, TODAS las pistas vuelven a esto: no solo la última elegida.
  const idiomasConfirmados = useRef<Record<number, string | undefined>>({})
  // Pack: el idioma elegido para las pistas de audio sin idioma, por temporada y
  // por posición. Solo lo CONFIRMADO (el nombre ya se recalculó con ello): es lo
  // que viaja a la cola, así el nombre y el remux del servidor dicen lo mismo.
  const [idiomasPorTemporada, setIdiomasPorTemporada] = useState<ReadonlyMap<number, IdiomasPorPosicion>>(new Map())
  // Lo elegido mientras se recalcula; null cuando no hay nada en vuelo.
  const [idiomasPackEnVuelo, setIdiomasPackEnVuelo] = useState<IdiomasPorPosicion | null>(null)
  useEffect(() => {
    versionIdioma.current++
    versionDatosPack.current++
    setRecalculandoIdioma(false)
    idiomasConfirmados.current = {}
    setIdiomasPackEnVuelo(null)
  }, [targetId])
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

  // Step 1 — automatic TMDB provider detection for WEB-DL with no provider.
  const [detectingProvider, setDetectingProvider] = useState(false)
  // Which target we've already fired the TMDB detection for — guarantees at
  // most ONE TMDB call per resolved item while this wizard stays open.
  const detectedTargetRef = useRef<number | null>(null)

  // Step 2 — checks + (on upload) apply + preflight + start
  const [preparing, setPreparing] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [uploadMsg, setUploadMsg] = useState<string | null>(null)
  const { checks, checksLoading, checksError, liveChecks, runChecks } = useComprobaciones(targetId, proveedorElegido)

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
    // eslint-disable-next-line react-hooks/exhaustive-deps -- la preselección solo vale al abrir; recargar con ella pisaría lo que elijas
  }, [item.id, isSeries, needsSelection])

  // La tanda activa: capítulos sueltos o temporadas, nunca las dos.
  const batchIsEpisodes = episodeQueue.length > 1
  const batchQueue = batchIsEpisodes ? episodeQueue : seasonQueue
  const batchItemTitle = (id: number) => {
    const row = (batchIsEpisodes ? episodes : seasons).find(x => x.id === id)
    return row ? listDisplayTitle(row) : `#${id}`
  }
  const {
    batchEnvChecks, batchContentChecks, batchChecksLoading, batchChecksIndex, batchViewId, setBatchViewId,
    batchChecksError, repetir: repetirComprobacionesTanda, mergedChecksFor, olvidar: olvidarComprobacionesTanda,
  } = useComprobacionesTanda({ step, batchQueue, batchPhase, proveedorElegido })

  // Un único sitio donde cambia lo que se sube. Si es otra cosa que antes se
  // descarta todo lo que colgaba de lo anterior (ajustes, caché de
  // nomenclatura, comprobaciones de la tanda); si es lo mismo (volver al paso 0
  // y pulsar Continuar) se conserva lo cargado y editado.
  const elegirSeleccion = (nueva: Seleccion) => {
    setSelError(null)
    if (!mismaSeleccion(seleccion, nueva)) {
      setSeleccion(nueva)
      setAjustesPorId(new Map())
      setProveedorElegido(new Map())
      setEpisodeFieldsById(new Map())
      olvidarComprobacionesTanda()
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
    setAudioWarning(resp.audio_warning ?? null)
    setSourceComparison(resp.source_comparison ?? null)
    setSourceMismatch(resp.source_mismatch_warning ?? null)
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
    // eslint-disable-next-line react-hooks/exhaustive-deps -- ajustesPorId a propósito fuera (ver abajo)
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
  // Sube con «Reintentar»: vuelve a generar todos, también los que fallaron.
  const [intentoPrecarga, setIntentoPrecarga] = useState(0)
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
        // Lo que ya se generó bien se queda (ver reintentarNomenclatura).
        const cache = new Map(episodeFieldsById)
        for (let i = 0; i < episodeQueue.length; i++) {
          if (!alive) return
          if (cache.has(episodeQueue[i])) continue
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
      } catch (e: unknown) {
        if (alive) setError(e instanceof Error ? e.message : 'Error cargando la nomenclatura')
      } finally {
        if (alive) setEpisodePrepping(false)
      }
    }
    run()
    return () => { alive = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- se genera al entrar en el paso o cambiar la tanda, no con cada ajuste
  }, [step, targetIsSeason, episodeQueue, intentoPrecarga])

  // «Reintentar» del paso 1. Con varios capítulos, loadFields solo traería el que se ve: se repite la
  // precarga, sin los que fallaron, para que no quede guardado su fallo. Los buenos no se vuelven a pedir:
  // un fallo nuevo en uno de ellos lo dejaría bloqueado y sin sus ediciones.
  const reintentarNomenclatura = () => {
    if (episodeQueue.length <= 1) { void loadFields(); return }
    setEpisodeFieldsById(prev => new Map([...prev].filter(([, r]) => !r.blocked)))
    setIntentoPrecarga(n => n + 1)
  }

  // Switching between already-generated episodes reads the cache — no refetch.
  useEffect(() => {
    if (step !== 1 || targetIsSeason || targetId == null) return
    if (episodeQueue.length <= 1 || episodePrepping) return
    const cached = episodeFieldsById.get(targetId)
    if (cached) applyFieldsResponse(cached, ajustesPorId.get(targetId), targetId)
    // eslint-disable-next-line react-hooks/exhaustive-deps -- solo al cambiar de capítulo: lee la caché y los ajustes de ese momento
  }, [targetId, episodePrepping])

  // --- Step 1 (season target): build the pack plan, polling progress while
  // it's in flight (real work per episode — build_nomenclature_proposal()).
  // `proveedor`: el elegido a mano para salir de un plan bloqueado por
  // proveedores distintos; si no, el que ya se eligió para esta temporada.
  const loadSeasonPlan = useCallback(async (proveedor?: string) => {
    if (targetId == null) return
    if (proveedor) elegirProveedor(targetId, proveedor)
    const yaElegido = proveedorElegido.has(targetId)
    const proveedorPedido = proveedor ?? proveedorParaServidor(proveedorElegido, targetId)
    // Lo ya elegido para esta temporada (al volver a ella desde el desplegable).
    const idiomasPedidos = idiomasPorTemporada.get(targetId)
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
        previewSeasonPack(targetId, proveedorPedido, idiomasParaServidor(idiomasPedidos)), getEmuSources(), getEmuProviders(),
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
        // El elegido a mano; si no, el que decide el servidor (nunca el
        // detectado de una visita anterior, que ya no tiene por qué valer).
        provider: proveedor ?? (yaElegido ? proveedorElegido.get(targetId) : plan.provider) ?? undefined,
        video_codec: plan.video_codec ?? undefined,
        dynamic_range: plan.dynamic_range ?? undefined,
        audio_summary: plan.audio_summary ?? undefined,
        subs: plan.subtitle_summary ?? undefined,
        tag: saved?.tag ?? plan.release_tag ?? undefined,
      })
      setInitialTag(saved?.tag || plan.release_tag || 'EMUWAREZ')
      setSourceComparison(plan.source_comparison ?? null)
      setSourceMismatch(plan.source_mismatch_warning ?? null)
      setAudioWarning(null)
      // Lo que el servidor aplicó de verdad: lo que no era una opción válida se cae.
      setIdiomasPorTemporada(prev => new Map(prev).set(targetId, idiomasDelServidor(plan.idiomas_audio)))
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
  }, [targetId, ajustesPorId, proveedorElegido, idiomasPorTemporada, sharedTitle])

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
  // Algo del formulario tocado a mano: un clic fuera o Escape lo perdería todo, así que antes se pregunta.
  const editado = useRef(false)
  const [confirmandoCierre, setConfirmandoCierre] = useState(false)
  const cerrarModal = () => {
    if (ocupado) return
    if (editado.current && batchPhase !== 'done') setConfirmandoCierre(true)
    else onClose()
  }

  useEffect(() => {
    if (step === 1 && cargadoPara.current !== objetivo && targetIsSeason) loadSeasonPlan()
  }, [step, objetivo, targetIsSeason, loadSeasonPlan])

  // Reset all per-target state (both single-file and season) whenever the
  // resolved target changes — a different item means unrelated data.
  useEffect(() => {
    setMiReport(null); setMiError(null); setShowMiCard(false); setMiLoading(false)
    // Otro contenido, otras pistas: las ediciones a mano no se arrastran, que
    // haría que un capítulo heredara los nombres que escribiste para el
    // anterior sin decírtelo.
    setRemuxPreview(null); setRemuxError(null); setRemuxEdits({}); setShowRemuxCard(false); setRemuxLoading(false)
    setSeasonPlan(null); setSeasonPlanError(null)
  }, [targetId])

  const detalles = useDetallesTemporada({
    targetId, targetIsSeason, objetivoActual, versionDatosPack, fields, proveedorElegido, idiomasPorTemporada,
    pistasAbiertas: showRemuxCard,
  })

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
        // Como setField('provider', …, false) fuera de una temporada, sin depender de él: se recrea en cada pintado.
        if (res.suggested) setFields(prev => ({ ...prev, provider: res.suggested }))
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
    editado.current = true
    setRemuxEdits(prev => ({ ...prev, [trackId]: { ...prev[trackId], ...patch } }))
  }

  // Idioma de una pista de audio sin idioma: cuenta para el nombre del release
  // (se pide el audio de nuevo) y para el nombre y la etiqueta de la pista.
  const elegirIdioma = async (trackId: number, code: string) => {
    const id = targetId
    if (id == null) return
    editado.current = true
    setRecalculandoIdioma(true)
    const previas = edicionesActuales.current
    const nuevas = { ...previas, [trackId]: { ...previas[trackId], language: code || undefined } }
    edicionesActuales.current = nuevas
    setRemuxEdits(nuevas)
    // Solo vale la respuesta de la última elección: una anterior que llegue tarde no la pisa.
    const version = ++versionIdioma.current
    const audio = (remuxPreview?.tracks ?? []).filter(t => t.type === 'audio')
    const idiomas: Record<number, string> = {}
    audio.forEach((t, i) => { const c = nuevas[t.id]?.language; if (c) idiomas[i + 1] = c })
    try {
      const [campos, plan] = await Promise.all([
        getNomenclatureFields(id, idiomas),
        applyTrackRemux(id, { dryRun: true, overrides: nuevas }),
      ])
      if (objetivoActual.current !== id || version !== versionIdioma.current) return
      // La vista previa vieja tiene el audio de antes: se quita y «Continuar» (que la exige)
      // espera a la que salga con los campos nuevos.
      setPreview(null)
      setFields(prev => ({ ...prev, audio_summary: campos.fields?.audio_summary }))
      setAudioWarning(campos.audio_warning ?? null)
      setRemuxPreview(plan)
      idiomasConfirmados.current = Object.fromEntries(
        Object.entries(nuevas).map(([pista, ed]) => [Number(pista), ed?.language]))
    } catch {
      // Sin recálculo, el nombre no lleva esos idiomas: todas las pistas vuelven a los del último
      // recálculo bueno (las demás ediciones de la tabla se quedan), para que el remux no aplique
      // un idioma que el nombre no dice. Solo si nadie ha elegido otra cosa después.
      if (objetivoActual.current !== id || version !== versionIdioma.current) return
      const revertidas = { ...edicionesActuales.current }
      for (const pista of Object.keys(revertidas).map(Number)) {
        const ed = { ...revertidas[pista], language: idiomasConfirmados.current[pista] }
        if (ed.language === undefined) delete ed.language
        if (Object.keys(ed).length) revertidas[pista] = ed
        else delete revertidas[pista]
      }
      edicionesActuales.current = revertidas
      setRemuxEdits(revertidas)
      setAudioWarning('No se pudo recalcular el nombre con ese idioma; la pista sigue sin idioma. Vuelve a elegirlo.')
    } finally {
      // Solo la última elección apaga la espera; una anterior que acabe antes no la quita.
      if (version === versionIdioma.current) setRecalculandoIdioma(false)
    }
  }

  // Pack: idioma de una pista de audio sin idioma, para todos los capítulos (una
  // elección por posición). Mismas reglas que elegirIdioma: Continuar espera al
  // recálculo, solo vale la última respuesta, y si falla vuelve a lo último que
  // se recalculó bien. A la cola solo viaja lo confirmado (idiomasPorTemporada).
  const elegirIdiomaPack = async (posicion: number, codigo: string) => {
    const id = targetId
    if (id == null) return
    editado.current = true
    const base = idiomasPackEnVuelo ?? idiomasPorTemporada.get(id) ?? SIN_IDIOMAS
    const nuevas = conIdioma(base, posicion, codigo)
    setIdiomasPackEnVuelo(nuevas)
    setRecalculandoIdioma(true)
    const version = ++versionIdioma.current
    try {
      const r = await getSeasonPackAudio(id, nuevas)
      if (objetivoActual.current !== id || version !== versionIdioma.current) return
      setIdiomasPorTemporada(prev => new Map(prev).set(id, idiomasDelServidor(r.idiomas_audio)))
      setFields(prev => ({ ...prev, audio_summary: r.audio_summary ?? undefined }))
      setSeasonPlan(prev => prev && {
        ...prev, audio_summary: r.audio_summary, custom: r.custom,
        audio_warning: r.audio_warning, pistas_sin_idioma: r.pistas_sin_idioma,
      })
      setAudioWarning(null)
      detalles.olvidarPorIdioma()
    } catch {
      if (objetivoActual.current !== id || version !== versionIdioma.current) return
      setAudioWarning('No se pudo recalcular el nombre con ese idioma; se queda lo que había. Vuelve a elegirlo.')
    } finally {
      // Solo la última elección apaga la espera y suelta lo que estaba en vuelo
      // (si falló, el selector vuelve a lo confirmado).
      if (version === versionIdioma.current) {
        setIdiomasPackEnVuelo(null)
        setRecalculandoIdioma(false)
      }
    }
  }

  // Debounced live preview of the final torrent name + internal title.
  useEffect(() => {
    if (targetIsSeason) return
    if (targetId == null || !Object.keys(fields).length) return
    const t = setTimeout(async () => {
      try { setPreview(await previewNomenclatureFields(targetId, fields, false)) } catch { /* non-blocking */ }
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
          video_codec: fields.video_codec, dynamic_range: fields.dynamic_range,
          audio_summary: fields.audio_summary, subtitle_summary: fields.subs, tag: fields.tag,
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

  const setField = (key: string, value: string | null, deUsuario = true) => {
    if (deUsuario) editado.current = true
    // Título is a property of the SERIES, so it is shared by every item in a
    // multi-episode or multi-season batch: picking it on episode 5 has to show
    // up on episode 1 too, and go up with all of them. Everything else
    // (Source, Proveedor, Tag) belongs to the individual file.
    if (key === 'title') setSharedTitle(value)
    if (targetIsSeason && targetId != null) {
      if (key === 'provider') elegirProveedor(targetId, value)
      if (key === 'source' && !PROVIDER_SOURCES.has(value || '')) elegirProveedor(targetId, null)
    }
    setFields(prev => {
      const updated = { ...prev, [key]: value }
      if (key === 'source' && !PROVIDER_SOURCES.has(value || '')) updated.provider = null
      return updated
    })
  }

  const sourceRequiresProvider = PROVIDER_SOURCES.has(fields.source || '')
  // Se oculta en cuanto Source ya dice lo mismo que MediaInfo.
  const avisoSource = avisoSourceVisible(sourceMismatch, sourceComparison?.from_mediainfo, fields.source)

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
          ? ajustesDeTemporada(
              { source: fields.source, tag: fields.tag, title: fields.title }, proveedorElegido, targetId,
              idiomasPorTemporada.get(targetId))
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
    // Un lote por tanda: Subidas agrupa estas temporadas y deja filtrarlas juntas.
    const loteId = nuevoLoteId()
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
        const checksResult = mergedChecksFor(seasonId) ?? await runUploadChecks(seasonId, undefined, proveedorParaServidor(proveedorElegido, seasonId))
        if (!checksResult.ready) {
          const reason = checksResult.checks.find(c => c.status === 'fail')?.message || 'Alguna comprobación falló'
          results.push({ seasonId, title, status: 'failed', reason })
          continue
        }
        const r = await queueUpload(seasonId, undefined, checksResult, null, ajustesDeTemporada(overridesMap.get(seasonId), proveedorElegido, seasonId, idiomasPorTemporada.get(seasonId)), s && peticionCubre(preselect, s) ? requestId : undefined, loteId)
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
    // Un lote por tanda, como en las temporadas.
    const loteId = nuevoLoteId()
    const results: typeof batchResults = []
    for (let i = 0; i < episodeQueue.length; i++) {
      const episodeId = episodeQueue[i]
      setBatchIndex(i)
      const ep = episodes.find(x => x.id === episodeId)
      const title = ep ? listDisplayTitle(ep) : `Capítulo ${episodeId}`
      try {
        const ov = overridesMap.get(episodeId)
        // Straight from the cache the step-1 pass already built — the save
        // endpoint rebuilds the whole proposal from what it's given rather
        // than merging, so it needs the episode's full field set, not just
        // the overridden bits.
        const current = episodeFieldsById.get(episodeId) ?? (ov ? await getNomenclatureFields(episodeId) : undefined)
        // Sin nomenclatura no hay nombre que subir, aunque sus comprobaciones pasen.
        if (current?.blocked) {
          results.push({ seasonId: episodeId, title, status: 'failed', reason: current.error || 'No se puede generar la nomenclatura.' })
          continue
        }
        if (ov && current) {
          await saveNomenclatureFields(episodeId, {
            ...(current.fields || {}),
            ...(ov.source !== undefined && ov.source !== null ? { source: ov.source } : {}),
            ...(ov.provider !== undefined && ov.provider !== null ? { provider: ov.provider } : {}),
            ...(ov.tag ? { tag: ov.tag } : {}),
            ...(ov.title ? { title: ov.title } : {}),
          })
        }
        // Igual que las temporadas: se reutiliza lo comprobado al entrar en
        // el paso 2 en vez de repetir las 4 de entorno por cada capítulo.
        const checksResult = mergedChecksFor(episodeId) ?? await runUploadChecks(episodeId)
        if (!checksResult.ready) {
          const reason = checksResult.checks.find(c => c.status === 'fail')?.message || 'Alguna comprobación falló'
          results.push({ seasonId: episodeId, title, status: 'failed', reason })
          continue
        }
        const r = await queueUpload(episodeId, undefined, checksResult, null, undefined, ep && peticionCubre(preselect, ep) ? requestId : undefined, loteId)
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

  // Just the single pack torrent name (season level): the live recompute
  // while editing, or the plan's own until then.
  const seasonDisplayTitle = seasonTitlePreview ?? seasonPlan?.season_pack_title

  return {
    item, onDone, onNavigate, onClose, needsSelection, allowMultiSeason, step, setStep, requestId, preselect, modoPistasAjuste,
    seleccion, targetId, targetIsSeason, seasonQueue, episodeQueue,
    // Paso 0
    seasons, episodes, selError, multiSelected, setMultiSelected, seasonUploadMode, setSeasonUploadMode,
    episodeSelected, setEpisodeSelected, confirmMultiSelection, confirmEpisodeSelection, confirmSeasonWhole,
    // Paso 1
    existingJob, existingJobBlocking, cambiarElemento,
    episodePrepping, episodePrepIndex, loading, error, reintentarNomenclatura,
    fields, setField, titleOptions, titleWarning, sources, providers, opcionesTag, detectingProvider,
    sourceRequiresProvider, sourceWarning, avisoSource, audioWarning, preview,
    sourceComparison, setSourceComparison, showSourceCompare, setShowSourceCompare, showEngineDetail, setShowEngineDetail,
    showMiCard, setShowMiCard, miReport, miLoading, miError, runMediaInfo,
    showRemuxCard, setShowRemuxCard, remuxPreview, remuxLoading, remuxError, remuxEdits, runTrackRemux,
    setRemuxEdit, elegirIdioma, recalculandoIdioma,
    seasonPlan, seasonPlanLoading, seasonPlanError, seasonProgress, loadSeasonPlan, seasonDisplayTitle,
    idiomasPackEnVuelo, idiomasPorTemporada, elegirIdiomaPack, detalles,
    goToUpload, preparing,
    // Paso 2
    checks, checksLoading, checksError, liveChecks, runChecks, canUpload, uploading, uploadMsg, doUpload,
    batchQueue, batchIsEpisodes, batchItemTitle, batchPhase, batchIndex, batchResults,
    batchViewId, setBatchViewId, batchEnvChecks, batchContentChecks, batchChecksLoading, batchChecksIndex,
    batchChecksError, repetirComprobacionesTanda, uploadAllSeasons, uploadAllEpisodes,
    // Cerrar
    cerrarModal, confirmandoCierre, setConfirmandoCierre,
  }
}

export type Asistente = ReturnType<typeof useAsistente>
