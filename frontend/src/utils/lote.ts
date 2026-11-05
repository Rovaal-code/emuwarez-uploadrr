/**
 * Un lote: varias subidas encoladas juntas (las tandas del asistente y «Subir por lotes»). Comparten un
 * `lote_id` (el de una tanda lo genera el navegador; el de «Subir por lotes», el servidor), y Subidas las agrupa
 * y filtra por él.
 */
import type { DashboardRecommendationItem } from '../api/dashboard'
import type { LibraryItemResponse, RequestItemResponse } from '../types/api'
import { seasonNotReadyReason } from './libraryItem'
import type { NivelDuplicado } from './resumenSubida'

// Copia de services/lotes.py::MAX_ELEMENTOS_LOTE: test_copias_frontend.py vigila que coincidan.
export const MAX_ELEMENTOS_LOTE = 50

// Lo único que acepta el servidor como `lote_id`: 12 caracteres hexadecimales en minúscula.
export const PATRON_LOTE_ID = /^[0-9a-f]{12}$/

// Con la que Subidas recoge, al entrar, el lote recién encolado desde «Subir por lotes» (como emuwarez_open_upload).
export const CLAVE_ABRIR_LOTE = 'emuwarez_open_lote'

const BYTES_LOTE_ID = 6

/** Un `lote_id` nuevo (12 hex). Sin `crypto.getRandomValues` (un navegador muy viejo o un test), con Math.random. */
export function nuevoLoteId(): string {
  const bytes = new Uint8Array(BYTES_LOTE_ID)
  const cripto = (globalThis as { crypto?: Crypto }).crypto
  if (cripto && typeof cripto.getRandomValues === 'function') {
    cripto.getRandomValues(bytes)
  } else {
    for (let i = 0; i < bytes.length; i++) bytes[i] = Math.floor(Math.random() * 256)
  }
  return Array.from(bytes, b => b.toString(16).padStart(2, '0')).join('')
}

// ── «Subir por lotes» desde Biblioteca ──────────────────────────────────────────────────────────────────────────

/**
 * Lo que se puede marcar en Biblioteca para un lote: películas, series (se expanden a sus temporadas) y temporadas
 * (como pack). Un capítulo no: desde Biblioteca solo se suben packs, y el que quiera uno suelto lo sube suelto.
 */
export function seleccionableEnLote(item: LibraryItemResponse): boolean {
  return item.item_type === 'movie' || item.item_type === 'series' || item.item_type === 'season'
}

/**
 * Por qué un elemento no puede entrar en un lote, o null si puede. Una temporada, si no se puede subir como pack
 * (la regla de `seasonNotReadyReason`). Una película o un capítulo, la regla de `episodeNotReadyReason`
 * (utils/libraryItem.ts: en disco y con castellano), pero con su propio texto, que aquel habla de «el capítulo».
 * Una serie no entra tal cual: se cambia por sus temporadas (`expandirSeleccion`).
 */
export function razonNoSubible(item: LibraryItemResponse): string | null {
  if (item.item_type === 'series') return 'Una serie se sube por temporadas.'
  if (item.item_type === 'season') return seasonNotReadyReason(item)
  const esCapitulo = item.item_type === 'episode'
  if (item.item_type !== 'movie' && !esCapitulo) return 'Esto no se sube por lotes.'
  if (item.local_status !== 'Disponible' && item.local_status !== 'Subido') {
    const estado = item.local_status || 'sin estado'
    return esCapitulo
      ? `El capítulo está «${estado}»: no lo tienes en disco.`
      : `La película está «${estado}»: no la tienes en disco.`
  }
  if (item.has_spanish_ok !== 1) {
    return item.has_spanish_ok === 0
      ? 'No tiene castellano ni en el audio ni en los subtítulos.'
      : 'No se han podido leer sus pistas: no se puede confirmar que tenga castellano.'
  }
  return null
}

