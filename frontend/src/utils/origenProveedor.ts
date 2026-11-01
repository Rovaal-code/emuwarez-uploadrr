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

// "Sin proveedor" elegido a mano, tal como lo entiende el servidor
// (nomenclature.SIN_PROVEEDOR): no es lo mismo que no mandar nada, que deja
// que el servidor lo detecte.
export const SIN_PROVEEDOR = ''

/**
 * El Proveedor elegido A MANO por temporada, en tres estados: sin entrada (no
 * se ha elegido), `null` ("Sin proveedor" elegido) o un código.
 */
export type ProveedoresElegidos = ReadonlyMap<number, string | null>

/**
 * Lo que se manda al servidor como `provider` de una temporada; lo leen igual
 * la vista previa del plan, las comprobaciones y la cola. `undefined`: no se
 * eligió nada (el servidor decide); `SIN_PROVEEDOR`: "Sin proveedor"; si no,
 * el código. El detectado nunca viaja como elección: con proveedores distintos
 * el pack se validaría sin que nadie eligiera uno.
 */
export function proveedorParaServidor(elegidos: ProveedoresElegidos, id: number): string | undefined {
  if (!elegidos.has(id)) return undefined
  return elegidos.get(id) ?? SIN_PROVEEDOR
}

/** Los ajustes de una temporada tal como viajan a la cola, con el Proveedor de proveedorParaServidor. */
export function ajustesDeTemporada(
  ajustes: Ajustes | undefined,
  elegidos: ProveedoresElegidos,
  id: number,
): Ajustes | undefined {
  const provider = proveedorParaServidor(elegidos, id)
  if (!ajustes && provider === undefined) return undefined
  return { ...(ajustes ?? {}), provider }
}
