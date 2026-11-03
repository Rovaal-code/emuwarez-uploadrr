import { describe, expect, it } from 'vitest'
import { esAtajoDePaleta, filtrarSecciones, moverSeleccion, normalizar } from '../paleta'

const SECCIONES = [
  { id: 'dashboard', titulo: 'Panel' },
  { id: 'library', titulo: 'Biblioteca' },
  { id: 'stats', titulo: 'Estadísticas' },
]

describe('paleta', () => {
  it('normaliza acentos y mayúsculas', () => {
    expect(normalizar('  Estadísticas ')).toBe('estadisticas')
  })

  it('filtra las secciones por título o por id, sin acentos', () => {
    expect(filtrarSecciones(SECCIONES, 'estadis').map(s => s.id)).toEqual(['stats'])
    expect(filtrarSecciones(SECCIONES, 'LIB').map(s => s.id)).toEqual(['library'])
    expect(filtrarSecciones(SECCIONES, 'dash').map(s => s.id)).toEqual(['dashboard'])
    expect(filtrarSecciones(SECCIONES, 'zzz')).toEqual([])
  })

  it('sin texto devuelve todas, en su orden', () => {
    expect(filtrarSecciones(SECCIONES, '  ')).toEqual(SECCIONES)
  })

  it('la selección da la vuelta por los dos lados y aguanta una lista vacía', () => {
    expect(moverSeleccion(2, 1, 3)).toBe(0)
    expect(moverSeleccion(0, -1, 3)).toBe(2)
    expect(moverSeleccion(1, 1, 3)).toBe(2)
    expect(moverSeleccion(0, 1, 0)).toBe(0)
  })

  it('reconoce Ctrl+K y Cmd+K, y nada más', () => {
    const base = { key: 'k', ctrlKey: false, metaKey: false, altKey: false, shiftKey: false }
    expect(esAtajoDePaleta({ ...base, ctrlKey: true })).toBe(true)
    expect(esAtajoDePaleta({ ...base, metaKey: true })).toBe(true)
    expect(esAtajoDePaleta({ ...base, key: 'K', ctrlKey: true })).toBe(true)
    expect(esAtajoDePaleta(base)).toBe(false)
    expect(esAtajoDePaleta({ ...base, ctrlKey: true, shiftKey: true })).toBe(false)
    expect(esAtajoDePaleta({ ...base, key: 'j', ctrlKey: true })).toBe(false)
  })
})
