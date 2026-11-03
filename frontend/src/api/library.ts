import { api } from './client'
import type { LibraryListResponse, LibraryItemResponse, SyncResponse } from '../types/api'
import type { EstadoCastellano } from '../utils/castellano'

// Los filtros de columna admiten varios valores: viajan como parámetro repetido.
export interface LibraryQueryParams {
  type?: string | string[]
  origin?: string
  instance_id?: number | number[]
  // Series/Season/Episode hierarchy — omit for "no filter" (CLI-style
  // callers), pass 0 (TOP_LEVEL_PARENT_FILTER, matches the backend
  // sentinel) for "top level only", or a real id to fetch that row's
  // direct children.
  parent_id?: number
  status?: string | string[]
  request_status?: string | string[]
  nomenclature?: string
  search?: string
  spanish?: EstadoCastellano | EstadoCastellano[]
  // Filtran por lo que enseña la columna; el servidor devuelve el nivel más alto que cumple.
  provider?: string[]
  resolution?: string[]
  source?: string[]
  release_group?: string[]
  emu?: string[]
  aporte?: string
  sort?: string
  limit?: number
  offset?: number
}

export async function getLibrary(params: LibraryQueryParams = {}): Promise<LibraryListResponse> {
  const qs = new URLSearchParams()
  const poner = (clave: string, v: string | number | (string | number)[] | undefined) => {
    for (const x of [v ?? []].flat()) if (x !== '') qs.append(clave, String(x))
  }
  poner('type', params.type)
  poner('origin', params.origin)
  poner('instance_id', params.instance_id)
  if (params.parent_id !== undefined) qs.set('parent_id', String(params.parent_id))
  poner('status', params.status)
  poner('request_status', params.request_status)
  poner('nomenclature', params.nomenclature)
  if (params.search) qs.set('search', params.search)
  poner('spanish', params.spanish)
  poner('provider', params.provider)
  poner('resolution', params.resolution)
  poner('source', params.source)
  poner('release_group', params.release_group)
  poner('emu', params.emu)
  poner('aporte', params.aporte)
  if (params.sort) qs.set('sort', params.sort)
  if (params.limit !== undefined) qs.set('limit', String(params.limit))
  if (params.offset !== undefined) qs.set('offset', String(params.offset))
  const query = qs.toString()
  return api.get<LibraryListResponse>(`/library${query ? `?${query}` : ''}`)
}

// Matches the backend's services/library.py::TOP_LEVEL_PARENT_FILTER.
export const TOP_LEVEL_PARENT_FILTER = 0

export async function getLibraryItem(id: number): Promise<LibraryItemResponse> {
  return api.get<LibraryItemResponse>(`/library/${id}`)
}

export interface MediaInfoRow {
  field: string
  mediainfo: string
  emu: string
  help?: string | null
}

export interface MediaInfoReport {
  available: boolean
  message: string | null
  rows: MediaInfoRow[]
  audio_summary?: string | null
}

export async function getMediaInfoReport(id: number): Promise<MediaInfoReport> {
  return api.get<MediaInfoReport>(`/library/${id}/mediainfo`)
}

export interface ProviderSuggestion {
  suggested: string | null
  tmdb_providers: string[]
  reason: string
}

export async function suggestProvider(id: number): Promise<ProviderSuggestion> {
  return api.get<ProviderSuggestion>(`/library/${id}/suggest-provider`)
}

export interface NomenclatureCheckResult {
  status: string | null
  expected: string
  actual: string
  diff: string[]
}

export interface NomenclatureCheckInfo {
  item_type: string
  status: string | null
  pending: number
  available: number
  seasons: number
  result: NomenclatureCheckResult | null
}

export interface NomenclatureCheckSummary {
  attempted: number
  evaluated: number
  correct: number
  not_adapted: number
  errors: number
  error_detail: string | null
  results: { id: number; status: string; error?: string }[]
}

export async function getNomenclatureCheckInfo(id: number): Promise<NomenclatureCheckInfo> {
  return api.get<NomenclatureCheckInfo>(`/library/${id}/nomenclature-check`)
}

