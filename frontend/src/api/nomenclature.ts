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

export async function previewNomenclature(itemId: number, forceRefresh = false): Promise<NomenclatureProposal> {
  return api.post<NomenclatureProposal>(`/library/${itemId}/nomenclature/preview`, { force_refresh: forceRefresh })
}

export async function adaptNomenclature(
  itemId: number,
  options: {
    dryRun?: boolean
    apply?: boolean
    confirmation?: string | null
    overwrite?: boolean
    proposalId?: number | null
  } = {},
): Promise<NomenclatureApplyResult> {
  const { dryRun = true, apply = false, confirmation = null, overwrite = false, proposalId = null } = options
  return api.post<NomenclatureApplyResult>(`/library/${itemId}/adapt-nomenclature`, {
    dry_run: dryRun,
    apply,
    confirmation,
    overwrite,
    proposal_id: proposalId,
  })
}
