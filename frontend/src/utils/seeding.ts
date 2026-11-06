import type { SeedingItem, SeedingResponse } from '../api/seeding'
import { formatBytes, formatNumero } from './format'

export const SIN_DATOS_QBIT = 'Sin datos de qBittorrent'

// Color por estado: solo acompaña al texto, que siempre se enseña.
const CLASE: Record<string, string> = {
  sembrando: 'badge status-available',
  en_cola: 'badge status-queued',
  comprobando: 'badge status-queued',
  moviendo: 'badge status-queued',
  pausado: 'badge status-partial',
  incompleto: 'badge status-partial',
  error: 'badge status-error',
  faltan_ficheros: 'badge status-error',
}

export function claseSeeding(estado: string): string {
  return CLASE[estado] ?? 'badge status-unknown'
}

// La entrada de esa subida, o undefined si no hay datos (sin cargar, qBittorrent caído) o no es una subida con torrent.
export function seedingDe(datos: SeedingResponse | null, jobId: number | undefined): SeedingItem | undefined {
  if (!datos?.disponible || jobId == null) return undefined
  return datos.items.find(i => i.job_id === jobId)
}

export function resumenSeeding(i: SeedingItem): string {
  return i.ratio == null ? i.etiqueta : `${i.etiqueta} · ratio ${formatNumero(i.ratio, 2)}`
}

// formatBytes enseña la raya con 0 bytes; aquí 0 es un dato y la raya es no saberlo.
export function textoSubido(i: SeedingItem): string {
  if (i.subido == null) return '—'
  return i.subido === 0 ? '0\u00A0B' : formatBytes(i.subido)
}
