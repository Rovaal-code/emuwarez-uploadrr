import { api } from './client'
import type { DashboardSummaryResponse, DashboardActivityResponse, LibraryListResponse } from '../types/api'

export async function getDashboardSummary(): Promise<DashboardSummaryResponse> {
  return api.get<DashboardSummaryResponse>('/dashboard/summary')
}

export async function getDashboardActivity(): Promise<DashboardActivityResponse> {
  return api.get<DashboardActivityResponse>('/dashboard/activity')
}

// Phase 11F — library items prioritized by EMU request satisfaction
export async function getDashboardLibraryActivity(limit = 10): Promise<LibraryListResponse> {
  return api.get<LibraryListResponse>(`/dashboard/library-activity?limit=${limit}`)
}
