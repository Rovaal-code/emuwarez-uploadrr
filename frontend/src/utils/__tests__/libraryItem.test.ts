/**
 * Las reglas que deciden qué se puede subir.
 *
 * Hasta hoy el frontend no tenía con qué probarse (hallazgo 7.1 de la
 * auditoría): 20.200 líneas verificadas a ojo. Se empieza por aquí porque es
 * donde vive la lógica que habilita o bloquea los botones, y porque
 * `SEASON_CONSISTENCY_FIELDS` es la última copia viva de la regla del pack
 * (hallazgo 2.1): el backend la genera desde una definición, el navegador no
 * puede llamar a Python y la tiene escrita a mano.
 */
import { describe, it, expect } from 'vitest'
import {
  isSeasonReady, episodeNotReadyReason, seasonNotReadyReason,
} from '../libraryItem'
import type { LibraryItemResponse } from '../../types/api'

function item(extra: Partial<LibraryItemResponse> = {}): LibraryItemResponse {
  return {
    id: 1, item_type: 'season', title: 'Serie - T1', local_status: 'Disponible',
    resolution: '1080p', video_codec: 'x264', has_spanish_ok: 1,
    ...extra,
  } as LibraryItemResponse
}

describe('una temporada lista para subir como pack', () => {
  it('lo está cuando la tiene entera, con resolución y códec', () => {
    expect(isSeasonReady(item())).toBe(true)
    expect(seasonNotReadyReason(item())).toBeNull()
  })

  it('no lo está si no la tienes en disco', () => {
    expect(isSeasonReady(item({ local_status: 'Faltante' }))).toBe(false)
  })

  // Este caso devolvía null "porque el que llama ya tiene su propio mensaje",
  // y solo lo tenía uno de los dos sitios que la usan: desde la ficha de una
  // SERIE la temporada incompleta salía deshabilitada, y desde la ficha de la
  // TEMPORADA la tarjeta "Temporada entera" salía habilitada y te dejaba
  // avanzar dos pasos para que el servidor lo rechazara al final.
  it.each(['Faltante', 'Parcial', 'Subido'])('y lo DICE cuando está %s', estado => {
    const t = item({ local_status: estado })
    expect(isSeasonReady(t)).toBe(false)
    expect(seasonNotReadyReason(t)).toContain('incompleta')
  })

  it('nunca dice que no está lista sin explicar por qué', () => {
    // La pareja tiene que ir siempre junta: un motivo vacío deja una tarjeta
    // deshabilitada sin nada que enseñar al pasar por encima.
    const rotas = [
      item({ local_status: 'Faltante' }),
      item({ resolution: null }),
      item({ video_codec: null }),
      item({ has_spanish_ok: 0 }),
      item({ has_spanish_ok: null }),
    ]
    for (const t of rotas) {
      expect(isSeasonReady(t)).toBe(false)
      expect(seasonNotReadyReason(t)).toBeTruthy()
    }
  })

  it('no lo está si sus capítulos no coinciden en resolución', () => {
    const t = item({ resolution: null })
    expect(isSeasonReady(t)).toBe(false)
    expect(seasonNotReadyReason(t)).toContain('resolución')
  })

  it('no lo está si no coinciden en códec de vídeo', () => {
    const t = item({ video_codec: null })
    expect(isSeasonReady(t)).toBe(false)
    expect(seasonNotReadyReason(t)).toContain('códec')
  })

  it('no lo está sin castellano', () => {
    expect(isSeasonReady(item({ has_spanish_ok: 0 }))).toBe(false)
  })

  it('tampoco cuando no se han podido leer las pistas', () => {
    // null no es "no lo tiene", es "no lo sabemos", y no saberlo no vale como
    // prueba de que cumple la regla.
    expect(isSeasonReady(item({ has_spanish_ok: null }))).toBe(false)
  })

  it('el source mezclado ya NO bloquea', () => {
    // Cambió en 2026-07-31: solo resolución y códec tienen que coincidir; el
    // resto se resuelve en el nombre del pack.
    expect(isSeasonReady(item({ source: null } as Partial<LibraryItemResponse>))).toBe(true)
  })

  it('una serie o una película no son temporadas: no aplica', () => {
    expect(isSeasonReady(item({ item_type: 'movie' }))).toBe(true)
    expect(seasonNotReadyReason(item({ item_type: 'series' }))).toBeNull()
  })
})

describe('un capítulo suelto', () => {
  const cap = (extra: Partial<LibraryItemResponse> = {}) =>
    item({ item_type: 'episode', ...extra })

  it('se puede subir si lo tienes y lleva castellano', () => {
    expect(episodeNotReadyReason(cap())).toBeNull()
    expect(episodeNotReadyReason(cap({ local_status: 'Subido' }))).toBeNull()
  })

  it('no se puede si no lo tienes en disco', () => {
    expect(episodeNotReadyReason(cap({ local_status: 'Faltante' }))).toContain('no lo tienes en disco')
  })

  it('no se puede sin castellano, y lo dice', () => {
    expect(episodeNotReadyReason(cap({ has_spanish_ok: 0 }))).toContain('no tiene castellano')
  })

  it('distingue "no lo tiene" de "no se ha podido leer"', () => {
    expect(episodeNotReadyReason(cap({ has_spanish_ok: null }))).toContain('no se han podido leer')
  })

  it('las reglas del pack NO le aplican', () => {
    // Un capítulo lleva su propio nombre y puede declarar su propio códec, así
    // que no le afecta que sus hermanos no coincidan.
    expect(episodeNotReadyReason(cap({ resolution: null, video_codec: null }))).toBeNull()
  })
})