export async function runNomenclatureCheck(id: number, force = false): Promise<NomenclatureCheckSummary> {
  return api.post<NomenclatureCheckSummary>(`/library/${id}/nomenclature-check?force=${force ? 'true' : 'false'}`, {})
}

export interface LibraryFilterOptions {
  providers: string[]
  qualities: string[]
  sources: string[]
  release_groups: string[]
  types: string[]
  statuses: string[]
  request_statuses: string[]
  nomenclature_statuses: string[]
  instances: { id: number; type: 'radarr' | 'sonarr'; name: string }[]
  emu_states: ('candidate' | 'present')[]
  aporte_states: ('yes' | 'no')[]
  spanish_states: EstadoCastellano[]
}

export async function getLibraryFilterOptions(): Promise<LibraryFilterOptions> {
  return api.get<LibraryFilterOptions>('/library/filter-options')
}

export async function syncAll(include_episodes = true): Promise<SyncResponse> {
  return api.post<SyncResponse>('/sync', { include_episodes })
}

export async function startLibrarySync(include_episodes = true): Promise<{ status: string }> {
  return api.post<{ status: string }>('/library/sync-start', { include_episodes })
}

export interface LibrarySyncProgress {
  active: boolean
  done: boolean
  phase: string
  imported: number
  missing: number
  total: number
  instance: string
  instance_type: string
  error: string | null
}

export async function getLibrarySyncProgress(): Promise<LibrarySyncProgress> {
  return api.get<LibrarySyncProgress>('/library/sync-progress')
}

export interface EmuSyncStatus {
  last_sync_at: string | null
  can_sync: boolean
  wait_seconds: number
  min_interval_seconds: number
  // Per-mode throttles: incremental (1/hour) and full (1/day).
  incremental_can_sync: boolean
  incremental_wait_seconds: number
  full_can_sync: boolean
  full_wait_seconds: number
  last_full_sync_at: string | null
}

export interface EmuSyncResult {
  status: string
  torrents: number
  items: number
  wait_seconds?: number
}

export async function getEmuSyncStatus(): Promise<EmuSyncStatus> {
  return api.get<EmuSyncStatus>('/library/emu-sync-status')
}

export interface EmuMatch {
  name: string
  resolution: string | null
  source: string | null
  codec: string | null
  has_spanish: number | null
  size: number | null
  // Tu copia frente a este torrent; null si no hay nada que comparar.
  veredicto?: 'mejor' | 'igual' | 'peor' | null
}

export interface EmuComparison {
  available: boolean
  message: string | null
  mine?: { resolution: string | null; source: string | null; codec: string | null; has_es: boolean; size: number | null }
  mine_available?: boolean
  matches: EmuMatch[]
  in_catalog?: number | null
  aportes?: { dim: string; detail: string }[]
  // Season only: eMuwarez has this season only as loose episodes (no season
  // pack), and whether you have every episode (so you could contribute the pack).
  only_episodes?: boolean
  have_all_episodes?: boolean
}

// `resolution` y `source`, si vienen, sustituyen a los de tu copia: lo que el asistente de subida pone en el nombre.
export async function getEmuComparison(
  id: number, tuya?: { resolution?: string | null; source?: string | null },
): Promise<EmuComparison> {
  const consulta = new URLSearchParams()
  if (tuya?.resolution) consulta.set('resolution', tuya.resolution)
  if (tuya?.source) consulta.set('source', tuya.source)
  const query = consulta.toString() ? `?${consulta}` : ''
  return api.get<EmuComparison>(`/library/${id}/emu-comparison${query}`)
}

export type EmuSyncMode = 'incremental' | 'full'

export async function emuSync(mode: EmuSyncMode = 'incremental'): Promise<{ status: string }> {
  return api.post<{ status: string }>(`/library/emu-sync?mode=${mode}`, {})
}

export interface EmuSyncProgress {
  active: boolean
  done: boolean
  phase: string
  torrents: number
  items: number
  page: number
  total_pages: number | null
  eta_seconds: number | null
  error: string | null
}

export async function getEmuSyncProgress(): Promise<EmuSyncProgress> {
  return api.get<EmuSyncProgress>('/library/emu-sync-progress')
}
