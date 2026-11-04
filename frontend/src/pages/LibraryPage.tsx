import { useState, useEffect, useCallback, useRef, useTransition, memo } from 'react'
import { getLibrary, TOP_LEVEL_PARENT_FILTER, getLibraryFilterOptions, getLibraryItem, type LibraryFilterOptions } from '../api/library'
import { Tooltip } from '../components/Tooltip'
import { getLocalStatusInfo } from '../utils/status'
import { useSync } from '../context/SyncContext'
import { EmuSyncButton } from '../components/EmuSyncButton'
import { useInstancias } from '../hooks/useInstancias'
import type { LibraryItemResponse, LibraryListResponse } from '../types/api'
import { PosterStatusIcon } from '../components/PosterStatusIcon'
import { ErrorState } from '../components/ErrorState'
import { EmptyState, FilaVacia } from '../components/EmptyState'
import { NomenclatureModal } from '../components/NomenclatureModal'
import { NomenclatureFieldsModal } from '../components/NomenclatureFieldsModal'
import { UploadPreflightModal } from '../components/UploadPreflightModal'
import { UploadWizardModal } from '../components/UploadWizardModal'
import { RequestFormModal } from '../components/RequestFormModal'
import { LibraryTreeRow, type LibraryActionKind } from '../components/LibraryTreeRow'
import { LargePosterCard } from '../components/LargePosterCard'
import { LibraryDetailPage } from '../components/LibraryDetailPage'
import { HeaderFilter } from '../components/HeaderFilter'
import { HeaderSort } from '../components/HeaderSort'
import { FilasVirtuales, RejillaVirtual } from '../components/FilasVirtuales'
import { posterUrl } from '../utils/libraryItem'
import { getDetailIdFromPath, pushDetailPath, closeDetailPath } from '../utils/detailUrl'
import { hayAlgunFiltro, necesitaTodosLosNiveles } from '../utils/filtrosBiblioteca'
import { hayMasQueCargar, textoDeResultados, unirPagina } from '../utils/paginacionBiblioteca'
import { CASTELLANO_OPCIONES, type EstadoCastellano } from '../utils/castellano'
import { useTardanza } from '../hooks/useTardanza'
import { useAlEntrar, useAlSalir } from '../context/SeccionVisible'
import { IconoLibros, IconoTipo } from '../components/Iconos'
import { formatNumero } from '../utils/format'
import { VistasGuardadas } from '../components/VistasGuardadas'
import {
  cargarVistas, conVista, persistirVistas, sinVista, ORDEN_POR_DEFECTO, type FiltrosDeVista, type VistaGuardada,
} from '../utils/vistasBiblioteca'

// Una sola lista vacía: volver a ponerla no cuenta como cambio y no recarga la biblioteca.
const NINGUNO: string[] = []
const LOAD_LIMIT = 20000  // show everything in one container (no pagination); backend caps here

// Spanish display label for each real item_type value the Tipo filter offers
// (only values that actually occur — see filterOptions.types).
const TYPE_LABELS: Record<string, string> = {
  movie: 'Película', series: 'Serie', season: 'Temporada', episode: 'Episodio',
}

const VIEW_MODE_STORAGE_KEY = 'emuwarez_uploadrr_library_view'

type ViewMode = 'grid' | 'grid-lg' | 'list'

function loadViewMode(): ViewMode {
  const stored = localStorage.getItem(VIEW_MODE_STORAGE_KEY)
  return stored === 'list' || stored === 'grid-lg' ? stored : 'grid'
}

// First N cards are above the fold on virtually any viewport at this tile
// size — eager + high fetch priority so they're already loaded by the time
// the grid paints, instead of visibly popping in as the browser's own
// lazy-load IntersectionObserver catches up. Everything past that stays
// "loading=lazy" as before (deferred until scrolled near).
const GRID_PRIORITY_COUNT = 30
// List rows are much shorter than poster tiles, so more of them fit above
// the fold — same rationale, higher count.
const LIST_PRIORITY_COUNT = 40
// Lo que mide una fila de la lista antes de pintarla (FilasVirtuales la
// corrige con la primera que mide de verdad).
const LIST_ROW_HEIGHT = 50
const LIST_COLUMNS = 7
const claveDeItem = (it: LibraryItemResponse) => it.id

// Memoized: a plain inline onClick={() => onSelect(item)} arrow would be a
// new function identity every render, defeating memo — so this takes a
// stable onSelect (openDetail, itself wrapping setSelected) and calls it with `item` internally.
const PosterCard = memo(function PosterCard({ item, onSelect, priority }: { item: LibraryItemResponse; onSelect: (item: LibraryItemResponse) => void; priority?: boolean }) {
  return (
    <div
      className="clickable bib-tarjeta"
      onClick={() => onSelect(item)}
    >
      <div className="bib-tarjeta-marco">
        {item.poster_url ? (
          <img
            src={posterUrl(item.poster_url, 'w342')}
            alt={item.title}
            loading={priority ? 'eager' : 'lazy'}
            fetchPriority={priority ? 'high' : 'auto'}
            className="bib-tarjeta-img"
            onError={e => { (e.currentTarget as HTMLImageElement).style.display = 'none' }}
          />
        ) : (
          <div className="bib-tarjeta-sin-img">
            <IconoTipo serie={item.item_type === 'series' || item.item_type === 'episode'} />
          </div>
        )}
        <div className="bib-tarjeta-estado">
          <PosterStatusIcon status={item.local_status} />
        </div>
      </div>
    </div>
  )
})

