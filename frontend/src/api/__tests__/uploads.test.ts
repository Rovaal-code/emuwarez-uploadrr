/**
 * Lo que la lista de Subidas pide al servidor: sin las filas preparatorias (que ocupaban sitio en la página), con
 * el límite explícito, y el registro por partes. Y el lote: el filtro de la lista y el `lote_id` al encolar, que una
 * subida suelta no manda.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('../client', () => ({ api: { get: vi.fn(), post: vi.fn() } }))

import { api } from '../client'
import { borrarLote, cancelarLote, countUploads, getLote, getUploadJobLogs, getUploads, queueLote, queueUpload, reintentarLote } from '../uploads'

const get = vi.mocked(api.get)
const post = vi.mocked(api.post)

beforeEach(() => {
  get.mockReset()
  get.mockResolvedValue([])
  post.mockReset()
  post.mockResolvedValue({ status: 'queued', job: null, errors: [] })
})

describe('la lista de subidas', () => {
  it('pide sin preparatorias y con el límite', async () => {
    await getUploads({ hide_preparatory: true, limit: 100 })
    expect(get).toHaveBeenCalledWith('/uploads?hide_preparatory=true&limit=100')
  })

  it('sin parámetros no añade nada', async () => {
    await getUploads()
    expect(get).toHaveBeenCalledWith('/uploads')
  })

  it('el total lleva los mismos filtros que la lista, menos el límite', async () => {
    get.mockResolvedValue({ total: 342 })
    expect(await countUploads({ status: 'failed', hide_preparatory: true })).toBe(342)
    expect(get).toHaveBeenCalledWith('/uploads/count?status=failed&hide_preparatory=true')
  })

  it('filtrada por lote: la lista y el total llevan el lote_id', async () => {
    await getUploads({ hide_preparatory: true, lote_id: '0123456789ab', limit: 100 })
    expect(get).toHaveBeenCalledWith('/uploads?hide_preparatory=true&limit=100&lote_id=0123456789ab')
    get.mockResolvedValue({ total: 3 })
    expect(await countUploads({ hide_preparatory: true, lote_id: '0123456789ab' })).toBe(3)
    expect(get).toHaveBeenCalledWith('/uploads/count?hide_preparatory=true&lote_id=0123456789ab')
  })
})

describe('encolar una subida', () => {
  it('suelta: el cuerpo no lleva lote_id', async () => {
    await queueUpload(10)
    const [ruta, cuerpo] = post.mock.calls[0]
    expect(ruta).toBe('/library/10/upload/queue')
    expect(cuerpo).not.toHaveProperty('lote_id')
  })

  it('de una tanda: el 7.º argumento viaja como lote_id', async () => {
    await queueUpload(21, undefined, null, null, undefined, 5, 'abcdef012345')
    expect(post.mock.calls[0][1]).toEqual(expect.objectContaining({ request_item_id: 5, lote_id: 'abcdef012345' }))
  })
})

describe('las acciones de un lote', () => {
  it('el resumen se pide por su lote_id', async () => {
    await getLote('0123456789ab')
    expect(get).toHaveBeenCalledWith('/uploads/lotes/0123456789ab')
  })

  it('cancelar pendientes manda si solo son las de la cola', async () => {
    await cancelarLote('0123456789ab', true)
    expect(post).toHaveBeenLastCalledWith('/uploads/lotes/0123456789ab/cancelar', { solo_pendientes: true })
    await cancelarLote('0123456789ab', false)
    expect(post).toHaveBeenLastCalledWith('/uploads/lotes/0123456789ab/cancelar', { solo_pendientes: false })
  })

  it('reintentar fallidas reanuda por defecto, o lo rehace todo si se pide', async () => {
    await reintentarLote('0123456789ab')
    expect(post).toHaveBeenLastCalledWith('/uploads/lotes/0123456789ab/reintentar', { desde_el_principio: false })
    await reintentarLote('0123456789ab', true)
    expect(post).toHaveBeenLastCalledWith('/uploads/lotes/0123456789ab/reintentar', { desde_el_principio: true })
  })

  it('borrar el lote manda el mismo token que el borrado suelto', async () => {
    await borrarLote('0123456789ab')
    expect(post).toHaveBeenLastCalledWith('/uploads/lotes/0123456789ab/borrar', { confirmation: 'BORRAR_SUBIDA' })
  })
})

describe('el registro de una subida', () => {
  it('el final: sin cursor', async () => {
    await getUploadJobLogs(7, 2000, 0, true)
    expect(get).toHaveBeenCalledWith('/uploads/7/logs?limit=2000&offset=0&tail=true')
  })

  it('lo nuevo: con la secuencia de la última línea que se tiene', async () => {
    await getUploadJobLogs(7, 5000, 0, false, 120)
    expect(get).toHaveBeenCalledWith('/uploads/7/logs?limit=5000&offset=0&tail=false&after_sequence=120')
  })
})

describe('«Subir por lotes»', () => {
  it('manda los elementos en su orden, tal cual', async () => {
    post.mockResolvedValue({ lote_id: '0123456789ab', encolados: 2, saltados: 0, resultados: [] })
    const checks = { checks: [], ready: true }
    const elementos = [
      { item_id: 12, checks, campos: { title: 'Dune', provider: 'AMZN' } },
      { item_id: 11, checks },
    ]
    expect((await queueLote(elementos)).encolados).toBe(2)
    expect(post).toHaveBeenCalledWith('/uploads/lote', { elementos })
  })
})
