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

// Secciones que están enseñando una copia que NADIE ha confirmado todavía:
// se entregó al montar y la recarga que debía confirmarla aún no ha vuelto.
// Importa porque si esa recarga FALLA, lo de la pantalla es un dato de una
// antigüedad que nadie conoce y sin nada que lo corrija — el único caso en
// que una copia se queda mintiendo, y no un instante sino hasta que toques
// algo. Afecta sobre todo a Biblioteca, que es la que no repide sola.
//
// Una recarga que falla NO es lo mismo que esto: si la copia ya se había
// confirmado, lo que hay en pantalla es bueno y se queda. Vaciar la tabla
// porque un refresco de fondo parpadeó sería peor que no hacer nada.
const sinConfirmar = new Set<string>()

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

/** Guarda la carga de una sección. Llamar SOLO cuando no hay filtros puestos.
 *  Guardar es lo que confirma la copia: los datos acaban de llegar bien. */
export function guardarPagina<T>(pagina: string, datos: T, opciones: OpcionesGuardar = {}): void {
  if (opciones.generacion !== undefined && opciones.generacion !== generacion) return
  guardado.set(pagina, datos)
  sinConfirmar.delete(pagina)
}

/** Lo último guardado de una sección, mientras no se haya invalidado. No marca
 *  nada: es la lectura a secas. Para montar una página, `tomarCopia`. */
export function ultimaPagina<T>(pagina: string): T | null {
  return guardado.has(pagina) ? (guardado.get(pagina) as T) : null
}

/** La copia con la que arranca una página, marcada como pendiente de
 *  confirmar. Se llama UNA vez al montar (desde un inicializador perezoso de
 *  useState), no en cada render: si se llamara en cada render volvería a
 *  marcar como sin confirmar algo que ya se confirmó. */
export function tomarCopia<T>(pagina: string): T | null {
  if (!guardado.has(pagina)) return null
  sinConfirmar.add(pagina)
  return guardado.get(pagina) as T
}

/** La recarga que debía confirmar la copia ha fallado.
 *
 *  Devuelve true si lo que hay en pantalla era una copia sin confirmar, y
 *  entonces quien llama tiene que vaciarlo: es un dato de antigüedad
 *  desconocida y ya no va a llegar nada que lo corrija, así que enseñar el
 *  error con la tabla vacía dice la verdad y enseñarlo con datos viejos no.
 *  La copia se tira también, para no repetir la escena al volver a entrar.
 *
 *  Devuelve false si los datos ya estaban confirmados: ahí el fallo es un
 *  refresco que parpadeó, y lo de la pantalla sigue siendo bueno. */
export function copiaNoConfirmada(pagina: string): boolean {
  if (!sinConfirmar.has(pagina)) return false
  olvidarPagina(pagina)
  return true
}

/** Tira lo guardado de una sección (o de todas) e invalida lo que esté en
 *  vuelo. Lo llaman las dos invalidaciones de la cabecera. */
export function olvidarPagina(pagina?: string): void {
  if (pagina) {
    guardado.delete(pagina)
    sinConfirmar.delete(pagina)
  } else {
    guardado.clear()
    sinConfirmar.clear()
  }
  generacion++
}
