// Lo que Tareas enseña de cada tarea y de sus ejecuciones, sin React: estados, cuentas atrás y duraciones.

export type TonoTarea = 'ok' | 'error' | 'aviso' | 'curso' | 'neutro'

const TONO_POR_ESTADO: Record<string, TonoTarea> = {
  completed: 'ok',
  failed: 'error',
  skipped: 'aviso',
  running: 'curso',
}

const ETIQUETA_POR_ESTADO: Record<string, string> = {
  completed: 'Completado',
  failed: 'Error',
  skipped: 'Omitido',
  running: 'Ejecutando',
  queued: 'En cola',
  pending: 'Pendiente',
}

export function tonoDeEstado(estado: string | null): TonoTarea {
  return (estado && TONO_POR_ESTADO[estado]) || 'neutro'
}

export function etiquetaDeEstado(estado: string | null): string {
  if (!estado) return 'Sin ejecutar'
  return ETIQUETA_POR_ESTADO[estado] ?? (estado.charAt(0).toUpperCase() + estado.slice(1))
}

/** «en 2h 5m», «en 4m 23s», «en 12s» o «en breve»; «—» sin fecha. */
export function cuentaAtras(objetivoIso: string | null, ahora: number): string {
  if (!objetivoIso) return '—'
  const objetivo = new Date(objetivoIso).getTime()
  if (Number.isNaN(objetivo)) return '—'
  const dif = objetivo - ahora
  if (dif <= 0) return 'en breve'
  const totalMin = Math.floor(dif / 60000)
  const h = Math.floor(totalMin / 60)
  const m = totalMin % 60
  if (h > 0) return `en ${h}h ${m}m`
  const s = Math.floor((dif % 60000) / 1000)
  return m > 0 ? `en ${m}m ${s}s` : `en ${s}s`
}

/** Lo que tardó una ejecución: «850 ms», «12 s» o «3 min 5 s»; «—» si falta alguna de las dos horas. */
export function duracion(inicioIso: string | null, finIso: string | null): string {
  if (!inicioIso || !finIso) return '—'
  const ms = new Date(finIso).getTime() - new Date(inicioIso).getTime()
  if (Number.isNaN(ms) || ms < 0) return '—'
  if (ms < 1000) return `${ms} ms`
  const s = Math.round(ms / 1000)
  if (s < 60) return `${s} s`
  const min = Math.floor(s / 60)
  return `${min} min ${s % 60} s`
}

/** El intervalo de una tarea como se lee: «30 min», «6h», «1h 30 min». */
export function etiquetaIntervalo(minutos: number): string {
  if (minutos < 60) return `${minutos} min`
  const h = Math.floor(minutos / 60)
  const m = minutos % 60
  return m === 0 ? `${h}h` : `${h}h ${m} min`
}
