/**
 * Lo que la interfaz hace con el modo de pistas.
 *
 * La regla de qué se aplica vive en el servidor (services/mkv_remux.py, con
 * tests/test_modo_pistas.py); esta copia decide lo que se puede tocar en la
 * tabla de Ver Pistas y qué mensaje sale. Que las dos digan lo mismo lo vigila
 * tests/test_copias_frontend.py, así que aquí solo se comprueba lo que es
 * exclusivamente de la pantalla.
 */
import { describe, it, expect } from 'vitest'
import {
  MODOS_PISTAS, MODO_PISTAS_POR_DEFECTO, AVISO_MODO_PISTAS,
  normalizarModo, reordena, renombra, tocaElFichero, type ModoPistas,
} from '../modoPistas'

const TODOS = MODOS_PISTAS.map(m => m.value)

describe('qué se puede editar en la tabla', () => {
  // La columna "Nombre nuevo": editable solo si de verdad se va a renombrar.
  // Ofrecer escribir un nombre que el servidor va a descartar es peor que no
  // ofrecerlo, porque el usuario cree que lo ha configurado.
  it.each<[ModoPistas, boolean]>([
    ['reordenar_y_renombrar', true],
    ['solo_renombrar', true],
    ['solo_reordenar', false],
    ['ninguno', false],
  ])('en %s la columna de nombre es editable: %s', (modo, esperado) => {
    expect(renombra(modo)).toBe(esperado)
  })

  // La casilla "Predet." va aparte: marcar la pista predeterminada no es ni
  // renombrar ni reordenar, y se hace en los tres modos que tocan el archivo.
  // Atándola a `renombra` se perdía poder elegirla en "Solo reordenar".
  it.each<[ModoPistas, boolean]>([
    ['reordenar_y_renombrar', true],
    ['solo_renombrar', true],
    ['solo_reordenar', true],
    ['ninguno', false],
  ])('en %s la casilla Predet. es editable: %s', (modo, esperado) => {
    expect(tocaElFichero(modo)).toBe(esperado)
  })

  it('solo reordenar deja tocar la predeterminada pero no el nombre', () => {
    expect(tocaElFichero('solo_reordenar')).toBe(true)
    expect(renombra('solo_reordenar')).toBe(false)
  })
})

describe('el mensaje de la tarjeta', () => {
  it('los cuatro modos tienen uno: la tarjeta nunca se calla', () => {
    for (const modo of TODOS) {
      expect(AVISO_MODO_PISTAS[modo].texto.length).toBeGreaterThan(0)
    }
  })

  it('cada mensaje es distinto', () => {
    const textos = new Set(TODOS.map(m => AVISO_MODO_PISTAS[m].texto))
    expect(textos.size).toBe(TODOS.length)
  })

  // El color dice cuánto se deja de hacer, no cuánto cuesta: reordenar es lo
  // caro y aun así va en azul, porque es el modo que lo hace todo.
  it('azul cuando se hace todo, ámbar a medias, rojo cuando no se toca nada', () => {
    expect(AVISO_MODO_PISTAS.reordenar_y_renombrar.tono).toBe('info')
    expect(AVISO_MODO_PISTAS.solo_renombrar.tono).toBe('aviso')
    expect(AVISO_MODO_PISTAS.solo_reordenar.tono).toBe('aviso')
    expect(AVISO_MODO_PISTAS.ninguno.tono).toBe('alto')
  })

  it('los que se quedan a medias mandan a Configuración', () => {
    for (const modo of TODOS) {
      const aviso = AVISO_MODO_PISTAS[modo]
      const completo = reordena(modo) && renombra(modo)
      expect(aviso.texto.includes('(Configuración)')).toBe(!completo)
    }
  })
})

describe('un valor que no se conoce', () => {
  // El servidor puede ser más nuevo, o alguien puede haber escrito el ajuste a
  // mano. Sin esto, el desplegable se quedaba en blanco y la tarjeta reventaba
  // buscando un mensaje que no existe.
  it.each([null, undefined, '', 'pepe', 'REORDENAR_Y_RENOMBRAR'])(
    'cae al valor de fábrica (%s)', valor => {
      expect(normalizarModo(valor)).toBe(MODO_PISTAS_POR_DEFECTO)
    })

  it.each(TODOS)('pero respeta los que sí conoce (%s)', modo => {
    expect(normalizarModo(modo)).toBe(modo)
  })

  it('el valor de fábrica es uno de la lista', () => {
    expect(TODOS).toContain(MODO_PISTAS_POR_DEFECTO)
  })

  // Reordenar rompe los hardlinks con el cliente de torrent y tarda según el
  // tamaño: de fábrica no se hace.
  it('de fábrica solo se renombra, que es lo barato', () => {
    expect(reordena(MODO_PISTAS_POR_DEFECTO)).toBe(false)
    expect(renombra(MODO_PISTAS_POR_DEFECTO)).toBe(true)
  })
})
