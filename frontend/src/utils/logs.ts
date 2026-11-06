import type { LogEntry } from '../api/logs'

// Lo que Logs necesita de una lista de líneas, sin React.

/** Un hash corto (FNV-1a de 32 bits) del texto: basta para distinguir mensajes distintos en una clave. */
function hashCorto(texto: string): string {
  let h = 0x811c9dc5
  for (let i = 0; i < texto.length; i++) {
    h ^= texto.charCodeAt(i)
    h = Math.imul(h, 0x01000193)
  }
  return (h >>> 0).toString(36)
}

/** Claves estables entre recargas: una línea que sigue ahí conserva su clave aunque otras entren por delante. */
export function clavesDeLineas(lineas: readonly LogEntry[]): string[] {
  const vistas = new Map<string, number>()
  return lineas.map(l => {
    const base = `${l.ts}|${l.level}|${l.logger}|${hashCorto(l.message)}`
    const n = vistas.get(base) ?? 0
    vistas.set(base, n + 1)
    return n === 0 ? base : `${base}#${n}`
  })
}

/** Si dos lecturas traen exactamente las mismas líneas: evita repintar mil filas cada 3 segundos para dejarlas igual. */
export function mismasLineas(a: readonly LogEntry[], b: readonly LogEntry[]): boolean {
  if (a.length !== b.length) return false
  return a.every((l, i) => {
    const o = b[i]
    return l.ts === o.ts && l.time === o.time && l.level === o.level && l.logger === o.logger && l.message === o.message
  })
}

/** La línea como texto plano, lista para pegar en un mensaje o un informe. */
export function textoDeLinea(l: LogEntry): string {
  return `${l.time} ${l.level} ${l.logger} ${l.message}`
}

export interface Trozo { texto: string; coincide: boolean }

/** Parte un texto en trozos que coinciden o no con la búsqueda (sin distinguir mayúsculas). Sin búsqueda, un solo trozo. */
export function trocearPorBusqueda(texto: string, busqueda: string): Trozo[] {
  const q = busqueda.trim().toLowerCase()
  if (!q) return [{ texto, coincide: false }]
  const bajo = texto.toLowerCase()
  const trozos: Trozo[] = []
  let desde = 0
  for (;;) {
    const i = bajo.indexOf(q, desde)
    if (i < 0) break
    if (i > desde) trozos.push({ texto: texto.slice(desde, i), coincide: false })
    trozos.push({ texto: texto.slice(i, i + q.length), coincide: true })
    desde = i + q.length
  }
  if (desde < texto.length) trozos.push({ texto: texto.slice(desde), coincide: false })
  return trozos.length ? trozos : [{ texto, coincide: false }]
}

/** La fecha («2026-11-06») de la hora de una línea, o null si no tiene ese formato. */
export function diaDeLinea(l: LogEntry): string | null {
  const m = /^(\d{4}-\d{2}-\d{2})\s/.exec(l.time)
  return m ? m[1] : null
}

/** La hora sin la fecha («07:29:32»); si no tiene el formato esperado, la hora tal cual. */
export function horaDeLinea(l: LogEntry): string {
  const m = /^\d{4}-\d{2}-\d{2}\s+(.*)$/.exec(l.time)
  return m ? m[1] : l.time
}
