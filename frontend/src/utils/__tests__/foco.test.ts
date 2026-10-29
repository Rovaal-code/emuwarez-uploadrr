/**
 * Con un modal abierto, Tab y Mayús+Tab dan la vuelta dentro de él en vez de
 * salir a la página de detrás.
 */
import { describe, it, expect } from 'vitest'
import { siguienteFoco } from '../foco'

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
