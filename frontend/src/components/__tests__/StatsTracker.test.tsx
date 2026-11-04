// @vitest-environment jsdom
/**
 * El bloque «En eMuwarez» del detalle de una subida: contadores del tracker, sin datos y «Actualizar».
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../../api/trackerStats', () => ({ getTrackerStats: vi.fn() }))

import { getTrackerStats, type TrackerStats } from '../../api/trackerStats'
import type { UploadJob } from '../../types/api'
import { StatsTrackerBloque } from '../StatsTracker'
import { boton, desmontar, esperar, montar, pulsar, texto } from './dom'

const m = vi.mocked(getTrackerStats)
const subida = (parcial: Partial<UploadJob> = {}): UploadJob =>
  ({ id: 7, status: 'completed', result_tracker: 'https://emu-warez.com/torrents/321', ...parcial }) as UploadJob
const stats = (parcial: Partial<TrackerStats> = {}): TrackerStats => ({
  aplica: true, configurado: true, disponible: true, mensaje: null, actualizado: '2026-11-04T10:00:00+00:00',
  seeders: 7, leechers: 2, completadas: 15000, freeleech: null, doble_subida: false, ...parcial,
})

beforeEach(() => { m.mockReset() })
afterEach(desmontar)

describe('StatsTrackerBloque', () => {
  it('enseña seeders, leechers y veces completado con cifras es-ES', async () => {
    m.mockResolvedValue(stats())
    await montar(<StatsTrackerBloque job={subida()} />)
    await esperar(() => texto().includes('Seeders'))
    const t = document.querySelector('[data-testid="stats-tracker"]')!.textContent!
    expect(t).toContain('7')
    expect(t).toContain('15.000 veces')
    expect(t).toContain('Leído')
    expect(t).not.toContain('Freeleech')
  })

  it('dice freeleech y doble subida solo si los tiene', async () => {
    m.mockResolvedValue(stats({ freeleech: '50%', doble_subida: true, completadas: 1 }))
    await montar(<StatsTrackerBloque job={subida()} />)
    await esperar(() => texto().includes('Freeleech'))
    expect(texto()).toContain('50%')
    expect(texto()).toContain('Doble')
    expect(texto()).toContain('1 vez')
  })

  it('sin ficha o sin completar no pide nada ni pinta el bloque', async () => {
    await montar(<StatsTrackerBloque job={subida({ result_tracker: null })} />)
    await montar(<StatsTrackerBloque job={subida({ status: 'failed' })} />)
    expect(m).not.toHaveBeenCalled()
    expect(document.querySelector('[data-testid="stats-tracker"]')).toBeNull()
  })

  it('si eMuwarez no responde dice por qué y no rompe', async () => {
    m.mockResolvedValue(stats({ disponible: false, mensaje: 'eMuwarez no responde', seeders: undefined }))
    await montar(<StatsTrackerBloque job={subida()} />)
    await esperar(() => texto().includes('Sin datos de eMuwarez'))
    expect(texto()).toContain('eMuwarez no responde')
  })

  it('un fallo de red deja el mensaje genérico, y «Actualizar» se salta la caché', async () => {
    m.mockRejectedValueOnce(new Error('red'))
    await montar(<StatsTrackerBloque job={subida()} />)
    await esperar(() => texto().includes('No se pudo consultar'))
    m.mockResolvedValue(stats())
    await pulsar(boton('Actualizar'))
    await esperar(() => texto().includes('Seeders'))
    expect(m).toHaveBeenLastCalledWith(7, true)
  })
})
