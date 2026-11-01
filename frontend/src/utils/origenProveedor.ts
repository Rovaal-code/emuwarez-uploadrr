import type { Ajustes } from './seleccionSubida'

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

/**
 * Los ajustes de una temporada tal como viajan a la subida: el Proveedor solo
 * si se eligió a mano (el campo Proveedor o el selector del conflicto). El
 * detectado no viaja: como provider_override, un pack bloqueado por capítulos
 * con proveedores distintos se validaría sin que nadie eligiera uno.
 */
export function ajustesDeTemporada(
  ajustes: Ajustes | undefined,
  elegidos: ReadonlyMap<number, string | null>,
  id: number,
): Ajustes | undefined {
  const elegido = elegidos.get(id) ?? null
  if (!ajustes && !elegido) return undefined
  return { ...(ajustes ?? {}), provider: elegido }
}
