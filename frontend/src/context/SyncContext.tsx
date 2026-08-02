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
import { syncRequests, getSyncStatus } from '../api/requests'
import { olvidarPagina } from '../utils/cachePaginas'
import { escucharEventos } from '../api/eventos'
import type { RequestSyncStatusResponse } from '../types/api'

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
  requestsStatus: RequestSyncStatusResponse | null
  startRequestsSync: (force: boolean) => void
  refreshRequestsStatus: () => void
  // eMuwarez (UNIT3D) doesn't expose a requests endpoint at all — whatever
  // the exact failure (404, 401, throttled...), none of it is meant to be
  // shown to the user as a raw message anywhere. The top bar's sync chip
  // shows a plain "No implementado" instead, briefly, then fades out.
  requestsUnavailable: boolean
  requestsFadingOut: boolean
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
  // La página MONTADA se recarga con esto; las demás están desmontadas y lo
  // que se les tira es su copia (utils/cachePaginas), en el mismo sitio.
  // Sube por dos hechos, no por el paso del tiempo: termina una
  // sincronización, o vuelves a la pestaña.
  lastInvalidatedAt: number
}

// Dos invalidaciones más juntas que esto se cuentan como una. No es un plazo
// de caducidad —eso se quitó a propósito— sino un aglutinador: ahora hay tres
// cosas que pueden pedir lo mismo casi a la vez (el aviso del servidor, el
// bucle que sigue la sincronización, y volver a la pestaña), y recargarlo todo
// tres veces seguidas no aporta nada. También cubre el alternar rápido entre
// ventanas, que es para lo que SWR tiene su propio estrangulamiento.
const AGLUTINAR_MS = 2000

