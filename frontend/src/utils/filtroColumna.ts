/**
 * Las reglas del desplegable de filtro de una columna (components/HeaderFilter),
 * fuera del componente para poder probarlas sin navegador.
 */

export interface OpcionFiltro { value: string; label: string }

/**
 * Lo que queda elegido tras pulsar `valor` en un filtro de selección múltiple.
 * '' es «Todos»: lo quita todo. Si no cambia nada devuelve la MISMA lista, para
 * que quien llama no lo tome por un cambio y no recargue.
 */
export function siguienteSeleccion(elegidos: readonly string[], valor: string): readonly string[] {
  if (valor === '') return elegidos.length ? [] : elegidos
  return elegidos.includes(valor) ? elegidos.filter(x => x !== valor) : [...elegidos, valor]
}

/** Lo elegido, con los nombres que enseña la columna y en el orden del menú. */
export function resumenFiltro(elegidos: readonly string[], opciones: readonly OpcionFiltro[]): string {
  const orden = new Map(opciones.map((o, i) => [o.value, i]))
  return [...elegidos]
    .sort((a, b) => (orden.get(a) ?? Infinity) - (orden.get(b) ?? Infinity))
    .map(v => opciones.find(o => o.value === v)?.label ?? v)
    .join(', ')
}
