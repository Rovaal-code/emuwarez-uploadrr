import { api } from './client'
import type { DashboardSummaryResponse, DashboardActivityResponse } from '../types/api'

export async function getDashboardSummary(): Promise<DashboardSummaryResponse> {
  return api.get<DashboardSummaryResponse>('/dashboard/summary')
}

export async function getDashboardActivity(): Promise<DashboardActivityResponse> {
  return api.get<DashboardActivityResponse>('/dashboard/activity')
}
