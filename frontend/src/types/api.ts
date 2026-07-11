// API response types matching backend schemas

export interface SetupStatusResponse {
  initialized: boolean
  admin_configured: boolean
  tmdb_configured: boolean
  emu_configured: boolean
  radarr_instances: number
  sonarr_instances: number
  jellyfin_configured: boolean
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
  // Phase 8B — request readiness (used by "Peticiones eMuwarez")
  requests_ready_to_upload?: number
  requests_need_nomenclature?: number
  requests_waiting_download?: number
  requests_blocked?: number
  // Phase 5B — already computed backend-side, just missing from the type
  requests_total?: number
  requests_compatible?: number
  requests_filled?: number
  requests_mine?: number
  requests_last_sync_at?: string | null
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
  username: string | null
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
  instance_id: number | null
  external_id: string | null
  tmdb_id: string | null
  imdb_id: string | null
  tvdb_id: string | null
  title_slug: string | null
  // Series/Season/Episode hierarchy — parent_id points at the containing
  // row's id (episode -> season, season -> series); null for movies/series.
  season_number: number | null
  episode_number: number | null
  parent_id: number | null
  path: string | null
  quality: string | null
  resolution: string | null
  source: string | null
  provider: string | null
  provider_label: string | null
  video_codec: string | null
  audio_codec: string | null
  audio_languages: string | null
  subtitle_languages: string | null
  size_bytes: number | null
  local_status: string
  request_status: string
  nomenclature_status: string
  updated_at: string | null
  // Phase 8A
  file_exists: boolean | null
  file_verified_at: string | null
  diagnostic_status: string | null
  diagnostic_summary: string | null
  recommended_action: string | null
  arr_queue_status: string | null
  arr_history_status: string | null
  // Phase 11E
  poster_url: string | null
  // eMuwarez catalog comparison: 1 = already on eMuwarez, 0 = not, null = not synced.
  emu_in_catalog: number | null
  emu_aportes: EmuAporte[] | null
}

export interface EmuAporte {
  dim: string
  detail: string
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
  // Phase 8A
  arr_queue_status: string | null
  arr_queue_progress: number | null
  arr_queue_timeleft: string | null
  arr_queue_error: string | null
  arr_history_error: string | null
  file_exists: boolean | null
  diagnostic_status: string | null
  recommended_action: string | null
  recommendation_reasons: string[] | null
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
  // Phase 8B
  readiness_status: string | null
  readiness_action: string | null
  readiness_best_library_item_id: number | null
}

// Phase 8B — Request Readiness

export interface RequestReadinessResponse {
  id: number
  request_item_id: number
  title: string | null
  emu_id: string | null
  best_library_item_id: number | null
  status: string
  recommended_action: string | null
  compatibility_score: number | null
  upload_readiness_score: number | null
  blockers: string[]
  reasons: string[]
  candidate_summary: Array<{rank: number; library_item_id: number; compatibility_score: number; readiness_status: string}>
  last_evaluated_at: string | null
  updated_at: string | null
}

export interface RequestReadinessListResponse {
  items: RequestReadinessResponse[]
  total: number
  limit: number
  offset: number
}

