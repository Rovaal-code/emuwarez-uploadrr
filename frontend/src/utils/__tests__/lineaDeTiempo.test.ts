import { describe, expect, it } from 'vitest'
import type { UploadJob, UploadProgressPhase } from '../../types/api'
import { NOMBRE_CORTO_FASE, lineaDeTiempo, segundosDeFase } from '../lineaDeTiempo'

const T0 = Date.parse('2026-11-02T10:00:00+00:00')
const hora = (s: number) => new Date(T0 + s * 1000).toISOString()
const fase = (key: string, ini: number | null, fin: number | null, status: UploadProgressPhase['status'] = 'done'): UploadProgressPhase =>
  ({ key, label: key, status, pct: 100, started_at: ini == null ? null : hora(ini), finished_at: fin == null ? null : hora(fin) })
const subida = (parcial: Partial<UploadJob>): UploadJob => ({ id: 1, status: 'completed', ...parcial }) as UploadJob

describe('segundosDeFase', () => {
  it('sin hora de inicio no hay duración', () => {
    expect(segundosDeFase(null, hora(5))).toBeNull()
  })
  it('sin fin propio usa el de respaldo', () => {
    expect(segundosDeFase(hora(0), null, hora(42))).toBe(42)
  })
})

describe('lineaDeTiempo', () => {
  it('da la duración de cada fase y las barras son proporcionales al total', () => {
    const l = lineaDeTiempo(subida({
      duration_seconds: 400,
      progress: { global_pct: 100, phases: [fase('nomenclature', 0, 100), fase('screenshots', 100, 400)] },
    }))
    expect(l.totalSegundos).toBe(400)
    expect(l.tramos.map(t => [t.nombre, t.segundos])).toEqual([['Nomenclatura', 100], ['Capturas', 300]])
    expect(l.tramos.map(t => t.fraccion)).toEqual([0.25, 0.75])
  })

  it('una fase de pistas omitida dice «omitida» y no cuenta tiempo, aunque tenga marcas', () => {
    const l = lineaDeTiempo(subida({
      remux_snapshot: { omitida: 'Ninguno' },
      progress: { global_pct: 100, phases: [fase('remux', 5, 5), fase('hash_torrent', 5, 15)] },
    }))
    expect(l.tramos[0]).toMatchObject({ nombre: 'Pistas', segundos: null, estado: 'omitida', fraccion: 0 })
    expect(l.tramos[1].segundos).toBe(10)
  })

  it('una fase sin marcas de tiempo enseña solo su estado, sin inventar duración', () => {
    const l = lineaDeTiempo(subida({
      duration_seconds: 60,
      progress: { global_pct: 100, phases: [fase('screenshots', null, null, 'done'), fase('uploading_emu', null, null, 'pending')] },
    }))
    expect(l.tramos.map(t => [t.segundos, t.estado])).toEqual([[null, 'completada'], [null, 'pendiente']])
  })

  it('una fase que quedó en curso acaba cuando acabó la subida', () => {
    const l = lineaDeTiempo(subida({
      status: 'failed', finished_at: hora(90), duration_seconds: 90,
      progress: { global_pct: 40, phases: [fase('hash_torrent', 30, null, 'running')] },
    }))
    expect(l.tramos[0].segundos).toBe(60)
  })

  it('si las fases suman más que el total (se solapan) ninguna barra pasa del eje', () => {
    const l = lineaDeTiempo(subida({
      duration_seconds: 100,
      progress: { global_pct: 100, phases: [fase('screenshots', 0, 100), fase('hash_torrent', 0, 100)] },
    }))
    expect(l.tramos.every(t => t.fraccion <= 0.5)).toBe(true)
  })

  it('sin duración guardada el total sale de las marcas de la subida, y sin ellas de la suma', () => {
    expect(lineaDeTiempo(subida({ started_at: hora(0), finished_at: hora(70) })).totalSegundos).toBe(70)
    expect(lineaDeTiempo(subida({ progress: { global_pct: 100, phases: [fase('screenshots', 0, 25)] } })).totalSegundos).toBe(25)
    expect(lineaDeTiempo(subida({})).totalSegundos).toBeNull()
  })

  it('una fase que el servidor no conoce usa su etiqueta', () => {
    expect(NOMBRE_CORTO_FASE.raro).toBeUndefined()
    expect(lineaDeTiempo(subida({ progress: { global_pct: 0, phases: [{ ...fase('raro', 0, 1), label: 'Rara' }] } })).tramos[0].nombre).toBe('Rara')
  })
})
