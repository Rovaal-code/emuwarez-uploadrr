import type { UploadJob } from '../types/api'
import { parseServerDate } from './format'

// Nombre corto de cada fase (las claves son las de PHASES en services/uploadrr_progress.py).
// Lo vigila tests/test_copias_frontend.py.
export const NOMBRE_CORTO_FASE: Record<string, string> = {
  nomenclature: 'Nomenclatura',
  remux: 'Pistas',
  verificacion_presubida: 'Inicio de Uploadrr',
  screenshots: 'Capturas',
  hash_torrent: 'Hash del torrent',
  uploading_emu: 'Subida a eMuwarez',
  qbittorrent_add: 'qBittorrent',
}

const TEXTO_ESTADO: Record<string, string> = {
  done: 'completada', running: 'en curso', pending: 'pendiente', failed: 'fallida', cancelled: 'cancelada',
}

// Segundos entre dos marcas del servidor, o null si la fase no tiene hora de inicio. Sin fin propio se
// usa `respaldoFin` (el fin de la subida) y, sin ninguno, la hora actual.
export function segundosDeFase(inicio?: string | null, fin?: string | null, respaldoFin?: string | null): number | null {
  if (!inicio) return null
  const fuente = fin ?? respaldoFin
  const hasta = fuente ? parseServerDate(fuente).getTime() : Date.now()
  return Math.max(0, Math.round((hasta - parseServerDate(inicio).getTime()) / 1000))
}

export interface Tramo {
  clave: string
  nombre: string
  // Con `segundos` null no hay duración que enseñar: va el estado en palabras («omitida», «pendiente»).
  segundos: number | null
  estado: string
  // Parte del eje de la línea de tiempo (0 a 1).
  fraccion: number
}

export interface LineaDeTiempo {
  tramos: Tramo[]
  totalSegundos: number | null
}

export function lineaDeTiempo(job: UploadJob): LineaDeTiempo {
  const fases = job.progress?.phases ?? []
  // Una fase que se quedó «en curso» cuando la subida paró no sigue contando: acaba donde acabó la subida.
  const respaldo = job.finished_at ?? null
  const medidas = fases.map(p => {
    if (p.key === 'remux' && job.remux_snapshot?.omitida) return { p, segundos: null, estado: 'omitida' }
    const segundos = segundosDeFase(p.started_at, p.finished_at, respaldo)
    return { p, segundos, estado: TEXTO_ESTADO[p.status] ?? p.status }
  })
  const suma = medidas.reduce((n, m) => n + (m.segundos ?? 0), 0)
  const total = job.duration_seconds ?? segundosDeFase(job.started_at, job.finished_at) ?? (suma > 0 ? suma : null)
  // El eje es el total de la subida, salvo que las fases sumen más (se solapan): así ninguna barra se sale.
  const eje = Math.max(total ?? 0, suma, 1)
  return {
    totalSegundos: total,
    tramos: medidas.map(({ p, segundos, estado }) => ({
      clave: p.key,
      nombre: NOMBRE_CORTO_FASE[p.key] ?? p.label,
      segundos,
      estado,
      fraccion: segundos == null ? 0 : segundos / eje,
    })),
  }
}
