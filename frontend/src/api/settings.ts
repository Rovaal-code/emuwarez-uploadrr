import { api } from './client'

export type UploadrrRuntimeType = 'uploadrr_emu' | 'uploadrr_generic'

export interface SettingsData {
  default_release_tag: string
  provider_priority_order: string[]
  tmdb_watch_region: string
  tmdb_language: string
  tmdb_api_key_configured: boolean
  tmdb_api_key_masked: string | null
  emu_api_key_configured: boolean
  emu_api_key_masked: string | null
  emu_username: string | null
  uploadrr_path: string | null
  uploadrr_runtime_type: UploadrrRuntimeType
  uploadrr_python_path: string | null
  uploadrr_timeout: number
  uploadrr_allowed_roots: string[]
  notify_discord_enabled: boolean
  notify_discord_webhook_configured: boolean
  notify_discord_webhook_masked: string | null
  notify_telegram_enabled: boolean
  notify_telegram_bot_token_configured: boolean
  notify_telegram_bot_token_masked: string | null
  notify_telegram_chat_id: string | null
  notify_event_types: { code: string; label: string }[]
  notify_discord_events: string[]
  notify_telegram_events: string[]
  series_ignore_specials: boolean
  recent_activity_limit: number
}

export interface SettingsUpdatePayload {
  default_release_tag?: string
  provider_priority_order?: string[]
  tmdb_watch_region?: string
  tmdb_language?: string
  tmdb_api_key?: string
  emu_api_key?: string
  emu_username?: string
  uploadrr_path?: string
  uploadrr_runtime_type?: UploadrrRuntimeType
  uploadrr_python_path?: string
  uploadrr_timeout?: number
  uploadrr_allowed_roots?: string[] | string
  notify_discord_enabled?: boolean
  notify_discord_webhook_url?: string
  notify_telegram_enabled?: boolean
  notify_telegram_bot_token?: string
  notify_telegram_chat_id?: string
  notify_discord_events?: string[]
  notify_telegram_events?: string[]
  series_ignore_specials?: boolean
  recent_activity_limit?: number
}

export function fetchSettings(): Promise<SettingsData> {
  return api.get<SettingsData>('/settings')
}

export function updateSettings(payload: SettingsUpdatePayload): Promise<SettingsData> {
  return api.put<SettingsData>('/settings', payload)
}
