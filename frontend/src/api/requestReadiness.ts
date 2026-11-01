import { api } from './client'
import type {
  RequestReadinessResponse,
  RequestCandidateResponse,
} from '../types/api'

export async function getReadiness(requestId: number): Promise<RequestReadinessResponse> {
  return api.get(`/requests/${requestId}/readiness`)
}

export async function getCandidates(requestId: number): Promise<RequestCandidateResponse[]> {
  return api.get(`/requests/${requestId}/candidates`)
}
