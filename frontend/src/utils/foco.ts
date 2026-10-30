/**
 * Tab dentro de un modal: a qué elemento saltar para que el foco no se salga.
 * Del último se vuelve al primero (y con Mayús, del primero al último); si el
 * foco está fuera, entra por el borde que toca. Devuelve null cuando el salto
 * normal del navegador ya se queda dentro, para que quien llame lo deje pasar.
 */
export function siguienteFoco<T>(enfocables: T[], actual: T | null, atras: boolean): T | null {
  if (enfocables.length === 0) return null
  const primero = enfocables[0]
  const ultimo = enfocables[enfocables.length - 1]
  const i = actual == null ? -1 : enfocables.indexOf(actual)
  if (i < 0) return atras ? ultimo : primero
  if (atras && i === 0) return ultimo
  if (!atras && i === enfocables.length - 1) return primero
  return null
}

/**
 * Al cerrar un modal, a quién devolver el foco. Normalmente a quien lo abrió,
 * pero si ese botón ya no está en la página (era de otro modal que se cerró al
 * abrir este, como MediaInfo al pasar a la comparación de fuentes), se sigue la
 * cadena: el foco va a donde lo habría devuelto aquel modal. `heredado` dice
 * eso para un elemento que ya no está; null si no hay nada mejor.
 */
export function destinoAlCerrar<T extends { isConnected: boolean }>(
  antes: T | null,
  heredado: (quitado: T) => T | null | undefined,
): T | null {
  const vistos = new Set<T>()
  let destino = antes
  while (destino && !destino.isConnected && !vistos.has(destino)) {
    vistos.add(destino)
    destino = heredado(destino) ?? null
  }
  return destino?.isConnected ? destino : null
}
