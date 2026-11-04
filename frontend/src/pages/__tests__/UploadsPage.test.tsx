// @vitest-environment jsdom
/**
 * Subidas con el servidor simulado: el chip «Lote · N» de las subidas de una tanda (solo con más de un elemento), el
 * filtro por lote que pone al pulsarlo (lo aplica el servidor, en la lista y en el total) y cómo se quita.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../../api/uploads', () => ({
  getUploads: vi.fn(), countUploads: vi.fn(), getUploadJob: vi.fn(), startUploadJob: vi.fn(),
  retryUploadJobQueued: vi.fn(), cancelUploadJob: vi.fn(), getUploadJobLogs: vi.fn(), deleteUploadJob: vi.fn(),
}))
vi.mock('../../api/instances', () => ({ getInstances: vi.fn(async () => []) }))
vi.mock('../../api/seeding', () => ({ getSeeding: vi.fn(async () => null) }))
vi.mock('../../api/eventos', () => ({
  suscribirse: vi.fn(() => () => {}), canalVivo: vi.fn(() => true), observarCanal: vi.fn(() => () => {}),
}))

import { countUploads, getUploads } from '../../api/uploads'
import { SeccionVisible } from '../../context/SeccionVisible'
import { SyncContext } from '../../context/SyncContext'
import type { UploadJob } from '../../types/api'
import { boton, desmontar, esperar, montar, pulsar, texto } from '../../components/__tests__/dom'
import { UploadsPage } from '../UploadsPage'

const LOTE = '0123456789ab'
const trabajo = (extra: Partial<UploadJob>) =>
  ({ id: 1, status: 'completed', media_type: 'episode', created_at: '2026-11-04T10:00:00', ...extra } as UploadJob)

const TANDA = trabajo({ id: 1, title: 'Serie - S01E01', lote_id: LOTE, lote_total: 3 })
const LOTE_DE_UNO = trabajo({ id: 2, title: 'Serie - S02E01', lote_id: 'ffffffffffff', lote_total: 1 })
const SUELTA = trabajo({ id: 3, title: 'Película suelta', media_type: 'movie', lote_id: null, lote_total: null })

async function pagina() {
  await montar(
    <SyncContext.Provider value={{ lastInvalidatedAt: 0, startAllSync: vi.fn(), isAnySyncing: false, todoPendiente: false } as never}>
      <SeccionVisible visible><UploadsPage onNavigate={vi.fn()} /></SeccionVisible>
    </SyncContext.Provider>,
  )
  await esperar(() => document.querySelectorAll('tbody tr').length > 0)
}

const chips = () => [...document.querySelectorAll<HTMLButtonElement>('button.sub-lote-chip')]
const filaDe = (titulo: string) =>
  [...document.querySelectorAll('tbody tr')].find(tr => tr.querySelector('.sub-titulo')?.textContent === titulo)!
const ultimaPeticion = () => vi.mocked(getUploads).mock.lastCall?.[0]
const ultimoRecuento = () => vi.mocked(countUploads).mock.lastCall?.[0]

beforeEach(() => {
  vi.mocked(getUploads).mockImplementation(async q => (q?.lote_id ? [TANDA] : [TANDA, LOTE_DE_UNO, SUELTA]))
  vi.mocked(countUploads).mockImplementation(async q => (q?.lote_id ? 1 : 3))
})
afterEach(async () => {
  await desmontar()
  vi.clearAllMocks()
})

describe('el chip del lote', () => {
  it('solo en la subida de un lote de más de un elemento', async () => {
    await pagina()
    expect(chips().map(c => c.textContent)).toEqual(['Lote · 3'])
    expect(filaDe('Serie - S01E01').querySelector('.sub-lote-chip')).not.toBeNull()
    expect(filaDe('Serie - S02E01').querySelector('.sub-lote-chip')).toBeNull()
    expect(filaDe('Película suelta').querySelector('.sub-lote-chip')).toBeNull()
    // Sin filtro, la lista y el total no llevan lote.
    expect(ultimaPeticion()?.lote_id).toBeUndefined()
    expect(ultimoRecuento()?.lote_id).toBeUndefined()
  })

  it('al pulsarlo pide al servidor solo ese lote, sin abrir la ficha', async () => {
    await pagina()
    await pulsar(chips()[0])
    await esperar(() => ultimaPeticion()?.lote_id === LOTE)
    expect(ultimoRecuento()).toEqual(expect.objectContaining({ lote_id: LOTE, hide_preparatory: true }))
    await esperar(() => document.querySelectorAll('tbody tr').length === 1)
    expect(texto()).toContain('Lote de 3 subidas · Quitar filtro de lote')
    // Sigue en la lista: el chip no abre el detalle de la subida.
    expect(document.querySelector('.page-title')?.textContent).toBe('Subidas')
  })

  it('«Quitar filtro de lote» vuelve a la lista entera', async () => {
    await pagina()
    await pulsar(chips()[0])
    await esperar(() => document.querySelectorAll('tbody tr').length === 1)
    await pulsar(boton('Quitar filtro de lote'))
    await esperar(() => document.querySelectorAll('tbody tr').length === 3)
    expect(ultimaPeticion()?.lote_id).toBeUndefined()
    expect(texto()).not.toContain('Quitar filtro de lote')
  })

  it('con el lote vacío, el estado vacío ofrece «Quitar filtros» y lo quita', async () => {
    await pagina()
    vi.mocked(getUploads).mockImplementation(async q => (q?.lote_id ? [] : [TANDA, LOTE_DE_UNO, SUELTA]))
    await pulsar(chips()[0])
    await esperar(() => texto().includes('Sin resultados'))
    expect(texto()).toContain('Lote · Quitar filtro de lote')

    await pulsar(boton('Quitar filtros'))
    await esperar(() => document.querySelectorAll('tbody tr').length === 3)
    expect(ultimaPeticion()?.lote_id).toBeUndefined()
    expect(chips()).toHaveLength(1)
  })
})
