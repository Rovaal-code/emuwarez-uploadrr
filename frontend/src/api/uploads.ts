import { api } from './client'
import type { UploadPreflightResponse, UploadJob } from '../types/api'

export async function uploadPreflight(itemId: number, requestId?: number): Promise<UploadPreflightResponse> {
  return api.post<UploadPreflightResponse>(`/library/${itemId}/upload/preflight`, { request_id: requestId ?? null })
}

export async function getUploads(): Promise<UploadJob[]> {
  return api.get<UploadJob[]>('/uploads')
}

export async function getUploadJob(jobId: number): Promise<UploadJob> {
  return api.get<UploadJob>(`/uploads/${jobId}`)
}
