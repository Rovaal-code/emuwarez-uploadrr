import { api } from './client'

export interface IntegrationTestResult {
  ok: boolean
  service: string
  status: string
  message: string
  details?: Record<string, unknown>
}

export function testTmdbConnection(params: {
  api_key?: string
  language?: string
  region?: string
} = {}): Promise<IntegrationTestResult> {
  return api.post<IntegrationTestResult>('/integrations/test/tmdb', params)
}

export function testEmuwarezConnection(params: {
  api_key?: string
  base_url?: string
} = {}): Promise<IntegrationTestResult> {
  return api.post<IntegrationTestResult>('/integrations/test/emuwarez', params)
}

export function testArrConnection(params: {
  kind: string
  base_url: string
  api_key: string
}): Promise<IntegrationTestResult> {
  return api.post<IntegrationTestResult>('/integrations/test/arr', params)
}

export function testUploadrrConnection(params: {
  path?: string
  python_path?: string
} = {}): Promise<IntegrationTestResult> {
  return api.post<IntegrationTestResult>('/integrations/test/uploadrr', params)
}

export function testSeerrConnection(params: {
  instance_id?: number
  base_url?: string
  api_key?: string
} = {}): Promise<IntegrationTestResult> {
  return api.post<IntegrationTestResult>('/integrations/test/seerr', params)
}
