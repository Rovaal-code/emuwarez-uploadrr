import { api } from './client'

// Mirror de services/seeding_qbit.py: lo que qBittorrent dice de cada subida completada.
export interface SeedingItem {
  job_id: number
  estado: string
  etiqueta: string
  ratio?: number
  subido?: number | null
  progreso?: number
  seeds?: number | null
  peers?: number | null
  hash?: string
  casamiento?: string
}

export interface SeedingResponse {
  configurado: boolean
  disponible: boolean
  mensaje: string | null
  actualizado: string | null
  items: SeedingItem[]
}

// `refresh` se salta la caché de ~60 s del servidor.
export function getSeeding(refresh = false): Promise<SeedingResponse> {
  return api.get<SeedingResponse>(`/uploads/seeding${refresh ? '?refresh=true' : ''}`)
}
