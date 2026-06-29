import { api } from './client'
import type { NomenclatureExistsResponse, NomenclatureProposal, NomenclatureApplyResult } from '../types/api'

export async function getNomenclature(itemId: number): Promise<NomenclatureExistsResponse> {
  return api.get<NomenclatureExistsResponse>(`/library/${itemId}/nomenclature`)
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
