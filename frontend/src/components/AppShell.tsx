import { useState, useEffect, useCallback, useRef, useLayoutEffect, lazy, Suspense } from 'react'
import { Sidebar } from './Sidebar'
import { SeccionVisible } from '../context/SeccionVisible'
import { Topbar } from './Topbar'
import { useMenuMovil } from '../hooks/useMenuMovil'
import type { CurrentUserResponse } from '../types/api'
import { guardedLeave, hasUnsavedChanges } from '../utils/unsavedGuard'
import { UnsavedChangesModal } from './UnsavedChangesModal'
import { TourOverlay } from './TourOverlay'
import { useTour } from '../context/TourContext'
import { pasosDelTour } from '../tour/steps'
import { CommandPalette } from './CommandPalette'
import { esAtajoDePaleta } from '../utils/paleta'

// The very first time the app is ready to use (right after finishing setup,
// or on any later reload before it's been seen), the guided tour launches on
// its own — closing it (even without finishing) marks it seen, so it never
// launches again on its own; it can still be relaunched any time from the
// Info button in the topbar.
const TOUR_SEEN_KEY = 'emuwarez_uploadrr_tour_seen'

// Pages
import { DashboardPage } from '../pages/DashboardPage'
import { LimiteDeErrores } from './LimiteDeErrores'
import { LoadingState } from './LoadingState'

// El Panel va en el chunk principal (es donde se entra); las demás secciones, cada una en el suyo. Con todas juntas
// eran 613 kB de JS que parsear antes de pintar nada, y de ellos la primera pantalla usa un tercio. No se nota al
// abrirlas: el premontaje de abajo las monta a los 2 s, así que su chunk baja en ese hueco y la primera visita sigue
// siendo instantánea.
const CARGAR_PAGINA = {
  library:   () => import('../pages/LibraryPage').then(m => ({ default: m.LibraryPage })),
  requests:  () => import('../pages/RequestsPage').then(m => ({ default: m.RequestsPage })),
  uploads:   () => import('../pages/UploadsPage').then(m => ({ default: m.UploadsPage })),
  stats:     () => import('../pages/EstadisticasPage').then(m => ({ default: m.EstadisticasPage })),
  guide:     () => import('../pages/GuidePage').then(m => ({ default: m.GuidePage })),
  tasks:     () => import('../pages/TasksPage').then(m => ({ default: m.TasksPage })),
  instances: () => import('../pages/InstancesPage').then(m => ({ default: m.InstancesPage })),
  logs:      () => import('../pages/LogsPage').then(m => ({ default: m.LogsPage })),
  settings:  () => import('../pages/SettingsPage').then(m => ({ default: m.SettingsPage })),
}
const LibraryPage = lazy(CARGAR_PAGINA.library)
const RequestsPage = lazy(CARGAR_PAGINA.requests)
const UploadsPage = lazy(CARGAR_PAGINA.uploads)
const EstadisticasPage = lazy(CARGAR_PAGINA.stats)
const GuidePage = lazy(CARGAR_PAGINA.guide)
const TasksPage = lazy(CARGAR_PAGINA.tasks)
const InstancesPage = lazy(CARGAR_PAGINA.instances)
const LogsPage = lazy(CARGAR_PAGINA.logs)
const SettingsPage = lazy(CARGAR_PAGINA.settings)

interface AppShellProps {
  user: CurrentUserResponse | null
  onLogout: () => void
}

const PAGE_TITLE: Record<string, string> = {
  dashboard:  'Panel',
  library:    'Biblioteca',
  requests:   'Peticiones',
  uploads:    'Subidas',
  stats:      'Estadísticas',
  guide:      'Guía',
  tasks:      'Tareas',
  instances:  'Instancias',
  logs:       'Logs',
  settings:   'Configuración',
}

