import { api, ApiClientError, clearToken, getToken } from './client'

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
  tipo: 'manual' | 'automatica' | 'subida'
  /** null: copia subida, no se sabe si lleva claves. */
  con_claves: boolean | null
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

export async function getMaintenanceStatus(): Promise<MaintenanceStatus> {
  return api.get<MaintenanceStatus>('/maintenance/status')
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

// Descargar y subir van aparte del cliente JSON: el cuerpo es un archivo, y el token solo viaja en la cabecera.
async function peticionDeArchivo(
  path: string, init: { method: 'GET' | 'POST'; body?: File },
): Promise<Response> {
  const token = getToken()
  const headers: Record<string, string> = {}
  if (token) headers['Authorization'] = `Bearer ${token}`
  if (init.body) headers['Content-Type'] = 'application/gzip'
  let resp: Response
  try {
    resp = await fetch(`/api${path}`, { method: init.method, body: init.body, headers })
  } catch (err) {
    throw new ApiClientError('No se pudo conectar con el servidor: la petición no llegó a completarse.', 0, err)
  }
  if (resp.status === 401) {
    clearToken()
    throw new ApiClientError('No autorizado', 401, null)
  }
  if (!resp.ok) {
    let detalle = resp.statusText
    try {
      const cuerpo = await resp.json()
      if (typeof cuerpo?.detail === 'string') detalle = cuerpo.detail
    } catch { /* sin cuerpo JSON: vale el texto del estado */ }
    throw new ApiClientError(detalle, resp.status, null)
  }
  return resp
}

export async function downloadBackup(name: string): Promise<void> {
  const resp = await peticionDeArchivo(`/maintenance/backups/${encodeURIComponent(name)}/download`, { method: 'GET' })
  const url = URL.createObjectURL(await resp.blob())
  const enlace = document.createElement('a')
  enlace.href = url
  enlace.download = name
  document.body.appendChild(enlace)
  enlace.click()
  enlace.remove()
  URL.revokeObjectURL(url)
}

export async function uploadBackup(file: File): Promise<{ ok: boolean; name: string; size_bytes: number }> {
  const resp = await peticionDeArchivo('/maintenance/backups/upload', { method: 'POST', body: file })
  return resp.json()
}

export async function restoreBackup(
  backup_name: string,
  opts: { dry_run?: boolean; apply?: boolean; confirmation?: string } = {},
): Promise<RestoreResult> {
  return api.post<RestoreResult>('/maintenance/restore', {
    backup_name,
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

// --- Versión en ejecución y si hay una más nueva publicada ---------------
export interface UltimaVersionPublicada {
  commit?: string | null
  commit_corto?: string | null
  digest?: string | null
  publicada?: string | null
  notas?: string | null
  version?: string | null
}

export interface VersionInfo {
  version: string
  commit?: string | null
  commit_corto?: string | null
  construida?: string | null
  digest?: string | null
  estado: 'al_dia' | 'hay_novedad' | 'desconocido'
  motivo?: string | null
  ultima: UltimaVersionPublicada
}

// `refrescar` salta la caché de una hora del backend: lo usa "Comprobar ahora".
export function getVersionInfo(refrescar = false): Promise<VersionInfo> {
  return api.get<VersionInfo>(`/runtime/version${refrescar ? '?refrescar=true' : ''}`)
}