/**
 * Lo que entra en «Subir por lotes»: el elemento de Biblioteca y, desde el Panel, la petición que cubre y su alcance
 * (como la preselección del asistente: `season` y, si la petición es de un capítulo, `episode`). Desde Biblioteca
 * solo va `item`.
 */
export interface EntradaLote {
  item: LibraryItemResponse
  requestId?: number
  alcance?: { season?: number | null; episode?: number | null }
}

export interface EntradasExpandidas {
  elementos: LibraryItemResponse[]
  // Las peticiones que cubre cada elemento, sin repetir y en el orden en que llegaron (la primera, la que se enlaza
  // si no se elige otra). Sin entrada, ninguna.
  peticiones: Map<number, number[]>
  // Una petición cuya temporada o capítulo no está en la biblioteca.
  avisos: string[]
}

/**
 * Lo marcado, con cada serie cambiada por sus temporadas (en orden de temporada; con `alcance.season`, solo esa) y
 * en el orden en que se marcó. Lo que llega dos veces (una temporada marcada sola y por su serie, o dos peticiones
 * sobre la misma fila) sale una vez, en el primer sitio donde aparece, y junta sus peticiones. Una serie de la que
 * no se cargaron las temporadas (no está en `temporadasDe`) no aporta nada. El tipo que cuenta es el de la fila real
 * (`item`): una petición de capítulo cuya fila resultó ser la temporada o la serie (el capítulo no está) no entra.
 */
export function expandirEntradas(
  entradas: readonly EntradaLote[],
  temporadasDe: ReadonlyMap<number, readonly LibraryItemResponse[]>,
): EntradasExpandidas {
  const vistos = new Set<number>()
  const elementos: LibraryItemResponse[] = []
  const peticiones = new Map<number, number[]>()
  const avisos: string[] = []
  const poner = (item: LibraryItemResponse, requestId: number | undefined) => {
    if (!vistos.has(item.id)) {
      vistos.add(item.id)
      elementos.push(item)
    }
    if (requestId == null) return
    const suyas = peticiones.get(item.id) ?? []
    if (!suyas.includes(requestId)) peticiones.set(item.id, [...suyas, requestId])
  }
  for (const { item, requestId, alcance } of entradas) {
    const season = alcance?.season ?? null
    const episode = alcance?.episode ?? null
    if (episode != null && item.item_type !== 'episode') {
      const codigo = `S${String(season ?? 0).padStart(2, '0')}E${String(episode).padStart(2, '0')}`
      avisos.push(`«${item.title}»: la petición es del capítulo ${codigo}, que no está en la biblioteca.`)
      continue
    }
    if (item.item_type !== 'series') { poner(item, requestId); continue }
    const cargadas = temporadasDe.get(item.id)
    const temporadas = [...(cargadas ?? [])]
      .filter(t => season == null || t.season_number === season)
      .sort((a, b) => (a.season_number ?? Number.MAX_SAFE_INTEGER) - (b.season_number ?? Number.MAX_SAFE_INTEGER))
    if (cargadas && cargadas.length > 0 && season != null && temporadas.length === 0) {
      avisos.push(`«${item.title}»: la temporada ${season} no está en la biblioteca.`)
    }
    for (const t of temporadas) poner(t, requestId)
  }
  // Dos peticiones sobre lo mismo que falta darían el mismo aviso dos veces.
  return { elementos, peticiones, avisos: [...new Set(avisos)] }
}

/** `expandirEntradas` de una selección de Biblioteca (sin peticiones ni alcance). */
export function expandirSeleccion(
  seleccion: readonly LibraryItemResponse[],
  temporadasDe: ReadonlyMap<number, readonly LibraryItemResponse[]>,
): LibraryItemResponse[] {
  return expandirEntradas(seleccion.map(item => ({ item })), temporadasDe).elementos
}

/**
 * Si un elemento llega marcado al Resumen según lo que ya hay en eMuwarez: un duplicado o una copia peor que todo
 * lo que hay, desmarcados (se pueden marcar a mano); sin nada con lo que comparar (`null`) o el resto, marcados.
 */