// Ancho de cada barra, variado a propósito (no todas iguales) para que la
// fila lea como texto esperando a llegar y no como un bloque gris plano.
const SkeletonBar = ({ width }: { width: number | string }) => (
  // El ancho es un valor calculado por fila: se queda en línea.
  <span className="skeleton-bar" style={{ width }} />
)

// Mientras carga la primera página de Biblioteca (3.6): solo pasa una vez
// por sesión (ver el comentario de `data`/`loading` más abajo — volver a la
// pestaña reutiliza lo último cargado), pero con 51k elementos tarda de
// sobra para que un spinner suelto se sienta como que la app no ha hecho
// nada. La forma de las filas/tarjetas es la real, para que no haya salto
// cuando lleguen los datos de verdad.
function LibraryTableSkeleton({ rows = 14 }: { rows?: number }) {
  return (
    <>
      {Array.from({ length: rows }, (_, i) => (
        <tr key={i} aria-hidden="true">
          <td>
            <div className="bib-esq-titulo">
              <div className="poster-thumb skeleton-bar bib-esq-poster" />
              <SkeletonBar width={120 + (i % 3) * 40} />
            </div>
          </td>
          {Array.from({ length: LIST_COLUMNS - 1 }, (_, c) => (
            <td key={c}><SkeletonBar width={40 + ((i + c) % 3) * 16} /></td>
          ))}
        </tr>
      ))}
    </>
  )
}

function LibraryGridSkeleton({ large }: { large?: boolean }) {
  return (
    <div className={`bib-esq-rejilla${large ? ' bib-esq-grande' : ''}`}>
      {Array.from({ length: large ? 12 : 24 }, (_, i) => (
        <div key={i} aria-hidden="true" className="bib-esq-tarjeta">
          <div className="skeleton-bar bib-esq-tarjeta-img" />
        </div>
      ))}
    </div>
  )
}

