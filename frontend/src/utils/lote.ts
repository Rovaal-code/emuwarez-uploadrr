/**
 * Un lote: varias subidas encoladas juntas (las tandas del asistente, y más adelante «Subir por lotes»). Comparten
 * un `lote_id` que genera el navegador, y Subidas las agrupa y filtra por él.
 */
import type { LibraryItemResponse } from '../types/api'
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
 * Por qué una película (o un capítulo) no puede entrar en un lote, o null si puede: la misma regla que
 * `episodeNotReadyReason` (utils/libraryItem.ts: en disco y con castellano), pero con su propio texto, que
 * aquel habla de «el capítulo». Una serie o una temporada todavía no van por lotes.
 */
export function razonNoSubible(item: LibraryItemResponse): string | null {
  const esCapitulo = item.item_type === 'episode'
  if (item.item_type !== 'movie' && !esCapitulo) return 'Por ahora el lote solo admite películas.'
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
