// @vitest-environment jsdom
/**
 * Subidas con el servidor simulado: el chip «Lote · N» de las subidas de una tanda (solo con más de un elemento), el
 * filtro por lote que pone al pulsarlo (lo aplica el servidor, en la lista y en el total) y cómo se quita; el banner
 * del lote (contadores, cancelar pendientes y reintentar fallidas) y el reintento de una cadena, solo desde su punta.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../../api/uploads', () => ({
  getUploads: vi.fn(), countUploads: vi.fn(), getUploadJob: vi.fn(), startUploadJob: vi.fn(),
  retryUploadJobQueued: vi.fn(), cancelUploadJob: vi.fn(), getUploadJobLogs: vi.fn(), deleteUploadJob: vi.fn(),
  getLote: vi.fn(), cancelarLote: vi.fn(), reintentarLote: vi.fn(),
}))
vi.mock('../../api/instances', () => ({ getInstances: vi.fn(async () => []) }))
vi.mock('../../api/seeding', () => ({ getSeeding: vi.fn(async () => null) }))
vi.mock('../../api/eventos', () => ({
  suscribirse: vi.fn(() => () => {}), canalVivo: vi.fn(() => true), observarCanal: vi.fn(() => () => {}),
}))

import { cancelarLote, countUploads, getLote, getUploadJob, getUploads, reintentarLote } from '../../api/uploads'
import { ApiClientError } from '../../api/client'
import { SeccionVisible } from '../../context/SeccionVisible'
import { SyncContext } from '../../context/SyncContext'
import type { LoteAccionResult, LoteResumen, UploadJob } from '../../types/api'
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
const RESUMEN: LoteResumen = {
  lote_id: LOTE, total: 3, en_cola: 1, en_marcha: 1, completadas: 1, fallidas: 0, canceladas: 0, creado: null,
  terminado: false, puede_cancelar: true, puede_reintentar: false,
}
const accion = (extra: Partial<LoteAccionResult>): LoteAccionResult =>
  ({ canceladas: 0, intactas: 0, reintentadas: 0, saltadas: [], resumen: null, ...extra })
const banner = () => document.querySelector('.sub-lote-banner')
const contadores = () => [...document.querySelectorAll('.sub-lote-contador')].map(li => li.textContent)

const ultimaPeticion = () => vi.mocked(getUploads).mock.lastCall?.[0]
const ultimoRecuento = () => vi.mocked(countUploads).mock.lastCall?.[0]

beforeEach(() => {
  vi.mocked(getUploads).mockImplementation(async q => (q?.lote_id ? [TANDA] : [TANDA, LOTE_DE_UNO, SUELTA]))
  vi.mocked(countUploads).mockImplementation(async q => (q?.lote_id ? 1 : 3))
  vi.mocked(getLote).mockResolvedValue(RESUMEN)
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
    expect(banner()!.textContent).toContain('Lote de 3 subidas')
    expect(getLote).toHaveBeenCalledWith(LOTE)
    // Sigue en la lista: el chip no abre el detalle de la subida.
    expect(document.querySelector('.page-title')?.textContent).toBe('Subidas')
  })

  it('«Quitar filtro» vuelve a la lista entera', async () => {
    await pagina()
    await pulsar(chips()[0])
    await esperar(() => document.querySelectorAll('tbody tr').length === 1)
    await pulsar(boton('Quitar filtro'))
    await esperar(() => document.querySelectorAll('tbody tr').length === 3)
    expect(ultimaPeticion()?.lote_id).toBeUndefined()
    expect(banner()).toBeNull()
  })

  it('con el lote vacío, el estado vacío ofrece «Quitar filtros» y lo quita', async () => {
    await pagina()
    vi.mocked(getUploads).mockImplementation(async q => (q?.lote_id ? [] : [TANDA, LOTE_DE_UNO, SUELTA]))
    vi.mocked(getLote).mockRejectedValue(new ApiClientError('Lote no encontrado.', 404, null))
    await pulsar(chips()[0])
    await esperar(() => texto().includes('Sin resultados'))
    // Sin filas, el título del lote no sabe cuántas tiene, y el servidor ya no lo conoce: sin contadores.
    expect(banner()!.querySelector('.sub-lote-banner-titulo')!.textContent).toBe('Lote')
    expect(contadores()).toEqual([])
    expect(boton('Cancelar pendientes')!.disabled).toBe(true)

    await pulsar(boton('Quitar filtros'))
    await esperar(() => document.querySelectorAll('tbody tr').length === 3)
    expect(ultimaPeticion()?.lote_id).toBeUndefined()
    expect(chips()).toHaveLength(1)
  })
})

// Filtra por el lote del chip y espera a que el banner tenga el resumen.
async function filtrarPorLote() {
  await pagina()
  await pulsar(chips()[0])
  await esperar(() => contadores().length > 0)
}
const casilla = () => document.querySelector<HTMLInputElement>('.sub-lote-casilla input[type="checkbox"]')!

describe('el banner del lote', () => {
  it('enseña los contadores que no son cero y habilita solo lo que se puede hacer', async () => {
    await filtrarPorLote()
    expect(contadores()).toEqual(['1 en cola', '1 en marcha', '1 completada'])
    expect(boton('Cancelar pendientes')!.disabled).toBe(false)
    expect(boton('Reintentar fallidas')!.disabled).toBe(true)
  })

  it('«Cancelar pendientes» pregunta antes y, sin la casilla, cancela solo las de la cola', async () => {
    vi.mocked(cancelarLote).mockResolvedValue(accion({ canceladas: 3, intactas: 1 }))
    await filtrarPorLote()
    const peticiones = vi.mocked(getUploads).mock.calls.length
    await pulsar(boton('Cancelar pendientes'))
    expect(document.querySelector('[role="dialog"]')).not.toBeNull()
    expect(cancelarLote).not.toHaveBeenCalled()
    expect(casilla().checked).toBe(false)
    await pulsar(boton('Cancelar las pendientes'))
    expect(cancelarLote).toHaveBeenCalledWith(LOTE, true)
    await esperar(() => document.querySelector('.sub-lote-aviso')?.textContent === '3 canceladas · 1 ya había empezado')
    // Y recarga la lista (y con ella el resumen).
    expect(vi.mocked(getUploads).mock.calls.length).toBeGreaterThan(peticiones)
    expect(document.querySelector('[role="dialog"]')).toBeNull()
  })

  it('con la casilla marcada para también las que ya están en marcha', async () => {
    vi.mocked(cancelarLote).mockResolvedValue(accion({ canceladas: 2 }))
    await filtrarPorLote()
    await pulsar(boton('Cancelar pendientes'))
    await pulsar(casilla())
    expect(casilla().checked).toBe(true)
    await pulsar(boton('Cancelar todas'))
    expect(cancelarLote).toHaveBeenCalledWith(LOTE, false)
    await esperar(() => document.querySelector('.sub-lote-aviso')?.textContent === '2 canceladas')
  })

  it('«Dejarlas seguir» cierra sin cancelar nada', async () => {
    await filtrarPorLote()
    await pulsar(boton('Cancelar pendientes'))
    await pulsar(boton('Dejarlas seguir'))
    expect(document.querySelector('[role="dialog"]')).toBeNull()
    expect(cancelarLote).not.toHaveBeenCalled()
  })

  it('«Reintentar fallidas» dice cuántas y por qué se saltó cada una', async () => {
    vi.mocked(getLote).mockResolvedValue({ ...RESUMEN, en_cola: 0, en_marcha: 0, fallidas: 2, puede_cancelar: false, puede_reintentar: true })
    vi.mocked(reintentarLote).mockResolvedValue(accion({
      reintentadas: 1, saltadas: [{ job_id: 4, title: 'Serie - S01E02', errors: ['Ya hay otra subida en marcha.'] }],
    }))
    await filtrarPorLote()
    expect(contadores()).toEqual(['1 completada', '2 fallidas'])
    expect(boton('Cancelar pendientes')!.disabled).toBe(true)
    const peticiones = vi.mocked(getUploads).mock.calls.length
    await pulsar(boton('Reintentar fallidas'))
    expect(reintentarLote).toHaveBeenCalledWith(LOTE)
    const aviso = await esperar(() => document.querySelector('.sub-lote-aviso'))
    expect(aviso.textContent).toContain('1 reintentada')
    expect(aviso.querySelector('li')!.textContent).toBe('Serie - S01E02: Ya hay otra subida en marcha.')
    expect(vi.mocked(getUploads).mock.calls.length).toBeGreaterThan(peticiones)
  })

  it('un fallo de la acción se enseña, no se traga', async () => {
    vi.mocked(cancelarLote).mockRejectedValue(new Error('El servidor no responde.'))
    await filtrarPorLote()
    await pulsar(boton('Cancelar pendientes'))
    await pulsar(boton('Cancelar las pendientes'))
    await esperar(() => document.querySelector('[role="alert"]')?.textContent === 'El servidor no responde.')
  })
})

describe('una cadena de reintentos', () => {
  const ORIGINAL = trabajo({ id: 5, status: 'failed', title: 'Película', media_type: 'movie' })
  const PUNTA = trabajo({ id: 6, status: 'failed', title: 'Película', media_type: 'movie', retry_of_job_id: 5, retry_count: 1 })

  it('solo se reintenta desde el último intento: el anterior lo tiene deshabilitado', async () => {
    vi.mocked(getUploads).mockResolvedValue([PUNTA, ORIGINAL])
    vi.mocked(countUploads).mockResolvedValue(2)
    await pagina()
    expect(document.querySelectorAll('tbody tr')).toHaveLength(1)
    await pulsar(document.querySelector('.sub-toggle-reintentos')!)
    const filas = [...document.querySelectorAll('tbody tr')]
    expect(filas).toHaveLength(2)
    const reintentar = (tr: Element) =>
      [...tr.querySelectorAll('button')].find(b => b.textContent?.includes('Reintentar'))!
    expect(filas[0].classList.contains('sub-fila-antigua')).toBe(false)
    expect(reintentar(filas[0]).disabled).toBe(false)
    expect(filas[1].classList.contains('sub-fila-antigua')).toBe(true)
    expect(reintentar(filas[1]).disabled).toBe(true)
  })
})

describe('«Ver el lote» desde el detalle de una subida', () => {
  it('cierra el detalle y filtra la tabla por su lote', async () => {
    vi.mocked(getUploadJob).mockResolvedValue({ ...TANDA, display_title: 'Serie (2024) - S01E01' })
    await pagina()
    await pulsar(filaDe('Serie - S01E01').querySelector('.sub-titulo')!)
    await esperar(() => texto().includes('Parte de un lote de 3'))
    await pulsar(boton('Ver el lote'))
    await esperar(() => ultimaPeticion()?.lote_id === LOTE)
    await esperar(() => banner())
    expect(document.querySelector('.page-title')?.textContent).toBe('Subidas')
  })
})
