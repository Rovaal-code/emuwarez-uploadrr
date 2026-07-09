// Status label and color mappings

export interface StatusInfo {
  label: string
  color: string
  cssClass: string
}

const LOCAL_STATUS_MAP: Record<string, StatusInfo> = {
  'Disponible':              { label: 'Disponible',              color: '#22c55e', cssClass: 'status-available' },
  // Rollup-only (series/season) — some but not all children available.
  'Parcial':                 { label: 'Parcial',                 color: '#f59e0b', cssClass: 'status-partial' },
  'Faltante':                { label: 'Faltante',                color: '#ef4444', cssClass: 'status-missing' },
  'En cola':                 { label: 'En cola',                 color: '#3b82f6', cssClass: 'status-queued' },
  'Descargando':             { label: 'Descargando',             color: '#818cf8', cssClass: 'status-downloading' },
  'Pendiente de importar':   { label: 'Pendiente de importar',   color: '#f59e0b', cssClass: 'status-pending' },
  'Error de importación':    { label: 'Error de importación',    color: '#ef4444', cssClass: 'status-error' },
  'Error de búsqueda':       { label: 'Error de búsqueda',       color: '#ef4444', cssClass: 'status-error' },
  'Subiendo':                { label: 'Subiendo',                color: '#a855f7', cssClass: 'status-uploading' },
  'Subido':                  { label: 'Subido',                  color: '#16a34a', cssClass: 'status-uploaded' },
  'Error':                   { label: 'Error',                   color: '#ef4444', cssClass: 'status-error' },
  'Desconocido':             { label: 'Desconocido',             color: '#6b7280', cssClass: 'status-unknown' },
}

const REQUEST_STATUS_MAP: Record<string, StatusInfo> = {
  'Sin petición':   { label: 'Sin petición',   color: '#6b7280', cssClass: 'req-none' },
  'Compatible':     { label: 'Compatible',     color: '#22c55e', cssClass: 'req-compatible' },
  'Parcial':        { label: 'Parcial',        color: '#f59e0b', cssClass: 'req-partial' },
  'No compatible':  { label: 'No compatible',  color: '#f97316', cssClass: 'req-not-compatible' },
  'Llena':          { label: 'Llena',          color: '#9ca3af', cssClass: 'req-filled' },
  'Desconocida':    { label: 'Desconocida',    color: '#6b7280', cssClass: 'req-unknown' },
}

const NOMENCLATURE_STATUS_MAP: Record<string, StatusInfo> = {
  'Correcta':     { label: 'Correcta',     color: '#22c55e', cssClass: 'nom-correct' },
  'No adaptada':  { label: 'No adaptada',  color: '#f59e0b', cssClass: 'nom-not-adapted' },
  'N/A':          { label: 'N/A',          color: '#6b7280', cssClass: 'nom-na' },
  'Desconocida':  { label: 'Desconocida',  color: '#6b7280', cssClass: 'nom-unknown' },
}

// task_runs.status values written by the backend (services/tasks.py):
// 'running' | 'completed' | 'failed'. Keyed by the raw backend value so the
// dashboard no longer collapses everything to "Desconocido".
const TASK_STATUS_MAP: Record<string, StatusInfo> = {
  'running':    { label: 'Ejecutando',  color: '#3b82f6', cssClass: 'status-queued' },
  'completed':  { label: 'Completado',  color: '#22c55e', cssClass: 'status-available' },
  'failed':     { label: 'Error',       color: '#ef4444', cssClass: 'status-error' },
}

export function getLocalStatusInfo(status: string): StatusInfo {
  return LOCAL_STATUS_MAP[status] ?? { label: status, color: '#6b7280', cssClass: 'status-unknown' }
}

export function getRequestStatusInfo(status: string): StatusInfo {
  return REQUEST_STATUS_MAP[status] ?? { label: status, color: '#6b7280', cssClass: 'req-unknown' }
}

export function getNomenclatureStatusInfo(status: string): StatusInfo {
  return NOMENCLATURE_STATUS_MAP[status] ?? { label: status, color: '#6b7280', cssClass: 'nom-unknown' }
}

export function getTaskStatusInfo(status: string | null): StatusInfo {
  if (!status) return { label: 'Desconocido', color: '#6b7280', cssClass: 'status-unknown' }
  return TASK_STATUS_MAP[status] ?? { label: status, color: '#6b7280', cssClass: 'status-unknown' }
}
