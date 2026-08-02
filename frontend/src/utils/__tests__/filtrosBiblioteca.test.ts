/**
 * Cuándo Biblioteca pide todos los niveles y no solo la raíz.
 *
 * Esto empezó siendo una lista de casos y por eso falló: enumerar los filtros
 * que aplanan hace que se olviden, y olvidarse de uno no da ningún error —
 * la tabla sale VACÍA y parece que no tienes nada de eso. Medido en la
 * auditoría, con 11 elementos: filtrar por Episodio devolvía 0 de 4, por
 * "Sin petición" 0 de 4, y buscar el título de un capítulo 0 de 1.
 *
 * Así que la regla es una: si hay algo filtrado, se pide en plano.
 */
import { describe, it, expect } from 'vitest'
import { necesitaTodosLosNiveles, hayAlgunFiltro } from '../filtrosBiblioteca'

// Todos los filtros de la pantalla. Si mañana se añade uno, va aquí y el test
// de abajo lo obliga a comportarse como los demás.
const TODOS_LOS_FILTROS = [
  'search', 'filterType', 'filterStatus', 'filterInstanceId', 'filterRequest',
  'filterSpanish', 'searchProvider', 'searchQuality', 'searchSource',
  'filterEmu', 'filterAporte',
] as const

describe('cuándo hay que pedir la biblioteca en plano', () => {
  it('sin nada puesto se queda el árbol, que es la vista de partida', () => {
    expect(necesitaTodosLosNiveles({})).toBe(false)
  })

  it.each(TODOS_LOS_FILTROS)('%s puesto obliga a aplanar', clave => {
    expect(necesitaTodosLosNiveles({ [clave]: 'algo' })).toBe(true)
  })

  it('un filtro en blanco no cuenta como puesto', () => {
    const enBlanco = Object.fromEntries(TODOS_LOS_FILTROS.map(k => [k, '']))
    expect(necesitaTodosLosNiveles(enBlanco)).toBe(false)
  })

  it('varios a la vez también', () => {
    expect(necesitaTodosLosNiveles({ filterType: 'movie', searchProvider: 'Netflix' })).toBe(true)
  })

  // Los casos concretos que se midieron rotos, por su nombre, para que si
  // alguien vuelve a recortar la regla se vea qué se rompe.
  it.each([
    ['Tipo = Episodio', { filterType: 'episode' }],
    ['Tipo = Temporada', { filterType: 'season' }],
    ['Petición = Sin petición', { filterRequest: 'Sin petición' }],
    ['Petición = No compatible', { filterRequest: 'No compatible' }],
    ['Español = Sí', { filterSpanish: 'yes' }],
    ['buscar el título de un capítulo', { search: 'T2E1' }],
  ])('%s (salía vacío)', (_nombre, filtros) => {
    expect(necesitaTodosLosNiveles(filtros)).toBe(true)
  })

  it('hayAlgunFiltro es la misma pregunta, por si hace falta en otro sitio', () => {
    expect(hayAlgunFiltro({ filterStatus: 'Disponible' })).toBe(true)
    expect(hayAlgunFiltro({})).toBe(false)
  })
})
