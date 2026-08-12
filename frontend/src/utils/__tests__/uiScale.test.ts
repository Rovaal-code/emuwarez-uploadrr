import { describe, it, expect } from 'vitest'
import {
  escalaPara,
  ANCHO_REFERENCIA,
  ESCALA_MINIMA,
  ESCALA_MAXIMA,
  CORTE_ESTRECHO,
} from '../uiScale'

describe('escalaPara', () => {
  it('deja la interfaz tal cual en la resolución para la que está calibrada', () => {
    expect(escalaPara(ANCHO_REFERENCIA)).toBe(1)
  })

  it('encoge en 1080p, para que ocupe la misma proporción que en 2K', () => {
    expect(escalaPara(1920)).toBe(0.75)
  })

  it('crece en 4K, que es donde se quedaba en miniatura', () => {
    expect(escalaPara(3840)).toBe(1.5)
  })

  it('no sigue encogiendo por debajo de 1080p: ahí el texto se volvería ilegible', () => {
    expect(escalaPara(1280)).toBe(ESCALA_MINIMA)
    expect(escalaPara(800)).toBe(ESCALA_MINIMA)
    expect(escalaPara(0)).toBe(ESCALA_MINIMA)
  })

  it('tiene tope por arriba, para que una pantalla enorme no la infle sin fin', () => {
    expect(escalaPara(8000)).toBe(ESCALA_MAXIMA)
  })

  it('redondea, para no repintar por diferencias invisibles', () => {
    // 2000 / 2560 = 0.78125 exacto
    expect(escalaPara(2000)).toBe(0.781)
  })

  it('crece de forma monótona con el ancho', () => {
    const anchos = [800, 1280, 1600, 1920, 2200, 2560, 3000, 3840, 5120]
    const escalas = anchos.map(escalaPara)
    for (let i = 1; i < escalas.length; i++) {
      expect(escalas[i]).toBeGreaterThanOrEqual(escalas[i - 1])
    }
  })

  it('el corte estrecho del CSS es el ancho de ventana que deja 1400px de contenido', () => {
    // Las media queries miran la ventana real, no el espacio que el zoom deja
    // al contenido: con la escala en su mínimo, 1400px de contenido salen de
    // una ventana de CORTE_ESTRECHO. Si esto cambia, hay que tocar el
    // "max-width" de components.css y dashboard.css.
    expect(CORTE_ESTRECHO).toBe(1050)
    expect(CORTE_ESTRECHO / escalaPara(CORTE_ESTRECHO)).toBeCloseTo(1400, 0)
  })
})
