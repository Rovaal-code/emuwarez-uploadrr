/**
 * El `lote_id` que agrupa las subidas de una tanda: siempre 12 hex en minúscula (el servidor rechaza cualquier otra
 * cosa con un 422), distinto en cada tanda, y también sin `crypto.getRandomValues`.
 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { LibraryItemResponse } from '../../types/api'
import {
  MAX_ELEMENTOS_LOTE, PATRON_LOTE_ID, marcadaPorDefecto, nombresRepetidos, nuevoLoteId, razonNoSubible,
} from '../lote'

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

const pelicula = (parcial: Partial<LibraryItemResponse> = {}) =>
  ({ id: 1, item_type: 'movie', title: 'Dune', local_status: 'Disponible', has_spanish_ok: 1, ...parcial }) as LibraryItemResponse

describe('razonNoSubible', () => {
  it('una película en disco y con castellano se puede subir, también si ya se subió', () => {
    expect(razonNoSubible(pelicula())).toBeNull()
    expect(razonNoSubible(pelicula({ local_status: 'Subido' }))).toBeNull()
  })

  it('habla de la película, no del capítulo', () => {
    const razon = razonNoSubible(pelicula({ local_status: 'Faltante' }))!
    expect(razon).toBe('La película está «Faltante»: no la tienes en disco.')
    expect(razon).not.toContain('capítulo')
  })

  it('un capítulo dice «el capítulo»', () => {
    expect(razonNoSubible(pelicula({ item_type: 'episode', local_status: 'Faltante' })))
      .toBe('El capítulo está «Faltante»: no lo tienes en disco.')
  })

  it('sin castellano, o sin poder leer sus pistas, no se puede', () => {
    expect(razonNoSubible(pelicula({ has_spanish_ok: 0 }))).toBe('No tiene castellano ni en el audio ni en los subtítulos.')
    expect(razonNoSubible(pelicula({ has_spanish_ok: null }))).toContain('no se puede confirmar que tenga castellano')
  })

  it('una serie o una temporada todavía no van por lotes', () => {
    expect(razonNoSubible(pelicula({ item_type: 'series' }))).toBe('Por ahora el lote solo admite películas.')
    expect(razonNoSubible(pelicula({ item_type: 'season' }))).toBe('Por ahora el lote solo admite películas.')
  })
})

describe('marcadaPorDefecto', () => {
  it('desmarca un duplicado y una copia peor que todo lo que hay', () => {
    expect(marcadaPorDefecto('duplicado')).toBe(false)
    expect(marcadaPorDefecto('peor')).toBe(false)
  })

  it('marca el resto, también sin nada con lo que comparar', () => {
    expect(marcadaPorDefecto(null)).toBe(true)
    expect(marcadaPorDefecto('trump')).toBe(true)
    expect(marcadaPorDefecto('mixto')).toBe(true)
    expect(marcadaPorDefecto('sin-comparar')).toBe(true)
  })
})

describe('nombresRepetidos', () => {
  it('marca las dos filas con el mismo nombre final, no las demás', () => {
    expect(nombresRepetidos([
      { id: 1, nombre: 'Dune (2021) 1080p WEB-DL' },
      { id: 2, nombre: 'Dune (2021) 2160p WEB-DL' },
      { id: 3, nombre: 'Dune (2021) 1080p WEB-DL ' },
    ])).toEqual(new Set([1, 3]))
  })

  it('sin nombre no cuenta como repetido', () => {
    expect(nombresRepetidos([{ id: 1, nombre: null }, { id: 2, nombre: '' }, { id: 3, nombre: undefined }]).size).toBe(0)
  })
})
