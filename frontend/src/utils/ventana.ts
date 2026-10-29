/**
 * Qué filas de una lista larga hay que pintar de verdad.
 *
 * Biblioteca pintaba TODAS: con 15.900 archivos y dos filtros puestos eran
 * 8.756 filas, 667.000 nodos en el DOM y casi 3 GB en la pestaña, medido. Una
 * pantalla enseña una veintena. Así que se pintan las que se ven, un margen
 * por arriba y por abajo para que al desplazarte no aparezcan en blanco, y el
 * resto se sustituye por un hueco de la altura que ocuparían.
 *
 * Las filas no miden todas lo mismo: una serie desplegada lleva dentro sus
 * temporadas y capítulos. Por eso se trabaja con la altura de cada una (la
 * medida si ya se pintó, una estimación si no) y no con una altura fija.
 *
 * Las `fijas` se pintan aunque estén fuera de la vista: son las series
 * desplegadas, que guardan dentro qué temporada abriste y en qué página de
 * capítulos ibas. Si se desmontaran al salir de la pantalla, volver a ellas
 * las encontraría plegadas.
 */

export type Tramo =
  | { tipo: 'fila'; indice: number }
  | { tipo: 'hueco'; alto: number; clave: string }

/** Dónde empieza cada fila: `inicios[i]` es la suma de las anteriores, y el
 *  último elemento (uno más que filas) es el alto total. */
export function inicios(alturas: readonly number[]): number[] {
  const r = new Array<number>(alturas.length + 1)
  r[0] = 0
  for (let i = 0; i < alturas.length; i++) r[i + 1] = r[i] + alturas[i]
  return r
}

/** La fila que ocupa la altura `y` (búsqueda binaria sobre `inicios`). */
export function filaEn(ini: readonly number[], y: number): number {
  const n = ini.length - 1
  if (n <= 0) return 0
  let lo = 0
  let hi = n - 1
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1
    if (ini[mid] <= y) lo = mid
    else hi = mid - 1
  }
  return lo
}

export interface PlanVentana {
  alturas: readonly number[]
  /** Desplazamiento dentro de la lista, ya descontada la cabecera. */
  desde: number
  /** Alto visible del contenedor. */
  alto: number
  /** Píxeles de más que se pintan por arriba y por abajo. */
  margen: number
  fijas?: ReadonlySet<number>
}

/** Las filas a pintar, en orden, con un hueco donde se saltan otras. */
export function planVentana({ alturas, desde, alto, margen, fijas }: PlanVentana): Tramo[] {
  const n = alturas.length
  if (n === 0) return []
  const ini = inicios(alturas)
  const primera = filaEn(ini, Math.max(0, desde - margen))
  const ultima = filaEn(ini, Math.max(0, desde + alto + margen))

  const indices: number[] = []
  for (const f of fijas ?? []) if (f >= 0 && f < n && (f < primera || f > ultima)) indices.push(f)
  for (let i = primera; i <= ultima; i++) indices.push(i)
  indices.sort((a, b) => a - b)

  const tramos: Tramo[] = []
  let siguiente = 0
  for (const i of indices) {
    if (i > siguiente) tramos.push({ tipo: 'hueco', alto: ini[i] - ini[siguiente], clave: `h${siguiente}` })
    tramos.push({ tipo: 'fila', indice: i })
    siguiente = i + 1
  }
  if (siguiente < n) tramos.push({ tipo: 'hueco', alto: ini[n] - ini[siguiente], clave: `h${siguiente}` })
  return tramos
}
