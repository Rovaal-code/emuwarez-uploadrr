/**
 * Si quedan subidas por cargar. Con el total conocido, las que faltan; sin él (el recuento falló), se da por hecho
 * que hay más mientras la lista llene el límite pedido, que es lo único que se puede saber. Nunca pasa de `maximo`,
 * lo que acepta el servidor.
 */
export function hayMasPorCargar(total: number | null, cargadas: number, limite: number, maximo: number): boolean {
  if (limite >= maximo) return false
  return total != null ? cargadas < total : cargadas >= limite
}
