// @vitest-environment jsdom
// Grupos de Peticiones: a cuál va cada estado y el orden por recompensa.
import { describe, expect, it } from 'vitest'
import {
  agruparPeticiones, grupoDePeticion, motivoDeLaPreparacion, type GrupoPeticion,
} from '../peticiones'

const p = (id: number, readiness: string | null, extra: Record<string, unknown> = {}) => ({
  id, readiness_status: readiness, compatibility_status: null as string | null, points: null as number | null,
  created_at: null as string | null, ...extra,
})

describe('grupoDePeticion', () => {
  const casos: [string, GrupoPeticion][] = [
    ['ready_to_upload', 'lista'], ['preflight_needed', 'lista'], ['needs_nomenclature', 'lista'],
    ['partially_available', 'parcial'], ['spec_mismatch', 'parcial'], ['no_castellano', 'parcial'],
    ['downloading', 'parcial'], ['pending_import', 'parcial'], ['import_error', 'parcial'],
    ['no_local_match', 'sin_copia'], ['file_missing', 'sin_copia'],
    ['claimed', 'cerrada'], ['claimed_unknown', 'cerrada'], ['pending_approval', 'cerrada'], ['filled', 'cerrada'],
    ['already_exists', 'cerrada'], ['uploaded', 'cerrada'], ['uploading', 'cerrada'],
  ]
  it.each(casos)('%s va a %s', (estado, grupo) => {
    expect(grupoDePeticion(p(1, estado))).toBe(grupo)
  })

  it('sin preparación guardada decide la compatibilidad de la columna', () => {
    expect(grupoDePeticion(p(1, null, { compatibility_status: 'Compatible' }))).toBe('lista')
    expect(grupoDePeticion(p(1, null, { compatibility_status: 'Parcial' }))).toBe('parcial')
    expect(grupoDePeticion(p(1, null, { compatibility_status: 'Reclamado' }))).toBe('cerrada')
    expect(grupoDePeticion(p(1, null, { compatibility_status: 'Sin coincidencia' }))).toBe('sin_copia')
    expect(grupoDePeticion(p(1, null))).toBe('sin_copia')
  })

  it('un estado de preparación que no conoce cae en la compatibilidad', () => {
    expect(grupoDePeticion(p(1, 'estado_nuevo', { compatibility_status: 'Compatible' }))).toBe('lista')
  })
})

describe('agruparPeticiones', () => {
  it('los grupos salen en su orden, sin los vacíos', () => {
    const grupos = agruparPeticiones([p(1, 'no_local_match'), p(2, 'ready_to_upload'), p(3, 'no_castellano')])
    expect(grupos.map(g => [g.titulo, g.items.map(i => i.id)])).toEqual([
      ['Lista para subir', [2]], ['Parcial', [3]], ['No la tienes', [1]],
    ])
  })

  it('dentro de cada grupo, la que más paga primero; sin puntos al final; a igual recompensa, la más nueva', () => {
    const [grupo] = agruparPeticiones([
      p(1, 'ready_to_upload', { points: 10, created_at: '2026-10-01T00:00:00Z' }),
      p(2, 'ready_to_upload', { points: null, created_at: '2026-11-01T00:00:00Z' }),
      p(3, 'ready_to_upload', { points: 250, created_at: '2026-09-01T00:00:00Z' }),
      p(4, 'ready_to_upload', { points: 10, created_at: '2026-10-20T00:00:00Z' }),
      p(5, 'ready_to_upload', { points: 0, created_at: '2026-10-20T00:00:00Z' }),
    ])
    expect(grupo.items.map(i => i.id)).toEqual([3, 4, 1, 5, 2])
  })

  it('no toca la lista de entrada', () => {
    const entrada = [p(1, 'ready_to_upload', { points: 1 }), p(2, 'ready_to_upload', { points: 9 })]
    agruparPeticiones(entrada)
    expect(entrada.map(i => i.id)).toEqual([1, 2])
  })

  it('sin peticiones no hay grupos', () => {
    expect(agruparPeticiones([])).toEqual([])
  })
})

describe('motivoDeLaPreparacion', () => {
  it('da una frase corta solo cuando la preparación explica por qué aún no está lista', () => {
    expect(motivoDeLaPreparacion({ readiness_status: 'no_castellano' })).toBe('Sin castellano')
    expect(motivoDeLaPreparacion({ readiness_status: 'needs_nomenclature' })).toBe('Falta la nomenclatura')
    for (const s of ['ready_to_upload', 'no_local_match', 'claimed', 'filled', 'uploaded', null, undefined]) {
      expect(motivoDeLaPreparacion({ readiness_status: s as string | null })).toBeNull()
    }
  })
})
