// @vitest-environment jsdom
/**
 * Subidas con el servidor simulado: el chip «Lote · N» de las subidas de una tanda (solo con más de un elemento), el
 * filtro por lote que pone al pulsarlo (lo aplica el servidor, en la lista y en el total) y cómo se quita; el banner
 * del lote (contadores, cancelar pendientes, reintentar fallidas y borrar el lote) y el reintento de una cadena, solo
 * desde su punta.
 */
import { act } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../../api/uploads', () => ({
  getUploads: vi.fn(), countUploads: vi.fn(), getUploadJob: vi.fn(), startUploadJob: vi.fn(),
  retryUploadJobQueued: vi.fn(), cancelUploadJob: vi.fn(), getUploadJobLogs: vi.fn(), deleteUploadJob: vi.fn(),
  getLote: vi.fn(), cancelarLote: vi.fn(), reintentarLote: vi.fn(), borrarLote: vi.fn(),
}))
vi.mock('../../api/instances', () => ({ getInstances: vi.fn(async () => []) }))
vi.mock('../../api/seeding', () => ({ getSeeding: vi.fn(async () => null) }))
vi.mock('../../api/eventos', () => ({
  suscribirse: vi.fn(() => () => {}), canalVivo: vi.fn(() => true), observarCanal: vi.fn(() => () => {}),
}))

import {
  borrarLote, cancelarLote, cancelUploadJob, countUploads, deleteUploadJob, getLote, getUploadJob, getUploads, reintentarLote,
  retryUploadJobQueued,
} from '../../api/uploads'
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
  terminado: false, puede_cancelar: true, puede_reintentar: false, parado: null, paradas: 0,
}
const accion = (extra: Partial<LoteAccionResult>): LoteAccionResult =>
  ({ canceladas: 0, intactas: 0, reintentadas: 0, saltadas: [], resumen: null, ...extra })
