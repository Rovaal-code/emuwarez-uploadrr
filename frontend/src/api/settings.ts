import { api } from './client'

export type UploadrrRuntimeType = 'uploadrr_emu' | 'uploadrr_generic'

export interface SettingsData {
  default_release_tag: string
  provider_priority_order: string[]
  tmdb_watch_region: string
  tmdb_language: string
  tmdb_localize_series_titles: boolean
  qbit_url: string | null
  qbit_port: string | null
  qbit_username: string | null
  qbit_password_configured: boolean
  qbit_configured: boolean
  image_hosts_available: { id: string; label: string; needs_key: boolean }[]
  image_hosts_enabled: string[]
  image_host_keys_configured: string[]
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
  use_hardlinks: boolean
  hardlink_base: string | null
  hardlink_configured: boolean
  notify_discord_enabled: boolean
  notify_discord_webhook_configured: boolean
  notify_discord_webhook_masked: string | null
  notify_telegram_enabled: boolean
  notify_telegram_bot_token_configured: boolean
  notify_telegram_bot_token_masked: string | null
  notify_telegram_chat_id: string | null
  notify_ui_enabled: boolean
  notify_event_types: { code: string; label: string }[]
  notify_ui_events: string[]
  notify_discord_events: string[]
  notify_telegram_events: string[]
  series_ignore_specials: boolean
  recent_activity_limit: number
  path_mappings: { from: string; to: string }[]
}

export interface SettingsUpdatePayload {
  default_release_tag?: string
  provider_priority_order?: string[]
  tmdb_watch_region?: string
  tmdb_language?: string
  tmdb_localize_series_titles?: boolean
  qbit_url?: string
  qbit_port?: string
  qbit_username?: string
  qbit_password?: string
  image_hosts_enabled?: string[]
  image_host_keys?: Record<string, string>
  tmdb_api_key?: string
  emu_api_key?: string
  emu_username?: string
  uploadrr_path?: string
  uploadrr_runtime_type?: UploadrrRuntimeType
  uploadrr_python_path?: string
  uploadrr_timeout?: number
  uploadrr_allowed_roots?: string[] | string
  use_hardlinks?: boolean
  hardlink_base?: string
  notify_discord_enabled?: boolean
  notify_discord_webhook_url?: string
  notify_telegram_enabled?: boolean
  notify_telegram_bot_token?: string
  notify_telegram_chat_id?: string
  notify_ui_enabled?: boolean
  notify_ui_events?: string[]
  notify_discord_events?: string[]
  notify_telegram_events?: string[]
  series_ignore_specials?: boolean
  recent_activity_limit?: number
  path_mappings?: { from: string; to: string }[]
}

export function fetchSettings(): Promise<SettingsData> {
  return api.get<SettingsData>('/settings')
}

export function updateSettings(payload: SettingsUpdatePayload): Promise<SettingsData> {
  return api.put<SettingsData>('/settings', payload)
}

// Create a real test hardlink in the given base dir (or the saved one if omitted)
// to verify hardlinks work before saving.
export function testHardlink(hardlink_base?: string): Promise<{ ok: boolean; message: string }> {
  return api.post<{ ok: boolean; message: string }>('/settings/test-hardlink', { hardlink_base })
}
