import { api } from './client'
import type { LibraryListResponse, LibraryItemResponse, SyncResponse } from '../types/api'

export interface LibraryQueryParams {
  type?: string
  origin?: string
  instance_id?: number
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
  if (params.status) qs.set('status', params.status)
  if (params.request_status) qs.set('request_status', params.request_status)
  if (params.nomenclature) qs.set('nomenclature', params.nomenclature)
  if (params.search) qs.set('search', params.search)
  if (params.limit !== undefined) qs.set('limit', String(params.limit))
  if (params.offset !== undefined) qs.set('offset', String(params.offset))
  const query = qs.toString()
  return api.get<LibraryListResponse>(`/library${query ? `?${query}` : ''}`)
}

export async function getLibraryItem(id: number): Promise<LibraryItemResponse> {
  return api.get<LibraryItemResponse>(`/library/${id}`)
}

export async function syncAll(include_episodes = true): Promise<SyncResponse> {
  return api.post<SyncResponse>('/sync', { include_episodes })
}
