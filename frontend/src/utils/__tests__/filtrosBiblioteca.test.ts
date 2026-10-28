/**
 * Cuándo Biblioteca pide todos los niveles y no solo la raíz.
 *
 * Esto empezó siendo una lista de casos y por eso falló: enumerar los filtros
 * que aplanan hace que se olviden, y olvidarse de uno no da ningún error —
 * la tabla sale VACÍA y parece que no tienes nada de eso. Medido en la
 * auditoría, con 11 elementos: filtrar por Episodio devolvía 0 de 4, por
 * "Sin petición" 0 de 4, y buscar el título de un capítulo 0 de 1.
 *
 * Así que la regla es una: si hay algo filtrado, se pide en plano. Con UNA
 * excepción, buscar, que se trata en el segundo bloque.
 */
import { describe, it, expect } from 'vitest'
import { necesitaTodosLosNiveles, hayAlgunFiltro } from '../filtrosBiblioteca'

// Los filtros de los desplegables. Si mañana se añade uno, va aquí y el test
// de abajo lo obliga a comportarse como los demás. Buscar NO está: tiene su
// propio bloque porque hace otra cosa.
const TODOS_LOS_FILTROS = [
  'filterType', 'filterStatus', 'filterInstanceId', 'filterRequest',
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
  ])('%s (salía vacío)', (_nombre, filtros) => {
    expect(necesitaTodosLosNiveles(filtros)).toBe(true)
  })

  it('hayAlgunFiltro es otra pregunta: ahí buscar SÍ cuenta como filtro', () => {
    expect(hayAlgunFiltro({ filterStatus: 'Disponible' })).toBe(true)
    expect(hayAlgunFiltro({ search: 'One Piece' })).toBe(true)
    expect(hayAlgunFiltro({})).toBe(false)
  })
})

/**
 * Buscar aplanaba como los demás, y con una serie larga era inservible: los
 * títulos de temporadas y capítulos llevan dentro el de la serie, así que
 * buscar "One Piece" acertaba en los tres niveles y devolvía la serie, sus
 * temporadas y todos sus capítulos como filas hermanas.
 *
 * Ahora la vista sigue siendo el árbol y es el BACKEND el que sube cada
 * acierto hasta su serie (services/library.py::_build_library_filter, con la
 * misma pareja de casos comprobada en tests/test_busqueda_biblioteca.py).
 */
describe('buscar es la excepción: mantiene el árbol', () => {
  it('buscar el nombre de una serie no aplana', () => {
    expect(necesitaTodosLosNiveles({ search: 'One Piece' })).toBe(false)
  })

  it('buscar el título de un capítulo tampoco: sale su serie', () => {
    expect(necesitaTodosLosNiveles({ search: 'T2E1' })).toBe(false)
  })

  // Buscar no aplana, pero tampoco impide que otro filtro lo haga: quien pone
  // Tipo = Episodio está pidiendo capítulos sueltos a propósito.
  it('con otro filtro puesto, ese otro manda y se aplana igual', () => {
    expect(necesitaTodosLosNiveles({ search: 'One Piece', filterType: 'episode' })).toBe(true)
  })
})

describe('columnas con varios valores', () => {
  it('una lista vacía no cuenta como filtro y una con algo sí', () => {
    expect(necesitaTodosLosNiveles({ filterType: [], searchSource: [] })).toBe(false)
    expect(necesitaTodosLosNiveles({ filterInstanceId: ['1', '2'] })).toBe(true)
  })
})
