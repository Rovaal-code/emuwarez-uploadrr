// Cálculos de los gráficos de línea de Estadísticas: del dato al trazo SVG, sin librerías de gráficos.

export interface PuntoSerie {
  dia: string            // YYYY-MM-DD
  valor: number | null   // null: ese día no hay cifra, y la línea se corta
}

export interface Medidas {
  ancho: number
  alto: number
  izquierda: number
  derecha: number
  arriba: number
  abajo: number
}

export interface PuntoTrazado {
  dia: string
  valor: number
  x: number
  y: number
}

export interface Trazado {
  /** Una por serie: el atributo `d` del <path> y los puntos con su posición. */
  lineas: { camino: string; puntos: PuntoTrazado[] }[]
  ticksY: { valor: number; y: number }[]
  ticksX: { dia: string; x: number }[]
}

export function diaAMs(dia: string): number {
  const [a, m, d] = dia.split('-').map(Number)
  return Date.UTC(a, m - 1, d)
}

/** «2026-11-02» a «02/11/2026», o a «02/11» con `corto`. Sin pasar por Date: no hay zonas horarias que torcer. */
export function formatDia(dia: string, corto = false): string {
  const [a, m, d] = dia.split('-')
  return corto ? `${d}/${m}` : `${d}/${m}/${a}`
}

const r1 = (n: number) => Math.round(n * 10) / 10

/**
 * Posiciona las series en el recuadro. El eje X es el tiempo real (un día sin instantánea deja hueco, no se
 * estira), y el Y va de lo más bajo a lo más alto de los datos con un margen para que la línea no toque los
 * bordes; con `desdeCero` (contadores como H&R) parte siempre de 0. Los ticks del eje Y son valores reales
 * de los datos: mínimo, medio y máximo.
 */
export function trazar(series: PuntoSerie[][], medidas: Medidas, desdeCero = false, marcasX = 3): Trazado {
  const { ancho, alto, izquierda, derecha, arriba, abajo } = medidas
  const valores = series.flatMap(s => s.flatMap(p => (p.valor === null ? [] : [p.valor])))
  const dias = [...new Set(series.flatMap(s => s.map(p => p.dia)))].sort()
  if (valores.length === 0 || dias.length === 0) return { lineas: series.map(() => ({ camino: '', puntos: [] })), ticksY: [], ticksX: [] }

  let bajo = Math.min(...valores)
  const alta = Math.max(...valores)
  if (desdeCero) bajo = Math.min(0, bajo)
  const relleno = bajo === alta ? Math.abs(alta) * 0.1 || 1 : (alta - bajo) * 0.08
  const minY = desdeCero && bajo === 0 ? 0 : bajo - relleno
  const maxY = alta + relleno

  const ms0 = diaAMs(dias[0])
  const span = diaAMs(dias[dias.length - 1]) - ms0
  const anchoUtil = ancho - izquierda - derecha
  const altoUtil = alto - arriba - abajo
  const posX = (dia: string) => izquierda + (span === 0 ? anchoUtil / 2 : ((diaAMs(dia) - ms0) / span) * anchoUtil)
  const posY = (v: number) => arriba + (1 - (v - minY) / (maxY - minY)) * altoUtil

  const lineas = series.map(serie => {
    const puntos: PuntoTrazado[] = []
    const trazos: string[] = []
    let abierto = false
    for (const p of serie) {
      if (p.valor === null) { abierto = false; continue }
      const x = r1(posX(p.dia))
      const y = r1(posY(p.valor))
      puntos.push({ dia: p.dia, valor: p.valor, x, y })
      trazos.push(`${abierto ? 'L' : 'M'}${x} ${y}`)
      abierto = true
    }
    return { camino: trazos.join(' '), puntos }
  })

  const mitad = (bajo + alta) / 2
  const niveles = bajo === alta ? [alta] : [bajo, mitad, alta]
  const ticksY = niveles.map(valor => ({ valor, y: r1(posY(valor)) }))
  // `marcasX` fechas a partes iguales del tiempo (con 3: la primera, la de en medio y la última). Los gráficos anchos
  // piden más; con menos días que marcas, una por día.
  const n = Math.max(1, Math.min(marcasX, dias.length))
  const fechas = n === 1 ? [dias[0]] : [...new Set(Array.from({ length: n }, (_, i) =>
    dias[Math.round((i * (dias.length - 1)) / (n - 1))]))]
  const ticksX = fechas.map(dia => ({ dia, x: r1(posX(dia)) }))
  return { lineas, ticksY, ticksX }
}

/** El resumen que lee un lector de pantalla en lugar del dibujo (la tabla de abajo trae todos los datos). */
export function describirSerie(nombre: string, serie: PuntoSerie[], formato: (n: number) => string): string {
  const con = serie.filter((p): p is PuntoSerie & { valor: number } => p.valor !== null)
  if (con.length === 0) return `${nombre}: sin datos en este rango.`
  const primero = con[0]
  const ultimo = con[con.length - 1]
  const valores = con.map(p => p.valor)
  const dias = `${con.length} ${con.length === 1 ? 'día' : 'días'} con datos`
  if (con.length === 1) return `${nombre}: ${formato(ultimo.valor)} el ${formatDia(ultimo.dia)}; ${dias}.`
  return `${nombre}: de ${formato(primero.valor)} el ${formatDia(primero.dia)} a ${formato(ultimo.valor)} el ${formatDia(ultimo.dia)}; `
    + `mínimo ${formato(Math.min(...valores))}, máximo ${formato(Math.max(...valores))}; ${dias}.`
}

/** Los días de un trazado (los de todas sus series, sin repetir y en orden) con su posición X: lo que se recorre con el
 * ratón o con las flechas. */
export function diasDelTrazado(t: Trazado): { dia: string; x: number }[] {
  const por = new Map<string, number>()
  for (const l of t.lineas) for (const p of l.puntos) por.set(p.dia, p.x)
  return [...por.entries()].sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0)).map(([dia, x]) => ({ dia, x }))
}

/** El índice del día cuya X queda más cerca de `x`; -1 si no hay días. */
export function diaMasCercano(dias: { x: number }[], x: number): number {
  let mejor = -1
  let distancia = Infinity
  dias.forEach((d, i) => {
    const dx = Math.abs(d.x - x)
    if (dx < distancia) { distancia = dx; mejor = i }
  })
  return mejor
}

/** Cuánto cambió una serie entre su primer y su último valor: diferencia y, si el primero no es cero, el porcentaje. */
export function variacion(serie: PuntoSerie[]): { diferencia: number; porcentaje: number | null } | null {
  const con = serie.filter((p): p is PuntoSerie & { valor: number } => p.valor !== null)
  if (con.length < 2) return null
  const primero = con[0].valor
  const diferencia = con[con.length - 1].valor - primero
  return { diferencia, porcentaje: primero === 0 ? null : (diferencia / Math.abs(primero)) * 100 }
}
