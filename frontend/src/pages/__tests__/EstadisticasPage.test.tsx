// @vitest-environment jsdom
/**
 * Estadísticas con el servidor simulado: lo que pide al entrar y al cambiar de rango, y lo que enseña con datos,
 * sin datos, con un solo día y cuando falla.
 */
import { useState } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../../api/estadisticas', () => ({ getEstadisticasCuenta: vi.fn() }))

import { getEstadisticasCuenta } from '../../api/estadisticas'
import { SeccionVisible } from '../../context/SeccionVisible'
import { SyncContext } from '../../context/SyncContext'
import type { PuntoCuenta } from '../../types/api'
import { boton, desmontar, esperar, montar, pulsar, texto } from '../../components/__tests__/dom'
import { EstadisticasPage } from '../EstadisticasPage'

const pedir = vi.mocked(getEstadisticasCuenta)

const punto = (dia: string, extra: Partial<PuntoCuenta> = {}): PuntoCuenta => ({
  dia, ratio: 4.1, subido_bytes: 1024 ** 4, bajado_bytes: 300 * 1024 ** 3, bonus: 12345.5, hit_and_runs: 0, ...extra,
})

beforeEach(() => { pedir.mockReset() })
afterEach(desmontar)

describe('EstadisticasPage', () => {
  it('con datos pinta los cuatro gráficos accesibles y la tabla con cifras es-ES', async () => {
    pedir.mockResolvedValue({ dias: 90, puntos: [punto('2026-10-01'), punto('2026-10-02', { ratio: 4.25, hit_and_runs: 1 })] })
    await montar(<EstadisticasPage />)
    await esperar(() => document.querySelector('svg[role="img"]'))

    expect(pedir).toHaveBeenCalledWith(90)
    const graficos = [...document.querySelectorAll('svg[role="img"]')]
    expect(graficos).toHaveLength(4)
    expect(graficos[0].getAttribute('aria-label')).toContain('Ratio: de 4,10 el 01/10/2026 a 4,25 el 02/10/2026')
    expect(graficos[1].getAttribute('aria-label')).toContain('Subido: de 1,0 TB')
    expect(graficos.every(g => g.querySelector('title'))).toBe(true)

    const filas = [...document.querySelectorAll('details table tbody tr')]
    expect(filas).toHaveLength(2)
    expect(filas[0].textContent).toContain('02/10/2026')   // la más reciente primero
    expect(filas[0].textContent).toContain('4,25')
    expect(filas[0].textContent).toContain('12.346')       // miles con punto
    expect(document.querySelectorAll('.est-leyenda li')).toHaveLength(2)
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
    expect(document.querySelectorAll('svg[role="img"]')).toHaveLength(3)
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

    await pulsar(boton('ver'))
    await esperar(() => pedir.mock.calls.length === 1)
    await pulsar(boton('ver'))   // se oculta: no repide
    expect(pedir).toHaveBeenCalledTimes(1)
  })
})
