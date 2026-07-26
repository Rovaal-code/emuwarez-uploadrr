import { api } from './client'

export interface GpuStats {
  name: string
  percent: number
  vram_used_gb: number
  vram_total_gb: number
  vram_percent: number
}

export interface SystemStats {
  cpu_percent: number
  cpu_name: string
  ram_percent: number
  ram_used_gb: number
  ram_total_gb: number
  disk_path: string
  disk_used_gb: number
  disk_total_gb: number
  disk_percent: number
  net_down_bps: number
  net_up_bps: number
  gpu: GpuStats | null
}

export async function getSystemStats(): Promise<SystemStats> {
  return api.get<SystemStats>('/system/stats')
}

export interface UploadConcurrencyEstimate {
  recommended: number
  ram_limited_to: number
  cpu_limited_to: number
  available_ram_gb: number
  cpu_cores: number
  assumed_ram_gb_per_slot: number
}

export async function getUploadConcurrencyEstimate(): Promise<UploadConcurrencyEstimate> {
  return api.get<UploadConcurrencyEstimate>('/system/upload-concurrency-estimate')
}
