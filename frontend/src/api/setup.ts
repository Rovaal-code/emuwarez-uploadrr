import { api } from './client'
import type { SetupStatusResponse, OkResponse } from '../types/api'

export async function getSetupStatus(): Promise<SetupStatusResponse> {
  return api.get<SetupStatusResponse>('/setup/status', { skipAuth: true })
}

export async function setupAdmin(username: string, password: string): Promise<OkResponse> {
  return api.post<OkResponse>('/setup/admin', { username, password }, { skipAuth: true })
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

export interface SetupInstancePayload {
  type: string
  name: string
  url: string
  api_key: string
  is_4k?: boolean
  is_anime?: boolean
}

// POST /setup/instances takes ONE flat instance per call (not an array) —
// this loops so the wizard can still let the user add several before
// continuing. (Phase 11C fix: this used to POST { instances: [...] } as a
// single wrapped body, which the endpoint always rejected with 422.)
export async function setupInstances(instances: SetupInstancePayload[]): Promise<OkResponse[]> {
  const results: OkResponse[] = []
  for (const inst of instances) {
    results.push(await api.post<OkResponse>('/setup/instances', inst))
  }
  return results
}

export async function setupNomenclature(params: {
  default_release_tag: string
  hardlink_base?: string
  use_hardlinks: boolean
  confirmation?: string
}): Promise<OkResponse> {
  return api.post<OkResponse>('/setup/nomenclature', params)
}

export async function setupComplete(): Promise<OkResponse> {
  return api.post<OkResponse>('/setup/complete')
}
