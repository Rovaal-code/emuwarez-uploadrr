/**
 * El `lote_id` que agrupa las subidas de una tanda: siempre 12 hex en minúscula (el servidor rechaza cualquier otra
 * cosa con un 422), distinto en cada tanda, y también sin `crypto.getRandomValues`.
 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { MAX_ELEMENTOS_LOTE, PATRON_LOTE_ID, nuevoLoteId } from '../lote'

afterEach(() => { vi.unstubAllGlobals() })

describe('nuevoLoteId', () => {
  it('da 12 caracteres hexadecimales en minúscula', () => {
    for (let i = 0; i < 50; i++) expect(nuevoLoteId()).toMatch(PATRON_LOTE_ID)
  })

  it('cada tanda lleva el suyo', () => {
    const ids = new Set(Array.from({ length: 50 }, () => nuevoLoteId()))
    expect(ids.size).toBe(50)
  })

  it('sin crypto, tira de Math.random y sigue dando el mismo formato', () => {
    vi.stubGlobal('crypto', undefined)
    const id = nuevoLoteId()
    expect(id).toMatch(PATRON_LOTE_ID)
  })
})

describe('el patrón del lote', () => {
  it('rechaza mayúsculas, longitudes distintas y lo que no es hexadecimal', () => {
    expect(PATRON_LOTE_ID.test('0123456789ab')).toBe(true)
    expect(PATRON_LOTE_ID.test('0123456789AB')).toBe(false)
    expect(PATRON_LOTE_ID.test('0123456789a')).toBe(false)
    expect(PATRON_LOTE_ID.test('0123456789abc')).toBe(false)
    expect(PATRON_LOTE_ID.test('0123456789ag')).toBe(false)
  })

  it('el tope de elementos es el del servidor', () => {
    expect(MAX_ELEMENTOS_LOTE).toBe(50)
  })
})
