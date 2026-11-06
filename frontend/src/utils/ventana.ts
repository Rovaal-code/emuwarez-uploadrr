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

/** A partir de cuántas filas una tabla (Peticiones, Subidas) pinta solo las que se ven. Por debajo se pinta
 *  entera, como siempre: con 43-65 nodos por fila, a 141 filas ya había fotogramas de 65-107 ms al desplazarse. */
export const UMBRAL_VIRTUAL = 50

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

/** Lo que se supone que mide una fila sin medir: la media de las medidas, redondeada, o `porDefecto` si aún no hay
 *  ninguna. */
export function altoMedio(medidas: Iterable<number>, porDefecto: number): number {
  let suma = 0
  let n = 0
  for (const m of medidas) { suma += m; n++ }
  return n ? Math.round(suma / n) : porDefecto
}

/**
 * El alto de cada fila de la lista: el medido si lo hay y, si no, la media de las filas ordinarias medidas que siguen
 * en la lista (`altoMedio`). Un número fijo se desviaría con el tamaño de la interfaz, y la primera fila sola también,
 * cuando no todas miden lo mismo (en Subidas, de 63 a 100 px según lleven motivo de error). Las filas que ya no están
 * (otro filtro) no cuentan, ni las que no son ordinarias (una cadena desplegada): esas valen solo para su sitio.
 */
export function alturasDeLaLista(
  claves: readonly number[], medidas: ReadonlyMap<number, number>, ordinarias: ReadonlySet<number>, porDefecto: number,
): number[] {
  const deLaMedia: number[] = []
  for (const k of claves) {
    const m = medidas.get(k)
    if (m != null && ordinarias.has(k)) deLaMedia.push(m)
  }
  const estimada = altoMedio(deLaMedia, porDefecto)
  return claves.map(k => medidas.get(k) ?? estimada)
}

/** Las columnas que pone `repeat(auto-fill, minmax(minimo, 1fr))` en `ancho`. */
export function columnasAutoFill(ancho: number, minimo: number, hueco: number): number {
  return Math.max(1, Math.floor((ancho + hueco) / (minimo + hueco)))
}

export interface PlanRejilla {
  total: number
  columnas: number
  /** Alto de una fila más el hueco que la separa de la siguiente. */
  paso: number
  desde: number
  alto: number
  margen: number
}

/** Las filas de una rejilla de tarjetas iguales a pintar, de `primera` a `ultima`. */
export function filasDeRejilla({ total, columnas, paso, desde, alto, margen }: PlanRejilla) {
  const filas = Math.ceil(total / columnas)
  const fila = (y: number) => Math.min(filas - 1, Math.max(0, Math.floor(y / paso)))
  return { filas, primera: fila(desde - margen), ultima: fila(desde + alto + margen) }
}

export interface MedidaRejilla {
  columnas: number
  alto: number
}

/** Cuántas veces seguidas, sin que cambie el scroll ni la lista, puede
 *  corregirse la medida de la rejilla. Una corrección normal necesita dos o
 *  tres (columnas y luego alto); si no se calma antes, algo oscila. */
export const AJUSTES_SEGUIDOS_MAX = 6

/**
 * Qué medida poner a la rejilla tras medirla, o null si se queda como está.
 *
 * El efecto de layout que mide corre tras cada pintado y vuelve a pintar si la
 * medida cambió. Si dos medidas se provocan una a la otra (el alto de la
 * primera tarjeta depende de cuál sea la primera, y cuál sea depende del alto),
 * eso nunca termina: React lo corta con el error 185 y la pantalla queda en
 * negro. `usados` cuenta las correcciones seguidas, y pasado el máximo la
 * medida se queda como está.
 */
export function medidaCorregida(actual: MedidaRejilla, medido: MedidaRejilla, usados: number): MedidaRejilla | null {
  if (medido.columnas === actual.columnas && medido.alto === actual.alto) return null
  if (usados >= AJUSTES_SEGUIDOS_MAX) return null
  return medido
}

export interface CuentaAjustes {
  clave: string
  usados: number
}

/**
 * La cuenta de correcciones seguidas tras medir. Empieza de nuevo cuando cambia
 * la `clave` (scroll, lista, ancho) y cuando la medida ya coincide con lo
 * medido: la rejilla se ha calmado y la siguiente corrección es otra. Si se
 * alcanza el tope con medidas todavía distintas, la cuenta se queda como está.
 */
export function cuentaTrasMedir(cuenta: CuentaAjustes, clave: string, coincide: boolean): CuentaAjustes {
  if (cuenta.clave !== clave || coincide) return { clave, usados: 0 }
  return cuenta
}

/**
 * Si el tope acaba de cortar una oscilación. El tope la para sin que se vea
 * nada, así que es el único momento de avisar de qué medidas saltaban. Quien
 * avisa sube `usados` por encima del tope, y esto ya no vuelve a ser cierto
 * hasta que la cuenta empiece de nuevo: un aviso por oscilación.
 */
export function topeRecienAlcanzado(cuenta: CuentaAjustes, coincide: boolean): boolean {
  return !coincide && cuenta.usados === AJUSTES_SEGUIDOS_MAX
}