export interface RequestCandidateResponse {
  id: number
  request_item_id: number
  library_item_id: number
  candidate_rank: number
  match_status: string
  match_score: number | null
  compatibility_status: string | null
  compatibility_score: number | null
  readiness_status: string | null
  readiness_score: number | null
  blockers: string[]
  reasons: string[]
  lib_title: string | null
  local_status: string | null
  resolution: string | null
  source: string | null
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

// Phase 6A — Nomenclature

export interface NomenclatureProposal {
  id?: number
  library_item_id: number
  status: 'draft' | 'valid' | 'warning' | 'blocked' | 'applied' | 'expired'
  current_name?: string
  current_path?: string
  proposed_title?: string
  proposed_filename?: string
  proposed_folder?: string
  proposed_path?: string
  media_type?: string
  tmdb_id?: string
  imdb_id?: string
  resolution?: string
  source?: string
  provider?: string
  video_codec?: string
  audio_summary?: string
  subtitle_summary?: string
  release_tag?: string
  warnings: string[]
  errors: string[]
  created_at?: string
  updated_at?: string
  hardlink_configured?: boolean
}

export interface NomenclatureExistsResponse {
  exists: boolean
  message?: string
  proposal?: NomenclatureProposal
}

// Phase 6 (Series/Season/Episode hierarchy) — season pack: one release for
// a whole Temporada, not N independent per-episode jobs.

export interface SeasonPackEpisodePlan {
  episode_id: number
  title?: string
  episode_number?: number
  source_path?: string
  destination_path?: string
  proposed_filename?: string
}

export interface SeasonPackPlanResponse {
  status: 'valid' | 'warning' | 'blocked'
  errors: string[]
  warnings: string[]
  season_pack_title?: string
  hardlink_base?: string
  hardlink_folder?: string
  episodes: SeasonPackEpisodePlan[]
}

export interface SeasonPackEpisodeResult {
  episode_id: number
  title?: string
  destination_path?: string
  status: string
  message?: string
  errors: string[]
}

export interface SeasonPackApplyResult {
  dry_run: boolean
  apply: boolean
  status: 'ready' | 'blocked' | 'applied' | 'failed'
  message?: string
  season_pack_title?: string
  hardlink_folder?: string
  warnings: string[]
  errors: string[]
  episodes: SeasonPackEpisodeResult[]
}

// Phase 6A — Upload preflight

export interface UploadJob {
  id?: number
  library_item_id?: number
  request_item_id?: number
  status: string
  stage?: string
  title?: string
  source_path?: string
  prepared_path?: string
  using_prepared_path?: boolean
  error_message?: string
  exit_code?: number
  process_id?: number
  started_at?: string
  finished_at?: string
  created_at?: string
  updated_at?: string
  // Phase 6D
  result_url?: string | null
  result_torrent_id?: string | null
  result_tracker?: string | null
  result_category?: string | null
  duration_seconds?: number | null
  retry_count?: number
  retry_of_job_id?: number | null
  safe_command_json?: string | null
  last_success_at?: string | null
  last_error_at?: string | null
  last_log_at?: string | null
  // Phase 10F
  runtime_type?: string | null
  command_preview?: string | null
  progress_phase?: string | null
}

// Phase 6D — Artifacts

export interface UploadArtifact {
  id?: number
  upload_job_id: number
  artifact_type: string
  name: string | null
  path: string | null
  url: string | null
  value: string | null
  created_at: string
}

export interface UploadArtifactsResponse {
  job_id: number
  artifacts: UploadArtifact[]
}

export interface UploadRetryRequest {
  dry_run: boolean
  start: boolean
  confirmation: string | null
}

// Phase 6C — Upload execution

export interface UploadJobLog {
  id?: number
  upload_job_id: number
  level: string
  message: string
  stream: string | null
  created_at: string
}

export interface UploadJobLogsResponse {
  job_id: number
  logs: UploadJobLog[]
  total: number
  limit: number
  offset: number
}

export interface UploadStartRequest {
  dry_run: boolean
  start: boolean
  confirmation: string | null
}

export interface UploadStartResult {
  job_id: number
  action: string
  status: string
  stage: string | null
  dry_run: boolean
  command_preview: string | null
  message: string | null
  error: string | null
}

// Phase 6B — Nomenclature apply result

export interface NomenclatureApplyResult {
  dry_run: boolean
  apply: boolean
  status: string
  source_path?: string
  destination_path?: string
  operation_id?: number
  proposal?: NomenclatureProposal
  warnings: string[]
  errors: string[]
  message?: string
}

export interface CommandPreview {
  uploadrr_path?: string
  tracker?: string
  category?: string
  title?: string
  tmdb_id?: string
  resolution?: string
  source_path?: string
  command_preview?: string
  note?: string
  using_prepared_path?: boolean
  // Phase 10E: Uploadrr-EMU contract fields.
  runtime_type?: string
  contract_valid?: boolean
  contract_errors?: string[]
  contract_warnings?: string[]
  can_execute?: boolean
  requires_confirmation?: string
  safe_to_execute?: boolean
}

export interface UploadPreflightResponse {
  status: string
  job?: UploadJob
  preflight: Record<string, unknown>
  command_preview?: CommandPreview
  warnings: string[]
  errors: string[]
}

// Phase 8C — Operational queue

export interface OperationalQueueItem {
  id: number
  queue_key: string
  item_type: string
  entity_type: string
  entity_id: number | null
  request_item_id: number | null
  library_item_id: number | null
  upload_job_id: number | null
  title: string | null
  subtitle: string | null
  status: string
  action: string
  blockers: string[]
  reasons: string[]
  context: Record<string, unknown>
  target_url: string | null
  created_at: string | null
  updated_at: string | null
  last_seen_at: string | null
  resolved_at: string | null
}

export interface OperationalQueueListResponse {
  items: OperationalQueueItem[]
  total: number
}

export interface OperationalQueueSummary {
  total: number
  open: number
  ready: number
  waiting: number
  blocked: number
  running: number
}

export interface OperationalQueueRefreshResponse {
  ok: boolean
  items_built: number
  summary: OperationalQueueSummary
}

export interface OperationalQueueActionResponse {
  ok: boolean
  item_id: number
  status: string
  reason: string | null
}

// Phase 9A — Guided queue actions
export interface QueueActionUI {
  route: string
  modal: string | null
  label: string
}

export interface QueueActionTarget {
  library_item_id?: number
  upload_job_id?: number
  request_item_id?: number
}

export interface QueueActionPlan {
  queue_item_id: number
  queue_key: string | null
  action: string
  flow: string
  target: QueueActionTarget
  ui: QueueActionUI
  requires_confirmation: boolean
  confirmation_token: string | null
  safe_to_execute_inline: boolean
  guided_flow: boolean
  blockers: string[]
  reasons: string[]
  title: string | null
  status: string
  item_type: string | null
}

export interface QueueActionPlanResponse {
  ok: boolean
  plan: QueueActionPlan
}

export interface QueueAvailableAction {
  action: string
  label: string
  flow: string
  safe_to_execute_inline: boolean
  requires_confirmation: boolean
  confirmation_token: string | null
  primary: boolean
}

export interface QueueActionsResponse {
  item_id: number
  actions: QueueAvailableAction[]
}

export interface QueueActionEvent {
  id: number
  queue_item_id: number
  action: string
  event_type: string
  status: string
  message: string | null
  details_json: string | null
  created_at: string
}

export interface QueueActionEventsResponse {
  item_id: number
  events: QueueActionEvent[]
  total: number
}

export interface ExecuteSafeActionResponse {
  ok: boolean
  action?: string
  blocked?: boolean
  message?: string
  guided_flow?: string
  ui_route?: string
  confirmation_token?: string | null
  result?: Record<string, unknown>
  error?: string
}
