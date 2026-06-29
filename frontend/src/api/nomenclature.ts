import { api } from './client'
import type { NomenclatureExistsResponse, NomenclatureProposal } from '../types/api'

export async function getNomenclature(itemId: number): Promise<NomenclatureExistsResponse> {
  return api.get<NomenclatureExistsResponse>(`/library/${itemId}/nomenclature`)
}

export async function previewNomenclature(itemId: number, forceRefresh = false): Promise<NomenclatureProposal> {
  return api.post<NomenclatureProposal>(`/library/${itemId}/nomenclature/preview`, { force_refresh: forceRefresh })
}

export async function adaptNomenclature(itemId: number, dryRun = true, apply = false): Promise<unknown> {
  return api.post(`/library/${itemId}/adapt-nomenclature`, { dry_run: dryRun, apply })
}