const banner = () => document.querySelector('.sub-lote-banner')
// Los botones del banner se apagan con aria-disabled (siguen enfocables y con su tooltip), no con disabled.
const apagado = (nombre: string) => boton(nombre)!.getAttribute('aria-disabled') === 'true'
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

  it('con el lote ya sin subidas, el estado vacío lo dice y ofrece «Quitar filtro del lote»', async () => {
    await pagina()
    vi.mocked(getUploads).mockImplementation(async q => (q?.lote_id ? [] : [TANDA, LOTE_DE_UNO, SUELTA]))
    vi.mocked(getLote).mockRejectedValue(new ApiClientError('Lote no encontrado.', 404, null))
    await pulsar(chips()[0])
    await esperar(() => texto().includes('Este lote ya no tiene subidas'))
    // El servidor ya no conoce el lote: ni «Sin resultados» ni contadores, y el banner lo dice.
    expect(texto()).not.toContain('Sin resultados')
    expect(banner()!.querySelector('.sub-lote-banner-titulo')!.textContent).toBe('Lote sin subidas')
    expect(contadores()).toEqual([])
    expect(apagado('Cancelar pendientes')).toBe(true)

    await pulsar(boton('Quitar filtro del lote'))
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
    expect(apagado('Cancelar pendientes')).toBe(false)
    expect(apagado('Reintentar fallidas')).toBe(true)
    expect(apagado('Borrar lote')).toBe(false)
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
    expect(apagado('Cancelar pendientes')).toBe(true)
    const peticiones = vi.mocked(getUploads).mock.calls.length
    await pulsar(boton('Reintentar fallidas'))
    expect(reintentarLote).toHaveBeenCalledWith(LOTE)
    const aviso = await esperar(() => document.querySelector('.sub-lote-aviso'))
    expect(aviso.textContent).toContain('1 reintentada')
    expect(aviso.querySelector('li')!.textContent).toBe('Serie - S01E02: Ya hay otra subida en marcha.')
    expect(vi.mocked(getUploads).mock.calls.length).toBeGreaterThan(peticiones)
  })

  it('si el freno paró el lote, dice por qué, cuántas paró y cómo relanzarlas', async () => {
    const parado = 'Lote parado: 5 fallos seguidos por «Forbidden (403)»'
    vi.mocked(getLote).mockResolvedValue({
      ...RESUMEN, en_cola: 0, en_marcha: 0, completadas: 0, fallidas: 5, canceladas: 3, total: 8,
      puede_cancelar: false, puede_reintentar: true, parado, paradas: 3,
    })
    await filtrarPorLote()
    expect(document.querySelector('.sub-lote-parado')!.textContent).toBe(
      `${parado}. 3 subidas no llegaron a empezar; «Reintentar fallidas» las relanza.`)
    expect(apagado('Reintentar fallidas')).toBe(false)
  })

  it('sin freno, no dice nada de él', async () => {
    await filtrarPorLote()
    expect(document.querySelector('.sub-lote-parado')).toBeNull()
  })

  it('«Borrar lote» pregunta antes, avisa de que borra la cadena entera y de las que no toca', async () => {
    vi.mocked(getLote).mockResolvedValue({ ...RESUMEN, fallidas: 2, total: 5 })
    vi.mocked(borrarLote).mockResolvedValue({ borradas: 3, intentos: 5, en_curso: 2, resumen: null })
    await filtrarPorLote()
    const peticiones = vi.mocked(getUploads).mock.calls.length
    await pulsar(boton('Borrar lote'))
    const dialogo = document.querySelector('[role="dialog"]')!
    expect(dialogo.textContent).toContain('3 subidas terminadas')
    expect(dialogo.textContent).toContain('fuera de este lote')
    expect(dialogo.textContent).toContain('Las 2 que siguen en cola o en marcha no se borran')
    expect(borrarLote).not.toHaveBeenCalled()
    await pulsar(boton('Borrar 3 subidas'))
    expect(borrarLote).toHaveBeenCalledWith(LOTE)
    await esperar(() => document.querySelector('.sub-lote-aviso')?.textContent ===
      '3 borradas (con 2 reintentos) · 2 siguen en cola o en marcha y no se han borrado')
    expect(vi.mocked(getUploads).mock.calls.length).toBeGreaterThan(peticiones)
    expect(document.querySelector('[role="dialog"]')).toBeNull()
    // El borrado suelto sigue siendo otra cosa.
    expect(deleteUploadJob).not.toHaveBeenCalled()
  })

  it('«Borrar lote» con todo terminado: la tabla dice que el lote ya no tiene subidas', async () => {
    vi.mocked(getLote).mockResolvedValue({ ...RESUMEN, en_cola: 0, en_marcha: 0, completadas: 3, puede_cancelar: false })
    vi.mocked(borrarLote).mockResolvedValue({ borradas: 3, intentos: 3, en_curso: 0, resumen: null })
    await filtrarPorLote()
    await pulsar(boton('Borrar lote'))
    // Tras borrar, el servidor ya no conoce el lote ni devuelve filas.
    vi.mocked(getUploads).mockImplementation(async q => (q?.lote_id ? [] : [LOTE_DE_UNO, SUELTA]))
    vi.mocked(getLote).mockRejectedValue(new ApiClientError('Lote no encontrado.', 404, null))
    await pulsar(boton('Borrar 3 subidas'))
    await esperar(() => texto().includes('Este lote ya no tiene subidas'))
    expect(document.querySelector('.sub-lote-aviso')!.textContent).toBe('3 borradas')
    expect(banner()!.querySelector('.sub-lote-banner-titulo')!.textContent).toBe('Lote sin subidas')
    expect(texto()).not.toContain('No hay subidas que coincidan con los filtros')

    await pulsar(boton('Quitar filtro del lote'))
    await esperar(() => document.querySelectorAll('tbody tr').length === 2)
    expect(banner()).toBeNull()
    expect(ultimaPeticion()?.lote_id).toBeUndefined()
  })

  it('«No borrar» cierra sin borrar nada, y sin terminadas no se puede borrar', async () => {
    await filtrarPorLote()
    await pulsar(boton('Borrar lote'))
    await pulsar(boton('No borrar'))
    expect(document.querySelector('[role="dialog"]')).toBeNull()
    expect(borrarLote).not.toHaveBeenCalled()

    await desmontar()
    vi.mocked(getLote).mockResolvedValue({ ...RESUMEN, completadas: 0, en_cola: 2 })
    await filtrarPorLote()
    expect(apagado('Borrar lote')).toBe(true)
    // Apagado, pulsarlo no abre la confirmación; y sigue sin disabled, para que el ratón y el foco lleguen al tooltip.
    expect(boton('Borrar lote')!.disabled).toBe(false)
    await pulsar(boton('Borrar lote'))
    expect(document.querySelector('[role="dialog"]')).toBeNull()
  })

  it('con la lista filtrada por el lote, las filas no repiten su chapa', async () => {
    await filtrarPorLote()
    expect(document.querySelectorAll('tbody tr').length).toBe(1)
    expect(chips()).toEqual([])
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

  it('solo se reintenta desde el último intento: el anterior no ofrece reintentar', async () => {
    vi.mocked(getUploads).mockResolvedValue([PUNTA, ORIGINAL])
    vi.mocked(countUploads).mockResolvedValue(2)
    await pagina()
    expect(document.querySelectorAll('tbody tr')).toHaveLength(1)
    await pulsar(document.querySelector('.sub-toggle-reintentos')!)
    const filas = [...document.querySelectorAll('tbody tr')]
    expect(filas).toHaveLength(2)
    const reintentar = (tr: Element) => tr.querySelector('button[aria-label="Reintentar"]')
    expect(filas[0].classList.contains('sub-fila-antigua')).toBe(false)
    expect(reintentar(filas[0])).not.toBeNull()
    expect(filas[1].classList.contains('sub-fila-antigua')).toBe(true)
    expect(reintentar(filas[1])).toBeNull()
    // Borrar sí: borra la cadena entera.
    expect(filas[1].querySelector('button[aria-label^="Borrar"]')).not.toBeNull()
  })

  it('cada fila ofrece solo lo que se puede hacer con ella', async () => {
    const VIVA = trabajo({ id: 7, status: 'running', title: 'En marcha', media_type: 'movie' })
    const HECHA = trabajo({ id: 8, status: 'completed', title: 'Hecha', media_type: 'movie' })
    vi.mocked(getUploads).mockResolvedValue([VIVA, HECHA, ORIGINAL])
    vi.mocked(countUploads).mockResolvedValue(3)
    await pagina()
    const acciones = (titulo: string) => [...filaDe(titulo).querySelectorAll('button[aria-label]')].map(b => b.getAttribute('aria-label'))
    expect(acciones('En marcha')).toEqual(['Cancelar'])
    expect(acciones('Hecha')).toEqual(['Borrar'])
    expect(acciones('Película')).toEqual(['Reintentar', 'Borrar'])
  })

  it('una subida fallida enseña el primer renglón de su error bajo el estado', async () => {
    vi.mocked(getUploads).mockResolvedValue([trabajo({ id: 9, status: 'failed', title: 'Rota', media_type: 'movie', error_message: 'Uploadrr falló\ncon la pila entera detrás' })])
    vi.mocked(countUploads).mockResolvedValue(1)
    await pagina()
    expect(filaDe('Rota').querySelector('.sub-estado-error')?.textContent).toBe('Uploadrr falló')
  })
})

