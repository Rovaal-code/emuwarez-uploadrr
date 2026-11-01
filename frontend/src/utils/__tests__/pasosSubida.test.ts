import { describe, expect, it } from 'vitest'
import { estadoDePaso, opcionesDeReintento } from '../pasosSubida'

describe('estadoDePaso', () => {
  it('cada estado del servidor tiene su texto', () => {
    for (const estado of ['hecho', 'en_curso', 'fallido', 'cancelado', 'pendiente']) {
      expect(estadoDePaso({ estado }).texto).toBeTruthy()
      // La clase dsub-paso-<clave> fija el color: tiene que existir en styles/detalle-subida.css.
      expect(estadoDePaso({ estado }).clave).toBe(estado)
    }
  })

  it('un estado desconocido cuenta como pendiente', () => {
    expect(estadoDePaso({ estado: 'raro' })).toBe(estadoDePaso({ estado: 'pendiente' }))
    expect(estadoDePaso({ estado: 'raro' }).clave).toBe('pendiente')
  })
})

describe('opcionesDeReintento', () => {
  it('sin paso desde el que reanudar solo hay un botón, que empieza por el principio', () => {
    expect(opcionesDeReintento({ reintento_desde_nombre: null })).toEqual([
      { etiqueta: 'Reintentar', desdeElPrincipio: false }])
    expect(opcionesDeReintento({})).toHaveLength(1)
  })

  it('si se puede reanudar, ofrece reanudar desde el paso y empezar de cero', () => {
    expect(opcionesDeReintento({ reintento_desde_nombre: 'Verificar antes de subir' })).toEqual([
      { etiqueta: 'Reintentar desde «Verificar antes de subir»', desdeElPrincipio: false },
      { etiqueta: 'Reintentar desde el principio', desdeElPrincipio: true },
    ])
  })
})
