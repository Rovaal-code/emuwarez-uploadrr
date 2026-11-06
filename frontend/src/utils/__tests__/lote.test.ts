/**
 * El `lote_id` que agrupa las subidas de una tanda: siempre 12 hex en minúscula (el servidor rechaza cualquier otra
 * cosa con un 422), distinto en cada tanda, y también sin `crypto.getRandomValues`.
 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { LibraryItemResponse } from '../../types/api'
import type { DashboardRecommendationItem } from '../../api/dashboard'
import {
  MAX_ELEMENTOS_LOTE, PATRON_LOTE_ID, claveDelPanel, entradaDePeticion, entradaDelPanel, expandirEntradas,
  expandirSeleccion, marcadaPorDefecto, nombresRepetidos, nuevoLoteId, peticionSeleccionableEnLote, razonNoSubible,
  seleccionableEnLote, conAvisoDeLote, loteDeNotificacion,
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

  it('«no la tienes en disco» solo con Faltante: una que se está subiendo sí está en disco', () => {
    const razon = razonNoSubible(pelicula({ local_status: 'Subiendo' }))!
    expect(razon).toBe('La película está «Subiendo»: ahora no se puede subir.')
    expect(razon).not.toContain('disco')
    expect(razonNoSubible(pelicula({ item_type: 'episode', local_status: 'Error' })))
      .toBe('El capítulo está «Error»: ahora no se puede subir.')
  })

  it('sin castellano, o sin poder leer sus pistas, no se puede', () => {
    expect(razonNoSubible(pelicula({ has_spanish_ok: 0 }))).toBe('No tiene castellano ni en el audio ni en los subtítulos.')
    expect(razonNoSubible(pelicula({ has_spanish_ok: null }))).toContain('no se puede confirmar que tenga castellano')
  })

  it('una temporada entra si se puede subir como pack, y si no, con el motivo de seasonNotReadyReason', () => {
    const temporada = (parcial: Partial<LibraryItemResponse> = {}) =>
      pelicula({ item_type: 'season', resolution: '1080p', video_codec: 'x264', ...parcial })
    expect(razonNoSubible(temporada())).toBeNull()
    expect(razonNoSubible(temporada({ local_status: 'Parcial' })))
      .toBe('Temporada incompleta: no todos los capítulos están Disponibles.')
    expect(razonNoSubible(temporada({ video_codec: null }))).toContain('no coinciden en el códec de vídeo')
    expect(razonNoSubible(temporada({ has_spanish_ok: 0 }))).toContain('no tiene castellano')
  })

  it('una serie no entra tal cual: se cambia por sus temporadas', () => {
    expect(razonNoSubible(pelicula({ item_type: 'series' }))).toBe('Una serie se sube por temporadas.')
  })
})

describe('seleccionableEnLote', () => {
  it('películas, series y temporadas; capítulos no', () => {
    expect(seleccionableEnLote(pelicula())).toBe(true)
    expect(seleccionableEnLote(pelicula({ item_type: 'series' }))).toBe(true)
    expect(seleccionableEnLote(pelicula({ item_type: 'season' }))).toBe(true)
    expect(seleccionableEnLote(pelicula({ item_type: 'episode' }))).toBe(false)
  })
})

describe('expandirSeleccion', () => {
  const de = (id: number, item_type: string, parcial: Partial<LibraryItemResponse> = {}) =>
    pelicula({ id, item_type, title: `#${id}`, ...parcial })
  const T = (id: number, serie: number, n: number) => de(id, 'season', { parent_id: serie, season_number: n })

  it('cambia cada serie por sus temporadas, en orden de temporada y en el orden en que se marcó', () => {
    const fuera = expandirSeleccion(
      [de(1, 'movie'), de(10, 'series'), de(2, 'movie')],
      new Map([[10, [T(12, 10, 2), T(11, 10, 1)]]]),
    )
    expect(fuera.map(e => e.id)).toEqual([1, 11, 12, 2])
  })

  it('una temporada marcada sola y por su serie sale una vez, donde aparece primero', () => {
    const temporadas = new Map([[10, [T(11, 10, 1), T(12, 10, 2)]]])
    expect(expandirSeleccion([T(12, 10, 2), de(10, 'series')], temporadas).map(e => e.id)).toEqual([12, 11])
    expect(expandirSeleccion([de(10, 'series'), T(12, 10, 2)], temporadas).map(e => e.id)).toEqual([11, 12])
  })

  it('una serie sin temporadas cargadas no aporta nada', () => {
    expect(expandirSeleccion([de(10, 'series'), de(1, 'movie')], new Map()).map(e => e.id)).toEqual([1])
  })
})

describe('expandirEntradas (desde el Panel)', () => {
  const de = (id: number, item_type: string, parcial: Partial<LibraryItemResponse> = {}) =>
    pelicula({ id, item_type, title: `#${id}`, ...parcial })
  const T = (id: number, serie: number, n: number) => de(id, 'season', { parent_id: serie, season_number: n })
  const temporadas = new Map([[10, [T(12, 10, 2), T(11, 10, 1)]]])

  it('una serie con `alcance.season` da solo esa temporada; sin ella, todas; las dos con su petición', () => {
    const r = expandirEntradas([
      { item: de(10, 'series'), requestId: 7, alcance: { season: 2 } },
      { item: de(10, 'series'), requestId: 8 },
    ], temporadas)
    expect(r.elementos.map(e => e.id)).toEqual([12, 11])
    expect([...r.peticiones]).toEqual([[12, [7, 8]], [11, [8]]])
    expect(r.avisos).toEqual([])
  })

  it('la misma fila por dos peticiones sale una vez con las dos, sin repetir', () => {
    const r = expandirEntradas([
      { item: de(1, 'movie'), requestId: 5 }, { item: de(1, 'movie'), requestId: 6 }, { item: de(1, 'movie'), requestId: 5 },
      { item: de(1, 'movie') },
    ], new Map())
    expect(r.elementos.map(e => e.id)).toEqual([1])
    expect(r.peticiones.get(1)).toEqual([5, 6])
  })

  it('avisa de una temporada o un capítulo pedidos que no están', () => {
    const r = expandirEntradas([
      { item: de(10, 'series'), requestId: 7, alcance: { season: 3 } },
      { item: T(11, 10, 1), requestId: 9, alcance: { season: 1, episode: 4 } },
    ], temporadas)
    expect(r.elementos).toEqual([])
    expect(r.avisos).toEqual([
      '«#10»: la temporada 3 no está en la biblioteca.',
      '«#11»: la petición es del capítulo S01E04, que no está en la biblioteca.',
    ])
  })

  it('dos peticiones sobre lo mismo que falta dan un solo aviso', () => {
    const r = expandirEntradas([
      { item: de(10, 'series'), requestId: 7, alcance: { season: 3 } },
      { item: de(10, 'series'), requestId: 8, alcance: { season: 3 } },
    ], temporadas)
    expect(r.avisos).toEqual(['«#10»: la temporada 3 no está en la biblioteca.'])
  })
})

describe('las filas del Panel', () => {
  const fila = (parcial: Partial<DashboardRecommendationItem>) => ({
    id: 5, item_type: 'season', rec_request_id: null, library_target_id: null, season_number: null, episode_number: null,
    ...parcial,
  }) as DashboardRecommendationItem
  const ficha = pelicula({ id: 55 })

  it('la clave junta la petición y la fila que se sube', () => {
    expect(claveDelPanel(fila({ rec_request_id: 77, library_target_id: 55 }))).toBe('77-55')
    expect(claveDelPanel(fila({}))).toBe('u-5')
  })

  it('una petición lleva su id y su alcance (el capítulo solo si es de capítulo); una idea, nada', () => {
    expect(entradaDelPanel(fila({ rec_request_id: 77, season_number: 2, episode_number: 3 }), ficha))
      .toEqual({ item: ficha, requestId: 77, alcance: { season: 2, episode: null } })
    expect(entradaDelPanel(fila({ rec_request_id: 78, item_type: 'episode', season_number: 1, episode_number: 12 }), ficha))
      .toEqual({ item: ficha, requestId: 78, alcance: { season: 1, episode: 12 } })
    expect(entradaDelPanel(fila({ season_number: 2 }), ficha)).toEqual({ item: ficha })
  })
})

describe('las peticiones de Peticiones', () => {
  const ficha = pelicula({ id: 55 })

  it('se marcan las que el Panel tiene en «Listo para subir»: compatibles, con fila y sin «no_castellano»', () => {
    const lista = { compatibility_status: 'Compatible', library_item_id: 5, readiness_status: 'ready_to_upload' }
    expect(peticionSeleccionableEnLote(lista)).toBe(true)
    // Sin preparación guardada todavía también: el Panel solo quita las que se han visto sin castellano.
    expect(peticionSeleccionableEnLote({ ...lista, readiness_status: null })).toBe(true)
    expect(peticionSeleccionableEnLote({ ...lista, readiness_status: 'no_castellano' })).toBe(false)
    expect(peticionSeleccionableEnLote({ ...lista, library_item_id: null })).toBe(false)
    expect(peticionSeleccionableEnLote({ ...lista, compatibility_status: 'Parcial' })).toBe(false)
    expect(peticionSeleccionableEnLote({ ...lista, compatibility_status: 'Reclamado' })).toBe(false)
  })

  it('lleva su id y su alcance, el capítulo solo si es de capítulo (como su «Subir a eMuwarez»)', () => {
    const sin = { req_scope: null, req_season: null, req_episode: null }
    expect(entradaDePeticion({ id: 70, ...sin }, ficha))
      .toEqual({ item: ficha, requestId: 70, alcance: { season: null, episode: null } })
    expect(entradaDePeticion({ id: 71, ...sin, req_scope: 'season', req_season: 2, req_episode: 3 }, ficha))
      .toEqual({ item: ficha, requestId: 71, alcance: { season: 2, episode: null } })
    expect(entradaDePeticion({ id: 72, req_scope: 'episode', req_season: 1, req_episode: 12 }, ficha))
      .toEqual({ item: ficha, requestId: 72, alcance: { season: 1, episode: 12 } })
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

describe('el aviso del lote', () => {
  it('al pasar a «Una por lote», un canal que avisaba de las subidas avisa también del lote', () => {
    expect(conAvisoDeLote(['upload_failed'])).toEqual(['upload_failed', 'upload_batch_done'])
    expect(conAvisoDeLote(['request_published', 'upload_completed'])).toEqual(['request_published', 'upload_completed', 'upload_batch_done'])
    // Ya lo tenía, o no avisaba de ninguna subida: igual que estaba.
    expect(conAvisoDeLote(['upload_completed', 'upload_batch_done'])).toEqual(['upload_completed', 'upload_batch_done'])
    expect(conAvisoDeLote(['request_published'])).toEqual(['request_published'])
    expect(conAvisoDeLote([])).toEqual([])
  })

  it('el lote de la notificación sale de su entity_id', () => {
    expect(loteDeNotificacion(parseInt('0123456789ab', 16))).toBe('0123456789ab')
    expect(loteDeNotificacion(parseInt('ffffffffffff', 16))).toBe('ffffffffffff')
    expect(loteDeNotificacion(0)).toBe('000000000000')
    expect(loteDeNotificacion(null)).toBeNull()
    expect(loteDeNotificacion(-1)).toBeNull()
    expect(loteDeNotificacion(1.5)).toBeNull()
    expect(loteDeNotificacion(2 ** 48)).toBeNull()
  })
})