const SyncContext = createContext<SyncContextValue | null>(null)

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
  const [requestsStatus, setRequestsStatus] = useState<RequestSyncStatusResponse | null>(null)
  const [requestsUnavailable, setRequestsUnavailable] = useState(false)
  const [requestsFadingOut, setRequestsFadingOut] = useState(false)
  const [message, setMessageText] = useState<string | null>(null)
  const [messageIsError, setMessageIsError] = useState(false)
  const [messageFadingOut, setMessageFadingOut] = useState(false)
  const [lastInvalidatedAt, setLastInvalidatedAt] = useState(0)

  const requestsUnavailableTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const requestsFadeTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const messageTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const messageFadeTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Shows a completion toast for 5s (then a 300ms fade, same feel as
  // flashRequestsUnavailable below) — green on success, red on error.
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

  // Shows the "No implementado en esta versión" chip for a beat, then fades
  // it out — same brief flash regardless of why this particular attempt
  // failed (404, 401, throttled...), since none of that is ever shown raw.
  const flashRequestsUnavailable = useCallback(() => {
    if (requestsUnavailableTimer.current) clearTimeout(requestsUnavailableTimer.current)
    if (requestsFadeTimer.current) clearTimeout(requestsFadeTimer.current)
    setRequestsFadingOut(false)
    setRequestsUnavailable(true)
    requestsUnavailableTimer.current = setTimeout(() => {
      setRequestsFadingOut(true)
      requestsFadeTimer.current = setTimeout(() => {
        setRequestsUnavailable(false)
        setRequestsFadingOut(false)
      }, 300)
    }, 1500)
  }, [])

  // Guards so a resume-on-mount check can't start a second polling loop, and a
  // double click can't fire two syncs.
  const libBusy = useRef(false)
  const catalogBusy = useRef(false)
  const requestsBusy = useRef(false)

  // "Nada de lo cargado vale ya": tira la copia de las secciones desmontadas y
  // avisa a la montada para que se recargue. Las dos mitades van juntas a
  // propósito, porque una sin la otra deja la mitad de la aplicación mintiendo.
  //
  // Se olvidan TODAS las secciones y no solo la que parece afectada: una
  // sincronización toca varias a la vez (el catálogo cambia el "Llena / Sin
  // petición" de Biblioteca, y los tres contadores del Panel).
  const ultimaInvalidacion = useRef(0)
  const invalidarTodo = useCallback(() => {
    const ahora = Date.now()
    if (ahora - ultimaInvalidacion.current < AGLUTINAR_MS) return
    ultimaInvalidacion.current = ahora
    olvidarPagina()
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
            : `Sincronizado: ${p.imported} elementos · ${p.missing} no disponibles`, !!p.error)
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

  // ---- eMuwarez requests sync (blocking call, no progress card) ----
  const startRequestsSync = useCallback((force: boolean) => {
    if (requestsBusy.current) return
    requestsBusy.current = true
    setRequestsSyncing(true)
    hideMessage()
    if (requestsUnavailableTimer.current) clearTimeout(requestsUnavailableTimer.current)
    if (requestsFadeTimer.current) clearTimeout(requestsFadeTimer.current)
    setRequestsUnavailable(false)
    setRequestsFadingOut(false)
    syncRequests(force)
      .then(res => {
        // eMuwarez/UNIT3D doesn't really support this endpoint — whatever
        // shape that takes (throttled, unavailable, a raw 401/404...), none
        // of it is a real error worth surfacing as text; only a genuine
        // success gets the generic message banner.
        if (res.ok) {
          showMessage(res.message, false)
          invalidarTodo()
        } else {
          flashRequestsUnavailable()
        }
      })
      .catch(() => flashRequestsUnavailable())
      .finally(() => {
        setRequestsSyncing(false)
        requestsBusy.current = false
        refreshRequestsStatus()
      })
  }, [invalidarTodo, refreshRequestsStatus, flashRequestsUnavailable, hideMessage, showMessage])

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
    getEmuSyncProgress().then(p => {
      if (p.active && !p.done && !catalogBusy.current) {
        catalogBusy.current = true
        setCatalogSyncing(true)
        setCatalogProgress(p)
        followCatalog()
      }
    }).catch(() => { /* ignore */ })
  }, [refreshCatalogStatus, refreshRequestsStatus, checkAndResumeLibrarySync, followCatalog])

  // Ambient poll: a scheduled task (the automatic tick, or "Ejecutar ahora" in
  // Tareas) can start a library sync without the user ever clicking anything
  // in this tab — the mount-time check above only catches one already running
  // at that moment. Poll slowly for one that started later; once detected,
  // the normal 800ms follow loop takes over from there.
  useEffect(() => {
    const timer = setInterval(() => { if (!libBusy.current) checkAndResumeLibrarySync() }, 8000)
    return () => clearInterval(timer)
  }, [checkAndResumeLibrarySync])

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

  // El aviso del servidor. Mientras solo llega "sync-terminada", así que esto
  // no sustituye a nada todavía: los once sondeos siguen donde estaban. Lo que
  // añade es enterarse de una sincronización que terminó SIN que este
  // navegador la hubiera lanzado — la programada, o la de otra pestaña — que
  // hasta ahora se descubría por casualidad, cuando el sondeo de turno pasaba
  // por ahí. Si el canal no levanta, se reintenta solo y no se rompe nada.
  useEffect(() => {
    return escucharEventos(aviso => {
      if (aviso.tipo === 'sync-terminada') invalidarTodo()
    })
  }, [invalidarTodo])

  const value: SyncContextValue = {
    libSyncing, libProgress, startLibrarySync,
    catalogSyncing, catalogProgress, catalogStatus, startCatalogSync, refreshCatalogStatus,
    requestsSyncing, requestsStatus, startRequestsSync, refreshRequestsStatus, requestsUnavailable, requestsFadingOut,
    isAnySyncing: libSyncing || catalogSyncing || requestsSyncing,
    message, messageIsError, messageFadingOut, lastInvalidatedAt,
  }
  return <SyncContext.Provider value={value}>{children}</SyncContext.Provider>
}
