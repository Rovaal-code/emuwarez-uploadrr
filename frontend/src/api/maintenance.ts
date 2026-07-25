import { api } from './client'

export interface MaintenanceStatus {
  ok: boolean
  config_inventory: {
    config_dir: string
    exists: boolean
    files: { name: string; size_bytes: number }[]
    total_size_bytes: number
  }
  database: {
    ok: boolean
    db_path?: string
    size_bytes?: number
    page_size?: number
    page_count?: number
    freelist_count?: number
    fragmentation_pct?: number
    error?: string
  }
  backups_count: number
  latest_backup: BackupInfo | null
}

export interface BackupInfo {
  name: string
  path: string
  size_bytes: number
  created_at: string
}

export interface ExportSettingsResult {
  ok: boolean
  settings?: Record<string, string | null>
  include_secrets?: boolean
  secrets_masked?: boolean
  total_keys?: number
  secret_keys_count?: number
  error?: string
}

export interface ImportSettingsResult {
  ok: boolean
  dry_run?: boolean
  action?: string
  keys_to_write?: string[]
  keys_written?: number
  keys_skipped_masked?: string[]
  message?: string
  error?: string
}

export interface BackupResult {
  ok: boolean
  archive_path?: string
  archive_name?: string
  size_bytes?: number
  include_secrets?: boolean
  config_dir?: string
  error?: string
}

export interface RestoreResult {
  ok: boolean
  dry_run?: boolean
  action?: string
  archive?: string
  target_dir?: string
  files_in_archive?: number
  files?: string[]
  files_restored?: number
  message?: string
  error?: string
}

export interface IntegrityCheckResult {
  ok: boolean
  db_path?: string
  result?: string[]
  message?: string
  error?: string
}

export interface VacuumResult {
  ok: boolean
  dry_run?: boolean
  action?: string
  db_path?: string
  size_bytes_before?: number
  size_bytes_after?: number
  bytes_saved?: number
  freelist_count?: number
  message?: string
  error?: string
}

export interface CleanupLogsResult {
  ok: boolean
  dry_run?: boolean
  action?: string
  days?: number
  files_found?: number
  files_deleted?: number
  files?: string[]
  bytes_to_free?: number
  bytes_freed?: number
  message?: string
  error?: string
}

export async function getMaintenanceStatus(): Promise<MaintenanceStatus> {
  return api.get<MaintenanceStatus>('/maintenance/status')
}

export async function exportSettings(includeSecrets = false, confirmation?: string): Promise<ExportSettingsResult> {
  const params = new URLSearchParams()
  if (includeSecrets) params.set('include_secrets', 'true')
  if (confirmation) params.set('confirmation', confirmation)
  const qs = params.toString()
  return api.get<ExportSettingsResult>(`/maintenance/export-settings${qs ? `?${qs}` : ''}`)
}

export async function importSettings(
  payload: Record<string, string | null>,
  opts: { dry_run?: boolean; apply?: boolean; confirmation?: string } = {},
): Promise<ImportSettingsResult> {
  return api.post<ImportSettingsResult>('/maintenance/import-settings', {
    payload,
    dry_run: opts.dry_run ?? true,
    apply: opts.apply ?? false,
    confirmation: opts.confirmation ?? null,
  })
}

export async function createBackup(opts: { include_secrets?: boolean; confirmation?: string } = {}): Promise<BackupResult> {
  return api.post<BackupResult>('/maintenance/backup', {
    include_secrets: opts.include_secrets ?? false,
    confirmation: opts.confirmation ?? null,
  })
}

export async function listBackups(): Promise<{ ok: boolean; backups: BackupInfo[]; count: number; backup_dir: string }> {
  return api.get('/maintenance/backups')
}

export async function restoreBackup(
  backup_path: string,
  opts: { dry_run?: boolean; apply?: boolean; confirmation?: string } = {},
): Promise<RestoreResult> {
  return api.post<RestoreResult>('/maintenance/restore', {
    backup_path,
    dry_run: opts.dry_run ?? true,
    apply: opts.apply ?? false,
    confirmation: opts.confirmation ?? null,
  })
}

export async function runIntegrityCheck(): Promise<IntegrityCheckResult> {
  return api.post<IntegrityCheckResult>('/maintenance/db/integrity-check', {})
}

export async function runVacuum(
  opts: { dry_run?: boolean; apply?: boolean; confirmation?: string } = {},
): Promise<VacuumResult> {
  return api.post<VacuumResult>('/maintenance/db/vacuum', {
    dry_run: opts.dry_run ?? true,
    apply: opts.apply ?? false,
    confirmation: opts.confirmation ?? null,
  })
}

export async function cleanupLogs(
  opts: { days?: number; dry_run?: boolean; apply?: boolean; confirmation?: string } = {},
): Promise<CleanupLogsResult> {
  return api.post<CleanupLogsResult>('/maintenance/logs/cleanup', {
    days: opts.days ?? 30,
    dry_run: opts.dry_run ?? true,
    apply: opts.apply ?? false,
    confirmation: opts.confirmation ?? null,
  })
}
