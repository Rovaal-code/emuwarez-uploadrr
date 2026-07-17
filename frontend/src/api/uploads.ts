import { api } from './client'
import type {
  UploadPreflightResponse,
  UploadJob,
  UploadJobLogsResponse,
  UploadStartRequest,
  UploadStartResult,
  UploadArtifactsResponse,
  UploadRetryRequest,
} from '../types/api'
import type { TrackRemuxOverride } from './nomenclature'

export async function uploadPreflight(itemId: number, requestId?: number): Promise<UploadPreflightResponse> {
  return api.post<UploadPreflightResponse>(`/library/${itemId}/upload/preflight`, { request_id: requestId ?? null })
}

export interface UploadQueueResult {
  status: string
  job: UploadJob | null
  errors: string[]
}

// Queues "Subir a eMuwarez": the job appears immediately in Subidas as
// 'queued' with a grace period (see services/upload_queue.py) before the
// server actually renames/remuxes/starts it — nothing runs synchronously here.
export async function queueUpload(
  itemId: number,
  remuxOverrides?: Record<number, TrackRemuxOverride>,
): Promise<UploadQueueResult> {
  return api.post<UploadQueueResult>(`/library/${itemId}/upload/queue`, { remux_overrides: remuxOverrides ?? null })
}

export async function getUploads(params?: { status?: string; limit?: number; offset?: number; search?: string }): Promise<UploadJob[]> {
  const qs = new URLSearchParams()
  if (params?.status) qs.set('status', params.status)
  if (params?.limit != null) qs.set('limit', String(params.limit))
  if (params?.offset != null) qs.set('offset', String(params.offset))
  if (params?.search) qs.set('search', params.search)
  const query = qs.toString()
  return api.get<UploadJob[]>(`/uploads${query ? `?${query}` : ''}`)
}

export async function getUploadJob(jobId: number): Promise<UploadJob> {
  return api.get<UploadJob>(`/uploads/${jobId}`)
}

export async function getUploadJobLogs(
  jobId: number,
  limit = 500,
  offset = 0,
): Promise<UploadJobLogsResponse> {
  return api.get<UploadJobLogsResponse>(`/uploads/${jobId}/logs?limit=${limit}&offset=${offset}`)
}

export async function getUploadJobArtifacts(jobId: number): Promise<UploadArtifactsResponse> {
  return api.get<UploadArtifactsResponse>(`/uploads/${jobId}/artifacts`)
}

export async function startUploadJob(
  jobId: number,
  body: UploadStartRequest,
): Promise<UploadStartResult> {
  return api.post<UploadStartResult>(`/uploads/${jobId}/start`, body)
}

export async function retryUploadJob(
  jobId: number,
  body: UploadRetryRequest,
): Promise<UploadStartResult> {
  return api.post<UploadStartResult>(`/uploads/${jobId}/retry`, body)
}

export async function cancelUploadJob(jobId: number): Promise<unknown> {
  return api.post<unknown>(`/uploads/${jobId}/cancel`, {})
}

export interface UploadCheck {
  id: string
  label: string
  status: 'ok' | 'fail' | 'skip'
  message: string
}
export interface UploadChecksResult {
  checks: UploadCheck[]
  ready: boolean
}

export async function runUploadChecks(itemId: number): Promise<UploadChecksResult> {
  return api.post<UploadChecksResult>(`/library/${itemId}/upload/checks`, {})
}

export interface UploadChecksProgress {
  checks: UploadCheck[]
  done: boolean
  ready: boolean
}

// Poll this WHILE runUploadChecks() is in flight to see each check land as it
// actually completes (the full run is ~30s of real network calls).
export async function getUploadChecksProgress(itemId: number): Promise<UploadChecksProgress> {
  return api.get<UploadChecksProgress>(`/library/${itemId}/upload/checks/progress`)
}
