import { api } from './client'
import type { ModoPistas } from '../utils/modoPistas'

export type UploadrrRuntimeType = 'uploadrr_emu' | 'uploadrr_generic'

export interface SettingsData {
  default_release_tag: string
  upload_tags?: string[]
  provider_priority_order: string[]
  tmdb_watch_region: string
  tmdb_localize_series_titles: boolean
  qbit_url: string | null
  qbit_tag: string | null
  source_engine_enabled: boolean
  emu_add_logo: boolean
  emu_per_episode_screens: boolean
  remux_track_mode: ModoPistas
  qbit_username: string | null
  qbit_password_configured: boolean
  qbit_qui_configured: boolean
  qbit_configured: boolean
  image_hosts_available: { id: string; label: string; needs_key: boolean; url?: string; favicon?: string | null }[]
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
  upload_max_concurrent: number
  path_mappings: { from: string; to: string }[]
}

export interface SettingsUpdatePayload {
  default_release_tag?: string
  upload_tags?: string[]
  provider_priority_order?: string[]
  tmdb_watch_region?: string
  tmdb_localize_series_titles?: boolean
  qbit_url?: string
  qbit_tag?: string
  source_engine_enabled?: boolean
  emu_add_logo?: boolean
  emu_per_episode_screens?: boolean
  remux_track_mode?: ModoPistas
  qbit_username?: string
  qbit_password?: string
  qbit_qui_proxy_url?: string
  qbit_qui_proxy_clear?: boolean
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
  upload_max_concurrent?: number
  path_mappings?: { from: string; to: string }[]
}

export function fetchSettings(): Promise<SettingsData> {
  return api.get<SettingsData>('/settings')
}

export function updateSettings(payload: SettingsUpdatePayload): Promise<SettingsData> {
  return api.put<SettingsData>('/settings', payload)
}
