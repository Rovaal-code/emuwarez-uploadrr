/**
 * Qué enseña la columna "Español" de Biblioteca.
 *
 * Antes solo miraba el AUDIO, así que una película con los diálogos en inglés
 * y subtítulos en castellano salía como "No" — y era perfectamente subible,
 * porque eMuwarez acepta cualquiera de las dos. La columna se llamaba igual
 * que la condición pero contestaba a algo más estrecho que ella.
 *
 * Ahora distingue los cuatro casos, y el color dice de un vistazo si cumple:
 *
 *   Ambos   verde   audio y subtítulos en castellano
 *   Audio   ámbar   solo el audio          } cumplen la condición de subida,
 *   Subs    ámbar   solo los subtítulos    } pero no están completos
 *   No      rojo    ni una cosa ni la otra
 *   —       gris    no se sabe
 *
 * El guion NO es "no tiene": es que no se ha podido leer. Un Faltante que no
 * está en disco, o un archivo corrupto del que MediaInfo no saca nada.
 * Enseñarlo como "No" sería afirmar algo que nadie ha comprobado, y encima es
 * lo que uno miraría para decidir si vuelve a descargarlo.
 */

export type EstadoCastellano = 'ambos' | 'audio' | 'subs' | 'no' | 'desconocido'

export interface ConCastellano {
  has_spanish_audio?: number | null
  has_spanish_subs?: number | null
}

export function estadoCastellano(item: ConCastellano): EstadoCastellano {
  const audio = item.has_spanish_audio
  const subs = item.has_spanish_subs
  if (audio === 1 && subs === 1) return 'ambos'
  if (audio === 1) return 'audio'
  if (subs === 1) return 'subs'
  // Con uno confirmado que NO y el otro sin leer, todavía puede aparecer
  // castellano por ese lado: no se puede decir "No" sin haber mirado los dos.
  if (audio === 0 && subs === 0) return 'no'
  return 'desconocido'
}

/** Texto y color de cada estado. Ámbar es el mismo de "Parcial" en el resto
 *  de la aplicación: cumple, pero no del todo. */
export const CASTELLANO_INFO: Record<Exclude<EstadoCastellano, 'desconocido'>,
                                    { label: string; cssClass: string }> = {
  ambos: { label: 'Ambos', cssClass: 'status-available' },
  audio: { label: 'Audio', cssClass: 'status-partial' },
  subs:  { label: 'Subs',  cssClass: 'status-partial' },
  no:    { label: 'No',    cssClass: 'status-missing' },
}

/** Lo que ofrece el desplegable de la columna, en este orden. */
export const CASTELLANO_OPCIONES: { value: EstadoCastellano; label: string }[] = [
  { value: 'ambos', label: 'Ambos' },
  { value: 'audio', label: 'Audio' },
  { value: 'subs', label: 'Subs' },
  { value: 'no', label: 'No' },
  { value: 'desconocido', label: '—' },
]
