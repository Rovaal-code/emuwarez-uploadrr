// @vitest-environment jsdom
/**
 * Mientras corre una sincronización, cada lectura de su progreso (cada 800 ms) repinta solo la barra que la enseña:
 * las secciones, también las ocultas, leen del contexto si hay algo sincronizándose y la marca de invalidación, que
 * no cambian en cada lectura.
 */
import { act } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../../api/library', () => ({
  startLibrarySync: vi.fn(), getLibrarySyncProgress: vi.fn(),
  emuSync: vi.fn(), getEmuSyncProgress: vi.fn(), getEmuSyncStatus: vi.fn(),
}))
vi.mock('../../api/requests', () => ({
  syncRequests: vi.fn(), getSyncStatus: vi.fn(), getRequestsSyncProgress: vi.fn(),
}))
vi.mock('../../api/eventos', () => ({ suscribirse: vi.fn(() => () => {}), canalVivo: vi.fn(() => true) }))

import { getEmuSyncProgress, getEmuSyncStatus, getLibrarySyncProgress } from '../../api/library'
import { getRequestsSyncProgress, getSyncStatus } from '../../api/requests'
import { SyncProvider, useSync, useSyncProgress } from '../SyncContext'
import { SeccionVisible } from '../SeccionVisible'
import { desmontar, montar } from '../../components/__tests__/dom'

const pintados = { visible: 0, oculta: 0, barra: 0 }

function Seccion({ cual }: { cual: 'visible' | 'oculta' }) {
  const { libSyncing, lastInvalidatedAt } = useSync()
  pintados[cual]++
  return <p data-seccion={cual}>{libSyncing ? 'sincronizando' : 'quieta'} {lastInvalidatedAt}</p>
}
function Barra() {
  const { libProgress } = useSyncProgress()
  pintados.barra++
  return <p data-barra>{libProgress ? libProgress.imported : '—'}</p>
}

let leidas = 0
beforeEach(() => {
  vi.useFakeTimers()
  leidas = 0
  pintados.visible = pintados.oculta = pintados.barra = 0
  vi.mocked(getLibrarySyncProgress).mockImplementation(async () => {
    leidas++
    return { active: true, done: false, phase: 'Importando', imported: leidas * 10, missing: 0, total: 5000, instance: 'Radarr', instance_type: 'radarr', error: null }
  })
  vi.mocked(getEmuSyncProgress).mockResolvedValue({ active: false, done: true, error: null, phase: '', torrents: 0, items: 0, page: 0, total_pages: null, eta_seconds: null })
  vi.mocked(getEmuSyncStatus).mockResolvedValue(null as never)
  vi.mocked(getRequestsSyncProgress).mockResolvedValue({ active: false, done: true, error: null, phase: '', page: 0, total_pages: null, imported: 0, message: '' })
  vi.mocked(getSyncStatus).mockResolvedValue(null as never)
})
afterEach(async () => {
  await desmontar()
  vi.useRealTimers()
})

describe('el progreso de una sincronización', () => {
  it('cada lectura repinta la barra y no las secciones', async () => {
    await montar(
      <SyncProvider>
        <Barra />
        <SeccionVisible visible><Seccion cual="visible" /></SeccionVisible>
        <SeccionVisible visible={false}><Seccion cual="oculta" /></SeccionVisible>
      </SyncProvider>,
    )
    // Al montar encuentra la sincronización en marcha y la sigue.
    await act(async () => { await vi.advanceTimersByTimeAsync(0) })
    expect(document.querySelector('[data-seccion="visible"]')!.textContent).toContain('sincronizando')
    const antes = { ...pintados }
    const leidasAntes = leidas

    for (let i = 0; i < 5; i++) await act(async () => { await vi.advanceTimersByTimeAsync(800) })

    expect(leidas - leidasAntes).toBeGreaterThanOrEqual(4)
    expect(document.querySelector('[data-barra]')!.textContent).toBe(String(leidas * 10))
    expect(pintados.barra - antes.barra).toBeGreaterThanOrEqual(4)
    expect(pintados.visible).toBe(antes.visible)
    expect(pintados.oculta).toBe(antes.oculta)
  })
})
