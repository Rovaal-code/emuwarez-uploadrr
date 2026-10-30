/**
 * Con un modal abierto, Tab y Mayús+Tab dan la vuelta dentro de él en vez de
 * salir a la página de detrás.
 */
import { describe, it, expect } from 'vitest'
import { destinoAlCerrar, siguienteFoco } from '../foco'

const botones = ['titulo', 'campo', 'cancelar', 'guardar']

describe('foco atrapado en un modal', () => {
  it('Tab en el último vuelve al primero', () => {
    expect(siguienteFoco(botones, 'guardar', false)).toBe('titulo')
  })

  it('Mayús+Tab en el primero va al último', () => {
    expect(siguienteFoco(botones, 'titulo', true)).toBe('guardar')
  })

  it('en medio deja hacer al navegador', () => {
    expect(siguienteFoco(botones, 'campo', false)).toBeNull()
    expect(siguienteFoco(botones, 'cancelar', true)).toBeNull()
  })

  it('con el foco fuera entra por el borde que toca', () => {
    expect(siguienteFoco(botones, 'fondo', false)).toBe('titulo')
    expect(siguienteFoco(botones, null, true)).toBe('guardar')
  })

  it('sin nada enfocable no propone nada', () => {
    expect(siguienteFoco([], 'fondo', false)).toBeNull()
  })
})

/**
 * Al cerrar un modal el foco vuelve a quien lo abrió, y si era un botón de
 * otro modal que ya se ha cerrado, a donde lo habría devuelto ese otro.
 */
describe('foco al cerrar un modal', () => {
  type Nodo = { nombre: string, isConnected: boolean, heredado?: Nodo }
  const heredado = (n: Nodo) => n.heredado

  it('vuelve a quien lo abrió si sigue en la página', () => {
    const boton: Nodo = { nombre: 'Ver MediaInfo', isConnected: true }
    expect(destinoAlCerrar(boton, heredado)).toBe(boton)
  })

  it('si quien lo abrió era de un modal cerrado, va a donde volvía ese', () => {
    const verMediaInfo: Nodo = { nombre: 'Ver MediaInfo', isConnected: true }
    const fuente: Nodo = { nombre: 'Bitrate de la fuente', isConnected: false, heredado: verMediaInfo }
    expect(destinoAlCerrar(fuente, heredado)).toBe(verMediaInfo)
  })

  it('sigue la cadena de varios modales cerrados', () => {
    const fuera: Nodo = { nombre: 'Subir', isConnected: true }
    const medio: Nodo = { nombre: 'medio', isConnected: false, heredado: fuera }
    const dentro: Nodo = { nombre: 'dentro', isConnected: false, heredado: medio }
    expect(destinoAlCerrar(dentro, heredado)).toBe(fuera)
  })

  it('sin nada en la página a donde volver, no propone nada', () => {
    expect(destinoAlCerrar({ nombre: 'quitado', isConnected: false }, heredado)).toBeNull()
    expect(destinoAlCerrar(null, heredado)).toBeNull()
  })

  it('una cadena que se cierra sobre sí misma no se queda dando vueltas', () => {
    const a: Nodo = { nombre: 'a', isConnected: false }
    const b: Nodo = { nombre: 'b', isConnected: false, heredado: a }
    a.heredado = b
    expect(destinoAlCerrar(a, heredado)).toBeNull()
  })
})
