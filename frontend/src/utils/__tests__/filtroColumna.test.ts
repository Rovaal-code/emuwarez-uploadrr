/**
 * El desplegable de filtro de una columna con selección múltiple.
 */
import { describe, it, expect } from 'vitest'
import { siguienteSeleccion, resumenFiltro } from '../filtroColumna'

describe('siguienteSeleccion', () => {
  it('marcar añade y desmarcar quita, sin tocar lo demás', () => {
    expect(siguienteSeleccion(['1080p'], '720p')).toEqual(['1080p', '720p'])
    expect(siguienteSeleccion(['1080p', '720p'], '1080p')).toEqual(['720p'])
  })

  it('«Todos» lo quita todo', () => {
    expect(siguienteSeleccion(['1080p', '720p'], '')).toEqual([])
  })

  it('«Todos» sin nada marcado no es un cambio: devuelve la misma lista', () => {
    // La misma, no una igual: Biblioteca recarga cuando cambia la referencia.
    const nada: string[] = []
    expect(siguienteSeleccion(nada, '')).toBe(nada)
  })
})

describe('resumenFiltro', () => {
  const opciones = [
    { value: '', label: 'Todos' },
    { value: 'candidate', label: 'No' },
    { value: 'present', label: 'Sí' },
  ]

  it('usa los nombres de la columna, en el orden del menú y no en el de los clics', () => {
    expect(resumenFiltro(['present', 'candidate'], opciones)).toBe('No, Sí')
  })

  it('un valor sin opción se enseña tal cual', () => {
    expect(resumenFiltro(['raro'], opciones)).toBe('raro')
  })
})
