import { api } from './client'
import type { InstanceSafeResponse, InstanceTestResponse, OkResponse, SyncResponse } from '../types/api'

export async function getInstances(): Promise<InstanceSafeResponse[]> {
  return api.get<InstanceSafeResponse[]>('/instances')
}

export interface AddInstancePayload {
  type: string
  name: string
  url: string
  api_key: string
  is_4k?: boolean
  is_anime?: boolean
}

export async function addInstance(payload: AddInstancePayload): Promise<OkResponse> {
  return api.post<OkResponse>('/instances', payload)
}

export interface UpdateInstancePayload {
  name?: string
  url?: string
  api_key?: string
  enabled?: boolean
  is_4k?: boolean
  is_anime?: boolean
}

export async function updateInstance(id: number, payload: UpdateInstancePayload): Promise<InstanceSafeResponse> {
  return api.put<InstanceSafeResponse>(`/instances/${id}`, payload)
}

export async function testInstance(id: number): Promise<InstanceTestResponse> {
  return api.post<InstanceTestResponse>(`/instances/${id}/test`)
}

export async function syncInstance(id: number): Promise<SyncResponse> {
  return api.post<SyncResponse>(`/instances/${id}/sync`)
}

export async function deleteInstance(id: number): Promise<OkResponse> {
  return api.delete<OkResponse>(`/instances/${id}`)
}
