import { describe, expect, it } from 'vitest'
import type { LogEntry } from '../../api/logs'
import {
  clavesDeLineas, diaDeLinea, horaDeLinea, mismasLineas, reutilizarLineas, textoDeLinea, trocearPorBusqueda,
} from '../logs'

function linea(extra: Partial<LogEntry> = {}): LogEntry {
  return { ts: 1, time: '2026-11-06 07:29:32', level: 'INFO', logger: 'emuwarez.request', message: 'GET /x → 200', ...extra }
}

describe('Logs: claves de línea', () => {
  it('una línea conserva su clave aunque entren otras por delante', () => {
    const a = linea({ ts: 1 })
    const b = linea({ ts: 2, message: 'otra' })
    const antes = clavesDeLineas([a])
    const despues = clavesDeLineas([b, a])
    expect(despues[1]).toBe(antes[0])
  })

  it('dos mensajes distintos de la misma longitud y el mismo segundo tienen claves distintas, y entrar líneas por delante no las cambia', () => {
    const a = linea({ message: 'aaaa' })
    const b = linea({ message: 'bbbb' })
    const [ka, kb] = clavesDeLineas([a, b])
    expect(ka).not.toBe(kb)
    const [nueva, ka2, kb2] = clavesDeLineas([linea({ ts: 2 }), a, b])
    expect(nueva).not.toBe(ka2)
    expect([ka2, kb2]).toEqual([ka, kb])
  })

  it('dos líneas idénticas no comparten clave', () => {
    const claves = clavesDeLineas([linea(), linea(), linea()])
    expect(new Set(claves).size).toBe(3)
  })
})

describe('Logs: lecturas iguales', () => {
  it('dos lecturas con las mismas líneas se reconocen y una línea nueva o un cambio de nivel no', () => {
    const a = [linea({ ts: 3 }), linea({ ts: 2 }), linea({ ts: 1 })]
    expect(mismasLineas(a, [...a])).toBe(true)
    expect(mismasLineas(a, [linea({ ts: 4 }), ...a])).toBe(false)
    expect(mismasLineas(a, [a[0], a[1], linea({ ts: 1, level: 'ERROR' })])).toBe(false)
    expect(mismasLineas([], [])).toBe(true)
  })

  it('un cambio en cualquier posición, incluidos el origen y la hora, cuenta como lectura distinta', () => {
    const a = Array.from({ length: 10 }, (_, i) => linea({ ts: 100 - i, message: `m${i}` }))
    for (const cambio of [{ logger: 'otro' }, { time: '2026-11-06 07:29:33' }, { message: 'distinto' }]) {
      const b = a.map((l, i) => (i === 5 ? { ...l, ...cambio } : l))
      expect(mismasLineas(a, b)).toBe(false)
    }
  })
})

describe('Logs: reutilizar las líneas de la lectura anterior', () => {
  it('con una línea nueva arriba, las que ya estaban conservan su objeto (memo solo pinta la nueva)', () => {
    const previas = [linea({ ts: 2, message: 'b' }), linea({ ts: 1, message: 'a' })]
    // El servidor las manda todas otra vez, parseadas de nuevo: mismos datos, objetos distintos.
    const nuevas = [linea({ ts: 3, message: 'c' }), linea({ ts: 2, message: 'b' }), linea({ ts: 1, message: 'a' })]
    const r = reutilizarLineas(previas, nuevas)
    expect(r).toHaveLength(3)
    expect(r[0]).toBe(nuevas[0])
    expect(r[1]).toBe(previas[0])
    expect(r[2]).toBe(previas[1])
  })

  it('sin nada nuevo devuelve la lectura anterior entera', () => {
    const previas = [linea({ ts: 1 })]
    expect(reutilizarLineas(previas, [linea({ ts: 1 })])).toBe(previas)
  })

  it('las repetidas (misma hora y mensaje) se reutilizan una a una, sin mezclar', () => {
    const previas = [linea({ ts: 1, message: 'x' }), linea({ ts: 1, message: 'x' })]
    const nuevas = [linea({ ts: 2, message: 'y' }), linea({ ts: 1, message: 'x' }), linea({ ts: 1, message: 'x' })]
    const r = reutilizarLineas(previas, nuevas)
    expect(r[1]).toBe(previas[0])
    expect(r[2]).toBe(previas[1])
  })
})

describe('Logs: texto, día y hora', () => {
  it('la línea copiada lleva hora, nivel, origen y mensaje', () => {
    expect(textoDeLinea(linea())).toBe('2026-11-06 07:29:32 INFO emuwarez.request GET /x → 200')
  })
  it('separa el día de la hora, y lo que no tiene ese formato se deja como está', () => {
    expect(diaDeLinea(linea())).toBe('2026-11-06')
    expect(horaDeLinea(linea())).toBe('07:29:32')
    expect(diaDeLinea(linea({ time: 'ayer' }))).toBeNull()
    expect(horaDeLinea(linea({ time: 'ayer' }))).toBe('ayer')
  })
})

describe('Logs: resaltar la búsqueda', () => {
  it('parte el texto en trozos sin distinguir mayúsculas y conserva el original', () => {
    expect(trocearPorBusqueda('Error al subir ERROR', 'error')).toEqual([
      { texto: 'Error', coincide: true },
      { texto: ' al subir ', coincide: false },
      { texto: 'ERROR', coincide: true },
    ])
  })
  it('sin búsqueda, o sin coincidencias, devuelve el texto entero', () => {
    expect(trocearPorBusqueda('hola', '  ')).toEqual([{ texto: 'hola', coincide: false }])
    expect(trocearPorBusqueda('hola', 'adiós')).toEqual([{ texto: 'hola', coincide: false }])
  })
  it('lo que se busca no se interpreta como una expresión regular', () => {
    expect(trocearPorBusqueda('a.b a+b', 'a+b')).toEqual([
      { texto: 'a.b ', coincide: false },
      { texto: 'a+b', coincide: true },
    ])
  })
})
