// Lo que el asistente de subida va a subir, en un solo valor: un elemento, una
// cola de temporadas o una cola de capítulos. Nunca dos colas a la vez.

export type ModoSeleccion = 'unico' | 'temporadas' | 'capitulos'

export interface Seleccion {
  modo: ModoSeleccion
  // La cola: solo hay en 'temporadas' y 'capitulos'.
  ids: readonly number[]
  // El elemento que se está viendo ahora (null hasta que se elige).
  objetivo: number | null
  // El objetivo es una temporada entera (pack), no un fichero.
  esTemporada: boolean
}

const SIN_COLA: readonly number[] = []

export const SIN_SELECCION: Seleccion = { modo: 'unico', ids: SIN_COLA, objetivo: null, esTemporada: false }

export const seleccionUnica = (id: number, esTemporada = false): Seleccion =>
  ({ modo: 'unico', ids: SIN_COLA, objetivo: id, esTemporada })

export const seleccionTemporadas = (ids: readonly number[]): Seleccion =>
  ({ modo: 'temporadas', ids, objetivo: ids[0] ?? null, esTemporada: true })

export const seleccionCapitulos = (ids: readonly number[]): Seleccion =>
  ({ modo: 'capitulos', ids, objetivo: ids[0] ?? null, esTemporada: false })

export const colaTemporadas = (s: Seleccion): readonly number[] => s.modo === 'temporadas' ? s.ids : SIN_COLA
export const colaCapitulos = (s: Seleccion): readonly number[] => s.modo === 'capitulos' ? s.ids : SIN_COLA

// Más de un elemento: el paso 2 sube la tanda entera en vez de un solo trabajo.
export const esTanda = (s: Seleccion): boolean => s.ids.length > 1

// Lo mismo elegido otra vez (volver al paso 0 y pulsar Continuar sin tocar
// nada): no hay que descartar lo ya cargado ni lo editado.
export function mismaSeleccion(a: Seleccion, b: Seleccion): boolean {
  return a.modo === b.modo
    && a.esTemporada === b.esTemporada
    && (a.modo === 'unico' ? a.objetivo === b.objetivo : a.ids.length === b.ids.length && a.ids.every((id, i) => id === b.ids[i]))
}

// Cambia de elemento dentro de la cola. Un id que no está en ella se ignora.
export function conObjetivo(s: Seleccion, id: number): Seleccion {
  return s.ids.includes(id) ? { ...s, objetivo: id } : s
}

// ¿Hay algo cacheado para cada id de la cola? Se mira por ids y no por
// cantidad: elegir otros tres capítulos dejaba tres entradas, las de antes.
export function cacheCubre(ids: readonly number[], cache: ReadonlyMap<number, unknown>): boolean {
  return ids.every(id => cache.has(id))
}

export interface Ajustes {
  source?: string | null; provider?: string | null; tag?: string | null; title?: string | null
  // Solo pack: el idioma elegido para cada pista de audio sin idioma, por posición.
  idiomas?: Record<number, string>
}

// Copia de `mapa` con los ajustes de `id`, pero solo si los campos que se
// guardan son de ese elemento: mientras carga otra temporada siguen siendo los
// de la anterior, y apuntarlos a la nueva les cambiaba el Source y el Tag.
export function conAjustes(
  mapa: ReadonlyMap<number, Ajustes>,
  id: number | null,
  duenoDeLosCampos: number | null,
  ajustes: Ajustes,
): Map<number, Ajustes> {
  const copia = new Map(mapa)
  if (id != null && id === duenoDeLosCampos) copia.set(id, ajustes)
  return copia
}

export interface AlcancePeticion { season?: number | null; episode?: number | null }

// ¿La petición de la que se abrió el asistente cubre este elemento? Lo que no
// se puede comparar (sin número) cuenta como cubierto.
export function peticionCubre(
  alcance: AlcancePeticion | undefined,
  elemento: { season_number?: number | null; episode_number?: number | null },
): boolean {
  if (!alcance) return true
  const otraTemporada = alcance.season != null && elemento.season_number != null && alcance.season !== elemento.season_number
  const otroCapitulo = alcance.episode != null && elemento.episode_number != null && alcance.episode !== elemento.episode_number
  return !otraTemporada && !otroCapitulo
}
