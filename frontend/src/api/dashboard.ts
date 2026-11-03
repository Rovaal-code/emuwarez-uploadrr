import { api } from './client'
import type { DashboardSummaryResponse, DashboardActivityResponse, EmuPerfil } from '../types/api'

// Phase 11G — dashboard "Recomendaciones": actionable content in three ranked
// groups (1 compatible request · 2 unique/upload · 3 missing/request).
export interface DashboardRecommendationItem {
  id: number
  rec_group: number
  item_type: string
  title: string | null
  content_name: string
  year: number | null
  poster_url: string | null
  local_status: string | null
  season_number: number | null
  episode_number: number | null
  size_bytes: number | null
  resolution: string | null
  source: string | null
  instance_type: string | null
  instance_id: number | null
  tmdb_id: string | null
  title_slug: string | null
  missing_count: number | null
  rec_request_id: number | null
  // La recompensa de la petición (grupo 1); null en los grupos 2 y 3 o si eMuwarez no la dice.
  rec_points: number | null
}

export async function getDashboardRecommendations(limit = 60): Promise<{ items: DashboardRecommendationItem[] }> {
  return api.get<{ items: DashboardRecommendationItem[] }>(`/dashboard/recommendations?limit=${limit}`)
}

export async function getDashboardSummary(): Promise<DashboardSummaryResponse> {
  return api.get<DashboardSummaryResponse>('/dashboard/summary')
}

export async function getDashboardActivity(): Promise<DashboardActivityResponse> {
  return api.get<DashboardActivityResponse>('/dashboard/activity')
}

export async function getEmuPerfil(): Promise<EmuPerfil> {
  return api.get<EmuPerfil>('/dashboard/emu-perfil')
}

export async function actualizarEmuPerfil(): Promise<EmuPerfil> {
  return api.post<EmuPerfil>('/dashboard/emu-perfil/actualizar')
}
