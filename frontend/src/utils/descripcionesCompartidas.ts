/**
 * Descripciones de tooltip compartidas.
 *
 * Para que el lector de pantalla lea un tooltip, el disparador apunta con
 * aria-describedby a un elemento oculto que ya existe antes del foco. Con uno
 * por disparador, una tabla de 50 filas dejaba cientos de <span hidden> con el
 * mismo texto ("Abrir en Sonarr", "Ver ficha"...). Aquí se guarda uno solo por
 * texto distinto, con un contador de cuántos disparadores lo usan: el nodo se
 * crea con el primero y se quita cuando se va el último.
 *
 * `crear` pone el nodo en la página y devuelve cómo quitarlo; así esto se
 * prueba sin navegador.
 */

export interface NodoDescripcion {
  remove(): void
}

interface Entrada {
  id: string
  nodo: NodoDescripcion | null
  usos: number
}

export function crearRegistroDescripciones(crear: (id: string, texto: string) => NodoDescripcion) {
  const entradas = new Map<string, Entrada>()
  let siguiente = 0

  return {
    /** El id del texto. Se puede pedir al renderizar: no crea el nodo. */
    idDe(texto: string): string {
      let e = entradas.get(texto)
      if (!e) {
        e = { id: `desc-tooltip-${++siguiente}`, nodo: null, usos: 0 }
        entradas.set(texto, e)
      }
      return e.id
    },

    /** Un disparador más usa el texto. `id` es el que dio idDe al renderizar. */
    montar(texto: string, id: string): void {
      let e = entradas.get(texto)
      if (!e) {
        // Se había soltado del todo entre el render y el montaje: vuelve con
        // el mismo id, que es el que ya lleva el disparador.
        e = { id, nodo: null, usos: 0 }
        entradas.set(texto, e)
      }
      if (!e.nodo) e.nodo = crear(e.id, texto)
      e.usos++
    },

    /** Un disparador deja de usar el texto; con el último se quita el nodo. */
    soltar(texto: string): void {
      const e = entradas.get(texto)
      if (!e) return
      e.usos--
      if (e.usos <= 0) {
        e.nodo?.remove()
        entradas.delete(texto)
      }
    },

    /** Cuántos textos distintos hay registrados (para los tests). */
    tamano(): number {
      return entradas.size
    },
  }
}
