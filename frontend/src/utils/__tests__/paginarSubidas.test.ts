/**
 * «Cargar más» en Subidas. Sin el total (el recuento falló) la lista se quedaba sin forma de pedir otra página.
 */
import { describe, it, expect } from 'vitest'
import { hayMasPorCargar } from '../paginarSubidas'

const MAX = 2000

describe('si quedan subidas por cargar', () => {
  it('con el total conocido, mientras no estén todas', () => {
    expect(hayMasPorCargar(250, 100, 100, MAX)).toBe(true)
    expect(hayMasPorCargar(100, 100, 100, MAX)).toBe(false)
    expect(hayMasPorCargar(60, 60, 100, MAX)).toBe(false)
  })

  it('sin el total, mientras la lista llene el límite pedido', () => {
    expect(hayMasPorCargar(null, 100, 100, MAX)).toBe(true)
    expect(hayMasPorCargar(null, 60, 100, MAX)).toBe(false)
  })

  it('nunca más allá del máximo del servidor', () => {
    expect(hayMasPorCargar(5000, 2000, 2000, MAX)).toBe(false)
    expect(hayMasPorCargar(null, 2000, 2000, MAX)).toBe(false)
  })
})
