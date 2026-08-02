/**
 * Cuándo Biblioteca pide todos los niveles y no solo la raíz.
 *
 * La lista enseña el árbol pidiendo `parent_id = 0`. Todo filtro que no se
 * pueda resolver mirando solo la raíz tiene que estar aquí, y olvidarse de uno
 * no da ningún error: la tabla sale VACÍA y parece que no tienes nada de eso.
 */
import { describe, it, expect } from 'vitest'
import { necesitaTodosLosNiveles } from '../filtrosBiblioteca'

describe('cuándo hay que pedir la biblioteca en plano', () => {
  it('sin filtros, basta con la raíz (el árbol de siempre)', () => {
    expect(necesitaTodosLosNiveles({})).toBe(false)
  })

  // El fallo que reportó Alvaro: filtrar por Temporada dejaba la tabla vacía,
  // porque se seguía pidiendo solo la raíz y una temporada nunca es raíz.
  it.each(['season', 'episode'])('filtrar por %s exige todos los niveles', tipo => {
    expect(necesitaTodosLosNiveles({ filterType: tipo })).toBe(true)
  })

  it.each(['movie', 'series'])('%s sí es raíz, así que no hace falta', tipo => {
    expect(necesitaTodosLosNiveles({ filterType: tipo })).toBe(false)
  })

  // Se calculan sumando lo que hay por debajo: pidiendo solo la raíz se
  // escondería una temporada cuyos capítulos son todos de un proveedor dentro
  // de una serie de varios.
  it.each(['searchProvider', 'searchQuality', 'searchSource', 'filterEmu', 'filterAporte'])(
    '%s exige todos los niveles', clave => {
      expect(necesitaTodosLosNiveles({ [clave]: 'algo' })).toBe(true)
    })

  it('un filtro vacío no cuenta como puesto', () => {
    expect(necesitaTodosLosNiveles({
      searchProvider: '', searchQuality: '', searchSource: '',
      filterEmu: '', filterAporte: '', filterType: '',
    })).toBe(false)
  })

  it('combinados también', () => {
    expect(necesitaTodosLosNiveles({ filterType: 'movie', searchProvider: 'Netflix' })).toBe(true)
  })

  // Los filtros que SÍ se resuelven en la raíz no deben forzar el plano: el
  // árbol es lo que hace legible la lista.
  it('un filtro de estado no obliga a aplanar', () => {
    expect(necesitaTodosLosNiveles({ filterType: 'series' })).toBe(false)
  })
})
