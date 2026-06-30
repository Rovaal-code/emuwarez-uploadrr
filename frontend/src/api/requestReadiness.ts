import { api } from './client'
import type {
  RequestReadinessResponse,
  RequestReadinessListResponse,
  RequestCandidateResponse,
  OkResponse,
} from '../types/api'

export interface ReadinessFilter {
  status?: string
  action?: string
  priority_bucket?: string
  search?: string
  limit?: number
  offset?: number
}

export async function listReadiness(filter?: ReadinessFilter): Promise<RequestReadinessListResponse> {
  const q = new URLSearchParams()
  if (filter?.status) q.set('status', filter.status)
  if (filter?.action) q.set('action', filter.action)
  if (filter?.priority_bucket) q.set('priority_bucket', filter.priority_bucket)
  if (filter?.search) q.set('search', filter.search)
  if (filter?.limit !== undefined) q.set('limit', String(filter.limit))
  if (filter?.offset !== undefined) q.set('offset', String(filter.offset))
  const qs = q.toString()
  return api.get(`/api/requests/readiness${qs ? '?' + qs : ''}`)
}

export async function refreshReadiness(limit?: number): Promise<OkResponse> {
  return api.post('/api/requests/readiness/refresh', limit ? { limit } : {})
}

export async function getReadiness(requestId: number): Promise<RequestReadinessResponse> {
  return api.get(`/api/requests/${requestId}/readiness`)
}

export async function evaluateReadiness(requestId: number): Promise<RequestReadinessResponse> {
  return api.post(`/api/requests/${requestId}/readiness/evaluate`, {})
}

export async function getCandidates(requestId: number): Promise<RequestCandidateResponse[]> {
  return api.get(`/api/requests/${requestId}/candidates`)
}

export async function listPrioritized(limit = 200): Promise<RequestReadinessListResponse> {
  return api.get(`/api/requests/prioritized?limit=${limit}`)
}
