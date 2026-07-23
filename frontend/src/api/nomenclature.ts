import { api } from './client'
import type { NomenclatureExistsResponse, NomenclatureProposal, NomenclatureApplyResult } from '../types/api'

export async function getNomenclature(itemId: number): Promise<NomenclatureExistsResponse> {
  return api.get<NomenclatureExistsResponse>(`/library/${itemId}/nomenclature`)
}

// Phase 10A — Sources, Providers, Fields, MKV title

export interface EmuSource {
  code: string
  label: string
}

export interface EmuProvider {
  code: string
  name: string
  domain?: string | null
}

export interface NomenclatureFields {
  title?: string
  year?: string
  resolution?: string
  source?: string
  provider?: string | null
  video_codec?: string
  audio_summary?: string
  subs?: string
  tag?: string
  [key: string]: string | null | undefined
}

export interface FieldsPreviewResult {
  torrent_name: string
  internal_mkv_title: string
  fields: NomenclatureFields
  provider_options: Array<{ code: string; name: string; label: string; tmdb_available: boolean }>
}

// Internal Source Tool (services/source_engine) full result — always scores
// all 9 eMuwarez source candidates, never returns "unknown".
export interface SourceEngineCandidate {
  label: string
  raw_score: number
  normalized_score: number
  rank: number
}

export interface SourceEngineEvidence {
  feature: string
  value: unknown
  strength: 'weak' | 'medium' | 'strong' | 'very_strong'
  reliability: number
  explanation: string
  contributions: Record<string, number>
}

export interface SourceEngineResult {
  prediction: {
    label: string
    raw_score: number
    confidence_score: number
    certainty: 'alto' | 'medio' | 'bajo'
    runner_up: string
    runner_up_score: number
    margin: number
    evidence_strength: number
  }
  performance: { duration_ms: number; timeout_ms: number; cache_hit: boolean; sample_coverage: number }
  ranking: SourceEngineCandidate[]
  evidence: SourceEngineEvidence[]
  contradictions: string[]
  explanation: { winner: string; winner_vs_runner_up: string }
  tools: Record<string, { available: boolean; version?: string | null; used?: boolean; error?: string | null }>
  engine_version: string
  error?: string
}

// Name vs Radarr/Sonarr vs MediaInfo-bitrate-tool cross-check for Source.
export interface SourceComparison {
  from_name: string | null
  from_radarr: string | null
  from_mediainfo: string | null
  // Whether from_mediainfo is a confirmed detection (no re-encode fingerprint
  // → WEB-DL is decisive) or just a bitrate-threshold guess that can't tell a
  // WEB-DL re-encode (WEBRip) from a disc re-encode (MicroHD/BluRay) apart.
  mediainfo_confirmed: boolean
  agree: boolean
  // Full Internal Source Tool result, when the engine could run.
  engine?: SourceEngineResult | null
}

// Reference row for the bitrate table behind the MediaInfo bitrate tool.
export interface SourceBitrateRow {
  source: string
  bitrate: string
  comment: string
}

export interface MkvTitlePreview {
  status: string
  prepared_path?: string | null
  torrent_name?: string | null
  internal_mkv_title?: string | null
  mkvpropedit_available?: boolean
  command_preview?: string | null
  errors?: string[]
  warnings?: string[]
}

export async function getEmuSources(): Promise<{ sources: EmuSource[] }> {
  return api.get<{ sources: EmuSource[] }>('/nomenclature/sources')
}

export async function getEmuProviders(): Promise<{ providers: EmuProvider[] }> {
  return api.get<{ providers: EmuProvider[] }>('/nomenclature/providers')
}

export async function getNomenclatureFields(itemId: number): Promise<{
  fields: NomenclatureFields
  torrent_name: string
  internal_mkv_title: string
  tmdb_available_providers?: string[]
  title_warning?: string | null
  source_warning?: string | null
  source_comparison?: SourceComparison | null
  source_bitrate_table?: SourceBitrateRow[] | null
  // Set when the file isn't accessible / MediaInfo can't read it: no name is
  // generated and `error` explains why.
  blocked?: boolean
  error?: string
}> {
  return api.get(`/library/${itemId}/nomenclature/fields`)
}

export async function previewNomenclatureFields(
  itemId: number,
  fields: NomenclatureFields,
): Promise<FieldsPreviewResult> {
  return api.post<FieldsPreviewResult>(`/library/${itemId}/nomenclature/preview-fields`, { fields })
}

export async function saveNomenclatureFields(
  itemId: number,
  fields: NomenclatureFields,
): Promise<{ ok: boolean; torrent_name: string; internal_mkv_title: string; fields: NomenclatureFields }> {
  return api.post(`/library/${itemId}/nomenclature/save-fields`, { fields })
}

export async function previewMkvTitle(itemId: number): Promise<MkvTitlePreview> {
  return api.get<MkvTitlePreview>(`/library/${itemId}/mkv-title/preview`)
}

export async function applyMkvTitle(
  itemId: number,
  options: { dryRun?: boolean; apply?: boolean; confirmation?: string | null } = {},
): Promise<MkvTitlePreview & { status: string }> {
  const { dryRun = true, apply = false, confirmation = null } = options
  return api.post(`/library/${itemId}/mkv-title/apply`, { dry_run: dryRun, apply, confirmation })
}

// Phase 12A — track reorder/rename (remux via mkvmerge)

export interface TrackRemuxTrack {
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

export interface TrackRemuxPreview {
  status: string
  library_item_id?: number
  prepared_path?: string | null
  using_prepared_copy?: boolean
  mkvmerge_available?: boolean
  order_changed?: boolean
  tracks?: TrackRemuxTrack[]
  ordered_tracks?: TrackRemuxTrack[]
  command_preview?: string | null
  errors?: string[]
  warnings?: string[]
}

export async function previewTrackRemux(itemId: number): Promise<TrackRemuxPreview> {
  return api.get<TrackRemuxPreview>(`/library/${itemId}/track-remux/preview`)
}

export interface TrackRemuxOverride {
  new_name?: string
  default_after?: boolean
}

export async function applyTrackRemux(
  itemId: number,
  options: {
    dryRun?: boolean
    apply?: boolean
    confirmation?: string | null
    /** Manual edits from the wizard's editable table, keyed by track id. */
    overrides?: Record<number, TrackRemuxOverride>
  } = {},
): Promise<TrackRemuxPreview> {
  const { dryRun = true, apply = false, confirmation = null, overrides } = options
  const overridesPayload = overrides && Object.keys(overrides).length > 0
    ? Object.fromEntries(Object.entries(overrides).map(([id, ov]) => [String(id), ov]))
    : undefined
  return api.post(`/library/${itemId}/track-remux/apply`, {
    dry_run: dryRun, apply, confirmation, overrides: overridesPayload,
  })
}

export async function previewNomenclature(itemId: number, forceRefresh = false): Promise<NomenclatureProposal> {
  return api.post<NomenclatureProposal>(`/library/${itemId}/nomenclature/preview`, { force_refresh: forceRefresh })
}

export async function adaptNomenclature(
  itemId: number,
  options: {
    dryRun?: boolean
    apply?: boolean
    confirmation?: string | null
    proposalId?: number | null
  } = {},
): Promise<NomenclatureApplyResult> {
  const { dryRun = true, apply = false, confirmation = null, proposalId = null } = options
  return api.post<NomenclatureApplyResult>(`/library/${itemId}/adapt-nomenclature`, {
    dry_run: dryRun,
    apply,
    confirmation,
    proposal_id: proposalId,
  })
}
