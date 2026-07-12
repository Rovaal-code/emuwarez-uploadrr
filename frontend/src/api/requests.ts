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
  status?: string
  category?: string
  resolution?: string
  source?: string
  emu_status?: string
  sort?: string
  limit?: number
  offset?: number
}

export async function getRequests(filter?: RequestsFilter): Promise<RequestListResponse> {
  const q = new URLSearchParams()
  if (filter?.search) q.set('search', filter.search)
  if (filter?.status) q.set('status', filter.status)
  if (filter?.category) q.set('category', filter.category)
  if (filter?.resolution) q.set('resolution', filter.resolution)
  if (filter?.source) q.set('source', filter.source)
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
