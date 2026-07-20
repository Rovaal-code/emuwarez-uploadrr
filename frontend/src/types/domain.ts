// Domain types and constants for the UI

export type LocalStatus =
  | 'Disponible'
  | 'Faltante'
  | 'En cola'
  | 'Descargando'
  | 'Pendiente de importar'
  | 'Error de importación'
  | 'Error de búsqueda'
  | 'Subiendo'
  | 'Subido'
  | 'Error'
  | 'Desconocido'

export type RequestStatus =
  | 'Sin petición'
  | 'Compatible'
  | 'Parcial'
  | 'No compatible'
  | 'Llena'
  | 'Desconocida'

export type NomenclatureStatus = 'Correcta' | 'No adaptada' | 'N/A' | 'Desconocida'

export type InstanceType = 'radarr' | 'sonarr' | 'jellyfin'

export type ItemType = 'movie' | 'series' | 'season' | 'episode'

// Sidebar navigation items
export interface NavItem {
  id: string
  label: string
  icon: string
}

export const NAV_ITEMS: NavItem[] = [
  { id: 'dashboard', label: 'Panel', icon: 'grid' },
  { id: 'library', label: 'Biblioteca', icon: 'library' },
  { id: 'requests', label: 'Peticiones', icon: 'requests' },
  { id: 'uploads', label: 'Subidas', icon: 'uploads' },
  { id: 'guide', label: 'Guía', icon: 'guide' },
  { id: 'tasks', label: 'Tareas', icon: 'tasks' },
  { id: 'instances', label: 'Instancias', icon: 'instances' },
  { id: 'logs', label: 'Logs', icon: 'logs' },
  { id: 'settings', label: 'Configuración', icon: 'settings' },
]

// Setup wizard step IDs (order: welcome -> admin -> emu ->
// instances -> tmdb -> nomenclature -> complete). No dedicated Uploadrr
// step — the service already ships with sensible runtime defaults;
// configurable later from Settings if needed.
export const SETUP_STEPS = [
  'welcome', 'admin', 'emu', 'instances', 'tmdb', 'qbit', 'providers', 'imagehosts', 'complete',
] as const
export type SetupStep = (typeof SETUP_STEPS)[number]

export const SETUP_STEP_LABELS: Record<SetupStep, string> = {
  welcome: 'Bienvenida',
  admin: 'Crear admin',
  emu: 'eMuwarez',
  instances: 'Instancias',
  tmdb: 'TMDb',
  qbit: 'qBittorrent',
  providers: 'Providers de vídeo',
  imagehosts: 'Imágenes',
  complete: 'Completar',
}