describe('las acciones de la lista que fallan', () => {
  const ROTA = trabajo({ id: 21, status: 'failed', title: 'Rota', media_type: 'movie' })
  const VIVA = trabajo({ id: 22, status: 'running', title: 'Viva', media_type: 'movie' })
  beforeEach(() => {
    vi.mocked(getUploads).mockResolvedValue([ROTA, VIVA])
    vi.mocked(countUploads).mockResolvedValue(2)
  })
  const aviso = () => document.querySelector('.sub-seccion [role="alert"]')

  it('si reintentar falla, lo dice sobre la tabla y se puede cerrar', async () => {
    vi.mocked(retryUploadJobQueued).mockRejectedValue(new Error('Ya hay una subida activa para este elemento'))
    await pagina()
    expect(aviso()).toBeNull()
    await pulsar(filaDe('Rota').querySelector('button[aria-label="Reintentar"]')!)
    await esperar(() => aviso())
    expect(aviso()!.textContent).toContain('Ya hay una subida activa para este elemento')
    await pulsar(boton('Cerrar'))
    expect(aviso()).toBeNull()
  })

  it('si cancelar falla, lo dice con el título de la subida', async () => {
    vi.mocked(cancelUploadJob).mockRejectedValue(new Error('El trabajo ya terminó'))
    await pagina()
    await pulsar(filaDe('Viva').querySelector('button[aria-label="Cancelar"]')!)
    await esperar(() => aviso())
    expect(aviso()!.textContent).toContain('No se pudo cancelar «Viva»: El trabajo ya terminó')
  })

  it('si fallan un reintento y luego una cancelación, enseña el fallo más reciente', async () => {
    vi.mocked(retryUploadJobQueued).mockRejectedValue(new Error('Ya hay una subida activa para este elemento'))
    vi.mocked(cancelUploadJob).mockRejectedValue(new Error('El trabajo ya terminó'))
    await pagina()
    await pulsar(filaDe('Rota').querySelector('button[aria-label="Reintentar"]')!)
    await esperar(() => aviso())
    await pulsar(filaDe('Viva').querySelector('button[aria-label="Cancelar"]')!)
    await esperar(() => aviso()?.textContent?.includes('No se pudo cancelar') ?? false)
    expect(aviso()!.textContent).not.toContain('Ya hay una subida activa')
  })

  it('un reintento que falla tarde, después de una cancelación más reciente, no tapa su error', async () => {
    let rechazarReintento: (e: Error) => void = () => {}
    vi.mocked(retryUploadJobQueued).mockReturnValue(new Promise((_, rej) => { rechazarReintento = rej }) as never)
    vi.mocked(cancelUploadJob).mockRejectedValue(new Error('El trabajo ya terminó'))
    await pagina()
    await pulsar(filaDe('Rota').querySelector('button[aria-label="Reintentar"]')!)
    await pulsar(filaDe('Viva').querySelector('button[aria-label="Cancelar"]')!)
    await esperar(() => aviso()?.textContent?.includes('No se pudo cancelar') ?? false)
    await act(async () => { rechazarReintento(new Error('Ya hay una subida activa para este elemento')) })
    await esperar(() => true)
    expect(aviso()!.textContent).toContain('No se pudo cancelar')
    expect(aviso()!.textContent).not.toContain('Ya hay una subida activa')
  })

  it('un reintento que acaba bien tarde, después de una cancelación fallida, no abre su ficha ni borra el aviso', async () => {
    let resolverReintento: (r: unknown) => void = () => {}
    vi.mocked(retryUploadJobQueued).mockReturnValue(new Promise(res => { resolverReintento = res }) as never)
    vi.mocked(cancelUploadJob).mockRejectedValue(new Error('El trabajo ya terminó'))
    await pagina()
    await pulsar(filaDe('Rota').querySelector('button[aria-label="Reintentar"]')!)
    await pulsar(filaDe('Viva').querySelector('button[aria-label="Cancelar"]')!)
    await esperar(() => aviso()?.textContent?.includes('No se pudo cancelar') ?? false)
    await act(async () => { resolverReintento({ job: { id: 999 } }) })
    await esperar(() => true)
    expect(getUploadJob).not.toHaveBeenCalledWith(999)
    expect(aviso()!.textContent).toContain('No se pudo cancelar')
  })
})

