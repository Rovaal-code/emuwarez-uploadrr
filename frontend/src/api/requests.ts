import { api } from './client'
import type {
  RequestListResponse,
  RequestDetailResponse,
  RequestSyncResponse,
  RequestSyncStatusResponse,
  OkResponse,
} from '../types/api'

export interface RequestsFilter {
  search?: string
  // Las columnas admiten varios valores: lista vacía = sin filtro.
  status?: string[]
  category?: string[]
  resolution?: string[]
  source?: string[]
  author?: string[]
  instance_id?: number[]
  emu_status?: string
  sort?: string
  limit?: number
  offset?: number
}

export async function getRequests(filter?: RequestsFilter): Promise<RequestListResponse> {
  const q = new URLSearchParams()
  if (filter?.search) q.set('search', filter.search)
  filter?.status?.forEach(v => q.append('status', v))
  filter?.category?.forEach(v => q.append('category', v))
  filter?.resolution?.forEach(v => q.append('resolution', v))
  filter?.source?.forEach(v => q.append('source', v))
  filter?.author?.forEach(v => q.append('author', v))
  filter?.instance_id?.forEach(v => q.append('instance_id', String(v)))
  if (filter?.emu_status) q.set('emu_status', filter.emu_status)
  if (filter?.sort) q.set('sort', filter.sort)
  if (filter?.limit !== undefined) q.set('limit', String(filter.limit))
  if (filter?.offset !== undefined) q.set('offset', String(filter.offset))
  const qs = q.toString()
  return api.get(`/requests${qs ? '?' + qs : ''}`)
}

export async function getSyncStatus(): Promise<RequestSyncStatusResponse> {
  return api.get('/requests/sync-status')
}

export async function syncRequests(force = false): Promise<RequestSyncResponse> {
  return api.post('/requests/sync', { force })
}

export async function getRequestDetail(id: number): Promise<RequestDetailResponse> {
  return api.get(`/requests/${id}`)
}

export async function rematchRequest(id: number): Promise<RequestDetailResponse> {
  return api.post(`/requests/${id}/match`, {})
}

export async function markRequestReviewed(id: number): Promise<OkResponse> {
  return api.post(`/requests/${id}/mark-reviewed`, {})
}
