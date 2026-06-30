import { api } from './client'
import type {
  OperationalQueueListResponse,
  OperationalQueueSummary,
  OperationalQueueRefreshResponse,
  OperationalQueueItem,
  OperationalQueueActionResponse,
} from '../types/api'

export async function listQueue(params?: {
  status?: string
  action?: string
  priority_bucket?: string
  item_type?: string
  search?: string
  limit?: number
  offset?: number
}): Promise<OperationalQueueListResponse> {
  const q = new URLSearchParams()
  if (params?.status) q.set('status', params.status)
  if (params?.action) q.set('action', params.action)
  if (params?.priority_bucket) q.set('priority_bucket', params.priority_bucket)
  if (params?.item_type) q.set('item_type', params.item_type)
  if (params?.search) q.set('search', params.search)
  if (params?.limit) q.set('limit', String(params.limit))
  if (params?.offset) q.set('offset', String(params.offset))
  const qs = q.toString()
  return api.get<OperationalQueueListResponse>(`/operational-queue${qs ? '?' + qs : ''}`)
}

export async function getQueueSummary(): Promise<OperationalQueueSummary> {
  return api.get<OperationalQueueSummary>('/operational-queue/summary')
}

export async function refreshQueue(body?: {
  limit?: number
  include_requests?: boolean
  include_library?: boolean
  include_uploads?: boolean
  include_arr?: boolean
}): Promise<OperationalQueueRefreshResponse> {
  return api.post<OperationalQueueRefreshResponse>('/operational-queue/refresh', body ?? {})
}

export async function getQueueItem(id: number): Promise<OperationalQueueItem> {
  return api.get<OperationalQueueItem>(`/operational-queue/${id}`)
}

export async function resolveQueueItem(id: number, reason?: string): Promise<OperationalQueueActionResponse> {
  return api.post<OperationalQueueActionResponse>(`/operational-queue/${id}/resolve`, { reason: reason ?? null })
}

export async function ignoreQueueItem(id: number, reason?: string): Promise<OperationalQueueActionResponse> {
  return api.post<OperationalQueueActionResponse>(`/operational-queue/${id}/ignore`, { reason: reason ?? null })
}
