// API response types matching backend schemas

export interface SetupStatusResponse {
  initialized: boolean
  admin_configured: boolean
  tmdb_configured: boolean
  emu_configured: boolean
  radarr_instances: number
  sonarr_instances: number
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

// Tu cuenta de eMuwarez: /api/user de UNIT3D tal cual, guardado una hora en el servidor.
export interface EmuPerfil {
  configured: boolean
  username: string | null
  group: string | null
  uploaded: string | null
  downloaded: string | null
  ratio: string | null
  buffer: string | null
  seeding: number | null
  leeching: number | null
  seedbonus: number | null
  hit_and_runs: number | null
  updated_at: string | null
  error: string | null
}

// Una instantánea diaria de tu cuenta de eMuwarez (Estadísticas); lo que no se pudo leer ese día va a null.
export interface PuntoCuenta {
  dia: string
  ratio: number | null
  subido_bytes: number | null
  bajado_bytes: number | null
  bonus: number | null
}

export interface EstadisticasCuenta {
  dias: number
  puntos: PuntoCuenta[]
}

export interface DashboardSummaryResponse {
  library_total: number
  available: number
  missing: number
  uploading: number
  completed: number
  unique_content?: number
  unique_movies?: number
  unique_seasons?: number
  unique_episodes?: number
  uploads_completed?: number
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
  requests_partial?: number
  requests_filled?: number
  requests_mine?: number
  requests_reclaimed?: number
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
  /** Solo al editar: lo que se ha guardado y conviene mirar (p. ej. la instancia no respondía). */
  warning?: string | null
}

export interface InstanceTestResponse {
  ok: boolean
  instance_id: number | null
  instance_name: string | null
  version: string | null
  username: string | null
  error: string | null
}

// Una petición de eMuwarez vista desde la ficha de Biblioteca (PeticionDeLaFichaResponse).
export interface PeticionDeLaFicha {
  id: number
  title: string | null
  // Solo si eMuwarez enseña el autor; si lo oculta, null.
  author: string | null
  is_mine: boolean
  points: number | null
  // La página pública de la petición en eMuwarez (sin consulta ni clave).
  url: string | null
  emu_status: string | null
  created_at: string | null
  req_scope: string | null
  req_season: number | null
  req_episode: number | null
  // null si es de la propia fila; si la cubre la de su temporada o su serie, de cuál.
  heredada_de: 'temporada' | 'serie' | null
  // El estado guardado en la fila que la tiene, y esa fila.
  estado: string | null
  library_item_id: number | null
}

export interface LibraryItemResponse {
  // La petición del elemento (o la que lo cubre desde su temporada o serie) y,
  // en una serie o temporada, las de lo que tiene debajo. Solo en la ficha.
  peticion?: PeticionDeLaFicha | null
  peticiones_debajo?: PeticionDeLaFicha[] | null
  // Todos los valores técnicos presentes bajo una serie o temporada
  // ("x264, x265"), solo para enseñar. Los campos sueltos siguen guardando el
  // valor único (o null cuando los capítulos no coinciden), que es lo que usa
  // la regla del pack. Solo llega en la ficha, no en la lista.
  rollup_all?: Record<string, string> | null
  providers_all?: { code: string; label: string | null }[] | null
  id: number
  item_type: string
  title: string
  // Canonical "Serie (Año)" / "Serie (Año) - Temporada X" / "Serie (Año) -
  // SxxEyy[ - Nombre del capítulo]" title — only set on the single-item
  // detail response, not on list rows.
  display_title: string | null
  year: number | null
  original_title: string | null
  instance_type: string | null
  instance_name: string | null
  instance_id: number | null
  external_id: string | null
  tmdb_id: string | null
  imdb_id: string | null
  tvdb_id: string | null
  tvmaze_id?: string | null
  mal_id: string | null
  title_slug: string | null
  // Series/Season/Episode hierarchy — parent_id points at the containing
  // row's id (episode -> season, season -> series); null for movies/series.
  season_number: number | null
  episode_number: number | null
  parent_id: number | null
  path: string | null
  // Real current local file once nomenclature has been applied — prefer
  // this over `path` for anything shown to the user (`path` stays in
  // Radarr/Sonarr's own raw convention and can go stale).
  prepared_path?: string | null
  quality: string | null
  resolution: string | null
  source: string | null
  release_group?: string | null
  provider: string | null
  provider_label: string | null
  video_codec: string | null
  audio_codec: string | null
  audio_languages: string | null
  // 1 = has Castilian audio, 0 = does not, null = unknown (no MediaInfo yet,
  // or a season/series with no held children to roll up).
  has_spanish_audio: number | null
  // Same for subtitles.
  has_spanish_subs: number | null
  // What the upload rules gate on: Castilian present either way (dubbed
  // content needs no subtitles). On a season row, 1 means every held episode
  // satisfies it.
  has_spanish_ok: number | null
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
  backdrop_url: string | null
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
  /** Archivos de vídeo que tienes de verdad: películas + capítulos en disco.
   *  No depende de los filtros, al revés que `total`. */
  archivos: number
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

// Phase 5B — Requests

export interface RequestMatchResponse {
  // The row the request is really about (a season's own row, where
  // library_item_id is the series). Links out of a request follow this one.
  library_target_id?: number | null
  id: number
  library_item_id: number | null
  library_title: string | null
  local_status: string | null
  local_resolution: string | null
  local_source: string | null
  local_video_codec: string | null
  local_audio_languages: string | null
  local_size: number | null
  local_tmdb_id: string | null
  local_imdb_id: string | null
  local_tvdb_id: string | null
  local_mal_id: string | null
  local_path: string | null
  content_name: string | null
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
  votes: number | null
  author: string | null
  is_mine: boolean
  // Quién la tiene reclamada en eMuwarez; null si no está reclamada.
  reclamada_por?: 'ti' | 'otro' | 'desconocido' | null
  req_scope: string | null
  req_season: number | null
  req_episode: number | null
  created_at: string | null
  tmdb_id: string | null
  imdb_id: string | null
  tvdb_id: string | null
  tvmaze_id?: string | null
  mal_id: string | null
  url: string | null
  compatibility_status: string | null
  compatibility_confidence: number | null
  library_item_id: number | null
  library_title: string | null
  library_year: number | null
  // Origen: la instancia de Radarr/Sonarr donde tienes el contenido. Todo
  // null cuando la petición no cruza con nada ("No importada").
  instance_type: string | null
  instance_name: string | null
  instance_id: number | null
  title_slug: string | null
  library_tmdb_id: string | null
  display_title: string | null
  local_status: string | null
  poster_url: string | null
  backdrop_url: string | null
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
  proposed_torrent_name?: string
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
}

// Phase 6 (Series/Season/Episode hierarchy) — season pack: one release for
// a whole Temporada, not N independent per-episode jobs.

export interface SeasonPackEpisodePlan {
  episode_id: number
  title?: string
  episode_number?: number
  source_path?: string
  nombre?: string
  proposed_filename?: string
}

export interface SeasonPackPlanResponse {
  // 'cancelled': the wizard was closed while the plan was still being built,
  // so the server stopped at the next episode boundary. Not an error state.
  status: 'valid' | 'blocked' | 'cancelled'
  errors: string[]
  warnings: string[]
  season_pack_title?: string | null
  pack_folder?: string | null
  episodes: SeasonPackEpisodePlan[]
  provider?: string | null
  // De dónde sale el proveedor ("manual", "file" o "tmdb") y el texto que lo explica.
  provider_source?: 'manual' | 'file' | 'tmdb' | null
  provider_source_detail?: string | null
  // Proveedores distintos en los nombres de los capítulos: el plan se bloquea
  // hasta que se elige uno en Proveedor.
  provider_conflict?: string[]
  // Field-by-field breakdown — same fields a movie/episode's nomenclature
  // grid shows. Source/Proveedor/Tag are editable here too, same as a
  // movie/episode (applied uniformly across every episode).
  series_title?: string | null
  // Same two choices the single-file field box offers for Título.
  title_options?: { value: string; kind: 'spanish' | 'english'; label: string }[]
  year?: number | null
  // Needed by the live title-preview call — a season opened from its
  // series' own ficha has no season_number of its own on the wizard's
  // `item` prop (that's the series), only the plan has it.
  season_number?: number | null
  resolution?: string | null
  source?: string | null
  video_codec?: string | null
  dynamic_range?: string | null
  audio_summary?: string | null
  subtitle_summary?: string | null
  // Los capítulos no traen el mismo audio: el título lleva CUSTOM.
  custom?: boolean
  release_tag?: string | null
  source_comparison?: import('../api/nomenclature').SourceComparison | null
  // MediaInfo apunta a otro source que el nombre o Radarr/Sonarr (capítulo
  // representativo). Solo avisa.
  source_mismatch_warning?: string | null
  // Capítulos que siguen con una pista de audio sin idioma; null si ninguno.
  audio_warning?: string | null
  // Las pistas de audio sin idioma, para elegir su idioma una vez para todo el pack.
  pistas_sin_idioma?: PistaSinIdiomaPack[]
  // Lo elegido y aplicado ({"1": "spa"}) y las opciones del selector.
  idiomas_audio?: Record<string, string>
  idiomas_elegibles?: { code: string; label: string }[]
}

export interface PistaSinIdiomaPack {
  // Posición entre las pistas de audio, desde 1: la misma en todos los capítulos.
  posicion: number
  // Códec y canales ("DD 5.1"), para reconocerla.
  pista?: string | null
  capitulos: (number | null)[]
  // El idioma elegido para ella, si hay.
  idioma?: string | null
}


// Job detail page — read-only snapshots + real phase progress

export interface UploadSnapshotTrack {
  id: number
  type: 'video' | 'audio' | 'subtitles'
  codec: string | null
  language: string | null
  current_name: string | null
  new_name: string
  default_before: boolean
  default_after: boolean
  forced: boolean
  changed: boolean
}

export interface UploadNomenclatureSnapshot {
  media_type?: string | null
  proposed_title?: string | null
  proposed_torrent_name?: string | null
  proposed_filename?: string | null
  series_title?: string | null
  year?: number | null
  season_number?: number | null
  tmdb_id?: string | null
  resolution?: string | null
  source?: string | null
  provider_final?: string | null
  video_codec?: string | null
  audio_summary?: string | null
  subtitle_summary?: string | null
  release_tag?: string | null
}

export interface UploadRemuxEpisodeSnapshot {
  episode_id: number
  title?: string | null
  episode_number?: number | null
  ordered_tracks?: UploadSnapshotTrack[]
  omitida?: string
}

export interface UploadRemuxSnapshot {
  ordered_tracks?: UploadSnapshotTrack[]
  episodes?: UploadRemuxEpisodeSnapshot[]
  // Por qué no se tocaron las pistas ("Ninguno", "sin reflink"…).
  omitida?: string
}

export interface UploadCheckResult {
  id: string
  label: string
  status: 'ok' | 'fail' | 'skip'
  message?: string
}

export interface UploadChecksSnapshot {
  checks: UploadCheckResult[]
  ready: boolean
}

export interface UploadProgressPhase {
  key: string
  label: string
  status: 'pending' | 'running' | 'done'
  pct: number
  started_at?: string | null
  finished_at?: string | null
}

export interface UploadProgressState {
  phases: UploadProgressPhase[]
  global_pct: number
}

// Phase 6A — Upload preflight

// Lo que Uploadrr-EMU ha dado por terminado dentro de «Subir con Uploadrr» (services/subida_pasos.py).
export interface SubpasoSubida {
  clave: string
  nombre: string
  hecho: boolean
}

// Un paso con nombre de una subida (services/subida_pasos.py).
export interface PasoSubida {
  clave: string
  nombre: string
  // hecho | en_curso | fallido | cancelado | pendiente
  estado: string
  subpasos?: SubpasoSubida[]
}

export interface UploadJob {
  id?: number
  library_item_id?: number
  request_item_id?: number
  status: string
  stage?: string
  // Los pasos con nombre, y desde cuál reanudaría un reintento (null: desde el principio).
  pasos?: PasoSubida[]
  reintento_desde?: string | null
  reintento_desde_nombre?: string | null
  // Lo que un reintento que reanuda no repetiría dentro de Uploadrr-EMU (capturas, torrent).
  reintento_reutiliza?: string[]
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
  media_type?: string | null
  poster_url?: string | null
  backdrop_url?: string | null
  year?: number | null
  // Canonical "Serie (Año)" / "Serie (Año) - Temporada X" / "Serie (Año) -
  // SxxEyy" display title — only set on the single-job GET, not the list.
  display_title?: string | null
  instance_type?: string | null
  instance_name?: string | null
  instance_id?: number | null
  tmdb_id?: string | null
  title_slug?: string | null
  request_status?: string | null
  // La petición que cubrió la subida, tal como era al encolarla (la fila de
  // Peticiones se borra cuando deja de estar abierta).
  request_title?: string | null
  request_url?: string | null
  queue_position?: number | null
  queue_total?: number | null
  nomenclature_snapshot?: UploadNomenclatureSnapshot | null
  remux_snapshot?: UploadRemuxSnapshot | null
  checks_snapshot?: UploadChecksSnapshot | null
  progress?: UploadProgressState | null
}

// Phase 6C — Upload execution

export interface UploadJobLog {
  id?: number
  upload_job_id: number
  level: string
  message: string
  stream: string | null
  created_at: string
  // Orden de la línea dentro de su subida: de aquí se sigue el registro en vivo.
  sequence?: number | null
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
  renombrable?: boolean
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
