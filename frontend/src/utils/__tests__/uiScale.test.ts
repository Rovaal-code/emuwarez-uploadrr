import { describe, it, expect } from 'vitest'
import {
  normalizarTamano,
  esEstrecha,
  TAMANOS,
  TAMANO_POR_DEFECTO,
  ANCHO_ESTRECHO,
} from '../uiScale'

describe('TAMANOS', () => {
  it('ofrece del 50% al 150% de diez en diez, con el 100% dentro', () => {
    expect(TAMANOS).toEqual([50, 60, 70, 80, 90, 100, 110, 120, 130, 140, 150])
    expect(TAMANOS).toContain(TAMANO_POR_DEFECTO)
  })
})

describe('normalizarTamano', () => {
  it('deja pasar los valores del desplegable', () => {
    for (const t of TAMANOS) expect(normalizarTamano(t)).toBe(t)
  })

  it('entiende el número guardado como texto, que es como sale de localStorage', () => {
    expect(normalizarTamano('120')).toBe(120)
    expect(normalizarTamano('90')).toBe(90)
  })

  it('cae en el 100% ante cualquier cosa que no sea un número', () => {
    expect(normalizarTamano(null)).toBe(TAMANO_POR_DEFECTO)
    expect(normalizarTamano(undefined)).toBe(TAMANO_POR_DEFECTO)
    expect(normalizarTamano('grande')).toBe(TAMANO_POR_DEFECTO)
    expect(normalizarTamano(NaN)).toBe(TAMANO_POR_DEFECTO)
    expect(normalizarTamano(Infinity)).toBe(TAMANO_POR_DEFECTO)
  })

  it('acota lo que se salga del rango, en vez de aplicarlo', () => {
    // Un valor manipulado a mano en localStorage no debe poder dejar la
    // interfaz en un tamaño del que no se pueda salir.
    expect(normalizarTamano(0)).toBe(50)
    expect(normalizarTamano(-300)).toBe(50)
    expect(normalizarTamano(5000)).toBe(150)
  })

  it('redondea al escalón más cercano', () => {
    expect(normalizarTamano(94)).toBe(90)
    expect(normalizarTamano(96)).toBe(100)
    expect(normalizarTamano(125)).toBe(120)   // empate: se queda con el primero
  })
})

describe('esEstrecha', () => {
  // El corte ya no puede ser una media query: esas miran la ventana real y el
  // zoom no existe para ellas. Lo que decide es el ancho de CONTENIDO, que es
  // ancho de ventana dividido por la escala.
  it('mira el ancho de contenido, no el de la ventana', () => {
    // 1920 de ventana al 150% deja 1280 de contenido: estrecha, aunque la
    // ventana sea de sobra ancha. Este es justo el caso que la media query
    // no veía.
    expect(esEstrecha(1920, 150)).toBe(true)
    expect(esEstrecha(1920, 100)).toBe(false)
  })

  it('al revés también: una ventana estrecha deja de serlo si encoges la interfaz', () => {
    expect(esEstrecha(1280, 100)).toBe(true)
    expect(esEstrecha(1280, 50)).toBe(false)   // 2560 de contenido
  })

  it('el corte cae exactamente en ANCHO_ESTRECHO', () => {
    expect(esEstrecha(ANCHO_ESTRECHO, 100)).toBe(false)
    expect(esEstrecha(ANCHO_ESTRECHO - 1, 100)).toBe(true)
  })

  it('al 100% se comporta igual que la media query de siempre', () => {
    for (const ancho of [800, 1024, 1280, 1399, 1400, 1401, 1920, 2560, 3840]) {
      expect(esEstrecha(ancho, 100)).toBe(ancho < 1400)
    }
  })
})