function unaPagina(page: string, onNavigate: (p: string) => void) {
  switch (page) {
    case 'dashboard':  return <DashboardPage onNavigate={onNavigate} />
    case 'library':    return <LibraryPage onNavigate={onNavigate} />
    case 'requests':   return <RequestsPage onNavigate={onNavigate} />
    case 'uploads':    return <UploadsPage onNavigate={onNavigate} />
    case 'stats':      return <EstadisticasPage />
    case 'guide':      return <GuidePage />
    case 'tasks':      return <TasksPage onNavigate={onNavigate} />
    case 'instances':  return <InstancesPage />
    case 'logs':       return <LogsPage />
    case 'settings':   return <SettingsPage />
    default:           return <DashboardPage />
  }
}

/**
 * Las secciones NO se desmontan al cambiar de pestaña: se quedan montadas y
 * ocultas, y volver a una es instantáneo.
 *
 * Antes esto era un `switch`, o sea que cambiar de pestaña destruía la sección
 * entera y volver a ella la levantaba de cero: pedir los datos otra vez,
 * volver a pintar la lista, y mientras tanto "Cargando…". Con Biblioteca eso
 * se notaba especialmente, porque pinta hasta 20.000 filas de una vez y
 * rehacerlas cuesta, hubiera cambiado algo o no.
 *
 * Hubo un intento intermedio de guardar la última carga de cada sección para
 * volver a pintarla al entrar. Tapaba el síntoma a medias —seguía habiendo que
 * rehacer todo el árbol— y traía sus propios problemas: cuándo caduca la
 * copia, qué hacer si al confirmarla falla la recarga, cómo no reutilizar una
 * lista filtrada bajo unos filtros ya reiniciados. Nada de eso existe si la
 * sección simplemente sigue ahí, así que se quitó entero.
 *
 * Se montan según se visitan, no todas de golpe: entrar en la aplicación no
 * puede costar levantar nueve pantallas de las que vas a mirar una.
 *
 * `display: contents` hace que este envoltorio no genere caja, así que la
 * sección sigue colocándose exactamente igual que cuando colgaba directa de
 * `.page-container`. La oculta va con `display: none`, que la saca del
 * renderizado y del árbol de accesibilidad: no ocupa, no se puede tabular a
 * ella, y el tour no la confunde con la buena (mide rectángulos, y los de una
 * sección oculta son de tamaño cero).
 */
// El orden en que se montan solas las que no has abierto. Primero las que
// cuestan (piden datos y pintan listas); las de después son casi instantáneas
// y van al final porque da igual cuándo lleguen.
const ORDEN_DE_PREPARADO = ['library', 'requests', 'uploads', 'dashboard',
                            'tasks', 'instances', 'settings', 'logs', 'stats', 'guide']

// Lo que se espera antes de empezar. El navegador tiene bastante que hacer
// justo después de arrancar (pintar la primera sección, pedir sus datos), y
// meterle ocho pantallas más en ese momento se notaría en lo único que el
// usuario está mirando.
const ESPERA_ANTES_DE_PREPARAR_MS = 2000

function PageContent({ page, onNavigate }: { page: string; onNavigate: (p: string) => void }) {
  const [, repintar] = useState(0)
  const visitadas = useRef<string[]>([])
  if (!visitadas.current.includes(page)) visitadas.current = [...visitadas.current, page]

  // Las secciones que no has abierto se van montando solas, en silencio, una
  // por una. Así pulsar cualquiera es instantáneo también la PRIMERA vez, que
  // era lo único que seguía costando una carga.
  //
  // Una por una y en huecos libres (`requestIdleCallback`), no las ocho de
  // golpe: montar Biblioteca puede significar pintar miles de filas, y hacerlo
  // todo junto congelaría la pantalla que sí estás mirando. Repartido, no se
  // nota.
  useEffect(() => {
    let cancelado = false
    const pedirHueco = window.requestIdleCallback ?? ((f: () => void) => setTimeout(f, 200))

    const siguiente = () => {
      if (cancelado) return
      const falta = ORDEN_DE_PREPARADO.find(p => !visitadas.current.includes(p))
      if (!falta) return
      visitadas.current = [...visitadas.current, falta]
      repintar(n => n + 1)
      pedirHueco(siguiente)
    }

    const arranque = setTimeout(() => pedirHueco(siguiente), ESPERA_ANTES_DE_PREPARAR_MS)
    return () => { cancelado = true; clearTimeout(arranque) }
  }, [])

  return (
    <>
      {visitadas.current.map(p => (
        <div key={p} style={{ display: p === page ? 'contents' : 'none' }}>
          <LimiteDeErrores>
            <SeccionVisible visible={p === page}>
              <Suspense fallback={<LoadingState />}>{unaPagina(p, onNavigate)}</Suspense>
            </SeccionVisible>
          </LimiteDeErrores>
        </div>
      ))}
    </>
  )
}

