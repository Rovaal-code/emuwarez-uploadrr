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
  // last completion message + a monotonically increasing marker so pages can
  // reload their own data when any sync finishes.
  message: string | null
  lastCompletedAt: number
}

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
  const [message, setMessage] = useState<string | null>(null)
  const [lastCompletedAt, setLastCompletedAt] = useState(0)

  // Guards so a resume-on-mount check can't start a second polling loop, and a
  // double click can't fire two syncs.
  const libBusy = useRef(false)
  const catalogBusy = useRef(false)
  const requestsBusy = useRef(false)

  const bumpCompleted = useCallback(() => setLastCompletedAt(Date.now()), [])

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
          setMessage(p.error
            ? `Error durante la sincronización: ${p.error}`
            : `Sincronizado: ${p.imported} elementos · ${p.missing} no disponibles`)
          bumpCompleted()
          break
        }
        await new Promise(r => setTimeout(r, 800))
      }
    } finally {
      setLibProgress(null)
      setLibSyncing(false)
      libBusy.current = false
    }
  }, [bumpCompleted])

  const startLibrarySync = useCallback(() => {
    if (libBusy.current) return
    libBusy.current = true
    setLibSyncing(true)
    setMessage(null)
    setLibProgress({ active: true, done: false, phase: 'Iniciando…', imported: 0, missing: 0, total: 0, instance: '', instance_type: '', error: null })
    apiStartLibrarySync(true)
      .then(() => followLibrary())
      .catch(() => {
        setMessage('Error durante la sincronización')
        setLibProgress(null)
        setLibSyncing(false)
        libBusy.current = false
      })
  }, [followLibrary])

  // ---- eMuwarez catalog sync ----
  const followCatalog = useCallback(async () => {
    try {
      for (let i = 0; i < 3600; i++) {
        const p = await getEmuSyncProgress()
        setCatalogProgress(p)
        if (p.done || !p.active) {
          setMessage(p.error
            ? `Error al sincronizar eMuwarez: ${p.error}`
            : `Catálogo eMuwarez: ${p.torrents} torrents, ${p.items} elementos comparados`)
          bumpCompleted()
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
  }, [bumpCompleted, refreshCatalogStatus])

  const startCatalogSync = useCallback((mode: EmuSyncMode = 'incremental') => {
    if (catalogBusy.current) return
    catalogBusy.current = true
    setCatalogSyncing(true)
    setMessage(null)
    setCatalogProgress({ active: true, done: false, phase: 'Iniciando…', torrents: 0, items: 0, page: 0, total_pages: null, eta_seconds: null, error: null })
    emuSync(mode)
      .then(() => followCatalog())
      .catch((e: unknown) => {
        setMessage(e instanceof Error ? e.message : 'Error al sincronizar con eMuwarez')
        setCatalogProgress(null)
        setCatalogSyncing(false)
        catalogBusy.current = false
        refreshCatalogStatus()
      })
  }, [followCatalog, refreshCatalogStatus])

  // ---- eMuwarez requests sync (blocking call, no progress card) ----
  const startRequestsSync = useCallback((force: boolean) => {
    if (requestsBusy.current) return
    requestsBusy.current = true
    setRequestsSyncing(true)
    setMessage(null)
    syncRequests(force)
      .then(res => {
        setMessage(res.message)
        if (res.ok) bumpCompleted()
      })
      .catch((e: unknown) => setMessage(e instanceof Error ? e.message : 'Error al sincronizar'))
      .finally(() => {
        setRequestsSyncing(false)
        requestsBusy.current = false
        refreshRequestsStatus()
      })
  }, [bumpCompleted, refreshRequestsStatus])

  // Load throttle statuses once, and resume any sync already running in the
  // background (e.g. started on another tab, or before a page reload).
  useEffect(() => {
    refreshCatalogStatus()
    refreshRequestsStatus()
    getLibrarySyncProgress().then(p => {
      if (p.active && !p.done && !libBusy.current) {
        libBusy.current = true
        setLibSyncing(true)
        setLibProgress(p)
        followLibrary()
      }
    }).catch(() => { /* ignore */ })
    getEmuSyncProgress().then(p => {
      if (p.active && !p.done && !catalogBusy.current) {
        catalogBusy.current = true
        setCatalogSyncing(true)
        setCatalogProgress(p)
        followCatalog()
      }
    }).catch(() => { /* ignore */ })
  }, [refreshCatalogStatus, refreshRequestsStatus, followLibrary, followCatalog])

  const value: SyncContextValue = {
    libSyncing, libProgress, startLibrarySync,
    catalogSyncing, catalogProgress, catalogStatus, startCatalogSync, refreshCatalogStatus,
    requestsSyncing, requestsStatus, startRequestsSync, refreshRequestsStatus,
    message, lastCompletedAt,
  }
  return <SyncContext.Provider value={value}>{children}</SyncContext.Provider>
}
