import { lazy, type ComponentType } from 'react'

// La misma firma que React.lazy.
type Componente = ComponentType<any>

// Los chunks diferidos llevan un hash en el nombre. Tras publicar una versión, una pestaña abierta con el bundle viejo
// pide `assets/X-<hash viejo>.js`, que ya no existe; y `lazy` guarda la promesa rechazada, así que la sección se
// quedaba rota hasta recargar a mano. Aquí se reintenta una vez y, si sigue fallando la carga, se recarga la página
// (que trae el index.html nuevo) una sola vez: la marca en sessionStorage evita el bucle si el chunk falta de verdad.

const CLAVE_RECARGA = 'emuwarez_recarga_por_chunk'
// Una recarga por pestaña en este plazo; pasado, otra publicación puede volver a recargar.
const PLAZO_ENTRE_RECARGAS_MS = 5 * 60_000

/** Recargar la página. En un objeto para que los tests lo puedan sustituir (jsdom no recarga). */
export const pagina = { recargar: () => window.location.reload() }

/** Si es el error de no poder bajar un módulo (Chrome, Firefox, Safari y el precargador de Vite). */
export function esErrorDeCarga(error: unknown): boolean {
  const texto = error instanceof Error ? `${error.name} ${error.message}` : String(error ?? '')
  return /dynamically imported module|Importing a module script failed|Unable to preload CSS|ChunkLoadError|Loading chunk/i
    .test(texto)
}

/** Recarga la página si no se ha recargado por esto hace poco. Devuelve si lo hizo. */
export function recargarPorChunk(): boolean {
  try {
    const ultima = Number(sessionStorage.getItem(CLAVE_RECARGA) ?? 0)
    if (Date.now() - ultima < PLAZO_ENTRE_RECARGAS_MS) return false
    sessionStorage.setItem(CLAVE_RECARGA, String(Date.now()))
  } catch {
    return false   // sin sessionStorage no hay cómo evitar el bucle: que lo vea el límite de errores
  }
  pagina.recargar()
  return true
}

export async function cargarConReintento<T>(cargar: () => Promise<T>): Promise<T> {
  try {
    return await cargar()
  } catch {
    try {
      return await cargar()
    } catch (error) {
      // Mientras la página se recarga no hay nada que pintar: la promesa se queda pendiente.
      if (esErrorDeCarga(error) && recargarPorChunk()) return new Promise<T>(() => {})
      throw error
    }
  }
}

/** `React.lazy` que sobrevive a un chunk que ya no existe (ver arriba). */
export function lazyConReintento<T extends Componente>(cargar: () => Promise<{ default: T }>) {
  return lazy<T>(() => cargarConReintento(cargar))
}
