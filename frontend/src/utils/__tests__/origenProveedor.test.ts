/** El texto que dice de dónde sale el proveedor de un pack de temporada. */
import { describe, it, expect } from 'vitest'
import { textoOrigenProveedor } from '../origenProveedor'

describe('textoOrigenProveedor', () => {
  it('dice dónde lo detectó el servidor', () => {
    expect(textoOrigenProveedor('FLMN', 'detectado en el nombre del archivo del capítulo 1', 'FLMN'))
      .toBe('Proveedor: FLMN (detectado en el nombre del archivo del capítulo 1)')
  })

  it('un proveedor cambiado a mano ya no es el detectado', () => {
    expect(textoOrigenProveedor('FLMN', 'sugerido por TMDb', 'NF'))
      .toBe('Proveedor: NF (elegido a mano; se aplica a todos los capítulos)')
  })

  it('sin proveedor no dice nada', () => {
    expect(textoOrigenProveedor('FLMN', 'sugerido por TMDb', null)).toBeNull()
    expect(textoOrigenProveedor(null, null, '')).toBeNull()
  })
})
