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
