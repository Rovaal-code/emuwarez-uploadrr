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
  limit?: number
  offset?: number
}

export async function getRequests(filter?: RequestsFilter): Promise<RequestListResponse> {
  const q = new URLSearchParams()
  if (filter?.search) q.set('search', filter.search)
  if (filter?.status) q.set('status', filter.status)
  if (filter?.limit !== undefined) q.set('limit', String(filter.limit))
  if (filter?.offset !== undefined) q.set('offset', String(filter.offset))
  const qs = q.toString()
  return api.get(`/api/requests${qs ? '?' + qs : ''}`)
}

export async function getSyncStatus(): Promise<RequestSyncStatusResponse> {
  return api.get('/api/requests/sync-status')
}

export async function syncRequests(force = false): Promise<RequestSyncResponse> {
  return api.post('/api/requests/sync', { force })
}

export async function getRequestDetail(id: number): Promise<RequestDetailResponse> {
  return api.get(`/api/requests/${id}`)
}

export async function rematchRequest(id: number): Promise<RequestDetailResponse> {
  return api.post(`/api/requests/${id}/match`, {})
}

export async function markRequestReviewed(id: number): Promise<OkResponse> {
  return api.post(`/api/requests/${id}/mark-reviewed`, {})
}
