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

export async function syncAll(include_episodes = true): Promise<SyncResponse> {
  return api.post<SyncResponse>('/sync', { include_episodes })
}
