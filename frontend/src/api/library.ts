import { api } from './client'
import type { LibraryListResponse, LibraryItemResponse, SyncResponse } from '../types/api'

export interface LibraryQueryParams {
  type?: string
  origin?: string
  instance_id?: number
  // Series/Season/Episode hierarchy — omit for "no filter" (CLI-style
  // callers), pass 0 (TOP_LEVEL_PARENT_FILTER, matches the backend
  // sentinel) for "top level only", or a real id to fetch that row's
  // direct children.
  parent_id?: number
  status?: string
  request_status?: string
  nomenclature?: string
  search?: string
  sort?: string
  limit?: number
  offset?: number
}

export async function getLibrary(params: LibraryQueryParams = {}): Promise<LibraryListResponse> {
  const qs = new URLSearchParams()
  if (params.type) qs.set('type', params.type)
  if (params.origin) qs.set('origin', params.origin)
  if (params.instance_id !== undefined) qs.set('instance_id', String(params.instance_id))
  if (params.parent_id !== undefined) qs.set('parent_id', String(params.parent_id))
  if (params.status) qs.set('status', params.status)
  if (params.request_status) qs.set('request_status', params.request_status)
  if (params.nomenclature) qs.set('nomenclature', params.nomenclature)
  if (params.search) qs.set('search', params.search)
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
}

export async function getLibraryFilterOptions(): Promise<LibraryFilterOptions> {
  return api.get<LibraryFilterOptions>('/library/filter-options')
}

export async function syncAll(include_episodes = true): Promise<SyncResponse> {
  return api.post<SyncResponse>('/sync', { include_episodes })
}

export interface EmuSyncStatus {
  last_sync_at: string | null
  can_sync: boolean
  wait_seconds: number
  min_interval_seconds: number
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

export async function getEmuComparison(id: number): Promise<EmuComparison> {
  return api.get<EmuComparison>(`/library/${id}/emu-comparison`)
}

export async function emuSync(): Promise<{ status: string }> {
  return api.post<{ status: string }>('/library/emu-sync', {})
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
