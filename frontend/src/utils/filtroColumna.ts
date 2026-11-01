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
  if (elegidos.includes(valor)) return elegidos.filter(x => x !== valor)
  return [...elegidos.filter(x => x !== EXCLUIDO + valor), valor]
}

/** Un valor con «!» delante es «todo menos este»: así viaja en la misma lista. */
export const EXCLUIDO = '!'

/** Lo que queda tras pulsar «ocultar» en `valor`: pasa de marcado a oculto, y pulsarlo otra vez lo suelta. */
export function siguienteExclusion(elegidos: readonly string[], valor: string): readonly string[] {
  const oculto = EXCLUIDO + valor
  return elegidos.includes(oculto)
    ? elegidos.filter(x => x !== oculto)
    : [...elegidos.filter(x => x !== valor), oculto]
}

/** Lo elegido, con los nombres que enseña la columna y en el orden del menú. */
export function resumenFiltro(elegidos: readonly string[], opciones: readonly OpcionFiltro[]): string {
  const orden = new Map(opciones.map((o, i) => [o.value, i]))
  const sinMarca = (v: string) => (v.startsWith(EXCLUIDO) && !orden.has(v) ? v.slice(1) : v)
  return [...elegidos]
    .sort((a, b) => (orden.get(sinMarca(a)) ?? Infinity) - (orden.get(sinMarca(b)) ?? Infinity))
    .map(v => {
      const nombre = opciones.find(o => o.value === sinMarca(v))?.label ?? sinMarca(v)
      return sinMarca(v) === v ? nombre : `sin ${nombre}`
    })
    .join(', ')
}

const plano = (s: string) => s.normalize('NFD').replace(/\p{M}/gu, '').toLowerCase()

/** Las opciones cuyo nombre contiene `texto`, sin mirar mayúsculas ni acentos.
 *  «Desmarcar todo» ('') no se esconde nunca. */
export function opcionesQueCoinciden<T extends OpcionFiltro>(opciones: readonly T[], texto: string): readonly T[] {
  const buscado = plano(texto.trim())
  if (!buscado) return opciones
  return opciones.filter(o => o.value === '' || plano(o.label).includes(buscado))
}
