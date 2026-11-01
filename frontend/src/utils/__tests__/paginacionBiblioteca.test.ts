import { describe, expect, it } from 'vitest'
import { hayAlgunFiltro, necesitaTodosLosNiveles } from '../filtrosBiblioteca'
import { hayMasQueCargar, textoDeResultados, unirPagina } from '../paginacionBiblioteca'

describe('textoDeResultados', () => {
  it('avisa de que faltan filas por cargar, filtrando o no', () => {
    expect(textoDeResultados(20000, 21500, false)).toBe('Mostrando 20.000 de 21.500')
    expect(textoDeResultados(20000, 30000, true)).toBe('Mostrando 20.000 de 30.000')
  })

  it('con todo cargado dice cuántos resultados hay solo si se está filtrando', () => {
    expect(textoDeResultados(17800, 17800, false)).toBeNull()
    expect(textoDeResultados(651, 651, true)).toBe('651 resultados')
    expect(textoDeResultados(1, 1, true)).toBe('1 resultado')
    expect(textoDeResultados(0, 0, true)).toBe('0 resultados')
  })
})

describe('hayMasQueCargar', () => {
  it('es cierto mientras el total supere lo cargado', () => {
    expect(hayMasQueCargar(20000, 20001)).toBe(true)
    expect(hayMasQueCargar(20000, 20000)).toBe(false)
    expect(hayMasQueCargar(0, 0)).toBe(false)
  })
})

describe('unirPagina', () => {
  it('añade la página nueva detrás, en orden', () => {
    expect(unirPagina([{ id: 1 }, { id: 2 }], [{ id: 3 }, { id: 4 }]).map(i => i.id)).toEqual([1, 2, 3, 4])
  })

  it('no repite una fila que ya estaba cargada', () => {
    expect(unirPagina([{ id: 1 }, { id: 2 }], [{ id: 2 }, { id: 3 }]).map(i => i.id)).toEqual([1, 2, 3])
  })

  it('no toca lo ya cargado', () => {
    const actual = [{ id: 1 }]
    unirPagina(actual, [{ id: 2 }])
    expect(actual).toEqual([{ id: 1 }])
  })
})

describe('con un filtro que oculta', () => {
  // Ocultar un valor de una columna es un filtro como otro: pide todos los niveles y cuenta los resultados.
  const filtros = { searchGroup: ['!B'] }

  it('cuenta como filtro activo y pide la biblioteca en plano', () => {
    expect(hayAlgunFiltro(filtros)).toBe(true)
    expect(necesitaTodosLosNiveles(filtros)).toBe(true)
  })

  it('dice cuántos resultados quedan, y «N de M» si falta cargar', () => {
    expect(textoDeResultados(4, 4, hayAlgunFiltro(filtros))).toBe('4 resultados')
    expect(textoDeResultados(3, 4, hayAlgunFiltro(filtros))).toBe('Mostrando 3 de 4')
  })
})
