/**
 * Tamaño de la interfaz, el que se elige en Configuración.
 *
 * Todo el CSS está escrito en píxeles fijos, así que en una pantalla grande la
 * interfaz se queda pequeña y en una pequeña se queda grande. Esto se aplica
 * con `zoom` sobre el body (globals.css) y lo arregla de una vez, sin tocar los
 * seiscientos y pico valores del CSS.
 *
 * **Se elige a mano, no se calcula.** Hubo una versión que deducía el factor
 * del ancho de la ventana; se quitó a propósito. Adivinar qué tamaño quiere
 * cada uno sale mal: la misma resolución se ve distinta según el tamaño físico
 * del monitor, a cuánto lo tengas y qué escalado tenga puesto el sistema. El
 * usuario lo ve y decide, que es más fiable que cualquier fórmula.
 *
 * **Se guarda por dispositivo** (localStorage), no en el servidor: depende de
 * la pantalla que tengas delante, así que abrir la aplicación desde un portátil
 * y desde un sobremesa tiene que poder dar dos tamaños distintos. Por eso no
 * viaja tampoco en el backup de configuración.
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

/** Lo que ofrece el desplegable de Configuración, en porcentaje. */
export const TAMANOS = [50, 60, 70, 80, 90, 100, 110, 120, 130, 140, 150]

/** Sin elegir nada, la interfaz se queda como está escrita en el CSS. */
export const TAMANO_POR_DEFECTO = 100

const LLAVE = 'uploadrr.tamano-interfaz'

/**
 * El ancho de contenido por debajo del cual la interfaz pasa a su disposición
 * estrecha. Antes esto era un `@media (max-width: 1400px)`, pero las media
 * queries miran la ventana REAL y el zoom no existe para ellas: al 150% en una
 * pantalla de 1920 el contenido dispone de 1280 y necesita la disposición
 * estrecha, mientras que la media query sigue viendo 1920 y no salta. Por eso
 * el corte se decide aquí y se publica como la clase `ui-estrecha` en el body,
 * que es contra lo que van ahora esas reglas del CSS.
 */
export const ANCHO_ESTRECHO = 1400

/** El porcentaje válido más cercano al valor dado. */
export function normalizarTamano(valor: unknown): number {
  const n = typeof valor === 'string' ? Number(valor) : valor
  if (typeof n !== 'number' || !Number.isFinite(n)) return TAMANO_POR_DEFECTO
  return TAMANOS.reduce((mejor, t) =>
    Math.abs(t - n) < Math.abs(mejor - n) ? t : mejor, TAMANOS[0])
}

/** Si con este tamaño la ventana se queda sin ancho de contenido suficiente. */
export function esEstrecha(anchoDeVentana: number, porcentaje: number): boolean {
  return anchoDeVentana / (porcentaje / 100) < ANCHO_ESTRECHO
}

export function tamanoGuardado(): number {
  try {
    const crudo = window.localStorage.getItem(LLAVE)
    return crudo == null ? TAMANO_POR_DEFECTO : normalizarTamano(crudo)
  } catch {
    // Modo incógnito con el almacenamiento capado, o un navegador que lo
    // bloquea: no es motivo para no arrancar, simplemente no se recuerda.
    return TAMANO_POR_DEFECTO
  }
}

let tamano = TAMANO_POR_DEFECTO
let escala = 1

/** El factor que está aplicado ahora mismo (1 = 100%). */
export function escalaUi(): number {
  return escala
}

/** El porcentaje que está aplicado ahora mismo. */
export function tamanoUi(): number {
  return tamano
}

/** Lo aplica a la página, sin guardarlo. */
export function aplicarTamano(porcentaje: number): number {
  tamano = normalizarTamano(porcentaje)
  escala = tamano / 100
  document.documentElement.style.setProperty('--ui-scale', String(escala))
  refrescarEstrecha()
  return tamano
}

/** Lo aplica y lo recuerda en este dispositivo. */
export function guardarTamano(porcentaje: number): number {
  const aplicado = aplicarTamano(porcentaje)
  try {
    window.localStorage.setItem(LLAVE, String(aplicado))
  } catch {
    // Ver tamanoGuardado(): sin almacenamiento el tamaño vale para esta sesión
    // y se olvida al recargar, que es mejor que romper el ajuste.
  }
  return aplicado
}

function refrescarEstrecha() {
  document.body.classList.toggle('ui-estrecha', esEstrecha(window.innerWidth, tamano))
}

/** Se llama una vez al arrancar (main.tsx). Devuelve cómo desengancharlo. */
export function iniciarEscaladoUi(): () => void {
  aplicarTamano(tamanoGuardado())
  // El tamaño ya no depende de la ventana, pero la disposición estrecha sí:
  // el ancho de contenido es ancho de ventana / escala, y la ventana cambia.
  window.addEventListener('resize', refrescarEstrecha)
  return () => window.removeEventListener('resize', refrescarEstrecha)
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
