/**
 * Qué enseña la columna "Español".
 *
 * Antes solo miraba el audio, así que una película con diálogos en inglés y
 * subtítulos en castellano salía como "No" — y es perfectamente subible,
 * porque eMuwarez acepta cualquiera de las dos.
 *
 * Lo delicado es el caso "no se sabe": con un lado confirmado que NO y el otro
 * sin leer todavía puede aparecer castellano por ese lado, así que decir "No"
 * sería afirmar algo que nadie ha comprobado.
 */
import { describe, it, expect } from 'vitest'
import { estadoCastellano, CASTELLANO_INFO, CASTELLANO_OPCIONES } from '../castellano'

const caso = (has_spanish_audio: number | null, has_spanish_subs: number | null) =>
  estadoCastellano({ has_spanish_audio, has_spanish_subs })

describe('el estado de castellano de un elemento', () => {
  it('en audio y en subtítulos, Ambos', () => {
    expect(caso(1, 1)).toBe('ambos')
  })

  it('solo en el audio, Audio', () => {
    expect(caso(1, 0)).toBe('audio')
  })

  // El caso que la columna se perdía entero.
  it('solo en los subtítulos, Subs', () => {
    expect(caso(0, 1)).toBe('subs')
  })

  it('en ninguno de los dos, No', () => {
    expect(caso(0, 0)).toBe('no')
  })

  // Los tres casos en que falta leer algo. El guion no es "no tiene": es un
  // Faltante que no está en disco, o un archivo del que no se saca nada.
  it.each<[number | null, number | null, string]>([
    [null, null, 'nada leído'],
    [0, null, 'el audio no, los subtítulos sin leer'],
    [null, 0, 'los subtítulos no, el audio sin leer'],
  ])('sin datos suficientes, desconocido (%s, %s: %s)', (a, s) => {
    expect(caso(a, s)).toBe('desconocido')
  })

  // Un lado confirmado basta para responder, aunque falte el otro: ya cumple.
  it('con un lado confirmado que SÍ, no hace falta el otro', () => {
    expect(caso(1, null)).toBe('audio')
    expect(caso(null, 1)).toBe('subs')
  })

  it('los 9 casos posibles tienen respuesta', () => {
    const valores = [1, 0, null]
    const salen = new Set(valores.flatMap(a => valores.map(s => caso(a, s))))
    expect(salen).toEqual(new Set(['ambos', 'audio', 'subs', 'no', 'desconocido']))
  })
})

describe('cómo se pintan', () => {
  it('Ambos en verde: es el único completo', () => {
    expect(CASTELLANO_INFO.ambos.cssClass).toBe('status-available')
  })

  // Los dos cumplen la condición de eMuwarez (basta una), pero ninguno está
  // completo: mismo ámbar que "Parcial" en el resto de la aplicación.
  it('Audio y Subs comparten el ámbar de Parcial', () => {
    expect(CASTELLANO_INFO.audio.cssClass).toBe('status-partial')
    expect(CASTELLANO_INFO.subs.cssClass).toBe(CASTELLANO_INFO.audio.cssClass)
  })

  it('No en rojo', () => {
    expect(CASTELLANO_INFO.no.cssClass).toBe('status-missing')
  })

  it('el desplegable ofrece los cinco, y "desconocido" como guion', () => {
    expect(CASTELLANO_OPCIONES.map(o => o.value))
      .toEqual(['ambos', 'audio', 'subs', 'no', 'desconocido'])
    expect(CASTELLANO_OPCIONES.find(o => o.value === 'desconocido')?.label).toBe('—')
  })

  it('cada estado con badge tiene su etiqueta en el desplegable', () => {
    for (const [estado, info] of Object.entries(CASTELLANO_INFO)) {
      expect(CASTELLANO_OPCIONES.find(o => o.value === estado)?.label).toBe(info.label)
    }
  })
})
