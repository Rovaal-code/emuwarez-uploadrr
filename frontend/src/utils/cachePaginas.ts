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
 * 3. Una sincronización lo tira TODO (SyncContext, al terminar cualquiera de
 *    las tres). El plazo de dos minutos acota cuánto puede desviarse lo
 *    guardado por su cuenta, pero sincronizar no es una desviación: es la
 *    aplicación entera cambiando de golpe. La página que estés viendo se
 *    recarga sola con `lastCompletedAt`; las demás están DESMONTADAS y solo
 *    tienen su copia, así que entrar en Biblioteca justo después de importar
 *    40 películas enseñaría la lista de antes, sin ellas. Eso incluye la
 *    sincronización programada, que termina sin que hayas tocado nada.
 */

export const VIGENCIA_MS = 120_000

const guardado = new Map<string, { datos: unknown; cuando: number }>()

// Sube cada vez que algo invalida lo guardado. Existe por una carrera real:
// Subidas repide cada 2,5 segundos y el Panel cada 15, así que una
// sincronización puede terminar con una petición YA EN VUELO. Esa petición
// trae datos de antes de la sincronización, y al resolver los guardaría —
// volviendo a meter en la caché justo lo que se acababa de tirar, para dos
// minutos. Quien pide datos se queda con la generación de ese momento y la
// devuelve al guardar; si no coincide, lo que trae ya no vale.
let generacion = 0

/** La generación actual. Se toma ANTES de pedir los datos. */
export function generacionCache(): number {
  return generacion
}

interface OpcionesGuardar {
  /** La generación de cuando se pidieron los datos. Si cambió, no se guardan. */
  generacion?: number
  ahora?: number
}

/** Guarda la carga de una sección. Llamar SOLO cuando no hay filtros puestos. */
export function guardarPagina<T>(pagina: string, datos: T, opciones: OpcionesGuardar = {}): void {
  if (opciones.generacion !== undefined && opciones.generacion !== generacion) return
  guardado.set(pagina, { datos, cuando: opciones.ahora ?? Date.now() })
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
  generacion++
}
