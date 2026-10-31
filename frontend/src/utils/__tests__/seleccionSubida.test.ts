/**
 * Lo que sube el asistente sale de un único valor: elegir "Temporada entera"
 * después de unos capítulos no puede dejar la cola de capítulos viva (subía los
 * capítulos sueltos con el nombre del pack), y elegir otros capítulos no puede
 * reutilizar la caché de los anteriores.
 */
import { describe, it, expect } from 'vitest'
import {
  SIN_SELECCION, seleccionUnica, seleccionTemporadas, seleccionCapitulos,
  colaTemporadas, colaCapitulos, esTanda, mismaSeleccion, conObjetivo,
  cacheCubre, conAjustes, peticionCubre,
} from '../seleccionSubida'

describe('una sola cola', () => {
  it('capítulos y luego temporada entera: la cola de capítulos desaparece', () => {
    const capitulos = seleccionCapitulos([11, 12, 13])
    expect(colaCapitulos(capitulos)).toEqual([11, 12, 13])
    expect(esTanda(capitulos)).toBe(true)

    const entera = seleccionUnica(7, true)
    expect(colaCapitulos(entera)).toEqual([])
    expect(colaTemporadas(entera)).toEqual([])
    expect(esTanda(entera)).toBe(false)
    expect(entera.objetivo).toBe(7)
    expect(entera.esTemporada).toBe(true)
  })

  it('cada modo solo expone su cola', () => {
    const temporadas = seleccionTemporadas([1, 2])
    expect(colaTemporadas(temporadas)).toEqual([1, 2])
    expect(colaCapitulos(temporadas)).toEqual([])
    expect(temporadas.esTemporada).toBe(true)

    const capitulos = seleccionCapitulos([5, 6])
    expect(colaTemporadas(capitulos)).toEqual([])
    expect(capitulos.esTemporada).toBe(false)
  })

  it('empieza por el primero de la cola', () => {
    expect(seleccionCapitulos([4, 5]).objetivo).toBe(4)
    expect(seleccionTemporadas([9]).objetivo).toBe(9)
    expect(seleccionCapitulos([]).objetivo).toBeNull()
  })

  it('un solo capítulo o una sola temporada no es tanda', () => {
    expect(esTanda(seleccionCapitulos([4]))).toBe(false)
    expect(esTanda(seleccionTemporadas([9]))).toBe(false)
    expect(esTanda(SIN_SELECCION)).toBe(false)
  })
})

describe('mismaSeleccion', () => {
  it('los mismos ids en el mismo orden son lo mismo elegido', () => {
    expect(mismaSeleccion(seleccionCapitulos([1, 2, 3]), seleccionCapitulos([1, 2, 3]))).toBe(true)
  })

  it('otros ids con la misma cantidad no lo son', () => {
    expect(mismaSeleccion(seleccionCapitulos([1, 2, 3]), seleccionCapitulos([2, 3, 4]))).toBe(false)
  })

  it('el mismo conjunto en otro modo no lo es', () => {
    expect(mismaSeleccion(seleccionCapitulos([1]), seleccionTemporadas([1]))).toBe(false)
    expect(mismaSeleccion(seleccionUnica(7, true), seleccionTemporadas([7]))).toBe(false)
    expect(mismaSeleccion(seleccionUnica(7, true), seleccionUnica(7, false))).toBe(false)
  })

  it('el elemento que se estaba viendo no cuenta', () => {
    const vista = conObjetivo(seleccionCapitulos([1, 2, 3]), 3)
    expect(mismaSeleccion(vista, seleccionCapitulos([1, 2, 3]))).toBe(true)
  })

  it('dos únicos se comparan por su objetivo', () => {
    expect(mismaSeleccion(seleccionUnica(7, true), seleccionUnica(7, true))).toBe(true)
    expect(mismaSeleccion(seleccionUnica(7, true), seleccionUnica(8, true))).toBe(false)
    expect(mismaSeleccion(SIN_SELECCION, seleccionUnica(7, true))).toBe(false)
  })
})

