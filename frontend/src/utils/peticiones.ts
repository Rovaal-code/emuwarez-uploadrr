import type { RequestItemResponse } from '../types/api'

// El título de una petición en una lista: el mismo en Peticiones y en el carril
// «Peticiones listas para subir» del Panel.
//
// The raw eMuwarez title is whatever the requester typed there — for a
// season/episode-scoped request it doesn't reliably say WHICH one, so the
// suffix is appended here, same format as the one this app itself builds
// when creating a petición (RequestFormModal): " - Temporada X" / " - SxxExx".
// Skipped if the title already ends in something matching that pattern (the
// requester already spelled it out on eMuwarez's own site).
// The year (when matched to a library item) is inserted right after `base`,
// before the " - Temporada X"/" - SxxEyy" suffix — same "Serie (Año) - …"
// convention as every other table/dedicated page (see DetailTitleText,
// which the callers wrap this in for the muted-gray styling).
export function requestDisplayTitle(item: Pick<RequestItemResponse,
  'title' | 'library_year' | 'req_scope' | 'req_season' | 'req_episode'>): string {
  const base = item.title || ''
  const year = item.library_year ? ` (${item.library_year})` : ''
  if (item.req_scope === 'season' && item.req_season != null && !/temporada\s*\d+\s*$/i.test(base)) {
    return `${base}${year} - Temporada ${item.req_season}`
  }
  if (item.req_scope === 'episode' && item.req_season != null && item.req_episode != null && !/S\d{1,2}E\d{1,3}\s*$/i.test(base)) {
    const code = `S${String(item.req_season).padStart(2, '0')}E${String(item.req_episode).padStart(2, '0')}`
    return `${base}${year} - ${code}`
  }
  return `${base}${year}`
}

// Los grupos de la lista de Peticiones: lo que se puede hacer con cada una.
export type GrupoPeticion = 'lista' | 'parcial' | 'sin_copia' | 'cerrada'

export const GRUPOS_PETICION: { id: GrupoPeticion; titulo: string; ayuda: string }[] = [
  { id: 'lista', titulo: 'Lista para subir', ayuda: 'Tienes el contenido y cumple lo pedido' },
  { id: 'parcial', titulo: 'Parcial', ayuda: 'Tienes algo, pero aún no se puede subir' },
  { id: 'sin_copia', titulo: 'No la tienes', ayuda: 'Sin copia en tu biblioteca' },
  { id: 'cerrada', titulo: 'Cerradas', ayuda: 'Reclamada por otro, ya llena o ya subida' },
]

// request_readiness.status (services/request_readiness.py) → grupo.
const GRUPO_POR_PREPARACION: Record<string, GrupoPeticion> = {
  ready_to_upload: 'lista',
  preflight_needed: 'lista',
  needs_nomenclature: 'lista',
  partially_available: 'parcial',
  spec_mismatch: 'parcial',
  no_castellano: 'parcial',
  downloading: 'parcial',
  pending_import: 'parcial',
  import_error: 'parcial',
  no_local_match: 'sin_copia',
  file_missing: 'sin_copia',
  claimed: 'cerrada',
  claimed_unknown: 'cerrada',
  pending_approval: 'cerrada',
  filled: 'cerrada',
  already_exists: 'cerrada',
  uploaded: 'cerrada',
  uploading: 'cerrada',
}

// Sin preparación guardada todavía, decide la compatibilidad que enseña la columna.
const GRUPO_POR_COMPATIBILIDAD: Record<string, GrupoPeticion> = {
  Compatible: 'lista',
  Parcial: 'parcial',
  Reclamado: 'cerrada',
  Pendiente: 'cerrada',
  Llena: 'cerrada',
}

export function grupoDePeticion(item: Pick<RequestItemResponse, 'readiness_status' | 'compatibility_status'>): GrupoPeticion {
  const porPreparacion = item.readiness_status ? GRUPO_POR_PREPARACION[item.readiness_status] : undefined
  return porPreparacion ?? GRUPO_POR_COMPATIBILIDAD[item.compatibility_status ?? ''] ?? 'sin_copia'
}

// La que más paga primero, las que no dicen puntos al final y, a igual recompensa, la más nueva (como `points_desc` del servidor).
function porRecompensa(a: Pick<RequestItemResponse, 'id' | 'points' | 'created_at'>, b: Pick<RequestItemResponse, 'id' | 'points' | 'created_at'>): number {
  if ((a.points == null) !== (b.points == null)) return a.points == null ? 1 : -1
  if (a.points !== b.points) return (b.points ?? 0) - (a.points ?? 0)
  const ca = a.created_at ?? '', cb = b.created_at ?? ''
  if (ca !== cb) return ca < cb ? 1 : -1
  return b.id - a.id
}

type ParaAgrupar = Pick<RequestItemResponse, 'id' | 'points' | 'created_at' | 'readiness_status' | 'compatibility_status'>

// Los grupos que tienen algo, en el orden de GRUPOS_PETICION y cada uno por recompensa.
export function agruparPeticiones<T extends ParaAgrupar>(items: T[]): { id: GrupoPeticion; titulo: string; ayuda: string; items: T[] }[] {
  return GRUPOS_PETICION
    .map(g => ({ ...g, items: items.filter(i => grupoDePeticion(i) === g.id).sort(porRecompensa) }))
    .filter(g => g.items.length > 0)
}

// Columna Autor: oculta salvo que se active (el autor sale en cada captura de pantalla).
const CLAVE_MOSTRAR_AUTOR = 'emuwarez_peticiones_mostrar_autor'

export function leerMostrarAutor(): boolean {
  try { return localStorage.getItem(CLAVE_MOSTRAR_AUTOR) === '1' } catch { return false }
}

export function guardarMostrarAutor(mostrar: boolean): void {
  try { localStorage.setItem(CLAVE_MOSTRAR_AUTOR, mostrar ? '1' : '0') } catch { /* sin almacenamiento: vale para esta visita */ }
}
