import { api } from './client'

export interface LogEntry {
  ts: number
  time: string
  level: string
  logger: string
  message: string
}

export interface LogsResponse {
  items: LogEntry[]
  count: number
}

export function getLogs(params: { limit?: number; level?: string; search?: string } = {}): Promise<LogsResponse> {
  const qs = new URLSearchParams()
  if (params.limit) qs.set('limit', String(params.limit))
  if (params.level) qs.set('level', params.level)
  if (params.search) qs.set('search', params.search)
  const q = qs.toString()
  return api.get<LogsResponse>(`/logs${q ? `?${q}` : ''}`)
}
