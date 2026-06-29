import { api } from './client'
import type {
  UploadPreflightResponse,
  UploadJob,
  UploadJobLogsResponse,
  UploadStartRequest,
  UploadStartResult,
} from '../types/api'

export async function uploadPreflight(itemId: number, requestId?: number): Promise<UploadPreflightResponse> {
  return api.post<UploadPreflightResponse>(`/library/${itemId}/upload/preflight`, { request_id: requestId ?? null })
}

export async function getUploads(): Promise<UploadJob[]> {
  return api.get<UploadJob[]>('/uploads')
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

export async function startUploadJob(
  jobId: number,
  body: UploadStartRequest,
): Promise<UploadStartResult> {
  return api.post<UploadStartResult>(`/uploads/${jobId}/start`, body)
}

export async function cancelUploadJob(jobId: number): Promise<unknown> {
  return api.post<unknown>(`/uploads/${jobId}/cancel`, {})
}
