// API response types matching backend schemas

export interface SetupStatusResponse {
  initialized: boolean
  admin_configured: boolean
  base_configured: boolean
  tmdb_configured: boolean
  emu_configured: boolean
  uploadrr_configured: boolean
  radarr_instances: number
  sonarr_instances: number
  jellyfin_configured: boolean
  seerr_configured: boolean
  next_step: string | null
}

export interface LoginResponse {
  token: string
  username: string
  role: string
  message: string
}

export interface CurrentUserResponse {
  id: number
  username: string
  role: string
  created_at: string
  last_login_at: string | null
}

export interface DashboardSummaryResponse {
  library_total: number
  available: number
  missing: number
  uploading: number
  completed: number
  radarr_items: number
  sonarr_items: number
  last_sync_at: string | null
}

export interface DashboardActivityItem {
  id: number
  name: string
  status: string
  started_at: string | null
  finished_at: string | null
  summary: string | null
}

export interface DashboardActivityResponse {
  items: DashboardActivityItem[]
}

export interface InstanceSafeResponse {
  id: number
  type: string
  name: string
  url: string
  api_key_masked: string
  enabled: boolean
  is_4k: boolean
  is_anime: boolean
  last_test_status: string | null
  last_test_at: string | null
  created_at: string
  updated_at: string | null
}

export interface InstanceTestResponse {
  ok: boolean
  instance_id: number | null
  instance_name: string | null
  version: string | null
  error: string | null
}

export interface LibraryItemResponse {
  id: number
  item_type: string
  title: string
  year: number | null
  original_title: string | null
  instance_type: string | null
  instance_name: string | null
  external_id: string | null
  tmdb_id: string | null
  imdb_id: string | null
  tvdb_id: string | null
  path: string | null
  quality: string | null
  resolution: string | null
  source: string | null
  size_bytes: number | null
  local_status: string
  request_status: string
  nomenclature_status: string
  updated_at: string | null
}

export interface LibraryListResponse {
  items: LibraryItemResponse[]
  total: number
  limit: number
  offset: number
}

export interface MissingItemResponse {
  id: number
  item_type: string
  title: string
  year: number | null
  instance_type: string | null
  instance_name: string | null
  tmdb_id: string | null
  imdb_id: string | null
  local_status: string
  request_status: string
  updated_at: string | null
}

export interface MissingListResponse {
  items: MissingItemResponse[]
  total: number
  limit: number
  offset: number
}

export interface SyncResponse {
  ok: boolean
  imported: number
  missing: number
  instances: number
  errors: string[]
  message: string
}

export interface OkResponse {
  ok: boolean
  message: string
}

export interface ApiError {
  detail: string
  status_code?: number
}

// Phase 5B — Requests

export interface RequestMatchResponse {
  id: number
  library_item_id: number | null
  library_title: string | null
  local_status: string | null
  local_resolution: string | null
  local_source: string | null
  local_path: string | null
  nomenclature_status: string | null
  status: string
  confidence: number
  resolution_match: boolean | null
  source_match: boolean | null
  id_match: boolean
  reasons: string[]
}

export interface RequestItemResponse {
  id: number
  emu_id: string
  title: string
  category: string | null
  requested_source: string | null
  requested_resolution: string | null
  emu_status: string | null
  points: number | null
  comments: number | null
  created_at: string | null
  tmdb_id: string | null
  imdb_id: string | null
  url: string | null
  compatibility_status: string | null
  compatibility_confidence: number | null
  library_item_id: number | null
  library_title: string | null
  local_status: string | null
  reviewed_at: string | null
  updated_at: string | null
}

export interface RequestDetailResponse extends RequestItemResponse {
  match: RequestMatchResponse | null
}

export interface RequestListResponse {
  items: RequestItemResponse[]
  total: number
  limit: number
  offset: number
}

export interface RequestSyncStatusResponse {
  last_sync_at: string | null
  next_sync_at: string | null
  can_sync: boolean
  wait_seconds: number
  min_interval_seconds: number
}

export interface RequestSyncResponse {
  ok: boolean
  status: string
  imported: number
  matched: number
  wait_seconds: number
  message: string
}

// Updated DashboardSummaryResponse with EMU fields
export interface DashboardSummaryResponseV2 extends DashboardSummaryResponse {
  requests_total: number
  requests_compatible: number
  requests_filled: number
  requests_last_sync_at: string | null
}
