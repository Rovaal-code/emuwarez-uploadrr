/**
 * La última carga de cada sección, para no volver a ver "Cargando…".
 *
 * Al cambiar de sección, AppShell DESMONTA la página (PageContent es un
 * switch), así que su estado se pierde y volver a entrar arrancaba de cero.
 * Recargar está bien —estas pantallas enseñan datos vivos— pero bloquear para
 * ello no: si hace un momento estabas ahí, se enseña lo último y se refresca
 * por detrás.
 *
 * DOS reglas, y las dos importan:
 *
 * 1. Solo se guarda la vista SIN FILTRAR. Los filtros se reinician al volver,
 *    así que reutilizar un resultado filtrado enseñaría una lista recortada
 *    bajo unos filtros vacíos: parecería que faltan cosas.
 * 2. Caduca a los dos minutos. Estas pantallas enseñan cosas vivas (una
 *    subida al 45% que ya terminó, un contador que cambió), y reutilizar una
 *    foto vieja sería mentir mientras llega la buena. Dos minutos es de sobra
 *    para ir a otra sección y volver, y poco para que lo enseñado mienta.
 */

export const VIGENCIA_MS = 120_000

const guardado = new Map<string, { datos: unknown; cuando: number }>()

/** Guarda la carga de una sección. Llamar SOLO cuando no hay filtros puestos. */
export function guardarPagina<T>(pagina: string, datos: T, ahora: number = Date.now()): void {
  guardado.set(pagina, { datos, cuando: ahora })
}

/** Lo último guardado de una sección, si sigue vigente. */
export function ultimaPagina<T>(pagina: string, ahora: number = Date.now()): T | null {
  const entrada = guardado.get(pagina)
  if (!entrada) return null
  if (ahora - entrada.cuando > VIGENCIA_MS) return null
  return entrada.datos as T
}

/** Tira lo guardado de una sección (o de todas). Lo usan los tests, y sirve
 *  para invalidar tras una acción que cambia los datos de verdad. */
export function olvidarPagina(pagina?: string): void {
  if (pagina) guardado.delete(pagina)
  else guardado.clear()
}
