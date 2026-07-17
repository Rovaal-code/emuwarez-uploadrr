import { api } from './client'
import type { SeasonPackPlanResponse } from '../types/api'
import type { MediaInfoReport } from './library'
import type { TrackRemuxPreview } from './nomenclature'

export function previewSeasonPack(seasonId: number): Promise<SeasonPackPlanResponse> {
  return api.get<SeasonPackPlanResponse>(`/library/season/${seasonId}/pack-preview`)
}

export interface SeasonPlanProgress {
  done: number
  total: number
  current_title?: string | null
}

// Poll this WHILE previewSeasonPack() is in flight — building the plan runs
// build_nomenclature_proposal() per episode (real work), so this shows
// "Comprobando N de M capítulos…" instead of a silent wait.
export function getSeasonPlanProgress(seasonId: number): Promise<SeasonPlanProgress> {
  return api.get<SeasonPlanProgress>(`/library/season/${seasonId}/pack-preview/progress`)
}

export interface SeasonEpisodeName {
  episode_id: number
  episode_number?: number | null
  title?: string | null
  torrent_name?: string | null
  internal_mkv_title?: string | null
  error?: string | null
}

// Backs "Ver nombre de todos los capítulos" — a season pack has no single
// "título del archivo interno", each episode file has its own.
export function getSeasonEpisodeNames(seasonId: number): Promise<{ episodes: SeasonEpisodeName[] }> {
  return api.get<{ episodes: SeasonEpisodeName[] }>(`/library/season/${seasonId}/episode-names`)
}

export interface SeasonEpisodeMediaInfo {
  episode_id: number
  episode_number?: number | null
  title?: string | null
  report: MediaInfoReport
}

export function getSeasonEpisodeMediaInfo(seasonId: number): Promise<{ episodes: SeasonEpisodeMediaInfo[] }> {
  return api.get<{ episodes: SeasonEpisodeMediaInfo[] }>(`/library/season/${seasonId}/episode-mediainfo`)
}

export interface SeasonEpisodeRemux {
  episode_id: number
  episode_number?: number | null
  title?: string | null
  plan: TrackRemuxPreview
}

// Read-only per-episode preview — no manual per-track overrides for season
// packs (each episode's own auto-computed plan is applied as-is).
export function getSeasonEpisodeRemuxPreview(seasonId: number): Promise<{ episodes: SeasonEpisodeRemux[] }> {
  return api.get<{ episodes: SeasonEpisodeRemux[] }>(`/library/season/${seasonId}/episode-remux-preview`)
}
