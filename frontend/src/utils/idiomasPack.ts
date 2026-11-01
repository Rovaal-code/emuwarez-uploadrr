// El idioma elegido para las pistas de audio sin idioma de un pack de
// temporada, por posición de la pista entre las de audio (desde 1), la misma
// que usa el servidor (season_pack.py / mkv_remux.idiomas_por_posicion). Una
// elección por posición vale para todos los capítulos del pack.
export type IdiomasPorPosicion = Readonly<Record<number, string>>

export const SIN_IDIOMAS: IdiomasPorPosicion = {}

/** Copia de `idiomas` con `codigo` en `posicion`; '' la quita (vuelve a «sin idioma»). */
export function conIdioma(idiomas: IdiomasPorPosicion, posicion: number, codigo: string): IdiomasPorPosicion {
  const copia: Record<number, string> = { ...idiomas }
  if (codigo) copia[posicion] = codigo
  else delete copia[posicion]
  return copia
}

/** Lo que viaja al servidor: undefined si no se ha elegido nada. */
export function idiomasParaServidor(idiomas: IdiomasPorPosicion | undefined): Record<number, string> | undefined {
  return idiomas && Object.keys(idiomas).length ? { ...idiomas } : undefined
}

/**
 * Los idiomas que el servidor dice haber aplicado ({"1": "spa"} en el JSON),
 * con la clave en número. Lo que no sea un texto se ignora.
 */
export function idiomasDelServidor(crudo: Readonly<Record<string, unknown>> | null | undefined): IdiomasPorPosicion {
  const salida: Record<number, string> = {}
  for (const [clave, codigo] of Object.entries(crudo ?? {})) {
    const posicion = Number(clave)
    if (Number.isInteger(posicion) && posicion > 0 && typeof codigo === 'string' && codigo) salida[posicion] = codigo
  }
  return salida
}

/** "Pista de audio 2 (DD 5.1), capítulos 1, 2 y 3" — la etiqueta del selector. */
export function etiquetaPistaSinIdioma(posicion: number, pista: string | null | undefined, capitulos: readonly (number | null)[]): string {
  const numeros = capitulos.filter((c): c is number => c != null)
  const donde = numeros.length === 0 ? ''
    : numeros.length === 1 ? `, capítulo ${numeros[0]}`
    : `, capítulos ${numeros.slice(0, -1).join(', ')} y ${numeros[numeros.length - 1]}`
  return `Pista de audio ${posicion}${pista ? ` (${pista})` : ''}${donde}`
}
