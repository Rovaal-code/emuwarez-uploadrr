import { api } from './client'

// Mirror de services/emu_torrent_stats.py: lo que eMuwarez dice del torrent de una subida completada.
export interface TrackerStats {
  aplica: boolean
  configurado: boolean
  disponible: boolean
  mensaje: string | null
  actualizado: string | null
  seeders?: number | null
  leechers?: number | null
  completadas?: number | null
  freeleech?: string | null
  doble_subida?: boolean
}

// `refresh` se salta la caché de 5 minutos del servidor (la clave de eMuwarez la comparten otras aplicaciones).
export function getTrackerStats(jobId: number, refresh = false): Promise<TrackerStats> {
  return api.get<TrackerStats>(`/uploads/${jobId}/tracker-stats${refresh ? '?refresh=true' : ''}`)
}
