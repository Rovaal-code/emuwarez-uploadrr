/** El texto que dice de dónde sale el proveedor de un pack de temporada. */
import { describe, it, expect } from 'vitest'
import { ajustesDeTemporada, textoOrigenProveedor } from '../origenProveedor'

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

describe('ajustesDeTemporada', () => {
  it('el proveedor detectado no viaja como elección', () => {
    // Pack bloqueado por AMZN y NF: el campo trae AMZN, pero nadie lo eligió.
    expect(ajustesDeTemporada({ source: 'WEB-DL', provider: 'AMZN', tag: 'X' }, new Map(), 7))
      .toEqual({ source: 'WEB-DL', provider: null, tag: 'X' })
  })

  it('el elegido a mano sí viaja', () => {
    expect(ajustesDeTemporada({ source: 'WEB-DL', provider: 'AMZN' }, new Map([[7, 'NF']]), 7))
      .toEqual({ source: 'WEB-DL', provider: 'NF' })
    expect(ajustesDeTemporada(undefined, new Map([[7, 'NF']]), 7)).toEqual({ provider: 'NF' })
  })

  it('sin ajustes ni elección no manda nada', () => {
    expect(ajustesDeTemporada(undefined, new Map([[8, 'NF']]), 7)).toBeUndefined()
  })
})
