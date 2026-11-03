// @vitest-environment jsdom
/**
 * «Sincronizar todo»: un botón que lanza la biblioteca, el catálogo de eMuwarez y las peticiones una tras otra, con
 * el servidor simulado. Lo que importa: el orden, que se salte lo que eMuwarez aún no deja repetir, y que un error
 * pare la cadena en vez de taparse con el siguiente paso.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../../api/library', () => ({
  startLibrarySync: vi.fn(), getLibrarySyncProgress: vi.fn(),
  emuSync: vi.fn(), getEmuSyncProgress: vi.fn(), getEmuSyncStatus: vi.fn(),
}))
vi.mock('../../api/requests', () => ({
  syncRequests: vi.fn(), getSyncStatus: vi.fn(), getRequestsSyncProgress: vi.fn(),
}))
vi.mock('../../api/eventos', () => ({ suscribirse: vi.fn(() => () => {}), canalVivo: vi.fn(() => true) }))

import { emuSync, getEmuSyncProgress, getEmuSyncStatus, getLibrarySyncProgress, startLibrarySync } from '../../api/library'
import { getRequestsSyncProgress, getSyncStatus, syncRequests } from '../../api/requests'
import { SyncProvider } from '../../context/SyncContext'
import { pasosDeSincronizarTodo } from '../../utils/sincronizarTodo'
import { boton, desmontar, esperar, montar, pulsar } from './dom'
import { SyncCard } from '../SyncCard'

const reposo = { active: false, done: true, error: null }
const estadoCatalogo = (puede: boolean) => ({
  last_sync_at: null, can_sync: puede, wait_seconds: 0, min_interval_seconds: 3600, incremental_can_sync: puede,
  incremental_wait_seconds: puede ? 0 : 600, full_can_sync: true, full_wait_seconds: 0, last_full_sync_at: null,
})
const estadoPeticiones = (puede: boolean) => ({
  last_sync_at: null, next_sync_at: null, can_sync: puede, wait_seconds: puede ? 0 : 900, min_interval_seconds: 3600,
})

const TODO = '↻ Sincronizar todo'
const llamadas: string[] = []

beforeEach(() => {
  llamadas.length = 0
  vi.mocked(getLibrarySyncProgress).mockResolvedValue({ ...reposo, phase: '', imported: 3, missing: 0, total: 3, instance: '', instance_type: '' })
  vi.mocked(startLibrarySync).mockImplementation(async () => { llamadas.push('biblioteca'); return {} as never })
  vi.mocked(getEmuSyncProgress).mockResolvedValue({ ...reposo, phase: '', torrents: 5, items: 5, page: 0, total_pages: null, eta_seconds: null })
  vi.mocked(emuSync).mockImplementation(async () => { llamadas.push('catalogo'); return {} as never })
  vi.mocked(getEmuSyncStatus).mockResolvedValue(estadoCatalogo(true))
  vi.mocked(getRequestsSyncProgress).mockResolvedValue({ ...reposo, phase: '', page: 0, total_pages: null, imported: 1, message: 'Peticiones sincronizadas' })
  vi.mocked(syncRequests).mockImplementation(async () => { llamadas.push('peticiones'); return { ok: true, status: 'started', message: '' } as never })
  vi.mocked(getSyncStatus).mockResolvedValue(estadoPeticiones(true))
})
afterEach(desmontar)

const montarBoton = () => montar(<SyncProvider><SyncCard /></SyncProvider>)

describe('qué pasos lanza «Sincronizar todo»', () => {
  it('los tres, en orden, si nada está limitado', () => {
    expect(pasosDeSincronizarTodo(estadoCatalogo(true), estadoPeticiones(true))).toEqual(['biblioteca', 'catalogo', 'peticiones'])
  })

  it('salta lo que eMuwarez aún no deja repetir', () => {
    expect(pasosDeSincronizarTodo(estadoCatalogo(false), estadoPeticiones(false))).toEqual(['biblioteca'])
    expect(pasosDeSincronizarTodo(estadoCatalogo(true), estadoPeticiones(false))).toEqual(['biblioteca', 'catalogo'])
  })

  it('sin saber aún el estado, lo intenta y decide el servidor', () => {
    expect(pasosDeSincronizarTodo(null, null)).toEqual(['biblioteca', 'catalogo', 'peticiones'])
  })
})

describe('el botón', () => {
  it('lanza los tres endpoints de siempre, uno tras otro', async () => {
    await montarBoton()
    await pulsar(boton(TODO))
    await esperar(() => llamadas.length === 3)
    expect(llamadas).toEqual(['biblioteca', 'catalogo', 'peticiones'])
    await esperar(() => boton(TODO))   // al terminar vuelve a estar disponible
  })

  it('no lanza la sincronización limitada por hora', async () => {
    vi.mocked(getSyncStatus).mockResolvedValue(estadoPeticiones(false))
    await montarBoton()
    await esperar(() => vi.mocked(getSyncStatus).mock.calls.length > 0)
    await pulsar(boton(TODO))
    await esperar(() => llamadas.length === 2)
    await esperar(() => boton(TODO))
    expect(llamadas).toEqual(['biblioteca', 'catalogo'])
  })

  it('un error en un paso para la cadena: el aviso no se tapa con el siguiente', async () => {
    vi.mocked(emuSync).mockImplementation(async () => { llamadas.push('catalogo'); throw new Error('Sin API key de eMuwarez') })
    await montarBoton()
    await pulsar(boton(TODO))
    await esperar(() => llamadas.length >= 2)
    await esperar(() => boton(TODO))
    expect(llamadas).toEqual(['biblioteca', 'catalogo'])
  })

  it('mientras corre está desactivado y no se puede lanzar dos veces', async () => {
    let terminar!: () => void
    vi.mocked(startLibrarySync).mockImplementation(() => new Promise(r => { llamadas.push('biblioteca'); terminar = () => r({} as never) }))
    await montarBoton()
    await pulsar(boton(TODO))
    await esperar(() => boton('Sincronizando…'))
    expect(boton('Sincronizando…')!.disabled).toBe(true)
    expect(llamadas).toEqual(['biblioteca'])
    terminar()
    await esperar(() => llamadas.length === 3)
  })
})
