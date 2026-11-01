import { createContext, useContext, useCallback, useEffect, useRef, useState } from 'react'
import {
  startLibrarySync as apiStartLibrarySync,
  getLibrarySyncProgress,
  emuSync,
  getEmuSyncProgress,
  getEmuSyncStatus,
  type LibrarySyncProgress,
  type EmuSyncProgress,
  type EmuSyncStatus,
  type EmuSyncMode,
} from '../api/library'
import { syncRequests, getSyncStatus, getRequestsSyncProgress, type RequestsSyncProgress } from '../api/requests'
import { suscribirse, canalVivo } from '../api/eventos'
import type { RequestSyncStatusResponse } from '../types/api'
import { formatNumero } from '../utils/format'

// Global sync state, shared by every page (Dashboard / Biblioteca / Peticiones).
// The pages are unmounted when you switch tabs, so if this state lived inside a
// page a running sync would "disappear" on navigation and its button would let
// you launch it again. Hosting it here keeps one source of truth: the same
// progress card and the same disabled buttons show up on every tab, and the
// backend throttle is never bypassed.
interface SyncContextValue {
  // Library (Radarr/Sonarr) sync
  libSyncing: boolean
  libProgress: LibrarySyncProgress | null
  startLibrarySync: () => void
  // eMuwarez catalog sync
  catalogSyncing: boolean
  catalogProgress: EmuSyncProgress | null
  catalogStatus: EmuSyncStatus | null
  startCatalogSync: (mode?: EmuSyncMode) => void
  refreshCatalogStatus: () => void
  // eMuwarez requests sync
  requestsSyncing: boolean
  requestsProgress: RequestsSyncProgress | null
  requestsStatus: RequestSyncStatusResponse | null
  startRequestsSync: (force: boolean) => void
  refreshRequestsStatus: () => void
  // True while any of the three syncs above is running — buttons for the
  // OTHER sync types use this to disable themselves, since running two syncs
  // at once caused a visual glitch in the top bar.
  isAnySyncing: boolean
  // Last completion message, shown as a toast in the topbar's sync row (see
  // SyncProgressBanner) — green on success, red on error, auto-dismissed
  // after 5s. Shared by Biblioteca/eMuwarez/Peticiones syncs alike, so it's
  // a single value rather than one per sync type.
  message: string | null
  messageIsError: boolean
  messageFadingOut: boolean
  // Marca creciente: "lo que tengas cargado ya no vale, vuelve a pedirlo".
  // La sección que se esté viendo recarga al momento; las demás están
  // montadas pero ocultas y lo hacen al volver a ellas (ver SeccionVisible).
  // Sube por dos hechos, no por el paso del tiempo: termina una
  // sincronización, o vuelves a la pestaña del navegador.
  lastInvalidatedAt: number
}

// Dos invalidaciones más juntas que esto se cuentan como una. No es un plazo
// de caducidad —eso se quitó a propósito— sino un aglutinador: ahora hay tres
// cosas que pueden pedir lo mismo casi a la vez (el aviso del servidor, el
// bucle que sigue la sincronización, y volver a la pestaña), y recargarlo todo
// tres veces seguidas no aporta nada. También cubre el alternar rápido entre
// ventanas, que es para lo que SWR tiene su propio estrangulamiento.
const AGLUTINAR_MS = 2000

export const SyncContext = createContext<SyncContextValue | null>(null)

export function useSync(): SyncContextValue {
  const ctx = useContext(SyncContext)
  if (!ctx) throw new Error('useSync must be used within <SyncProvider>')
  return ctx
}

