import { describe, expect, it } from 'vitest'
import type { SeedingResponse } from '../../api/seeding'
import type { UploadJob } from '../../types/api'
import { estadoVisible } from '../estadoDeSubida'

const subida = (parcial: Partial<UploadJob>): UploadJob => ({ id: 7, status: 'completed', ...parcial }) as UploadJob
const seeding = (estado: string, etiqueta: string): SeedingResponse => ({
  configurado: true, disponible: true, mensaje: null, actualizado: null, items: [{ job_id: 7, estado, etiqueta }],
})
const pasos = (estado: string) => [
  { clave: 'nomenclatura', nombre: 'Comprobar y poner el nombre', estado: 'hecho' },
  { clave: 'subida', nombre: 'Subir con Uploadrr', estado },
]

describe('estadoVisible', () => {
  it('una subida completada con ficha dice que está en eMuwarez y, si hay datos, cómo siembra', () => {
    const e = estadoVisible(subida({ result_url: 'https://emu/t/1' }), seeding('sembrando', 'Sembrando'))
    expect(e).toMatchObject({ tono: 'ok', simbolo: '✓', titulo: 'Subido a eMuwarez' })
    expect(e.seeding?.texto).toBe('Sembrando en qBittorrent')
    expect(e.seeding?.clase).toContain('status-available')
  })

  it('sin datos de qBittorrent no inventa el seeding', () => {
    expect(estadoVisible(subida({ result_url: 'https://emu/t/1' }), null).seeding).toBeUndefined()
  })

  it('un seeding con problemas sale con su color pero la subida sigue completada', () => {
    const e = estadoVisible(subida({ result_url: 'x' }), seeding('faltan_ficheros', 'Faltan ficheros'))
    expect(e.tono).toBe('ok')
    expect(e.seeding?.clase).toContain('status-error')
  })

  it('completada pero sin entrar en qBittorrent es un aviso con motivo', () => {
    const e = estadoVisible(subida({
      result_url: 'x',
      progress: { global_pct: 100, phases: [{ key: 'qbittorrent_add', label: 'q', status: 'failed', pct: 0 }] },
    }), null)
    expect(e.tono).toBe('aviso')
    expect(e.motivo).toContain('qBittorrent')
  })

  it('una fallida dice en qué paso falló y por qué', () => {
    const e = estadoVisible(subida({ status: 'failed', error_message: 'Sin espacio en disco', pasos: pasos('fallido') }), null)
    expect(e).toMatchObject({ tono: 'error', titulo: 'Falló en «Subir con Uploadrr»', motivo: 'Sin espacio en disco' })
  })

  it('una fallida sin paso conocido sigue diciendo que falló', () => {
    expect(estadoVisible(subida({ status: 'failed' }), null).titulo).toBe('La subida falló')
  })

  it('una cancelada es neutra y dice dónde se paró', () => {
    const e = estadoVisible(subida({ status: 'cancelled', pasos: pasos('cancelado') }), null)
    expect(e).toMatchObject({ tono: 'neutro', titulo: 'Cancelada en «Subir con Uploadrr»' })
  })

  it('en cola dice su puesto', () => {
    expect(estadoVisible(subida({ status: 'queued', queue_position: 2, queue_total: 3 }), null))
      .toMatchObject({ tono: 'curso', titulo: 'En cola', resumen: 'Puesto 2 de 3' })
  })

  it('en marcha dice la fase', () => {
    const e = estadoVisible(subida({
      status: 'running',
      progress: { global_pct: 50, phases: [{ key: 'hash_torrent', label: 'Cálculo de hash', status: 'running', pct: 40 }] },
    }), null)
    expect(e.titulo).toBe('Subiendo')
    expect(e.resumen).toContain('Calculando hash del torrent (1/1)')
  })
})
