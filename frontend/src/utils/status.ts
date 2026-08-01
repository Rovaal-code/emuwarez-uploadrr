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
  // Shown as plain "Importación" in amber, not as a red error: Radarr/Sonarr
  // reports this while the file is sitting in the download folder waiting to
  // be imported, which resolves itself most of the time. Painting it red made
  // routine, self-healing states look like something to act on. The KEY stays
  // the raw value Radarr/Sonarr stores — only its presentation changes.
  'Error de importación':    { label: 'Importación',             color: '#f59e0b', cssClass: 'status-pending' },
  'Error de búsqueda':       { label: 'Error de búsqueda',       color: '#ef4444', cssClass: 'status-error' },
  'Subiendo':                { label: 'Subiendo',                color: '#a855f7', cssClass: 'status-uploading' },
  'Subido':                  { label: 'Subido',                  color: '#16a34a', cssClass: 'status-uploaded' },
  'Error':                   { label: 'Error',                   color: '#ef4444', cssClass: 'status-error' },
  'Desconocido':             { label: 'Desconocido',             color: '#6b7280', cssClass: 'status-unknown' },
}

const REQUEST_STATUS_MAP: Record<string, StatusInfo> = {
  'Sin petición':   { label: 'Sin petición',   color: '#9ca3af', cssClass: 'req-none' },
  'Compatible':     { label: 'Compatible',     color: '#22c55e', cssClass: 'req-compatible' },
  'Parcial':        { label: 'Parcial',        color: '#f59e0b', cssClass: 'req-partial' },
  'No compatible':  { label: 'No compatible',  color: '#ef4444', cssClass: 'req-not-compatible' },
  // Shown as "Faltante", in red: there IS an entry in your library for this
  // request, but no file on disk — the very same state Biblioteca calls
  // Faltante. It used to render as a plain dash, which buried an actionable
  // verdict among the genuinely empty cells.
  'No disponible':  { label: 'Faltante',       color: '#ef4444', cssClass: 'req-unavailable' },
  // No library entry at all, not even one without a file. Neutral white
  // rather than red: nothing is wrong with your copy, you simply don't have
  // one. The backend already speaks this value in its status filter, so it's
  // filterable like the rest instead of being an unfilterable dash.
  'Sin coincidencia': { label: 'No importada', color: '#e5e7eb', cssClass: 'req-not-imported' },
  'Reclamado':      { label: 'Reclamado',      color: '#a855f7', cssClass: 'req-claimed' },
  'Pendiente':      { label: 'Pendiente',      color: '#eab308', cssClass: 'req-pending' },
  // Más apagado que 'Sin petición': una petición llena ya está resuelta.
  'Llena':          { label: 'Llena',          color: '#6b7280', cssClass: 'req-filled' },
  'Desconocida':    { label: 'Desconocida',    color: '#6b7280', cssClass: 'req-unknown' },
}

const NOMENCLATURE_STATUS_MAP: Record<string, StatusInfo> = {
  'Correcta':      { label: 'Correcta',      color: '#22c55e', cssClass: 'nom-correct' },
  'No comprobada': { label: 'No comprobada', color: '#9ca3af', cssClass: 'nom-unchecked' },
  'Parcial':       { label: 'Parcial',       color: '#f59e0b', cssClass: 'nom-partial' },
  'No adaptada':   { label: 'No adaptada',   color: '#ef4444', cssClass: 'nom-not-adapted' },
  'N/A':           { label: 'N/A',           color: '#6b7280', cssClass: 'nom-na' },
  'Desconocida':   { label: 'Desconocida',   color: '#6b7280', cssClass: 'nom-unknown' },
}

// eMuwarez catalog comparison. "No" (not on the tracker) is the actionable
// opportunity → green like "Disponible"; "Sí" (already there) is neutral →
// gray like "No adaptada"; "Nuevo" (aportes cell, content not on eMuwarez at
// all) → green like "Disponible".
const EMU_STATUS_MAP: Record<string, StatusInfo> = {
  'No':      { label: 'No',      color: '#22c55e', cssClass: 'status-available' },
  'Sí':      { label: 'Sí',      color: '#9ca3af', cssClass: 'nom-na' },
  // Series with some seasons on eMuwarez and some not — amber, like other "Parcial".
  'Parcial': { label: 'Parcial', color: '#f59e0b', cssClass: 'status-partial' },
  'Nuevo':   { label: 'Nuevo',   color: '#22c55e', cssClass: 'status-available' },
}

// Castilian audio ("Español" column). Opposite polarity to EMU_STATUS_MAP
// above: eMuwarez all but requires Spanish audio, so "Sí" is the healthy state
// (green) and "No" is what you need to act on (red).
const SPANISH_STATUS_MAP: Record<string, StatusInfo> = {
  'Sí': { label: 'Sí', color: '#22c55e', cssClass: 'status-available' },
  'No': { label: 'No', color: '#ef4444', cssClass: 'status-missing' },
}

export function getSpanishStatusInfo(status: string): StatusInfo {
  return SPANISH_STATUS_MAP[status] ?? { label: status, color: '#6b7280', cssClass: 'status-unknown' }
}

// task_runs.status values written by the backend (services/tasks.py):
// 'running' | 'completed' | 'failed'. Keyed by the raw backend value so the
// dashboard no longer collapses everything to "Desconocido".
const TASK_STATUS_MAP: Record<string, StatusInfo> = {
  'running':    { label: 'Ejecutando',  color: '#3b82f6', cssClass: 'status-queued' },
  'completed':  { label: 'Completado',  color: '#22c55e', cssClass: 'status-available' },
  'failed':     { label: 'Error',       color: '#ef4444', cssClass: 'status-error' },
  'skipped':    { label: 'Omitido',     color: '#f59e0b', cssClass: 'status-partial' },
  'queued':     { label: 'En cola',     color: '#3b82f6', cssClass: 'status-queued' },
  'pending':    { label: 'Pendiente',   color: '#f59e0b', cssClass: 'status-pending' },
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

export function getEmuStatusInfo(status: string): StatusInfo {
  return EMU_STATUS_MAP[status] ?? { label: status, color: '#6b7280', cssClass: 'status-unknown' }
}

export function getTaskStatusInfo(status: string | null): StatusInfo {
  if (!status) return { label: 'Desconocido', color: '#6b7280', cssClass: 'status-unknown' }
  return TASK_STATUS_MAP[status] ?? { label: status, color: '#6b7280', cssClass: 'status-unknown' }
}
