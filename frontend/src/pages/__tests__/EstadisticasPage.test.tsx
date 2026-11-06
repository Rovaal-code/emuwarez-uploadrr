// @vitest-environment jsdom
/**
 * Estadísticas con el servidor simulado: lo que pide al entrar y al cambiar de rango, y lo que enseña con datos,
 * sin datos, con un solo día y cuando falla.
 */
import { act, useState } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../../api/estadisticas', () => ({ getEstadisticasCuenta: vi.fn() }))
vi.mock('../../api/dashboard', () => ({ getDashboardSummary: vi.fn() }))

import { getDashboardSummary } from '../../api/dashboard'
import { getEstadisticasCuenta } from '../../api/estadisticas'
import { SeccionVisible } from '../../context/SeccionVisible'
import { SyncContext } from '../../context/SyncContext'
import type { DashboardSummaryResponse, PuntoCuenta } from '../../types/api'
import { boton, desmontar, esperar, montar, pulsar, texto } from '../../components/__tests__/dom'
import { EstadisticasPage } from '../EstadisticasPage'

const pedir = vi.mocked(getEstadisticasCuenta)
const pedirResumen = vi.mocked(getDashboardSummary)

const resumen = (extra: Partial<DashboardSummaryResponse> = {}): DashboardSummaryResponse => ({
  library_total: 51372, available: 15861, missing: 57, uploading: 0, completed: 0, unique_content: 283,
  unique_movies: 141, unique_seasons: 142, unique_episodes: 900, uploads_completed: 14, radarr_items: 220,
  sonarr_items: 51152, last_sync_at: null, next_sync_at: null, requests_total: 322, requests_compatible: 15,
  requests_partial: 2, requests_reclaimed: 4, requests_mine: 1, ...extra,
})

const punto = (dia: string, extra: Partial<PuntoCuenta> = {}): PuntoCuenta => ({
  dia, ratio: 4.1, subido_bytes: 1024 ** 4, bajado_bytes: 300 * 1024 ** 3, bonus: 12345.5, ...extra,
})

beforeEach(() => {
  pedir.mockReset()
  pedirResumen.mockReset()
  pedirResumen.mockResolvedValue(resumen())
})
afterEach(desmontar)

