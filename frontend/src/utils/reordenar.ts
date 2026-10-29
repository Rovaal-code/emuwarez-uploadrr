/**
 * Reordenar una lista con el teclado: qué orden sale al pulsar una tecla sobre
 * la asa de una fila. Flecha arriba/abajo mueve una posición; Inicio/Fin la
 * lleva al principio o al final. Devuelve null si la tecla no mueve nada (no es
 * una de estas, o la fila ya está en el borde), para que quien llame deje
 * pasar la tecla.
 */
export function moverConTecla(ids: string[], id: string, tecla: string): string[] | null {
  const desde = ids.indexOf(id)
  if (desde < 0) return null
  const hasta =
    tecla === 'ArrowUp' ? desde - 1
    : tecla === 'ArrowDown' ? desde + 1
    : tecla === 'Home' ? 0
    : tecla === 'End' ? ids.length - 1
    : null
  if (hasta === null || hasta < 0 || hasta >= ids.length || hasta === desde) return null
  const lista = [...ids]
  lista.splice(desde, 1)
  lista.splice(hasta, 0, id)
  return lista
}