export function LibraryPage({ onNavigate }: { onNavigate?: (page: string) => void } = {}) {
  // Volver a Biblioteca no vuelve a enseñar "Cargando…": se parte de lo último
  // que se cargó SIN FILTROS y se refresca por detrás. Los filtros sí se
  // reinician, y por eso solo se guarda la vista sin filtrar: reutilizar un
  // resultado filtrado bajo unos filtros vacíos parecería que faltan cosas.
  const [data, setData] = useState<LibraryListResponse | null>(null)
  const [loading, setLoading] = useState(true)
  // Applying a column filter fetches every level (up to LOAD_LIMIT)
  // and re-renders a large list — a synchronous commit that briefly froze the
  // UI after `loading` had already flipped back to false. Committing the data
  // inside a transition keeps `isPending`
  // true through that heavy render so we can keep showing "Cargando…".
  const [isPending, startTransition] = useTransition()
  const [error, setError] = useState<string | null>(null)
  const [selected, setSelected] = useState<LibraryItemResponse | null>(null)

  // Keeps /library/:id in sync with whichever item's detail page is open —
  // works uniformly for a movie, series, season, or episode row, since they
  // all share the same library_items.id regardless of item_type.
  const openDetail = useCallback((item: LibraryItemResponse) => {
    pushDetailPath('library', item.id)
    setSelected(item)
    // A row clicked straight from the list/grid never carries display_title
    // (only the single-item GET computes the canonical "Serie (Año)"-style
    // title, to avoid a parent-walk query per list row) — refresh once so
    // the dedicated page ends up with the full title instead of the raw one.
    getLibraryItem(item.id).then(full => {
      setSelected(prev => (prev && prev.id === item.id ? full : prev))
    }).catch(() => {})
  }, [])
  const closeDetail = useCallback(() => {
    closeDetailPath('library')
    setSelected(null)
  }, [])
  // La petición de la ficha, en su ficha de Peticiones: por el mismo camino que
  // la campana y el Panel (Peticiones lo recoge al entrar, useAlEntrar).
  const openRequest = useCallback((requestId: number) => {
    try { sessionStorage.setItem('emuwarez_open_request', String(requestId)) } catch { /* ignore */ }
    onNavigate?.('requests')
  }, [onNavigate])
  // Only opened from the "Pósters grandes" view — the small modal (grid/list) stays as-is.
  const [nomenclatureItem, setNomenclatureItem] = useState<LibraryItemResponse | null>(null)
  const [fieldsItem, setFieldsItem] = useState<LibraryItemResponse | null>(null)
  const [uploadItem, setUploadItem] = useState<LibraryItemResponse | null>(null)
  const [wizardItem, setWizardItem] = useState<LibraryItemResponse | null>(null)
  const [requestItem, setRequestItem] = useState<LibraryItemResponse | null>(null)
  const [viewMode, setViewMode] = useState<ViewMode>(loadViewMode)

  // Movie/episode leaf rows: open the existing single-item modals as before.
  // Season/Series rows: 'upload' opens the same unified wizard too — it asks
  // which season/episode (or the whole season) to target, and handles a
  // whole-season pack internally (server-side).
  // Stable reference (empty deps: only calls setState setters, which React
  // itself guarantees are stable) — LibraryTreeRow is memoized, and a new
  // function identity on every render here would defeat that memoization
  // for every row's onAction prop.
  const handleTreeAction = useCallback((kind: LibraryActionKind, item: LibraryItemResponse) => {
    if (kind === 'nomenclature') { setNomenclatureItem(item); return }
    if (kind === 'fields') { setFieldsItem(item); return }
    if (kind === 'request') { setRequestItem(item); return }
    // 'upload' abre el asistente. Él decide qué preguntar según el tipo: una
    // serie elige temporadas, una temporada elige entre pack y capítulos
    // sueltos, y una película o un capítulo entran directos.
    setWizardItem(item)
  }, [])

  useEffect(() => { localStorage.setItem(VIEW_MODE_STORAGE_KEY, viewMode) }, [viewMode])

  const instances = useInstancias()

  // Excel-style column filters: every option list below reflects values that
  // actually occur somewhere in the library (all levels — a value that only
  // exists in a mixed series' episodes wouldn't appear in the top-level list
  // otherwise), never an invented fixed list (e.g. LocalStatus has ~10
  // possible values; only offer the ones some item actually has).
  const [filterOptions, setFilterOptions] = useState<LibraryFilterOptions | null>(null)
  const providerOptions = filterOptions?.providers ?? []
  const qualityOptions = filterOptions?.qualities ?? []
  const sourceOptions = filterOptions?.sources ?? []
  const groupOptions = filterOptions?.release_groups ?? []

  // Diagnostic actions — relocated here from the removed standalone
  // Library + eMuwarez syncs are global (shared with the Dashboard/Peticiones
  // and the progress banner), so a running sync stays visible and its button
  // stays disabled on every tab.
  const { libSyncing, startLibrarySync, lastInvalidatedAt, isAnySyncing } = useSync()
  // Una sincronización puede traer valores nuevos (un grupo, un proveedor): se vuelven a pedir.
  useEffect(() => {
    let alive = true
    getLibraryFilterOptions().then(o => { if (alive) setFilterOptions(o) }).catch(() => {})
    return () => { alive = false }
  }, [lastInvalidatedAt])

  // Filters
  const [search, setSearch] = useState('')
  // The input itself stays bound to `search` for instant feedback while
  // typing; `load()` only reacts to `debouncedSearch` — with up to
  // LOAD_LIMIT (20000) rows fetched and re-rendered per search, firing that
  // on every keystroke made typing visibly stutter (worst right after the
  // initial load, when the browser is still busiest).
  const [debouncedSearch, setDebouncedSearch] = useState('')
  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(search), 350)
    return () => clearTimeout(t)
  }, [search])
  const [filterType, setFilterType] = useState<string[]>(NINGUNO)
  const [filterStatus, setFilterStatus] = useState<string[]>(NINGUNO)
  const [filterInstanceId, setFilterInstanceId] = useState<string[]>(NINGUNO)
  const [filterRequest, setFilterRequest] = useState<string[]>(NINGUNO)
  // Las columnas admiten varios valores: lista vacía = sin filtro.
  const [searchProvider, setSearchProvider] = useState<string[]>(NINGUNO)
  const [searchQuality, setSearchQuality] = useState<string[]>(NINGUNO)
  const [searchSource, setSearchSource] = useState<string[]>(NINGUNO)
  const [searchGroup, setSearchGroup] = useState<string[]>(NINGUNO)
  const [filterEmu, setFilterEmu] = useState<string[]>(NINGUNO)
  const [filterAporte, setFilterAporte] = useState('')
  const [filterSpanish, setFilterSpanish] = useState<string[]>(NINGUNO)
  const [sortBy, setSortBy] = useState(ORDEN_POR_DEFECTO)
  const [offset, setOffset] = useState(0)
  const [vistas, setVistas] = useState<VistaGuardada[]>(cargarVistas)

  // Con cualquier filtro puesto se pide la biblioteca en plano. Ver
  // utils/filtrosBiblioteca: recortar a la raíz mientras filtras dejaba la
  // tabla vacía para valores que el propio desplegable ofrecía.
  const filtros = {
    search: debouncedSearch, filterType, filterStatus, filterInstanceId,
    filterRequest, filterSpanish, searchProvider, searchQuality, searchSource, searchGroup,
    filterEmu, filterAporte,
  }
  const flatFilter = necesitaTodosLosNiveles(filtros)
  const filtrando = hayAlgunFiltro(filtros)

  // Lo que guarda una vista: la búsqueda tal como está escrita, los filtros y el orden.
  const filtrosDeAhora: FiltrosDeVista = {
    search, type: filterType, status: filterStatus, instanceId: filterInstanceId, request: filterRequest,
    provider: searchProvider, quality: searchQuality, source: searchSource, group: searchGroup,
    emu: filterEmu, aporte: filterAporte, spanish: filterSpanish, sort: sortBy,
  }
  function aplicarVista({ filtros: f }: VistaGuardada) {
    setSearch(f.search); setDebouncedSearch(f.search)
    setFilterType(f.type); setFilterStatus(f.status); setFilterInstanceId(f.instanceId); setFilterRequest(f.request)
    setSearchProvider(f.provider); setSearchQuality(f.quality); setSearchSource(f.source); setSearchGroup(f.group)
    setFilterEmu(f.emu); setFilterAporte(f.aporte); setFilterSpanish(f.spanish); setSortBy(f.sort)
    setOffset(0)
  }
  function guardarVista(nombre: string) {
    const sig = conVista(vistas, nombre, filtrosDeAhora, Date.now().toString(36))
    setVistas(sig)
    persistirVistas(sig)
  }
  function quitarVista(vista: VistaGuardada) {
    const sig = sinVista(vistas, vista.id)
    setVistas(sig)
    persistirVistas(sig)
  }

  // Todos los filtros van al servidor. Proveedor, Resolución, Source, Grupo,
  // eMuwarez y Aportes se filtraban aquí sobre lo cargado, que con más de
  // LOAD_LIMIT filas no era la biblioteca entera; el servidor ya devuelve el
  // nivel más alto que cumple (la serie, o solo sus temporadas que cumplen).
  // Solo cuenta la última petición: una vieja más lenta no pisa la nueva.
  const ultimaCarga = useRef(0)
  // Un aviso de "recarga" que llegó con una carga en marcha: se atiende al acabar.
  const recargaPendiente = useRef(false)
  const cargando = useRef(false)
  const consulta = useCallback((desde: number) => getLibrary({
    search: debouncedSearch || undefined,
    type: filterType,
    status: filterStatus,
    instance_id: filterInstanceId.map(Number),
    request_status: filterRequest,
    spanish: filterSpanish as EstadoCastellano[],
    provider: searchProvider,
    resolution: searchQuality,
    source: searchSource,
    release_group: searchGroup,
    emu: filterEmu,
    aporte: filterAporte || undefined,
    sort: sortBy,
    parent_id: flatFilter ? undefined : TOP_LEVEL_PARENT_FILTER,
    limit: LOAD_LIMIT,
    offset: desde,
  }), [debouncedSearch, filterType, filterStatus, filterInstanceId, filterRequest, flatFilter, filterSpanish,
    searchProvider, searchQuality, searchSource, searchGroup, filterEmu, filterAporte, sortBy])
  const [cargandoMas, setCargandoMas] = useState(false)
  const [fallaMas, setFallaMas] = useState(false)
  const load = useCallback(async () => {
    const esta = ++ultimaCarga.current
    recargaPendiente.current = false
    cargando.current = true
    setLoading(true)
    setError(null)
    setFallaMas(false)
    // Una tanda de "Cargar más" en marcha ya no vale: su respuesta se tira y el botón no espera por ella.
    setCargandoMas(false)
    try {
      const result = await consulta(offset)
      if (esta === ultimaCarga.current) startTransition(() => setData(result))
    } catch {
      if (esta === ultimaCarga.current) setError('Error al cargar la biblioteca')
    } finally {
      if (esta === ultimaCarga.current) {
        cargando.current = false
        setLoading(false)
        if (recargaPendiente.current) load()
      }
    }
  }, [consulta, offset])

  useEffect(() => { load() }, [load])

  // La siguiente tanda cuando hay más filas que las 20.000 que se piden de una vez. Si mientras llega se
  // recarga o cambia un filtro (`ultimaCarga` avanza), su respuesta ya no vale y se tira.
  const cargarMas = useCallback(async () => {
    // Con la primera página de otro filtro en camino, el desplazamiento saldría de los resultados viejos.
    if (cargando.current) return
    const carga = ultimaCarga.current
    setCargandoMas(true)
    setFallaMas(false)
    try {
      const result = await consulta((data?.items.length ?? 0) + offset)
      if (carga === ultimaCarga.current) {
        const antes = data?.items ?? []
        const unidas = unirPagina(antes, result.items)
        // Si el orden cambió (una sincronización) la tanda puede traer solo filas ya mostradas: sin crecer,
        // "Cargar más" pediría lo mismo para siempre. Se rehace la primera página.
        if (result.items.length > 0 && unidas.length === antes.length) load()
        else startTransition(() => setData(prev => prev && { ...result, items: unirPagina(prev.items, result.items) }))
      }
    } catch {
      if (carga === ultimaCarga.current) setFallaMas(true)
    } finally {
      // Solo la tanda vigente apaga el indicador: una vieja no pisa el de una carga nueva.
      if (carga === ultimaCarga.current) setCargandoMas(false)
    }
  }, [consulta, data, offset, load])

  // "Ver en Biblioteca" desde una petición, desde una subida, desde el Panel o
  // desde la campana: el id viene apuntado en sessionStorage y se recoge aquí.
  //
  // Al ENTRAR y no al montar. Antes era un efecto de montaje y bastaba, porque
  // la sección se levantaba de cero cada vez que entrabas; ahora se monta una
  // sola vez —y encima al arrancar la aplicación, cuando todavía no hay nada
  // apuntado—, así que no volvía a mirar nunca: la aplicación cambiaba a
  // Biblioteca y te dejaba donde lo hubieras dejado, sin abrir nada.
  useAlEntrar(() => {
    let pending: string | null = null
    try { pending = sessionStorage.getItem('emuwarez_open_library_item') } catch { /* ignore */ }
    if (!pending) return
    try { sessionStorage.removeItem('emuwarez_open_library_item') } catch { /* ignore */ }
    getLibraryItem(Number(pending)).then(openDetail).catch(() => { /* ignore */ })
  })

  function quitarFiltros() {
    setSearch(''); setDebouncedSearch('')
    setFilterType(NINGUNO); setFilterStatus(NINGUNO); setFilterInstanceId(NINGUNO); setFilterRequest(NINGUNO)
    setSearchProvider(NINGUNO); setSearchQuality(NINGUNO); setSearchSource(NINGUNO); setSearchGroup(NINGUNO)
    setFilterEmu(NINGUNO); setFilterAporte(''); setFilterSpanish(NINGUNO)
    setOffset(0)
  }

  // Al SALIR, la sección vuelve a su estado de partida: la tabla, sin filtros
  // y con el orden por defecto. Si no, volver te dejaba en la ficha que
  // abriste hace media hora o con un filtro que ya no recuerdas haber puesto.
  //
  // Al salir y NO al entrar: reiniciando al entrar se borraría justo el
  // contenido al que te acaban de mandar (el useAlEntrar de arriba).
  useAlSalir(() => {
    setSelected(null)
    closeDetailPath('library')
    quitarFiltros()
    setSortBy(ORDEN_POR_DEFECTO)
  })

  // Deep link: /library/:id (bookmark, reload, or a link shared elsewhere) —
  // resolve the id straight from the URL, same as the sessionStorage hand-off
  // above. On mount this only OPENS (never force-closes on a bare /library) —
  // the sessionStorage/CustomEvent hand-offs above land on a bare /library
  // path themselves and may resolve on the very same tick, so unconditionally
  // closing here on mount would win the race and wipe out whatever they just
  // opened. Closing on a bare path is left entirely to real back/forward
  // navigation (popstate never fires from our own pushDetailPath/
  // closeDetailPath calls, only from the user actually using the browser's
  // back/forward buttons), which happens well after mount.
  useEffect(() => {
    const id = getDetailIdFromPath('library')
    if (id != null) getLibraryItem(id).then(setSelected).catch(() => { /* ignore */ })

    const onPopState = () => {
      const popId = getDetailIdFromPath('library')
      if (popId == null) { setSelected(null); return }
      getLibraryItem(popId).then(setSelected).catch(() => { /* ignore */ })
    }
    window.addEventListener('popstate', onPopState)
    return () => window.removeEventListener('popstate', onPopState)
  }, [])

  // Opened from the "Nuevo contenido único" notification: pre-apply the
  // Aportes = Aporta filter so the list lands already showing exactly what
  // that notification was about, instead of the unfiltered list.
  useEffect(() => {
    let pending: string | null = null
    try { pending = sessionStorage.getItem('emuwarez_library_filter_aporte') } catch { /* ignore */ }
    if (!pending) return
    try { sessionStorage.removeItem('emuwarez_library_filter_aporte') } catch { /* ignore */ }
    setFilterAporte(pending)
    setOffset(0)
  }, [])

  // Same two hand-offs as above, but live — the sessionStorage reads only
  // fire once, on mount, so clicking a notification while Biblioteca is
  // ALREADY the open page (no remount happens) would otherwise do nothing.
  // NotificationBell dispatches these same-tick, in addition to stashing
  // sessionStorage for the cross-page case.
  useEffect(() => {
    const onOpenItem = (e: Event) => {
      const id = (e as CustomEvent<number>).detail
      if (id == null) return
      try { sessionStorage.removeItem('emuwarez_open_library_item') } catch { /* ignore */ }
      getLibraryItem(id).then(openDetail).catch(() => { /* ignore */ })
    }
    const onFilterAporte = (e: Event) => {
      const value = (e as CustomEvent<string>).detail
      if (!value) return
      try { sessionStorage.removeItem('emuwarez_library_filter_aporte') } catch { /* ignore */ }
      setFilterAporte(value)
      setOffset(0)
    }
    window.addEventListener('emuwarez:open-library-item', onOpenItem)
    window.addEventListener('emuwarez:library-filter-aporte', onFilterAporte)
    return () => {
      window.removeEventListener('emuwarez:open-library-item', onOpenItem)
      window.removeEventListener('emuwarez:library-filter-aporte', onFilterAporte)
    }
  }, [openDetail])

  // Refresh the list whenever any global sync finishes (library or eMuwarez).
  // Deliberately NOT depending on `load`: it's a useCallback keyed on every
  // filter, so including it made each filter change fire this reload on top of
  // the one the [load] effect above already does — two full fetches back to
  // back, which is what made the table flash "cargando" twice in a row. Same
  // shape RequestsPage uses.
  // Recarga en cuanto algo cambia si esta sección se ve; si está oculta, SeccionVisible
  // no le pasa la marca hasta que se vuelva a ver (recargar Biblioteca cada vez que
  // volvías a la pestaña del navegador pedía 20.000 filas para nada).
  // Con una carga en marcha no se relanza: volver a la pestaña del navegador
  // la tiraba y empezaba otra, y con un filtro lento no acababa nunca. Se
  // apunta y se repide una vez al acabar, por si fue una sincronización.
  useEffect(() => {
    if (!lastInvalidatedAt) return
    if (cargando.current) recargaPendiente.current = true
    else load()
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `load` cambia con cada filtro y recargaría dos veces (ver arriba)
  }, [lastInvalidatedAt])

  // Enter aplica la búsqueda ya, sin esperar al retardo. El cambio de `debouncedSearch` es lo que recarga: llamar
  // a load() aquí lo hacía con la búsqueda de antes y luego otra vez con la nueva.
  function applyFilters() {
    setOffset(0)
    setDebouncedSearch(search)
  }

  const items = data?.items ?? []
  const archivos = data?.archivos ?? 0
  const hayMas = hayMasQueCargar(items.length, data?.total ?? 0)
  const resumenResultados = textoDeResultados(items.length, data?.total ?? 0, filtrando)

  // La tabla solo se apaga si la espera se nota. Filtrar u ordenar tarda unos
  // milisegundos, y apagarla en cuanto sale la petición se veía como un
  // parpadeo: molestaba más que la propia espera y daba sensación de lentitud
  // justo cuando va rápido. Con una biblioteca enorme sí tarda, y entonces el
  // apagado aparece y dice que el clic ha hecho algo.
  const tarda = useTardanza((loading || isPending) && !!data)
  const refrescando = tarda ? ' bib-refrescando' : ''

  // La lista solo pinta lo que se ve (FilasVirtuales). Las series desplegadas
  // se pintan siempre, para no perder lo que tienen abierto al salir de vista.
  const listaRef = useRef<HTMLDivElement>(null)
  // Los pósters, igual: solo las filas de tarjetas que se ven (RejillaVirtual).
  const rejillaRef = useRef<HTMLDivElement>(null)
  const cabeceraRef = useRef<HTMLTableSectionElement>(null)
  const [desplegadas, setDesplegadas] = useState<ReadonlySet<number>>(() => new Set())
  const alDesplegar = useCallback((id: number, abierta: boolean) => {
    setDesplegadas(prev => {
      if (prev.has(id) === abierta) return prev
      const sig = new Set(prev)
      if (abierta) sig.add(id); else sig.delete(id)
      return sig
    })
  }, [])
  const pintarFila = useCallback((item: LibraryItemResponse, i: number) => (
    <LibraryTreeRow
      item={item}
      depth={0}
      instances={instances}
      onSelect={openDetail}
      onAction={handleTreeAction}
      onReload={load}
      priority={i < LIST_PRIORITY_COUNT}
      onExpandedChange={alDesplegar}
    />
  ), [instances, openDetail, handleTreeAction, load, alDesplegar])

  // Modals/overlays, shared by the list view and the detail page so an action
  // triggered from the detail page (Subir/Petición) shows its window without
  // having to go back to the library first.
  const modals = (
    <>
      {nomenclatureItem && (
        <NomenclatureModal itemId={nomenclatureItem.id} itemTitle={nomenclatureItem.title} onClose={() => setNomenclatureItem(null)} />
      )}
      {fieldsItem && (
        <NomenclatureFieldsModal itemId={fieldsItem.id} itemTitle={fieldsItem.title} onClose={() => setFieldsItem(null)} onSaved={load} />
      )}
      {uploadItem && (
        <UploadPreflightModal itemId={uploadItem.id} itemTitle={uploadItem.title} onClose={() => setUploadItem(null)} />
      )}
      {wizardItem && (
        <UploadWizardModal
          item={wizardItem}
          onClose={() => setWizardItem(null)}
          onDone={() => { load() }}
          onNavigate={onNavigate}
        />
      )}
      {requestItem && (
        <RequestFormModal item={requestItem} onClose={() => setRequestItem(null)} />
      )}
    </>
  )

  // Dedicated detail page (Radarr/Sonarr-style) — shown in place of the list
  // when an item is selected, instead of a modal/card.
  if (selected) {
    return (
      <div className="bib-pagina">
        <LibraryDetailPage
          item={selected}
          instances={instances}
          onBack={closeDetail}
          onSelect={openDetail}
          onAction={handleTreeAction}
          onOpenRequest={onNavigate ? openRequest : undefined}
        />
        {modals}
      </div>
    )
  }

  // Se calcula una vez y se usa en dos sitios (la tabla real y su esqueleto
  // de carga, más abajo) para que no haya dos copias de las columnas que
  // acaben diciendo cosas distintas.
  const tableHeadRow = (
    <tr>
      {/* Tipo, origen, resolución, proveedor, source y grupo ya no son columnas: van en la línea bajo el título, y sus filtros aquí. */}
      <th className="bib-col-titulo">
        <div className="bib-cab-titulo">
          <span className="bib-cab-nombre">Título</span>
          <HeaderFilter label="Tipo" value={filterType} onChange={v => { setFilterType(v); setOffset(0) }} options={[
            { value: '', label: 'Todos' }, ...(filterOptions?.types ?? []).map(t => ({ value: t, label: TYPE_LABELS[t] ?? t })),
          ]} />
          <HeaderFilter label="Origen" value={filterInstanceId} onChange={v => { setFilterInstanceId(v); setOffset(0) }} options={[
            { value: '', label: 'Todos' },
            ...(filterOptions?.instances ?? []).map(inst => ({ value: String(inst.id), label: `${inst.type === 'radarr' ? 'Radarr' : 'Sonarr'}: ${inst.name.length > 15 ? inst.name.slice(0, 15) + '…' : inst.name}` })),
          ]} />
          <HeaderFilter label="Resolución" value={searchQuality} onChange={setSearchQuality} ocultable options={[
            { value: '', label: 'Todas' }, ...qualityOptions.map(q => ({ value: q, label: q })),
          ]} />
          <HeaderFilter label="Proveedor" value={searchProvider} onChange={setSearchProvider} ocultable options={[
            { value: '', label: 'Todos' }, ...providerOptions.map(p => ({ value: p, label: p })),
          ]} />
          <HeaderFilter label="Source" value={searchSource} onChange={setSearchSource} ocultable options={[
            { value: '', label: 'Todos' }, ...sourceOptions.map(s => ({ value: s, label: s })),
          ]} />
          <HeaderFilter label="Grupo" value={searchGroup} onChange={setSearchGroup} ocultable options={[
            { value: '', label: 'Todos' }, ...groupOptions.map(g => ({ value: g, label: g })),
          ]} />
        </div>
      </th>
      <th><HeaderFilter label="Estado" value={filterStatus} onChange={v => { setFilterStatus(v); setOffset(0) }} options={[
        { value: '', label: 'Todos' },
        // Through the same label map the badges use, or the filter
        // would offer "Error de importación" for a column showing
        // "Importación".
        ...(filterOptions?.statuses ?? []).map(s => ({ value: s, label: getLocalStatusInfo(s).label })),
      ]} /></th>
      <th><HeaderFilter label="Petición" value={filterRequest} onChange={v => { setFilterRequest(v); setOffset(0) }} options={[
        { value: '', label: 'Todas' }, ...(filterOptions?.request_statuses ?? []).map(s => ({ value: s, label: s })),
      ]} /></th>
      <th><HeaderFilter label="Español" value={filterSpanish} onChange={v => { setFilterSpanish(v); setOffset(0) }} options={[
        { value: '', label: 'Todos' },
        // Las etiquetas salen de la misma tabla que pinta la celda
        // (utils/castellano), para que el desplegable no pueda
        // ofrecer un nombre que la columna no usa.
        ...(filterOptions?.spanish_states ?? []).map(s => ({
          value: s,
          label: CASTELLANO_OPCIONES.find(o => o.value === s)?.label ?? s,
        })),
      ]} /></th>
      <th><HeaderFilter label="EMuwarez" value={filterEmu} onChange={v => { setFilterEmu(v); setOffset(0) }} options={[
        { value: '', label: 'Todos' }, ...(filterOptions?.emu_states ?? []).map(s => ({ value: s, label: s === 'present' ? 'Sí' : 'No' })),
      ]} /></th>
      <HeaderSort label="Tamaño" desc="size_desc" asc="size_asc" sortBy={sortBy} onSort={v => { setSortBy(v); setOffset(0) }} />
      <th className="col-actions">Acciones</th>
    </tr>
  )

  const sinResultados = {
    title: 'Sin resultados',
    body: 'Nada de la biblioteca cumple estos filtros.',
    action: <button className="btn btn-primary btn-sm" onClick={quitarFiltros}>Quitar filtros</button>,
  }

  return (
    <div data-tour="library-content" className="bib-pagina">
      <div className="page-header">
        <div>
          <div className="page-title">Biblioteca</div>
          <div className="page-subtitle">
            {/* Cuenta ARCHIVOS (películas + capítulos que tienes), no filas de la
                tabla: enseñando las filas, una serie con 90 capítulos contaba 1.
                Por eso no cambia al filtrar — la pregunta es "cuánto tengo". */}
            {/* Mientras carga no se sabe cuántos hay: "Sin elementos" mentía. */}
            {archivos > 0
              ? `${formatNumero(archivos)} archivos sincronizados`
              : loading && !data ? 'Contando archivos…' : 'Sin elementos'}
          </div>
        </div>
        <div className="bib-acciones">
          <Tooltip content="Consulta tus instancias de Radarr/Sonarr y actualiza la biblioteca local (títulos, rutas, estado en disco y nomenclatura).">
            <button
              className="btn btn-primary btn-sm"
              onClick={startLibrarySync}
              disabled={isAnySyncing}
            >
              {libSyncing
                ? <><span className="spinner bib-spinner" /> Sincronizando…</>
                : '↻ Sincronizar biblioteca'}
            </button>
          </Tooltip>
          <EmuSyncButton />
        </div>
      </div>

      {/* Search by title + filters + view modes, all on one line */}
      <div className="filters-bar">
        <input
          className="form-input bib-buscar"
          placeholder="Buscar título…"
          value={search}
          onChange={e => { setSearch(e.target.value); if (!e.target.value) { setOffset(0) } }}
          onKeyDown={e => e.key === 'Enter' && applyFilters()}
        />
        <select className="form-input form-select bib-orden" value={sortBy} onChange={e => { setSortBy(e.target.value); setOffset(0) }}>
          <option value="title_asc">Orden: Título (A-Z)</option>
          <option value="title_desc">Orden: Título (Z-A)</option>
          <option value="updated_desc">Orden: RR (Reciente)</option>
          <option value="year_desc">Orden: Año (Nuevo)</option>
          <option value="year_asc">Orden: Año (Antiguo)</option>
          <option value="size_desc">Orden: Tamaño (Más)</option>
          <option value="size_asc">Orden: Tamaño (Menos)</option>
        </select>
        <VistasGuardadas vistas={vistas} actual={filtrosDeAhora} onAplicar={aplicarVista} onGuardar={guardarVista} onQuitar={quitarVista} />
        {/* La tabla apagada sola no decía que estuviera cargando. */}
        {tarda && (
          <span role="status" className="bib-cargando">
            <span className="spinner bib-spinner" /> Cargando…
          </span>
        )}
        {data && resumenResultados && <span className="text-muted">{resumenResultados}</span>}
        {data && hayMas && (
          <button className="btn btn-secondary btn-sm" onClick={cargarMas} disabled={cargandoMas || loading || isPending}>
            {cargandoMas ? 'Cargando…' : 'Cargar más'}
          </button>
        )}
        {fallaMas && <span className="text-muted">No se pudieron cargar más filas</span>}
        <div className="bib-vistas">
          <Tooltip content="Vista de pósters">
            <button
              className={`btn btn-primary btn-sm${viewMode === 'grid' ? '' : ' bib-vista-apagada'}`}
              onClick={() => setViewMode('grid')}
              aria-label="Vista de pósters"
            >
              ▦
            </button>
          </Tooltip>
          <Tooltip content="Vista de pósters grandes">
            <button
              className={`btn btn-primary btn-sm${viewMode === 'grid-lg' ? '' : ' bib-vista-apagada'}`}
              onClick={() => setViewMode('grid-lg')}
              aria-label="Vista de pósters grandes"
            >
              ▦▦
            </button>
          </Tooltip>
          <Tooltip content="Vista de lista">
            <button
              className={`btn btn-primary btn-sm${viewMode === 'list' ? '' : ' bib-vista-apagada'}`}
              onClick={() => setViewMode('list')}
              aria-label="Vista de lista"
            >
              ☰
            </button>
          </Tooltip>
        </div>
      </div>

      {(loading || isPending) && !items.length ? (
        viewMode === 'list' ? (
          <div className="activity-section bib-bloque-lista">
            <div className="bib-scroll">
              <table className="data-table bib-tabla">
                <thead>{tableHeadRow}</thead>
                <tbody><LibraryTableSkeleton /></tbody>
              </table>
            </div>
          </div>
        ) : (
          <div className="activity-section bib-bloque-rejilla">
            <LibraryGridSkeleton large={viewMode === 'grid-lg'} />
          </div>
        )
      ) : error ? (
        <ErrorState message={error} onRetry={load} />
      ) : items.length === 0 && !filtrando ? (
        <EmptyState
          icon={<IconoLibros />}
          title="Biblioteca vacía"
          body="Añade instancias Radarr/Sonarr en la sección Instancias y sincroniza para ver el contenido aquí."
        />
      ) : items.length === 0 && viewMode !== 'list' ? (
        <EmptyState icon={<IconoLibros />} {...sinResultados} />
      ) : viewMode !== 'list' ? (
        <div ref={rejillaRef} className={`activity-section bib-bloque-rejilla${refrescando}`}>
          <RejillaVirtual
            items={items}
            clave={claveDeItem}
            minimo={viewMode === 'grid-lg' ? 220 : 140}
            hueco={viewMode === 'grid-lg' ? 20 : 16}
            contenedor={rejillaRef}
            pintar={(item, i) => viewMode === 'grid-lg'
              ? <LargePosterCard item={item} onSelect={openDetail} priority={i < GRID_PRIORITY_COUNT} />
              : <PosterCard item={item} onSelect={openDetail} priority={i < GRID_PRIORITY_COUNT} />}
          />
        </div>
      ) : (
        <div className={`activity-section bib-bloque-lista${refrescando}`}>
          <div ref={listaRef} className="bib-scroll">
            <table className="data-table bib-tabla">
              <thead ref={cabeceraRef}>{tableHeadRow}</thead>
              {items.length === 0 ? (
                <FilaVacia columnas={LIST_COLUMNS} icon={<IconoLibros />} {...sinResultados} />
              ) : (
                <FilasVirtuales
                  items={items}
                  clave={claveDeItem}
                  alturaEstimada={LIST_ROW_HEIGHT}
                  columnas={LIST_COLUMNS}
                  contenedor={listaRef}
                  cabecera={cabeceraRef}
                  fijas={desplegadas}
                  pintar={pintarFila}
                />
              )}
            </table>
          </div>
        </div>
      )}

      {modals}
    </div>
  )
}