// Tabs that map to a URL path, so the address bar reflects the current tab
// (bookmarkable / reloadable). The backend already serves index.html for any
// non-/api path (SPA fallback), so a deep link like /library works on reload.
const VALID_PAGES = ['dashboard', 'library', 'uploads', 'stats', 'requests', 'guide', 'tasks', 'instances', 'logs', 'settings']

function pageFromPath(): string {
  const seg = window.location.pathname.replace(/^\/+/, '').split('/')[0]
  return VALID_PAGES.includes(seg) ? seg : 'dashboard'
}

// La sección de la URL (/library al recargar) se empieza a pedir ya, al cargar este módulo, y no al pintarla: así su
// chunk baja a la vez que el resto del arranque en vez de después.
const inicial = pageFromPath()
if (inicial in CARGAR_PAGINA) void CARGAR_PAGINA[inicial as keyof typeof CARGAR_PAGINA]().catch(() => { /* lo reintenta lazy */ })

export function AppShell({ user, onLogout }: AppShellProps) {
  const [activePage, setActivePage] = useState<string>(pageFromPath)
  const { start: startTour } = useTour()
  const [paletaAbierta, setPaletaAbierta] = useState(false)
  const menu = useMenuMovil()

  // La pestaña del navegador dice dónde estás (historial, pestañas fijadas, lector de pantalla).
  useEffect(() => {
    document.title = PAGE_TITLE[activePage] ? `${PAGE_TITLE[activePage]} · eMuwarez Uploadrr` : 'eMuwarez Uploadrr'
  }, [activePage])

  useEffect(() => {
    if (localStorage.getItem(TOUR_SEEN_KEY) !== '1') {
      startTour(pasosDelTour(menu.movil), {
        onClose: () => localStorage.setItem(TOUR_SEEN_KEY, '1'),
      })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- el tour se ofrece una sola vez, al abrir la aplicación
  }, [])

  const navigate = useCallback((page: string) => {
    if (page === pageFromPath()) return
    // Ask (styled modal) before leaving a form with unsaved changes.
    guardedLeave(() => {
      setActivePage(page)
      const path = `/${page}`
      if (window.location.pathname !== path) {
        window.history.pushState({}, '', path)
      }
    })
  }, [])

  // Ctrl+K / Cmd+K abre (o cierra) la paleta de búsqueda desde cualquier sección.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!esAtajoDePaleta(e)) return
      e.preventDefault()
      setPaletaAbierta(abierta => !abierta)
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [])

  // La ficha de la Biblioteca se abre por la URL (/library/:id), como hace la campana.
  const abrirElemento = useCallback((id: number) => {
    guardedLeave(() => {
      window.history.pushState({}, '', `/library/${id}`)
      window.dispatchEvent(new PopStateEvent('popstate'))
    })
  }, [])

  // Elegir una sección en la paleta. Si ya estás en ella con una ficha abierta (/library/42), vuelve a la lista:
  // `navigate` no hace nada cuando la sección es la misma.
  const abrirSeccion = useCallback((id: string) => {
    if (id !== pageFromPath() || window.location.pathname === `/${id}`) { navigate(id); return }
    guardedLeave(() => {
      window.history.pushState({}, '', `/${id}`)
      window.dispatchEvent(new PopStateEvent('popstate'))
    })
  }, [navigate])

  // Keep the tab in sync with browser back/forward.
  const paginaVigente = useRef(activePage)
  paginaVigente.current = activePage
  useEffect(() => {
    const onPop = (e: PopStateEvent) => {
      const destino = pageFromPath()
      // Un popstate lanzado por código (la campana) ya ha preguntado antes de mover la URL.
      if (!e.isTrusted || destino === paginaVigente.current || !hasUnsavedChanges()) {
        setActivePage(destino)
        return
      }
      // Atrás/Adelante ya ha cambiado la URL: se pone la de antes y se pregunta.
      const ruta = window.location.pathname + window.location.search
      window.history.pushState({}, '', `/${paginaVigente.current}`)
      guardedLeave(() => {
        setActivePage(destino)
        window.history.pushState({}, '', ruta)
      })
    }
    window.addEventListener('popstate', onPop)
    return () => window.removeEventListener('popstate', onPop)
  }, [])

  // Warn before a full reload / closing the tab while there are unsaved changes.
  useEffect(() => {
    const onBeforeUnload = (e: BeforeUnloadEvent) => {
      if (hasUnsavedChanges()) {
        e.preventDefault()
        e.returnValue = ''
      }
    }
    window.addEventListener('beforeunload', onBeforeUnload)
    return () => window.removeEventListener('beforeunload', onBeforeUnload)
  }, [])

  // El desplazamiento lo lleva `.page-container`, que ahora es uno solo para
  // todas las secciones: sin esto, dejar Biblioteca a media altura y entrar en
  // Peticiones te dejaba en mitad de Peticiones. Se guarda el de la que sale y
  // se restaura el de la que entra, así que cada sección recuerda por dónde
  // ibas, que es parte de que volver se sienta instantáneo.
  const contenedor = useRef<HTMLElement | null>(null)
  const alturas = useRef<Record<string, number>>({})
  const paginaActual = useRef(activePage)

  // Se apunta MIENTRAS te desplazas, no al cambiar de sección. Intenté lo
  // segundo y no funciona: para cuando el efecto puede leer `scrollTop`, el
  // navegador ya ha recortado el desplazamiento a la altura de la sección
  // nueva, así que lo que se guardaba de la que salía era casi siempre 0.
  useEffect(() => {
    const caja = contenedor.current
    if (!caja) return
    const apuntar = () => { alturas.current[paginaActual.current] = caja.scrollTop }
    caja.addEventListener('scroll', apuntar, { passive: true })
    return () => caja.removeEventListener('scroll', apuntar)
  }, [])

  // Antes de pintar, para que no se vea el salto.
  useLayoutEffect(() => {
    paginaActual.current = activePage
    const caja = contenedor.current
    if (caja) caja.scrollTop = alturas.current[activePage] ?? 0
  }, [activePage])

  return (
    <div className="app-shell hud-app">
      {/* Primer tabulador de la página: salta la barra lateral y la cabecera. Es un botón, no un enlace: no navega a ningún sitio. */}
      <button type="button" className="saltar-contenido" onClick={() => contenedor.current?.focus()}>
        Saltar al contenido
      </button>
      <UnsavedChangesModal />
      {menu.abierto && <div className="sidebar-velo" onClick={menu.cerrar} aria-hidden="true" />}
      <Sidebar
        active={activePage} onNavigate={navigate} movil={menu.movil} abierta={menu.abierto} onCerrar={menu.cerrar}
        onTour={() => { menu.cerrar(); startTour(pasosDelTour(menu.movil)) }}
        user={user} onLogout={onLogout}
      />
      <div className="main-content" inert={menu.abierto}>
        <Topbar
          user={user}
          pageTitle={PAGE_TITLE[activePage] ?? ''}
          onLogout={onLogout}
          onBuscar={() => setPaletaAbierta(true)}
          menu={menu}
        />
        <main className="page-container" id="contenido" tabIndex={-1} ref={contenedor}>
          <PageContent page={activePage} onNavigate={navigate} />
        </main>
      </div>
      <TourOverlay activePage={activePage} navigate={navigate} />
      {paletaAbierta && (
        <CommandPalette
          secciones={Object.entries(PAGE_TITLE).map(([id, titulo]) => ({ id, titulo }))}
          onSeccion={abrirSeccion}
          onElemento={abrirElemento}
          onClose={() => setPaletaAbierta(false)}
        />
      )}
    </div>
  )
}
