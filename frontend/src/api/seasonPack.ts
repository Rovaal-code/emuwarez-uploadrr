import { api } from './client'
import type { PistaSinIdiomaPack, SeasonPackPlanResponse } from '../types/api'
import type { MediaInfoReport } from './library'
import type { TrackRemuxPreview, SourceComparison } from './nomenclature'

// `provider`: el Proveedor elegido a mano (utils/origenProveedor.ts::
// proveedorParaServidor; '' es "Sin proveedor"). Con él, capítulos con
// proveedores distintos en el nombre ya no bloquean el pack.
// `idiomas`: el idioma elegido para cada pista de audio sin idioma, por posición
// (utils/idiomasPack.ts); vale para todos los capítulos.
export function previewSeasonPack(
  seasonId: number, provider?: string, idiomas?: Record<number, string>,
): Promise<SeasonPackPlanResponse> {
  const qs = new URLSearchParams()
  if (provider !== undefined) qs.set('provider', provider)
  if (idiomas && Object.keys(idiomas).length) qs.set('idiomas', JSON.stringify(idiomas))
  const query = qs.toString()
  return api.get<SeasonPackPlanResponse>(`/library/season/${seasonId}/pack-preview${query ? `?${query}` : ''}`)
}

export interface SeasonPackAudio {
  audio_summary: string | null
  // Los capítulos no traen el mismo audio: el título lleva CUSTOM.
  custom: boolean
  // Capítulos que siguen con una pista de audio sin idioma; null si ninguno.
  audio_warning: string | null
  pistas_sin_idioma: PistaSinIdiomaPack[]
  idiomas_audio: Record<string, string>
}

// Solo el audio del pack con los idiomas elegidos, sin rehacer el plan entero
// (sin propuestas por capítulo ni TMDb): respalda el selector de idioma.
export function getSeasonPackAudio(seasonId: number, idiomas: Record<number, string>): Promise<SeasonPackAudio> {
  const qs = Object.keys(idiomas).length ? `?idiomas=${encodeURIComponent(JSON.stringify(idiomas))}` : ''
  return api.get<SeasonPackAudio>(`/library/season/${seasonId}/pack-audio${qs}`)
}

export interface SeasonPackFieldsPreviewFields {
  title?: string | null
  year?: number | null
  season_number?: number | null
  resolution?: string | null
  source?: string | null
  provider?: string | null
  video_codec?: string | null
  dynamic_range?: string | null
  audio_summary?: string | null
  subtitle_summary?: string | null
  custom?: boolean
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

// Tells the server to stop building this season's plan (one real proposal per
// episode). Called when the wizard closes mid-build; best-effort by design, a
// failure here must never block closing the modal.
export async function cancelSeasonPackPreview(seasonId: number): Promise<void> {
  try {
    await api.post(`/library/season/${seasonId}/pack-preview/cancel`, {})
  } catch { /* closing anyway */ }
}

export interface SeasonEpisodeName {
  // "Serie (Año) - SxxEyy" tal cual lo construye el backend
  // (services/library.content_display_title), el mismo formato que Ver
  // MediaInfo y que el resto de la aplicación.
  display_title: string
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
  overrides?: { source?: string | null; provider?: string | null; tag?: string | null; idiomas?: Record<number, string> },
): Promise<{ episodes: SeasonEpisodeName[] }> {
  const qs = new URLSearchParams()
  if (overrides?.idiomas && Object.keys(overrides.idiomas).length) qs.set('idiomas', JSON.stringify(overrides.idiomas))
  if (overrides?.source) qs.set('source', overrides.source)
  // '' es "Sin proveedor" elegido a mano: también se manda.
  if (overrides?.provider != null) qs.set('provider', overrides.provider)
  if (overrides?.tag) qs.set('tag', overrides.tag)
  const query = qs.toString()
  return api.get<{ episodes: SeasonEpisodeName[] }>(`/library/season/${seasonId}/episode-names${query ? `?${query}` : ''}`)
}

export interface SeasonEpisodeMediaInfo {
  episode_id: number
  episode_number?: number | null
  title?: string | null
  // "Serie (Año) - SxxEyy - Título del capítulo" — same canonical format
  // Biblioteca/Subidas/Peticiones already use (services/library.py's
  // content_display_title), backs the accordion header.
  display_title?: string | null
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
  display_title?: string | null
  plan: TrackRemuxPreview
}

// Read-only per-episode preview — no manual per-track overrides for season
// packs (each episode's own auto-computed plan is applied as-is), salvo el
// idioma elegido para las pistas de audio sin idioma (`idiomas`, por posición).
export function getSeasonEpisodeRemuxPreview(
  seasonId: number, idiomas?: Record<number, string>,
): Promise<{ episodes: SeasonEpisodeRemux[] }> {
  const qs = idiomas && Object.keys(idiomas).length ? `?idiomas=${encodeURIComponent(JSON.stringify(idiomas))}` : ''
  return api.get<{ episodes: SeasonEpisodeRemux[] }>(`/library/season/${seasonId}/episode-remux-preview${qs}`)
}
