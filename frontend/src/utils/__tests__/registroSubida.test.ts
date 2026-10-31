/**
 * El registro de una subida en vivo: la primera petición trae el final y las siguientes solo lo posterior a la
 * última línea que se tiene. Si el cursor se pierde o se aplica mal, el registro se repite o se salta líneas sin
 * dar ningún error.
 */
import { describe, it, expect } from 'vitest'
import { aplicarLineas, ultimaSecuenciaDe } from '../registroSubida'
import type { UploadJobLog } from '../../types/api'

const linea = (sequence: number | null, message = `línea ${sequence}`) =>
  ({ upload_job_id: 1, level: 'info', message, stream: 'stdout', created_at: '2026-10-31T10:00:00Z', sequence } as UploadJobLog)

describe('el cursor es la secuencia de la última línea', () => {
  it('la de la última línea recibida', () => {
    expect(ultimaSecuenciaDe([linea(8), linea(9), linea(10)], 3)).toBe(10)
  })

  it('sin líneas nuevas se queda donde estaba', () => {
    expect(ultimaSecuenciaDe([], 7)).toBe(7)
  })

  it('las filas de antes de existir la secuencia no la mueven', () => {
    expect(ultimaSecuenciaDe([linea(null), linea(null)], 0)).toBe(0)
    expect(ultimaSecuenciaDe([linea(4), linea(null)], 0)).toBe(4)
  })
})

describe('aplicar lo que llega', () => {
  it('sin cursor lo que llega es el final del registro y reemplaza lo anterior', () => {
    const previas = [linea(1)]
    expect(aplicarLineas(previas, [linea(8), linea(9)], 0, 100).map(l => l.sequence)).toEqual([8, 9])
  })

  it('con cursor se añade detrás', () => {
    const r = aplicarLineas([linea(8), linea(9)], [linea(10), linea(11)], 9, 100)
    expect(r.map(l => l.sequence)).toEqual([8, 9, 10, 11])
  })

  it('con cursor y nada nuevo no cambia la lista (no hay que repintar)', () => {
    const previas = [linea(8), linea(9)]
    expect(aplicarLineas(previas, [], 9, 100)).toBe(previas)
  })

  it('solo se guardan las últimas «max» líneas', () => {
    const r = aplicarLineas([linea(1), linea(2), linea(3)], [linea(4), linea(5)], 3, 4)
    expect(r.map(l => l.sequence)).toEqual([2, 3, 4, 5])
  })
})
