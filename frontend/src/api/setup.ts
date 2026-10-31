import { api } from './client'
import type { SetupStatusResponse, OkResponse } from '../types/api'

export async function getSetupStatus(): Promise<SetupStatusResponse> {
  return api.get<SetupStatusResponse>('/setup/status', { skipAuth: true })
}

export async function setupAdmin(username: string, password: string): Promise<OkResponse> {
  return api.post<OkResponse>('/setup/admin', { username, password }, { skipAuth: true })
}

export async function setupTmdb(api_key: string, region = 'ES', localize_series_titles = true): Promise<OkResponse> {
  return api.post<OkResponse>('/setup/tmdb', { api_key, region, localize_series_titles })
}

export async function setupEmu(api_key: string, endpoint_url: string | null = null): Promise<OkResponse> {
  return api.post<OkResponse>('/setup/emu', { api_key, endpoint_url })
}

// El puerto va dentro de la url; `tag` es la etiqueta que qBittorrent pone al
// torrent para reconocer tus subidas (vacía = no etiquetar).
export async function setupQbit(url: string, username = '', password = '', tag = ''): Promise<OkResponse> {
  return api.post<OkResponse>('/setup/qbit', { url, username, password, tag })
}

export async function setupImghosts(enabled: string[], keys: Record<string, string>): Promise<OkResponse> {
  return api.post<OkResponse>('/setup/imghosts', { enabled, keys })
}

export interface SetupInstancePayload {
  type: string
  name: string
  url: string
  api_key: string
  is_4k?: boolean
  is_anime?: boolean
}

// POST /setup/instances takes ONE flat instance per call (not an array); the
// wizard calls it once per instance so each can leave its draft as it's saved.
export async function setupInstance(inst: SetupInstancePayload): Promise<OkResponse> {
  return api.post<OkResponse>('/setup/instances', inst)
}

export async function setupComplete(): Promise<OkResponse> {
  return api.post<OkResponse>('/setup/complete')
}
