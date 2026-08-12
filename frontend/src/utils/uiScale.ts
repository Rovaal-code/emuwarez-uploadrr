/**
 * Escalado global de la interfaz según la resolución de pantalla.
 *
 * Todo el CSS de la aplicación está escrito en píxeles fijos, calibrado para
 * una pantalla de 2560px de ancho (2K). Sin nada más, esos mismos píxeles se
 * comen la pantalla en 1080p y se quedan en miniatura en 4K: la interfaz "mide"
 * lo mismo en píxeles, pero cada píxel ocupa una fracción distinta de pantalla.
 * Aquí se calcula un factor y se aplica con `zoom` sobre el body (globals.css),
 * de forma que ocupe la misma proporción en las tres resoluciones.
 *
 * Se usa `zoom` y no `transform: scale()` a propósito: zoom rehace el layout, y
 * el texto se dibuja nítido a su tamaño real. transform escala una imagen ya
 * dibujada, y todo saldría borroso.
 *
 * El precio de zoom es que las coordenadas se parten en dos espacios:
 *   - Escalado (lo que ve el ojo): getBoundingClientRect(), y clientX/clientY
 *     de los eventos de ratón.
 *   - Sin escalar (lo que se escribe en el CSS): scrollWidth, offsetWidth, los
 *     valores de style.top/left que se ponen a mano, y window.innerWidth.
 * Mezclar los dos da posiciones que se desvían más cuanto más lejos del 100%.
 * Por eso todo el que mida para luego posicionar pasa por `medir()`,
 * `anchoVentana()` y `altoVentana()` de aquí abajo, que devuelven siempre el
 * espacio sin escalar.
 */

/** La resolución para la que está calibrado el CSS. */
export const ANCHO_REFERENCIA = 2560

/**
 * Por debajo de 1920px ya no se encoge más: seguir bajando volvería el texto
 * ilegible, y para ventanas estrechas están las media queries de siempre.
 */
export const ESCALA_MINIMA = 0.75

/** Tope por arriba, para que una pantalla enorme no infle la interfaz sin fin. */
export const ESCALA_MAXIMA = 2

/**
 * El ancho de ventana real por debajo del cual la interfaz pasa a su versión
 * estrecha. Con la escala al mínimo (0,75) el contenido dispone de
 * ancho / 0,75, así que los 1400px de contenido de las media queries se
 * alcanzan con una ventana de 1050px. Cambiar ESCALA_MINIMA obliga a recalcular
 * este número en el CSS.
 */
export const CORTE_ESTRECHO = Math.round(1400 * ESCALA_MINIMA)

/** Redondeado a tres decimales para no repintar por diferencias invisibles. */
export function escalaPara(ancho: number): number {
  const bruta = ancho / ANCHO_REFERENCIA
  const acotada = Math.min(ESCALA_MAXIMA, Math.max(ESCALA_MINIMA, bruta))
  return Math.round(acotada * 1000) / 1000
}

let escala = 1

/** El factor que está aplicado ahora mismo. */
export function escalaUi(): number {
  return escala
}

export function aplicarEscala(ancho: number): number {
  escala = escalaPara(ancho)
  document.documentElement.style.setProperty('--ui-scale', String(escala))
  return escala
}

/** Se llama una vez al arrancar (main.tsx). Devuelve cómo desengancharlo. */
export function iniciarEscaladoUi(): () => void {
  aplicarEscala(window.innerWidth)
  const alRedimensionar = () => aplicarEscala(window.innerWidth)
  window.addEventListener('resize', alRedimensionar)
  return () => window.removeEventListener('resize', alRedimensionar)
}

/**
 * Pasa una medida del espacio escalado al espacio sin escalar. Para lo que no
 * es un rect entero: clientX/clientY de un evento, el ancho de un
 * getClientRects(), etc.
 */
export function sinEscalar(valor: number): number {
  return valor / escala
}

export interface RectoSinEscalar {
  top: number
  left: number
  right: number
  bottom: number
  width: number
  height: number
}

/**
 * Como getBoundingClientRect(), pero en píxeles CSS sin escalar: lo que hay que
 * usar siempre que la medida vaya a acabar en un style.top/left/width.
 */
export function medir(el: Element): RectoSinEscalar {
  const r = el.getBoundingClientRect()
  return {
    top: r.top / escala,
    left: r.left / escala,
    right: r.right / escala,
    bottom: r.bottom / escala,
    width: r.width / escala,
    height: r.height / escala,
  }
}

/** El ancho de la ventana en el mismo espacio sin escalar que `medir()`. */
export function anchoVentana(): number {
  return window.innerWidth / escala
}

/** El alto de la ventana en el mismo espacio sin escalar que `medir()`. */
export function altoVentana(): number {
  return window.innerHeight / escala
}
