import { api } from './client'
import type { MissingListResponse } from '../types/api'

export interface MissingQueryParams {
  limit?: number
  offset?: number
}

export async function getMissing(params: MissingQueryParams = {}): Promise<MissingListResponse> {
  const qs = new URLSearchParams()
  if (params.limit !== undefined) qs.set('limit', String(params.limit))
  if (params.offset !== undefined) qs.set('offset', String(params.offset))
  const query = qs.toString()
  return api.get<MissingListResponse>(`/missing${query ? `?${query}` : ''}`)
}
