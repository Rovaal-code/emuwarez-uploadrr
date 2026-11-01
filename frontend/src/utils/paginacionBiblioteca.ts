import { formatNumero } from './format'

/**
 * Biblioteca pide las filas de 20.000 en 20.000. Con una biblioteca grande una
 * vista (el árbol entero, o un filtro amplio como «Tipo = Episodio») tiene más
 * filas que eso, y la tabla enseñaba solo las primeras sin decirlo: ordenada de
 * la A a la Z se cortaba hacia la mitad del alfabeto y parecía completa.
 */

/** Lo que dice la barra de filtros sobre cuántas filas hay, o null si no hace falta decir nada. */
export function textoDeResultados(mostradas: number, total: number, filtrando: boolean): string | null {
  if (total > mostradas) return `Mostrando ${formatNumero(mostradas)} de ${formatNumero(total)}`
  if (!filtrando) return null
  return total === 1 ? '1 resultado' : `${formatNumero(total)} resultados`
}

export function hayMasQueCargar(mostradas: number, total: number): boolean {
  return total > mostradas
}

/** Añade la página nueva a lo ya cargado, sin repetir las filas que ya estaban (si la biblioteca cambió entre peticiones). */
export function unirPagina<T extends { id: number }>(actual: readonly T[], nueva: readonly T[]): T[] {
  const vistos = new Set(actual.map(it => it.id))
  return [...actual, ...nueva.filter(it => !vistos.has(it.id))]
}
