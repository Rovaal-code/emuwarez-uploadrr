// Lógica pura de la paleta Ctrl+K: normalizar lo que se escribe, filtrar las secciones y mover la selección.

/** Minúsculas y sin acentos, para que «biblioteca» encuentre «Biblioteca» y «estadisticas», «Estadísticas». */
export function normalizar(texto: string): string {
  return texto.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().trim()
}

export interface Seccion {
  id: string
  titulo: string
}

/** Las secciones cuyo nombre contiene lo escrito. Sin texto, todas, en su orden. */
export function filtrarSecciones(secciones: Seccion[], consulta: string): Seccion[] {
  const q = normalizar(consulta)
  if (!q) return secciones
  return secciones.filter(s => normalizar(s.titulo).includes(q) || normalizar(s.id).includes(q))
}

/** La posición siguiente en una lista circular de `total` elementos (`paso` = +1 o -1). */
export function moverSeleccion(actual: number, paso: number, total: number): number {
  if (total <= 0) return 0
  return (actual + paso + total) % total
}

/** Si la combinación es Ctrl+K (o Cmd+K en Mac). */
export function esAtajoDePaleta(e: Pick<KeyboardEvent, 'key' | 'ctrlKey' | 'metaKey' | 'altKey' | 'shiftKey'>): boolean {
  return e.key.toLowerCase() === 'k' && (e.ctrlKey || e.metaKey) && !e.altKey && !e.shiftKey
}