export function SyncProvider({ children }: { children: React.ReactNode }) {
  const [libSyncing, setLibSyncing] = useState(false)
  const [libProgress, setLibProgress] = useState<LibrarySyncProgress | null>(null)
  const [catalogSyncing, setCatalogSyncing] = useState(false)
  const [catalogProgress, setCatalogProgress] = useState<EmuSyncProgress | null>(null)
  const [catalogStatus, setCatalogStatus] = useState<EmuSyncStatus | null>(null)
  const [requestsSyncing, setRequestsSyncing] = useState(false)
  const [requestsProgress, setRequestsProgress] = useState<RequestsSyncProgress | null>(null)
  const [requestsStatus, setRequestsStatus] = useState<RequestSyncStatusResponse | null>(null)
  const [message, setMessageText] = useState<string | null>(null)
  const [messageIsError, setMessageIsError] = useState(false)
  const [messageFadingOut, setMessageFadingOut] = useState(false)
  const [lastInvalidatedAt, setLastInvalidatedAt] = useState(0)

  const messageTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const messageFadeTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Shows a completion toast for 5s (then a 300ms fade) — green on success,
  // red on error.
  const showMessage = useCallback((text: string, isError: boolean) => {
    if (messageTimer.current) clearTimeout(messageTimer.current)
    if (messageFadeTimer.current) clearTimeout(messageFadeTimer.current)
    setMessageFadingOut(false)
    setMessageIsError(isError)
    setMessageText(text)
    messageTimer.current = setTimeout(() => {
      setMessageFadingOut(true)
      messageFadeTimer.current = setTimeout(() => {
        setMessageText(null)
        setMessageFadingOut(false)
      }, 300)
    }, 5000)
  }, [])

  // Clears any toast still showing/fading right as a NEW sync starts, so it
  // can't linger on top of (or alongside) the fresh progress chip.
  const hideMessage = useCallback(() => {
    if (messageTimer.current) clearTimeout(messageTimer.current)
    if (messageFadeTimer.current) clearTimeout(messageFadeTimer.current)
    setMessageFadingOut(false)
    setMessageText(null)
  }, [])

  // Guards so a resume-on-mount check can't start a second polling loop, and a
  // double click can't fire two syncs.
  const libBusy = useRef(false)
  const catalogBusy = useRef(false)
  const requestsBusy = useRef(false)

  // "Nada de lo cargado vale ya, volved a pedirlo".
  //
  // Ojo con lo que NO hace: no borra nada de la pantalla. Hubo una versión que
  // sí, y fue un error — volver de otra pestaña del navegador dispara esto, y
  // dejaba a todas las secciones sin nada que enseñar, así que entrar en
  // cualquiera de ellas volvía a sacar "Cargando…". Revalidar es refrescar por
  // detrás, no vaciar y empezar de cero.
  //
  // Se avisa a TODAS y no solo a la que parece afectada: una sincronización
  // toca varias a la vez (el catálogo cambia el "Llena / Sin petición" de
  // Biblioteca, y los tres contadores del Panel).
  const ultimaInvalidacion = useRef(0)
  const invalidarTodo = useCallback(() => {
    const ahora = Date.now()
    if (ahora - ultimaInvalidacion.current < AGLUTINAR_MS) return
    ultimaInvalidacion.current = ahora
    setLastInvalidatedAt(ahora)
  }, [])

  const refreshCatalogStatus = useCallback(() => {
    getEmuSyncStatus().then(setCatalogStatus).catch(() => { /* optional */ })
  }, [])
  const refreshRequestsStatus = useCallback(() => {
    getSyncStatus().then(setRequestsStatus).catch(() => { /* optional */ })
  }, [])

  // ---- Library sync ----
  const followLibrary = useCallback(async () => {
    try {
      for (let i = 0; i < 3600; i++) {
        const p = await getLibrarySyncProgress()
        setLibProgress(p)
        if (p.done || !p.active) {
          showMessage(p.error
            ? `Error durante la sincronización: ${p.error}`
            : `Sincronizado: ${formatNumero(p.imported)} elementos; ${formatNumero(p.missing)} no disponibles`, !!p.error)
          invalidarTodo()
          break
        }
        await new Promise(r => setTimeout(r, 800))
      }
    } finally {
      setLibProgress(null)
      setLibSyncing(false)
      libBusy.current = false
    }
  }, [invalidarTodo, showMessage])

  const startLibrarySync = useCallback(() => {
    if (libBusy.current) return
    libBusy.current = true
    setLibSyncing(true)
    hideMessage()
    setLibProgress({ active: true, done: false, phase: 'Iniciando…', imported: 0, missing: 0, total: 0, instance: '', instance_type: '', error: null })
    apiStartLibrarySync(true)
      .then(() => followLibrary())
      .catch(() => {
        showMessage('Error durante la sincronización', true)
        setLibProgress(null)
        setLibSyncing(false)
        libBusy.current = false
      })
  }, [followLibrary, hideMessage, showMessage])

  // ---- eMuwarez catalog sync ----
  const followCatalog = useCallback(async () => {
    try {
      for (let i = 0; i < 3600; i++) {
        const p = await getEmuSyncProgress()
        setCatalogProgress(p)
        if (p.done || !p.active) {
          showMessage(p.error
            ? `Error al sincronizar eMuwarez: ${p.error}`
            : `Catálogo eMuwarez: ${p.torrents} torrents, ${p.items} elementos comparados`, !!p.error)
          invalidarTodo()
          break
        }
        await new Promise(r => setTimeout(r, 800))
      }
    } finally {
      setCatalogProgress(null)
      setCatalogSyncing(false)
      catalogBusy.current = false
      refreshCatalogStatus()
    }
  }, [invalidarTodo, refreshCatalogStatus, showMessage])

  const startCatalogSync = useCallback((mode: EmuSyncMode = 'incremental') => {
    if (catalogBusy.current) return
    catalogBusy.current = true
    setCatalogSyncing(true)
    hideMessage()
    setCatalogProgress({ active: true, done: false, phase: 'Iniciando…', torrents: 0, items: 0, page: 0, total_pages: null, eta_seconds: null, error: null })
    emuSync(mode)
      .then(() => followCatalog())
      .catch((e: unknown) => {
        showMessage(e instanceof Error ? e.message : 'Error al sincronizar con eMuwarez', true)
        setCatalogProgress(null)
        setCatalogSyncing(false)
        catalogBusy.current = false
        refreshCatalogStatus()
      })
  }, [followCatalog, refreshCatalogStatus, hideMessage, showMessage])

  // ---- eMuwarez requests sync (en segundo plano: se sigue su progreso, no una petición colgada) ----
  const followRequests = useCallback(async () => {
    try {
      for (let i = 0; i < 3600; i++) {
        const p = await getRequestsSyncProgress()
        setRequestsProgress(p)
        if (p.done || !p.active) {
          showMessage(p.error ? `Error al sincronizar las peticiones: ${p.error}` : p.message || 'Peticiones sincronizadas', !!p.error)
          invalidarTodo()
          break
        }
        await new Promise(r => setTimeout(r, 800))
      }
    } finally {
      setRequestsProgress(null)
      setRequestsSyncing(false)
      requestsBusy.current = false
      refreshRequestsStatus()
    }
  }, [invalidarTodo, refreshRequestsStatus, showMessage])

  const startRequestsSync = useCallback((force: boolean) => {
    if (requestsBusy.current) return
    requestsBusy.current = true
    setRequestsSyncing(true)
    hideMessage()
    setRequestsProgress({ active: true, done: false, phase: 'Iniciando…', page: 0, total_pages: null, imported: 0, message: '', error: null })
    const terminar = () => {
      setRequestsProgress(null)
      setRequestsSyncing(false)
      requestsBusy.current = false
      refreshRequestsStatus()
    }
    syncRequests(force)
      .then(res => {
        if (res.status === 'started') return followRequests()
        // "throttled" y "busy" llegan con ok: false y su propio mensaje.
        showMessage(res.message, !res.ok)
        terminar()
      })
      // Un fallo de verdad: el mensaje del servidor (el detail del 502).
      .catch((e: unknown) => {
        showMessage(e instanceof Error ? e.message : 'Error al sincronizar las peticiones', true)
        terminar()
      })
  }, [followRequests, refreshRequestsStatus, hideMessage, showMessage])

  // Una sincronización de peticiones ya en marcha (la programada, otra pestaña o una recarga de página): se sigue.
  const checkAndResumeRequestsSync = useCallback(() => {
    if (requestsBusy.current) return
    getRequestsSyncProgress().then(p => {
      if (p.active && !p.done && !requestsBusy.current) {
        requestsBusy.current = true
        setRequestsSyncing(true)
        setRequestsProgress(p)
        followRequests()
      }
    }).catch(() => { /* ignore */ })
  }, [followRequests])

  // Checks for a library (Radarr/Sonarr) sync already running server-side and
  // hands off to the normal follow loop if one is found — reused both on
  // mount (resuming one started before a page reload) and by the ambient
  // poll below (catching one a scheduled task started later, with nobody
  // having clicked anything in this tab).
  const checkAndResumeLibrarySync = useCallback(() => {
    if (libBusy.current) return
    getLibrarySyncProgress().then(p => {
      if (p.active && !p.done && !libBusy.current) {
        libBusy.current = true
        setLibSyncing(true)
        setLibProgress(p)
        followLibrary()
      }
    }).catch(() => { /* ignore */ })
  }, [followLibrary])

  // Load throttle statuses once, and resume any sync already running in the
  // background (e.g. started on another tab, or before a page reload).
  useEffect(() => {
    refreshCatalogStatus()
    refreshRequestsStatus()
    checkAndResumeLibrarySync()
    checkAndResumeRequestsSync()
    getEmuSyncProgress().then(p => {
      if (p.active && !p.done && !catalogBusy.current) {
        catalogBusy.current = true
        setCatalogSyncing(true)
        setCatalogProgress(p)
        followCatalog()
      }
    }).catch(() => { /* ignore */ })
  }, [refreshCatalogStatus, refreshRequestsStatus, checkAndResumeLibrarySync, checkAndResumeRequestsSync, followCatalog])

  // Una tarea programada (el tic automático, o "Ejecutar ahora" en Tareas)
  // puede arrancar una sincronización sin que nadie toque nada en esta
  // pestaña. La comprobación al montar solo pilla las que YA estaban
  // corriendo, así que hacía falta enterarse de las que empiezan después: eso
  // era un sondeo cada 8 segundos, y ahora lo dice el servidor al empezar. En
  // cuanto se detecta, el bucle de seguimiento de siempre toma el relevo.
  //
  // El sondeo se queda de red de seguridad, muy espaciado: sin él, con el
  // canal caído la barra de arriba no aparecería nunca para una
  // sincronización que no hayas lanzado tú.
  useEffect(() => suscribirse('sync-empezada', () => {
    if (!libBusy.current) checkAndResumeLibrarySync()
    if (!requestsBusy.current) checkAndResumeRequestsSync()
  }), [checkAndResumeLibrarySync, checkAndResumeRequestsSync])

  useEffect(() => {
    let vivo = true
    let timer: ReturnType<typeof setTimeout> | undefined
    // Encadenado en vez de setInterval: así cada vuelta vuelve a mirar si el
    // canal está en pie, sin tener que suscribirse también a eso aquí.
    const tic = () => {
      if (!libBusy.current) checkAndResumeLibrarySync()
      if (!requestsBusy.current) checkAndResumeRequestsSync()
      if (vivo) timer = setTimeout(tic, canalVivo() ? 60_000 : 8000)
    }
    timer = setTimeout(tic, canalVivo() ? 60_000 : 8000)
    return () => { vivo = false; if (timer) clearTimeout(timer) }
  }, [checkAndResumeLibrarySync, checkAndResumeRequestsSync])

  // Volver a la pestaña revalida. Es `refetchOnWindowFocus`, que SWR y TanStack
  // Query traen activado por defecto, y es lo que sustituye al plazo de
  // caducidad que tenía la caché: el caso que aquel intentaba cubrir a ciegas
  // era la pestaña abierta toda la noche, y esto lo cubre sabiendo cuándo pasa
  // en vez de suponerlo. Importa sobre todo para Biblioteca, que es la única
  // que no repide por su cuenta: sin esto se queda con lo de anoche hasta que
  // la toques.
  //
  // Se estrangula a 5 segundos (el valor por defecto de SWR): alternar entre
  // ventanas es algo que se hace muchas veces seguidas, y cada vuelta dispara
  // una recarga completa de la página montada.
  useEffect(() => {
    const alVolver = () => {
      if (document.visibilityState !== 'visible') return
      invalidarTodo()
    }
    document.addEventListener('visibilitychange', alVolver)
    return () => document.removeEventListener('visibilitychange', alVolver)
  }, [invalidarTodo])

  // El aviso del servidor cuando termina una sincronización, la haya lanzado
  // este navegador o no — la programada, o la de otra pestaña, que hasta ahora
  // se descubrían por casualidad cuando al sondeo de turno le tocaba pasar por
  // ahí. Si el canal no levanta, se reintenta solo y no se rompe nada.
  useEffect(() => suscribirse('sync-terminada', () => invalidarTodo()), [invalidarTodo])

  const value: SyncContextValue = {
    libSyncing, libProgress, startLibrarySync,
    catalogSyncing, catalogProgress, catalogStatus, startCatalogSync, refreshCatalogStatus,
    requestsSyncing, requestsProgress, requestsStatus, startRequestsSync, refreshRequestsStatus,
    isAnySyncing: libSyncing || catalogSyncing || requestsSyncing,
    message, messageIsError, messageFadingOut, lastInvalidatedAt,
  }
  return <SyncContext.Provider value={value}>{children}</SyncContext.Provider>
}