describe('las columnas', () => {
  it('una sola columna Fecha, relativa, con las dos fechas exactas aparte', async () => {
    await pagina()
    const cab = [...document.querySelectorAll('thead th')].map(th => th.textContent?.trim())
    expect(cab).toContain('Fecha')
    expect(cab).not.toContain('Creado')
    expect(cab).not.toContain('Finalizado')
    expect(filaDe('Película suelta').querySelector('td.sub-fecha')!.textContent).toMatch(/^hace /)
  })

  it('sin ninguna subida, el vacío lleva a Biblioteca', async () => {
    vi.mocked(getUploads).mockResolvedValue([])
    vi.mocked(countUploads).mockResolvedValue(0)
    const navegar = vi.fn()
    await montar(
      <SyncContext.Provider value={{ lastInvalidatedAt: 0, startAllSync: vi.fn(), isAnySyncing: false, todoPendiente: false } as never}>
        <SeccionVisible visible><UploadsPage onNavigate={navegar} /></SeccionVisible>
      </SyncContext.Provider>,
    )
    await esperar(() => boton('Ir a Biblioteca'))
    expect(texto()).not.toContain('preflight')
    await pulsar(boton('Ir a Biblioteca'))
    expect(navegar).toHaveBeenCalledWith('library')
  })
})

