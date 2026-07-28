import { api } from './client'
import type { SeasonPackPlanResponse } from '../types/api'
import type { MediaInfoReport } from './library'
import type { TrackRemuxPreview, SourceComparison } from './nomenclature'

export function previewSeasonPack(seasonId: number): Promise<SeasonPackPlanResponse> {
  return api.get<SeasonPackPlanResponse>(`/library/season/${seasonId}/pack-preview`)
}

export interface SeasonPackFieldsPreviewFields {
  title?: string | null
  year?: number | null
  season_number?: number | null
  resolution?: string | null
  source?: string | null
  provider?: string | null
  video_codec?: string | null
  audio_summary?: string | null
  subtitle_summary?: string | null
  tag?: string | null
}

// Cheap live preview of the season pack title while editing Source/
// Proveedor/Tag — no DB/disk work server-side, so safe to call on every
// debounced keystroke (mirrors previewNomenclatureFields for a single item).
export function previewSeasonPackFields(
  seasonId: number, fields: SeasonPackFieldsPreviewFields,
): Promise<{ torrent_name: string | null }> {
  return api.post<{ torrent_name: string | null }>(`/library/season/${seasonId}/pack-preview-fields`, fields)
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
// `overrides` — the season's own Source/Proveedor/Tag as currently edited in
// the wizard, so every episode's name reflects the same choice as the
// season pack's own title instead of its own auto-detected values.
export function getSeasonEpisodeNames(
  seasonId: number,
  overrides?: { source?: string | null; provider?: string | null; tag?: string | null },
): Promise<{ episodes: SeasonEpisodeName[] }> {
  const qs = new URLSearchParams()
  if (overrides?.source) qs.set('source', overrides.source)
  if (overrides?.provider) qs.set('provider', overrides.provider)
  if (overrides?.tag) qs.set('tag', overrides.tag)
  const query = qs.toString()
  return api.get<{ episodes: SeasonEpisodeName[] }>(`/library/season/${seasonId}/episode-names${query ? `?${query}` : ''}`)
}

export interface SeasonEpisodeMediaInfo {
  episode_id: number
  episode_number?: number | null
  title?: string | null
  report: MediaInfoReport
  // Computed once from the first available episode and reused for every
  // episode — a season pack can only reach this screen once every episode
  // already agrees on source (build_season_pack_plan blocks otherwise).
  source_comparison?: SourceComparison | null
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
