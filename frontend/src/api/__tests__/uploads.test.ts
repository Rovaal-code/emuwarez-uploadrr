/**
 * Lo que la lista de Subidas pide al servidor: sin las filas preparatorias (que ocupaban sitio en la página), con
 * el límite explícito, y el registro por partes.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('../client', () => ({ api: { get: vi.fn(), post: vi.fn() } }))

import { api } from '../client'
import { countUploads, getUploadJobLogs, getUploads } from '../uploads'

const get = vi.mocked(api.get)

beforeEach(() => {
  get.mockReset()
  get.mockResolvedValue([])
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
