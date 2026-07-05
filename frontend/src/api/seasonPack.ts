import { api } from './client'
import type { SeasonPackPlanResponse, SeasonPackApplyResult } from '../types/api'

export function previewSeasonPack(seasonId: number): Promise<SeasonPackPlanResponse> {
  return api.get<SeasonPackPlanResponse>(`/library/season/${seasonId}/pack-preview`)
}

export function adaptSeasonPack(
  seasonId: number,
  body: { dry_run?: boolean; apply?: boolean; confirmation?: string },
): Promise<SeasonPackApplyResult> {
  return api.post<SeasonPackApplyResult>(`/library/season/${seasonId}/adapt-pack`, body)
}
