/**
 * Vistas guardadas de Biblioteca: una combinación de filtros, búsqueda y orden con nombre, para volver a ella con un clic.
 *
 * Los filtros viven en el estado de la página y no en la URL, así que una vista guarda esos valores. Se quedan en
 * este navegador (localStorage): no hay endpoint ni migración, y quien las usa es una sola persona.
 */

const CLAVE_VISTAS = 'emuwarez_uploadrr_library_views'
const MAX_VISTAS = 20
export const MAX_NOMBRE_VISTA = 40

export interface FiltrosDeVista {
  search: string
  type: string[]
  status: string[]
  instanceId: string[]
  request: string[]
  provider: string[]
  quality: string[]
  source: string[]
  group: string[]
  emu: string[]
  aporte: string
  spanish: string[]
  sort: string
}

export interface VistaGuardada {
  id: string
  nombre: string
  filtros: FiltrosDeVista
}

export const ORDEN_POR_DEFECTO = 'title_asc'

export const SIN_FILTROS: FiltrosDeVista = {
  search: '', type: [], status: [], instanceId: [], request: [], provider: [], quality: [], source: [], group: [],
  emu: [], aporte: '', spanish: [], sort: ORDEN_POR_DEFECTO,
}

const LISTAS = ['type', 'status', 'instanceId', 'request', 'provider', 'quality', 'source', 'group', 'emu', 'spanish'] as const

/** Lo guardado, vuelto a la forma de siempre: lo que falta o viene torcido se queda como «sin filtro». */
function normalizar(crudo: unknown): FiltrosDeVista {
  const o = (crudo && typeof crudo === 'object' ? crudo : {}) as Record<string, unknown>
  const f: FiltrosDeVista = { ...SIN_FILTROS }
  for (const k of LISTAS) {
    const v = o[k]
    f[k] = Array.isArray(v) ? v.filter((x): x is string => typeof x === 'string') : []
  }
  if (typeof o.search === 'string') f.search = o.search
  if (typeof o.aporte === 'string') f.aporte = o.aporte
  if (typeof o.sort === 'string' && o.sort) f.sort = o.sort
  return f
}

export function mismosFiltros(a: FiltrosDeVista, b: FiltrosDeVista): boolean {
  return a.search === b.search && a.aporte === b.aporte && a.sort === b.sort
    && LISTAS.every(k => a[k].length === b[k].length && a[k].every((v, i) => v === b[k][i]))
}

/** Hay algo que guardar: algún filtro, una búsqueda o un orden que no es el de partida. */
export function hayAlgoQueGuardar(f: FiltrosDeVista): boolean {
  return !mismosFiltros(f, SIN_FILTROS)
}

export function cargarVistas(): VistaGuardada[] {
  try {
    const crudo = JSON.parse(localStorage.getItem(CLAVE_VISTAS) ?? '[]')
    if (!Array.isArray(crudo)) return []
    return crudo
      .filter(v => v && typeof v.id === 'string' && typeof v.nombre === 'string' && v.nombre.trim())
      .map(v => ({ id: v.id, nombre: v.nombre.trim().slice(0, MAX_NOMBRE_VISTA), filtros: normalizar(v.filtros) }))
      .slice(0, MAX_VISTAS)
  } catch {
    return []
  }
}

export function persistirVistas(vistas: VistaGuardada[]): void {
  try { localStorage.setItem(CLAVE_VISTAS, JSON.stringify(vistas)) } catch { /* sin almacenamiento: la vista vale esta sesión */ }
}

/** Añade la vista; si ya hay una con ese nombre (sin distinguir mayúsculas) la sustituye. */
export function conVista(vistas: VistaGuardada[], nombre: string, filtros: FiltrosDeVista, id: string): VistaGuardada[] {
  const limpio = nombre.trim().slice(0, MAX_NOMBRE_VISTA)
  if (!limpio) return vistas
  const clave = limpio.toLocaleLowerCase()
  const resto = vistas.filter(v => v.nombre.toLocaleLowerCase() !== clave)
  return [...resto, { id, nombre: limpio, filtros }].slice(-MAX_VISTAS)
}

export function sinVista(vistas: VistaGuardada[], id: string): VistaGuardada[] {
  return vistas.filter(v => v.id !== id)
}