describe('EstadisticasPage', () => {
  it('con datos pinta los tres gráficos accesibles y la tabla con cifras es-ES', async () => {
    pedir.mockResolvedValue({ dias: 90, puntos: [punto('2026-10-01'), punto('2026-10-02', { ratio: 4.25 })] })
    await montar(<EstadisticasPage />)
    await esperar(() => document.querySelector('svg[role="img"]'))

    expect(pedir).toHaveBeenCalledWith(90)
    const graficos = [...document.querySelectorAll('svg[role="img"]')]
    expect(graficos).toHaveLength(3)
    // «Subido y bajado» va primero (ocupa toda la fila), luego Ratio y Bonus.
    expect(graficos[0].getAttribute('aria-label')).toContain('Subido: de 1,0 TB')
    expect(graficos[1].getAttribute('aria-label')).toContain('Ratio: de 4,10 el 01/10/2026 a 4,25 el 02/10/2026')
    expect(graficos.every(g => g.querySelector('title'))).toBe(true)

    const filas = [...document.querySelectorAll('details table tbody tr')]
    expect(filas).toHaveLength(2)
    expect(filas[0].textContent).toContain('02/10/2026')   // la más reciente primero
    expect(filas[0].textContent).toContain('4,25')
    expect(filas[0].textContent).toContain('12.346')       // miles con punto
    expect(document.querySelectorAll('.est-leyenda li')).toHaveLength(2)
  })

  it('cada gráfico lee su último valor y lo que cambió; con las flechas se lee el de cada día y Escape lo suelta', async () => {
    pedir.mockResolvedValue({ dias: 90, puntos: [punto('2026-10-01'), punto('2026-10-02', { ratio: 4.25 }), punto('2026-10-03', { ratio: 5.1 })] })
    await montar(<EstadisticasPage />)
    await esperar(() => document.querySelector('.est-plot'))
    const ratioFig = [...document.querySelectorAll('figure.est-grafico')].find(f => f.textContent?.startsWith('Ratio'))!
    expect(ratioFig.querySelector('.est-lectura-valor')!.textContent).toBe('5,10')
    expect(ratioFig.querySelector('.est-lectura-delta')!.textContent).toBe('+1,00 (+24,4 %)')
    expect(ratioFig.querySelector('.est-grafico-fecha')!.textContent).toBe('Último dato: 03/10/2026')

    const plot = ratioFig.querySelector('.est-plot')!
    const tecla = async (key: string) => { await act(async () => { plot.dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true })) }) }
    await tecla('ArrowLeft')
    expect(ratioFig.querySelector('.est-lectura-valor')!.textContent).toBe('4,25')
    expect(ratioFig.querySelector('.est-grafico-fecha')!.textContent).toBe('02/10/2026')
    expect(ratioFig.querySelector('[aria-live]')!.textContent).toBe('02/10/2026: Ratio 4,25.')
    expect(ratioFig.querySelectorAll('.est-punto-activo')).toHaveLength(1)
    await tecla('Home')
    expect(ratioFig.querySelector('.est-lectura-valor')!.textContent).toBe('4,10')
    await tecla('Escape')
    expect(ratioFig.querySelector('.est-lectura-valor')!.textContent).toBe('5,10')
    expect(ratioFig.querySelector('.est-guia')).toBeNull()
  })

  it('un día sin cifra de una serie lo dice al recorrerlo', async () => {
    pedir.mockResolvedValue({ dias: 90, puntos: [punto('2026-10-01'), punto('2026-10-02', { bajado_bytes: null }), punto('2026-10-03')] })
    await montar(<EstadisticasPage />)
    await esperar(() => document.querySelector('.est-plot'))
    const plot = document.querySelector('.est-plot')!
    await act(async () => { plot.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowLeft', bubbles: true })) })
    expect(plot.querySelector('[aria-live]')!.textContent).toBe('02/10/2026: Subido 1,0 TB, Bajado sin dato.')
  })

  it('arriba lleva las diez tarjetas que tenía el Panel, con las mismas cifras y los nombres de la franja', async () => {
    pedir.mockResolvedValue({ dias: 90, puntos: [punto('2026-10-01')] })
    await montar(<EstadisticasPage />)
    await esperar(() => document.querySelector('.stat-card'))

    const tarjetas = new Map([...document.querySelectorAll('.stat-card')].map(t => [
      t.querySelector('.stat-card-label')!.textContent, t.querySelector('.stat-card-value')!.textContent]))
    expect(tarjetas.size).toBe(10)
    expect(tarjetas.get('En biblioteca')).toBe('51.372')
    expect(tarjetas.get('En disco')).toBe('15.861')
    expect(tarjetas.get('Faltantes')).toBe('57')
    expect(tarjetas.get('Únicos sin subir')).toBe('283')
    expect(tarjetas.get('Tus subidas')).toBe('14')
    expect(tarjetas.get('Peticiones abiertas')).toBe('322')
    expect(tarjetas.get('Peticiones compatibles')).toBe('15')
    expect(tarjetas.get('Peticiones parciales')).toBe('2')
    expect(tarjetas.get('Peticiones reclamadas')).toBe('4')
    expect(tarjetas.get('Mis peticiones')).toBe('1')
    expect(texto()).toContain('141 películas')
  })

  it('las tarjetas salen aunque aún no haya ninguna instantánea de la cuenta', async () => {
    pedir.mockResolvedValue({ dias: 90, puntos: [] })
    await montar(<EstadisticasPage />)
    await esperar(() => texto().includes('Todavía no hay datos'))
    expect(document.querySelectorAll('.stat-card')).toHaveLength(10)
  })

  it('si fallan las cifras, la evolución de la cuenta sale igual', async () => {
    pedirResumen.mockRejectedValue(new Error('503'))
    pedir.mockResolvedValue({ dias: 90, puntos: [punto('2026-10-01')] })
    await montar(<EstadisticasPage />)
    await esperar(() => document.querySelector('svg[role="img"]'))
    expect(document.querySelectorAll('.stat-card')).toHaveLength(0)
  })

  it('un día sin cifra sale como raya en la tabla y no rompe la línea del resto', async () => {
    pedir.mockResolvedValue({ dias: 90, puntos: [punto('2026-10-01'), punto('2026-10-02', { ratio: null }), punto('2026-10-03')] })
    await montar(<EstadisticasPage />)
    await esperar(() => document.querySelector('svg[role="img"]'))
    expect(document.querySelectorAll('details table tbody tr')[1].textContent).toContain('—')
  })

  it('cambiar de rango vuelve a pedir con ese número de días', async () => {
    pedir.mockResolvedValue({ dias: 30, puntos: [punto('2026-10-01')] })
    await montar(<EstadisticasPage />)
    await esperar(() => document.querySelector('svg[role="img"]'))

    await pulsar(boton('365 días'))
    await esperar(() => pedir.mock.calls.length === 2)
    expect(pedir).toHaveBeenLastCalledWith(365)
    expect(boton('365 días')!.getAttribute('aria-pressed')).toBe('true')
    expect(boton('90 días')!.getAttribute('aria-pressed')).toBe('false')
  })

  it('con un solo día avisa de que la línea llega mañana', async () => {
    pedir.mockResolvedValue({ dias: 90, puntos: [punto('2026-10-01')] })
    await montar(<EstadisticasPage />)
    await esperar(() => document.querySelector('svg[role="img"]'))
    expect(texto()).toContain('Solo hay un día guardado')
    expect(document.querySelectorAll('circle').length).toBeGreaterThan(0)
  })

  it('una serie sin ningún valor dice que no hay datos en vez de dibujar un eje vacío', async () => {
    pedir.mockResolvedValue({ dias: 90, puntos: [punto('2026-10-01', { bonus: null }), punto('2026-10-02', { bonus: null })] })
    await montar(<EstadisticasPage />)
    await esperar(() => document.querySelector('svg[role="img"]'))
    expect(document.querySelectorAll('svg[role="img"]')).toHaveLength(2)
    expect(texto()).toContain('Sin datos de esto en este rango')
  })

  it('sin ninguna instantánea dice que se empieza a guardar hoy', async () => {
    pedir.mockResolvedValue({ dias: 90, puntos: [] })
    await montar(<EstadisticasPage />)
    await esperar(() => texto().includes('Todavía no hay datos'))
    expect(texto()).toContain('Se empieza a guardar hoy')
    expect(document.querySelector('svg[role="img"]')).toBeNull()
  })

  it('mientras carga enseña el cargando', async () => {
    pedir.mockReturnValue(new Promise(() => {}))
    await montar(<EstadisticasPage />)
    expect(texto()).toContain('Cargando estadísticas')
  })

  it('si falla enseña el error y Reintentar vuelve a pedir', async () => {
    pedir.mockRejectedValueOnce(new Error('503'))
    await montar(<EstadisticasPage />)
    await esperar(() => texto().includes('No se pudo cargar'))

    pedir.mockResolvedValue({ dias: 90, puntos: [punto('2026-10-01')] })
    await pulsar(boton('Reintentar'))
    await esperar(() => document.querySelector('svg[role="img"]'))
    expect(pedir).toHaveBeenCalledTimes(2)
  })

  it('oculta no pide nada, y al pasar a verse pide una vez', async () => {
    pedir.mockResolvedValue({ dias: 90, puntos: [] })
    function Seccion() {
      const [visible, setVisible] = useState(false)
      return (
        <SyncContext.Provider value={{ lastInvalidatedAt: 0 } as never}>
          <button onClick={() => setVisible(v => !v)}>ver</button>
          <SeccionVisible visible={visible}><EstadisticasPage /></SeccionVisible>
        </SyncContext.Provider>
      )
    }
    await montar(<Seccion />)
    expect(pedir).not.toHaveBeenCalled()
    expect(pedirResumen).not.toHaveBeenCalled()

    await pulsar(boton('ver'))
    await esperar(() => pedir.mock.calls.length === 1)
    await pulsar(boton('ver'))   // se oculta: no repide
    expect(pedir).toHaveBeenCalledTimes(1)
    expect(pedirResumen).toHaveBeenCalledTimes(1)
  })
})