describe('conObjetivo', () => {
  it('cambia de elemento dentro de la cola sin tocar la cola', () => {
    const s = conObjetivo(seleccionCapitulos([1, 2, 3]), 2)
    expect(s.objetivo).toBe(2)
    expect(colaCapitulos(s)).toEqual([1, 2, 3])
  })

  it('ignora un id que no está en la cola', () => {
    const base = seleccionCapitulos([1, 2, 3])
    expect(conObjetivo(base, 99)).toBe(base)
  })
})

describe('cacheCubre', () => {
  it('compara ids, no cantidad: E2,E3,E4 con la caché de E1,E2,E3 no está cubierto', () => {
    const cache = new Map<number, unknown>([[1, 'a'], [2, 'b'], [3, 'c']])
    expect(cacheCubre([1, 2, 3], cache)).toBe(true)
    expect(cacheCubre([2, 3, 4], cache)).toBe(false)
  })

  it('con la caché vacía no cubre nada, y una cola vacía siempre está cubierta', () => {
    expect(cacheCubre([1], new Map())).toBe(false)
    expect(cacheCubre([], new Map())).toBe(true)
  })
})

describe('conAjustes', () => {
  const ajustes = { source: 'WEB-DL', provider: 'AMZN', tag: 'EMUWAREZ', title: 'Los Tudor' }

  it('guarda los ajustes si los campos son de ese elemento', () => {
    const r = conAjustes(new Map(), 5, 5, ajustes)
    expect(r.get(5)).toEqual(ajustes)
  })

  it('no guarda los de la temporada anterior mientras carga la nueva', () => {
    // Campos de la temporada 1, y se intenta apuntarlos a la 2.
    const r = conAjustes(new Map(), 2, 1, ajustes)
    expect(r.has(2)).toBe(false)
  })

  it('con un objetivo sin cargar tampoco guarda nada', () => {
    expect(conAjustes(new Map(), null, null, ajustes).size).toBe(0)
    expect(conAjustes(new Map(), 3, null, ajustes).size).toBe(0)
  })

  it('devuelve una copia y conserva lo que ya había', () => {
    const previo = new Map([[1, { source: 'BluRay' }]])
    const r = conAjustes(previo, 2, 2, ajustes)
    expect(r).not.toBe(previo)
    expect(r.get(1)).toEqual({ source: 'BluRay' })
    expect(previo.has(2)).toBe(false)
  })
})

describe('peticionCubre', () => {
  it('una petición de la temporada 2 no cubre la 1 ni la 3', () => {
    const alcance = { season: 2, episode: null }
    expect(peticionCubre(alcance, { season_number: 2 })).toBe(true)
    expect(peticionCubre(alcance, { season_number: 1 })).toBe(false)
    expect(peticionCubre(alcance, { season_number: 3 })).toBe(false)
  })

  it('una petición de un capítulo solo cubre ese', () => {
    const alcance = { season: 2, episode: 4 }
    expect(peticionCubre(alcance, { season_number: 2, episode_number: 4 })).toBe(true)
    expect(peticionCubre(alcance, { season_number: 2, episode_number: 5 })).toBe(false)
  })

  it('la temporada entera cubre el capítulo pedido', () => {
    expect(peticionCubre({ season: 2, episode: 4 }, { season_number: 2, episode_number: null })).toBe(true)
  })

  it('una petición de la serie, o sin alcance, lo cubre todo', () => {
    expect(peticionCubre({ season: null, episode: null }, { season_number: 3 })).toBe(true)
    expect(peticionCubre(undefined, { season_number: 3, episode_number: 9 })).toBe(true)
  })

  it('lo que no se puede comparar cuenta como cubierto', () => {
    expect(peticionCubre({ season: 2, episode: 4 }, {})).toBe(true)
    expect(peticionCubre({ season: 2, episode: null }, { season_number: null })).toBe(true)
  })
})
