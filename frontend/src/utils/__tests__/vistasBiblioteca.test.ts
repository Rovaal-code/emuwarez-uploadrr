// @vitest-environment jsdom
/** Las vistas guardadas de Biblioteca: se guardan en el navegador, se recuperan aunque lo guardado venga torcido y no se duplican por nombre. */
import { afterEach, describe, expect, it } from 'vitest'
import {
  SIN_FILTROS, cargarVistas, conVista, hayAlgoQueGuardar, mismosFiltros, persistirVistas, sinVista,
  type FiltrosDeVista,
} from '../vistasBiblioteca'

const CLAVE = 'emuwarez_uploadrr_library_views'
const FLUX: FiltrosDeVista = { ...SIN_FILTROS, group: ['FLUX'], sort: 'size_desc' }

afterEach(() => localStorage.clear())

describe('hayAlgoQueGuardar', () => {
  it('con todo en su sitio no hay nada que guardar', () => {
    expect(hayAlgoQueGuardar(SIN_FILTROS)).toBe(false)
  })

  it('un filtro, una búsqueda o un orden distinto sí', () => {
    expect(hayAlgoQueGuardar({ ...SIN_FILTROS, quality: ['1080p'] })).toBe(true)
    expect(hayAlgoQueGuardar({ ...SIN_FILTROS, search: 'dune' })).toBe(true)
    expect(hayAlgoQueGuardar({ ...SIN_FILTROS, sort: 'year_desc' })).toBe(true)
  })
})

describe('mismosFiltros', () => {
  it('compara los valores, no las referencias', () => {
    expect(mismosFiltros(FLUX, { ...FLUX, group: ['FLUX'] })).toBe(true)
    expect(mismosFiltros(FLUX, { ...FLUX, group: ['NTb'] })).toBe(false)
    expect(mismosFiltros(FLUX, { ...FLUX, sort: 'size_asc' })).toBe(false)
  })
})

describe('conVista y sinVista', () => {
  it('añade la vista con su nombre sin espacios sobrantes', () => {
    const v = conVista([], '  Solo FLUX ', FLUX, 'a')
    expect(v).toEqual([{ id: 'a', nombre: 'Solo FLUX', filtros: FLUX }])
  })

  it('con el mismo nombre (sin mirar mayúsculas) sustituye la anterior', () => {
    const una = conVista([], 'Solo FLUX', FLUX, 'a')
    const dos = conVista(una, 'solo flux', { ...FLUX, group: ['NTb'] }, 'b')
    expect(dos).toHaveLength(1)
    expect(dos[0].id).toBe('b')
    expect(dos[0].filtros.group).toEqual(['NTb'])
  })

  it('un nombre vacío no añade nada', () => {
    expect(conVista([], '   ', FLUX, 'a')).toEqual([])
  })

  it('quita solo la vista pedida', () => {
    const v = conVista(conVista([], 'Una', FLUX, 'a'), 'Otra', SIN_FILTROS, 'b')
    expect(sinVista(v, 'a').map(x => x.id)).toEqual(['b'])
  })
})

describe('persistencia', () => {
  it('lo guardado vuelve igual', () => {
    const v = conVista([], 'Solo FLUX', FLUX, 'a')
    persistirVistas(v)
    expect(cargarVistas()).toEqual(v)
  })

  it('sin nada guardado, ninguna vista', () => {
    expect(cargarVistas()).toEqual([])
  })

  it('un JSON roto no tumba la página', () => {
    localStorage.setItem(CLAVE, '{no es json')
    expect(cargarVistas()).toEqual([])
    localStorage.setItem(CLAVE, '{"a": 1}')
    expect(cargarVistas()).toEqual([])
  })

  it('tira las entradas sin nombre o sin id y completa los filtros que faltan', () => {
    localStorage.setItem(CLAVE, JSON.stringify([
      { id: 'a', nombre: 'Buena', filtros: { group: ['FLUX', 3], sort: 'size_desc' } },
      { id: 'b', nombre: '  ' },
      { nombre: 'Sin id' },
      null,
    ]))
    expect(cargarVistas()).toEqual([
      { id: 'a', nombre: 'Buena', filtros: { ...SIN_FILTROS, group: ['FLUX'], sort: 'size_desc' } },
    ])
  })
})
