import { api } from './client'

export interface SettingsData {
  default_release_tag: string
  provider_priority_order: string[]
  tmdb_watch_region: string
  tmdb_language: string
  tmdb_api_key_configured: boolean
  tmdb_api_key_masked: string | null
}

export interface SettingsUpdatePayload {
  default_release_tag?: string
  provider_priority_order?: string[]
  tmdb_watch_region?: string
  tmdb_language?: string
  tmdb_api_key?: string
}

export function fetchSettings(): Promise<SettingsData> {
  return api.get<SettingsData>('/settings')
}

export function updateSettings(payload: SettingsUpdatePayload): Promise<SettingsData> {
  return api.put<SettingsData>('/settings', payload)
}
