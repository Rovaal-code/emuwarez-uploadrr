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
