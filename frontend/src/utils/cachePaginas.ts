/**
 * La última carga de cada sección, para no volver a ver "Cargando…".
 *
 * Al cambiar de sección, AppShell DESMONTA la página (PageContent es un
 * switch), así que su estado se pierde y volver a entrar arrancaba de cero.
 * Recargar está bien —estas pantallas enseñan datos vivos— pero bloquear para
 * ello no: si hace un momento estabas ahí, se enseña lo último y se refresca
 * por detrás. El patrón se llama stale-while-revalidate.
 *
 * AQUÍ NO HAY PLAZO DE CADUCIDAD, y es una decisión, no un olvido. Hubo uno de
 * dos minutos y no defendía nada: la copia solo se ve mientras llega la
 * recarga, y la recarga sale SIEMPRE. Un reloj no distingue una copia buena de
 * una mala, solo adivina. Lo que invalida son hechos, y son dos:
 *
 * 1. Termina una sincronización (SyncContext, cualquiera de las tres, incluida
 *    la programada). No es que la copia se haya desviado un poco: es la
 *    aplicación entera cambiando de golpe. Importas 40 películas, y entrar en
 *    Biblioteca enseñaría la lista de antes, sin ellas.
 * 2. Vuelves a la pestaña (SyncContext, `visibilitychange`). Cubre lo que el
 *    plazo intentaba cubrir a ciegas —la pestaña abierta toda la noche— pero
 *    sabiendo cuándo pasa en vez de suponerlo. Es `refetchOnWindowFocus`, que
 *    SWR y TanStack Query traen activado por defecto.
 *
 * La otra regla, esta de quien llama: solo se guarda la vista SIN FILTRAR. Los
 * filtros se reinician al volver, así que reutilizar un resultado filtrado
 * enseñaría una lista recortada bajo unos filtros vacíos, y parecería que
 * faltan cosas. Esas librerías lo resuelven metiendo los filtros en la clave;
 * aquí no hace falta, porque la vista filtrada no se vuelve a ver.
 */

const guardado = new Map<string, unknown>()

// Sube cada vez que algo invalida lo guardado. Existe por una carrera real:
// Subidas repide cada 2,5 segundos y el Panel cada 15, así que una
// sincronización puede terminar con una petición YA EN VUELO. Esa petición
// trae datos de antes, y al resolver los guardaría — volviendo a meter en la
// caché justo lo que se acababa de tirar. Quien pide datos se queda con la
// generación de ese momento y la devuelve al guardar; si no coincide, lo que
// trae ya no vale.
let generacion = 0

/** La generación actual. Se toma ANTES de pedir los datos. */
export function generacionCache(): number {
  return generacion
}

interface OpcionesGuardar {
  /** La generación de cuando se pidieron los datos. Si cambió, no se guardan. */
  generacion?: number
}

/** Guarda la carga de una sección. Llamar SOLO cuando no hay filtros puestos. */
export function guardarPagina<T>(pagina: string, datos: T, opciones: OpcionesGuardar = {}): void {
  if (opciones.generacion !== undefined && opciones.generacion !== generacion) return
  guardado.set(pagina, datos)
}

/** Lo último guardado de una sección, mientras no se haya invalidado. */
export function ultimaPagina<T>(pagina: string): T | null {
  return guardado.has(pagina) ? (guardado.get(pagina) as T) : null
}

/** Tira lo guardado de una sección (o de todas) e invalida lo que esté en
 *  vuelo. Lo llaman las dos invalidaciones de la cabecera. */
export function olvidarPagina(pagina?: string): void {
  if (pagina) guardado.delete(pagina)
  else guardado.clear()
  generacion++
}
