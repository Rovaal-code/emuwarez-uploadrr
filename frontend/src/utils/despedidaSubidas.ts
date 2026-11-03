/**
 * Las subidas que acaban de terminar no desaparecen de golpe del Panel.
 *
 * «En curso» (antes «Actividad de subida») enseña solo las vivas, así que en el instante en que
 * una terminaba se esfumaba de la lista. Si no estabas mirando esa décima de
 * segundo, no llegabas a ver que había terminado: la fila simplemente ya no
 * estaba. Ahora se queda un rato con su estado final y luego se va
 * desvaneciendo.
 *
 * Vale para cualquier final, no solo el bueno: una subida FALLIDA
 * desapareciendo en el acto es el mismo problema y peor, porque el fallo no
 * llegarías a verlo nunca desde aquí.
 */
import type { UploadJob } from '../types/api'
import { ACTIVE_JOB_STATUSES } from './uploadStatus'

/** Lo que se queda quieta con su estado final, antes de empezar a irse. */
export const ESPERA_MS = 10_000

/** Lo que tarda en desvanecerse, ya con el reloj cumplido. */
export const DESVANECER_MS = 1_500

/**
 * Cuáles de las que estaban vivas han dejado de estarlo.
 *
 * Se resuelve comparando con la vuelta anterior y no mirando el estado, porque
 * "terminada" no es un estado sino tres (completada, fallida, cancelada) y
 * cualquiera de ellos es un final. Lo que interesa es el paso de viva a no
 * viva, que es lo que el usuario acaba de perderse.
 *
 * `todas` es la respuesta entera del servidor, sin filtrar: hace falta para
 * poder devolver la fila con su estado FINAL, que es justo lo que se va a
 * enseñar esos diez segundos.
 */
export function queSalieron(todas: UploadJob[], vivasAntes: Set<number>): UploadJob[] {
  return todas.filter(j =>
    j.id != null && vivasAntes.has(j.id) && !ACTIVE_JOB_STATUSES.has(j.status))
}

/** Las que están vivas ahora mismo. */
export function soloVivas(todas: UploadJob[]): UploadJob[] {
  return todas.filter(j => ACTIVE_JOB_STATUSES.has(j.status))
}

export function idsDe(subidas: UploadJob[]): Set<number> {
  return new Set(subidas.map(j => j.id).filter((id): id is number => id != null))
}
