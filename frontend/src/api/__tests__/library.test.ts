/**
 * La comparación con el catálogo de eMuwarez: sin parámetros pide lo de siempre, y con ellos manda la
 * resolución y el source que el asistente de subida va a poner en el nombre.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('../client', () => ({ api: { get: vi.fn(), post: vi.fn() } }))

import { api } from '../client'
import { getEmuComparison } from '../library'

const get = vi.mocked(api.get)

beforeEach(() => {
  get.mockReset()
  get.mockResolvedValue({})
})

describe('getEmuComparison', () => {
  it('sin lo tuyo pide la comparación a secas', async () => {
    await getEmuComparison(7)
    expect(get).toHaveBeenCalledWith('/library/7/emu-comparison')
  })

  it('con la resolución y el source de lo que se sube', async () => {
    await getEmuComparison(7, { resolution: '2160p', source: 'WEB-DL' })
    expect(get).toHaveBeenCalledWith('/library/7/emu-comparison?resolution=2160p&source=WEB-DL')
  })

  it('lo que falta no se manda', async () => {
    await getEmuComparison(7, { resolution: null, source: 'BluRay' })
    expect(get).toHaveBeenCalledWith('/library/7/emu-comparison?source=BluRay')
  })
})
