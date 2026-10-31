import type { UploadJobLog } from '../types/api'

/**
 * Seguir el registro de una subida en vivo sin bajarlo entero cada vez: la primera petición trae las últimas
 * líneas y las siguientes solo las posteriores a la última que se tiene, que se identifica por su `sequence`.
 */

/** La `sequence` de la última línea que trae una (las líneas llegan por orden), o `antes` si ninguna. */
export function ultimaSecuenciaDe(nuevas: UploadJobLog[], antes: number): number {
  for (let i = nuevas.length - 1; i >= 0; i--) {
    const n = nuevas[i].sequence
    if (n != null) return n
  }
  return antes
}

/**
 * El registro tras una respuesta. Sin cursor (`desde` = 0) lo que llega es el final del registro y reemplaza lo
 * que hubiera; con él son líneas nuevas y se añaden detrás, quedándose con las últimas `max`.
 */
export function aplicarLineas(previas: UploadJobLog[], nuevas: UploadJobLog[], desde: number, max: number): UploadJobLog[] {
  if (desde <= 0) return nuevas
  if (nuevas.length === 0) return previas   // misma referencia: no hay nada que repintar
  return [...previas, ...nuevas].slice(-max)
}
