import { api } from './client'
import type { SetupStatusResponse, OkResponse } from '../types/api'

export async function getSetupStatus(): Promise<SetupStatusResponse> {
  return api.get<SetupStatusResponse>('/setup/status', { skipAuth: true })
}

export async function setupAdmin(username: string, password: string): Promise<OkResponse> {
  return api.post<OkResponse>('/setup/admin', { username, password }, { skipAuth: true })
}

export async function setupBase(app_name: string, timezone: string): Promise<OkResponse> {
  return api.post<OkResponse>('/setup/base', { app_name, timezone })
}

export async function setupUploadrr(uploadrr_path: string): Promise<OkResponse> {
  return api.post<OkResponse>('/setup/uploadrr', { uploadrr_path })
}

export async function setupTmdb(api_key: string, language = 'es-ES', region = 'ES'): Promise<OkResponse> {
  return api.post<OkResponse>('/setup/tmdb', { api_key, language, region })
}

export async function setupEmu(api_key: string, endpoint_url: string | null = null): Promise<OkResponse> {
  return api.post<OkResponse>('/setup/emu', { api_key, endpoint_url })
}

export async function setupInstances(instances: unknown[]): Promise<OkResponse> {
  return api.post<OkResponse>('/setup/instances', { instances })
}

export async function setupComplete(): Promise<OkResponse> {
  return api.post<OkResponse>('/setup/complete')
}