describe('lista virtualizada pasadas las 50', () => {
  const muchas = (n: number) => Array.from({ length: n }, (_, i) =>
    trabajo({ id: 1000 + i, title: `Subida ${i}`, media_type: 'movie', created_at: `2026-11-04T10:${String(i % 60).padStart(2, '0')}:00` }))
  const pintadas = () => document.querySelectorAll('tbody tr.sub-tarjeta').length

  it('con 50 o menos se pinta entera', async () => {
    vi.mocked(getUploads).mockResolvedValue(muchas(50))
    vi.mocked(countUploads).mockResolvedValue(50)
    await pagina()
    expect(pintadas()).toBe(50)
    expect(document.querySelector('tr.fila-hueco')).toBeNull()
  })

  it('con más de 50 solo pinta lo que se ve, y cada subida con sus intentos anteriores en su bloque', async () => {
    const lista = muchas(80)
    lista[0] = trabajo({ ...lista[0], status: 'failed', retry_of_job_id: 999, retry_count: 1, created_at: '2026-11-05T10:00:00' })
    lista.push(trabajo({ id: 999, status: 'failed', title: 'Subida 0', media_type: 'movie', created_at: '2026-11-01T10:00:00' }))
    vi.mocked(getUploads).mockResolvedValue(lista)
    vi.mocked(countUploads).mockResolvedValue(81)
    await pagina()
    expect(pintadas()).toBeGreaterThan(0)
    expect(pintadas()).toBeLessThan(30)
    expect(document.querySelector('tr.fila-hueco')).not.toBeNull()
    await pulsar(document.querySelector('.sub-toggle-reintentos')!)
    const bloque = document.querySelector('tr.sub-fila-antigua')!.closest('tbody')!
    expect([...bloque.querySelectorAll('tr')].map(tr => tr.classList.contains('sub-fila-antigua'))).toEqual([false, true])
  })
})

describe('cancelar desde el detalle de una subida', () => {
  it('si falla, lo dice en el detalle y al volver a la lista no queda un aviso viejo', async () => {
    const VIVA = trabajo({ id: 22, status: 'running', title: 'Viva', media_type: 'movie' })
    vi.mocked(getUploads).mockResolvedValue([VIVA])
    vi.mocked(countUploads).mockResolvedValue(1)
    vi.mocked(getUploadJob).mockResolvedValue({ ...VIVA, display_title: 'Viva' })
    vi.mocked(cancelUploadJob).mockRejectedValue(new Error('El trabajo ya terminó'))
    await pagina()
    await pulsar(filaDe('Viva').querySelector('.sub-titulo')!)
    await esperar(() => document.querySelector('.dsub-resultado, .dsub-cabecera, [class*="dsub"]') !== null)
    const cancelar = [...document.querySelectorAll<HTMLButtonElement>('button')].find(b => b.textContent?.trim() === 'Cancelar')!
    await pulsar(cancelar)
    const confirmar = [...document.querySelectorAll<HTMLButtonElement>('[role="dialog"] button')].find(b => /Cancelar subida|Sí, cancelar|Cancelar la subida/.test(b.textContent ?? ''))
    if (confirmar) await pulsar(confirmar)
    await esperar(() => texto().includes('No se pudo cancelar'))
    await pulsar(boton('Volver') ?? [...document.querySelectorAll<HTMLButtonElement>('button')].find(b => /Volver|Subidas/.test(b.getAttribute('aria-label') ?? b.textContent ?? ''))!)
    await esperar(() => document.querySelectorAll('tbody tr').length > 0)
    expect(document.querySelector('.sub-seccion [role="alert"]')).toBeNull()
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

describe('el lote recién encolado desde Biblioteca', () => {
  afterEach(() => { sessionStorage.clear() })

  it('al entrar, la tabla sale filtrada por él y la marca se gasta', async () => {
    sessionStorage.setItem('emuwarez_open_lote', LOTE)
    await pagina()
    await esperar(() => ultimaPeticion()?.lote_id === LOTE)
    await esperar(() => banner()?.textContent?.includes('Lote de 3 subidas'))
    expect(sessionStorage.getItem('emuwarez_open_lote')).toBeNull()
  })

  it('con Subidas ya abierta, el aviso de la campana también la filtra por el lote', async () => {
    await pagina()
    await esperar(() => ultimaPeticion() !== undefined)
    expect(ultimaPeticion()?.lote_id).toBeUndefined()
    sessionStorage.setItem('emuwarez_open_lote', LOTE)
    await act(async () => { window.dispatchEvent(new CustomEvent('emuwarez:open-lote', { detail: LOTE })) })
    await esperar(() => ultimaPeticion()?.lote_id === LOTE)
    await esperar(() => banner()?.textContent?.includes('Lote de 3 subidas'))
    expect(sessionStorage.getItem('emuwarez_open_lote')).toBeNull()
  })

  it('un lote_id que no tiene la forma de uno no filtra nada', async () => {
    sessionStorage.setItem('emuwarez_open_lote', 'no-es-un-lote')
    await pagina()
    expect(ultimaPeticion()?.lote_id).toBeUndefined()
    expect(sessionStorage.getItem('emuwarez_open_lote')).toBeNull()
  })
})