export function marcadaPorDefecto(nivel: NivelDuplicado | null): boolean {
  return nivel !== 'duplicado' && nivel !== 'peor'
}

/**
 * Los ids de las filas cuyo nombre final de torrent sale más de una vez en el lote. Dos copias con el mismo nombre
 * irían a la misma carpeta de Uploadrr-EMU y la segunda fallaría, así que se marcan las dos. Sin nombre no cuenta.
 */
export function nombresRepetidos(filas: readonly { id: number; nombre: string | null | undefined }[]): Set<number> {
  const porNombre = new Map<string, number[]>()
  for (const { id, nombre } of filas) {
    const clave = nombre?.trim()
    if (!clave) continue
    porNombre.set(clave, [...(porNombre.get(clave) ?? []), id])
  }
  return new Set([...porNombre.values()].filter(ids => ids.length > 1).flat())
}

// ── «Subir seleccionadas» desde «Listo para subir» del Panel ────────────────────────────────────────────────────

/**
 * La clave de una fila del Panel en la selección: la petición (o `u`, sin petición) y la fila que se subiría. Dos
 * peticiones sobre el mismo elemento son dos filas (el grupo 1 hace una por petición); el modal las junta.
 */
export function claveDelPanel(fila: DashboardRecommendationItem): string {
  return `${fila.rec_request_id ?? 'u'}-${fila.library_target_id ?? fila.id}`
}

/**
 * Lo que entra en el lote por una fila del Panel, como abre el asistente su «Subir»: `item` es la fila real de la
 * biblioteca (`getLibraryItem(library_target_id ?? id)`), y una petición lleva su id y su alcance (la temporada y,
 * si la petición es de un capítulo, el capítulo). Una idea sin petición entra sola.
 */
export function entradaDelPanel(fila: DashboardRecommendationItem, item: LibraryItemResponse): EntradaLote {
  return entradaConPeticion(
    item, fila.rec_request_id, fila.season_number, fila.item_type === 'episode' ? fila.episode_number : null)
}

/**
 * Lo que entra en el lote por una petición (del Panel o de Peticiones): la fila real y, si hay petición, su id y su
 * alcance (`episode` solo si la petición es de un capítulo). Sin petición, el elemento solo.
 */
function entradaConPeticion(
  item: LibraryItemResponse, requestId: number | null | undefined,
  season: number | null | undefined, episode: number | null | undefined,
): EntradaLote {
  if (requestId == null) return { item }
  return { item, requestId, alcance: { season: season ?? null, episode: episode ?? null } }
}

// ── «Subir seleccionadas» desde Peticiones ──────────────────────────────────────────────────────────────────────

/**
 * Si una petición de la lista de Peticiones se puede marcar para el lote: las mismas que salen en «Listo para subir»
 * del Panel (`get_dashboard_recommendations`, grupo 1): su mejor coincidencia es «Compatible», cruza con una fila de
 * la biblioteca y su copia no se ha visto sin castellano.
 */
export function peticionSeleccionableEnLote(
  peticion: Pick<RequestItemResponse, 'compatibility_status' | 'library_item_id' | 'readiness_status'>,
): boolean {
  return peticion.compatibility_status === 'Compatible'
    && peticion.library_item_id != null
    && peticion.readiness_status !== 'no_castellano'
}

/**
 * Lo que entra en el lote por una petición de Peticiones, como abre el asistente su «Subir a eMuwarez»: `item` es la
 * fila a la que se refiere (`match.library_target_id`: la temporada o el capítulo pedidos, no la serie que cruzó), con
 * la petición y su alcance (la temporada y, si la petición es de un capítulo, el capítulo).
 */
export function entradaDePeticion(
  peticion: Pick<RequestItemResponse, 'id' | 'req_scope' | 'req_season' | 'req_episode'>, item: LibraryItemResponse,
): EntradaLote {
  return entradaConPeticion(
    item, peticion.id, peticion.req_season, peticion.req_scope === 'episode' ? peticion.req_episode : null)
}
