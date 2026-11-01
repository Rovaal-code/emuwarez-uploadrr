/**
 * De dónde sale el proveedor de un pack de temporada, para enseñarlo bajo el
 * campo Proveedor del asistente: "Proveedor: FLMN (detectado en el nombre del
 * archivo del capítulo 1)". El servidor decide el proveedor una sola vez para
 * la carpeta y todos los capítulos y dice de dónde lo ha sacado.
 */
export function textoOrigenProveedor(
  propuesto: string | null | undefined,
  detalle: string | null | undefined,
  actual: string | null | undefined,
): string | null {
  if (!actual) return null
  // Cambiado en el desplegable: ya no es lo que detectó el servidor.
  if (actual !== propuesto) return `Proveedor: ${actual} (elegido a mano; se aplica a todos los capítulos)`
  return detalle ? `Proveedor: ${actual} (${detalle})` : null
}
