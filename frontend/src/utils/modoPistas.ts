/**
 * Qué se le hace a las pistas de un archivo antes de subirlo.
 *
 * Son DOS cosas independientes y hasta ahora el ajuste solo decidía una:
 * reordenar sí o no, dando por hecho que renombrar se hacía siempre. Además
 * había una casilla en la tarjeta de Ver Pistas para conservar los nombres
 * actuales, que hacía lo mismo desde otro sitio y solo aparecía subiendo una
 * película o un capítulo suelto. Ahora las dos decisiones viven en el mismo
 * desplegable de Configuración → Otros.
 *
 * Lo que cuesta cada una, que es de donde sale el valor de fábrica:
 *
 *   renombrar   se edita la cabecera en el sitio (mkvpropedit). No copia los
 *               datos y es casi instantáneo por grande que sea el archivo.
 *   reordenar   obliga a rehacer el contenedor entero (mkvmerge) y a sustituir
 *               el archivo, y tarda según el tamaño.
 *
 * Un archivo que comparte un torrent (hardlink) no se escribe: renombrar va a
 * una copia por reflink y reordenar se omite (services/upload_queue.py).
 *
 * La lista es copia de services/mkv_remux.py::ETIQUETAS_MODO_PISTAS y la
 * vigila tests/test_copias_frontend.py, que es lo que evita que Configuración
 * ofrezca un valor que el servidor rechace con un 422.
 */

export type ModoPistas =
  | 'reordenar_y_renombrar'
  | 'solo_renombrar'
  | 'solo_reordenar'
  | 'ninguno'

export const MODO_PISTAS_POR_DEFECTO: ModoPistas = 'solo_renombrar'

/** Lo que ofrece el desplegable de Configuración, en este orden. */
export const MODOS_PISTAS: { value: ModoPistas; label: string }[] = [
  { value: 'reordenar_y_renombrar', label: 'Reordenar y renombrar' },
  { value: 'solo_renombrar', label: 'Solo renombrar' },
  { value: 'solo_reordenar', label: 'Solo reordenar' },
  { value: 'ninguno', label: 'Ninguno' },
]

export function reordena(modo: ModoPistas): boolean {
  return modo === 'reordenar_y_renombrar' || modo === 'solo_reordenar'
}

export function renombra(modo: ModoPistas): boolean {
  return modo === 'reordenar_y_renombrar' || modo === 'solo_renombrar'
}

/** Si se va a tocar el archivo. Con "Ninguno" no, y por eso ahí tampoco se
 *  marca la pista predeterminada: en los otros tres sí, marcarla no es ni
 *  renombrar ni reordenar. */
export function tocaElFichero(modo: ModoPistas): boolean {
  return modo !== 'ninguno'
}

/**
 * Lo que dice la tarjeta de Ver Pistas. Sale SIEMPRE, no solo cuando algo está
 * apagado: antes solo avisaba de que la ordenación estaba desactivada, y con
 * cuatro estados posibles callarse en los demás deja al usuario adivinando por
 * qué la tabla enseña lo que enseña.
 *
 * El color va con lo que se deja de hacer, no con lo que cuesta: azul cuando
 * se hace todo, ámbar cuando se hace la mitad, rojo cuando no se toca nada.
 */
export const AVISO_MODO_PISTAS: Record<ModoPistas, { texto: string; tono: 'info' | 'aviso' | 'alto' }> = {
  reordenar_y_renombrar: {
    texto: 'Las pistas se reordenarán y se renombrarán',
    tono: 'info',
  },
  solo_renombrar: {
    texto: 'Solo se renombrarán las pistas. El orden se queda como está (Configuración)',
    tono: 'aviso',
  },
  solo_reordenar: {
    texto: 'Solo se reordenarán las pistas. Los nombres se quedan como están (Configuración)',
    tono: 'aviso',
  },
  ninguno: {
    texto: 'Las pistas no se tocan: ni el orden ni los nombres (Configuración)',
    tono: 'alto',
  },
}

/** El desplegable y la tarjeta tienen que aguantar un valor que no conozcan
 *  (una versión más nueva del servidor, un ajuste escrito a mano). */
export function normalizarModo(valor: string | null | undefined): ModoPistas {
  return MODOS_PISTAS.some(m => m.value === valor)
    ? (valor as ModoPistas)
    : MODO_PISTAS_POR_DEFECTO
}
