import { api } from './client'

export interface ArrInstanceHealth {
  instance_id: number
  instance_type: string
  instance_name: string
  url: string
  enabled: boolean
  ok: boolean
  version?: string
  app_name?: string
  error?: string
  health_status: 'ok' | 'warning' | 'error'
  checked_at: string
}

export interface ArrHealthSummary {
  radarr: number
  sonarr: number
  ok: number
  warning: number
  error: number
}

export interface ArrHealthResponse {
  instances: ArrInstanceHealth[]
  summary: ArrHealthSummary
  checked_at: string
}

export interface ArrHealthRefreshResponse {
  ok: boolean
  health: ArrHealthResponse
  queue_refresh: object | null
  history_refresh: object | null
}

export interface VerifyFilesResponse {
  ok: boolean
  items_checked: number
  files_found: number
  errors: number
  warnings: number
  results: object[]
}

export interface RecommendationResponse {
  item_id: number
  title: string
  recommended_action: string | null
  recommendation_reasons: string[]
  diagnostic_status: string | null
  diagnostic_summary: string | null
  recommendation_updated_at?: string
}

export interface LibraryDiagnosticsResponse {
  items: object[]
  total: number
  limit: number
  offset: number
}

export async function getArrHealth(): Promise<ArrHealthResponse> {
  return api.get<ArrHealthResponse>('/arr/health')
}

export async function refreshArrHealth(params?: {
  include_queue?: boolean
  include_history?: boolean
  history_page_size?: number
}): Promise<ArrHealthRefreshResponse> {
  const qs = new URLSearchParams()
  if (params?.include_queue !== undefined) qs.set('include_queue', String(params.include_queue))
  if (params?.include_history !== undefined) qs.set('include_history', String(params.include_history))
  if (params?.history_page_size !== undefined) qs.set('history_page_size', String(params.history_page_size))
  const query = qs.toString()
  return api.post<ArrHealthRefreshResponse>(`/arr/health/refresh${query ? `?${query}` : ''}`, {})
}

export async function verifyLibraryFiles(params?: {
  limit?: number
  status?: string
}): Promise<VerifyFilesResponse> {
  const qs = new URLSearchParams()
  if (params?.limit !== undefined) qs.set('limit', String(params.limit))
  if (params?.status) qs.set('status', params.status)
  const query = qs.toString()
  return api.post<VerifyFilesResponse>(`/library/verify-files${query ? `?${query}` : ''}`, {})
}

export async function verifySingleFile(itemId: number): Promise<object> {
  return api.post<object>(`/library/${itemId}/verify-file`, {})
}

export async function refreshRecommendations(params?: { status?: string }): Promise<{ ok: boolean; items_updated: number; errors: number }> {
  const qs = new URLSearchParams()
  if (params?.status) qs.set('status', params.status)
  const query = qs.toString()
  return api.post(`/library/recommendations/refresh${query ? `?${query}` : ''}`, {})
}

export async function getItemRecommendation(itemId: number): Promise<RecommendationResponse> {
  return api.get<RecommendationResponse>(`/library/${itemId}/recommendation`)
}

export async function getLibraryDiagnostics(params?: {
  limit?: number
  offset?: number
  status?: string
  search?: string
}): Promise<LibraryDiagnosticsResponse> {
  const qs = new URLSearchParams()
  if (params?.limit !== undefined) qs.set('limit', String(params.limit))
  if (params?.offset !== undefined) qs.set('offset', String(params.offset))
  if (params?.status) qs.set('status', params.status)
  if (params?.search) qs.set('search', params.search)
  const query = qs.toString()
  return api.get<LibraryDiagnosticsResponse>(`/library/diagnostics${query ? `?${query}` : ''}`)
}

export async function getMissingDiagnostics(params?: {
  limit?: number
  offset?: number
}): Promise<LibraryDiagnosticsResponse> {
  const qs = new URLSearchParams()
  if (params?.limit !== undefined) qs.set('limit', String(params.limit))
  if (params?.offset !== undefined) qs.set('offset', String(params.offset))
  const query = qs.toString()
  return api.get<LibraryDiagnosticsResponse>(`/missing/diagnostics${query ? `?${query}` : ''}`)
}
