// @vitest-environment jsdom
// La línea de medidores al pie de la barra lateral: formatos, valores ausentes y lo que lee un lector de pantalla.
import { act } from 'react'
import { afterEach, describe, expect, it } from 'vitest'

import type { SystemStats } from '../../api/system'
import { ResumenSistema } from '../SystemStatusPanel'
import { desmontar, montar } from './dom'

// El tooltip mide el texto con un Range, que jsdom no sabe medir.
Range.prototype.getClientRects = () => [] as unknown as DOMRectList

const stats = (parcial: Partial<SystemStats> = {}): SystemStats => ({
  cpu_percent: 0, cpu_name: 'AMD Ryzen 5 5600G', ram_percent: 1.4, ram_used_gb: 0.5, ram_total_gb: 32,
  disk_path: '/data/uploads', disk_used_gb: 60, disk_total_gb: 1000, disk_percent: 6,
  net_down_bps: 0, net_up_bps: 0, gpu: null, ...parcial,
})

const medidas = () => [...document.querySelectorAll('.sys-med')]
const resumen = () => medidas().map(m => m.textContent?.replace(/\s+/g, ' ').trim())
// El detalle sale en el tooltip, que con el teclado se abre al enfocar.
async function detalle(el: Element) {
  await act(async () => { (el as HTMLElement).focus() })
  return document.querySelector('[role="tooltip"]')?.textContent
}

afterEach(desmontar)

describe('ResumenSistema', () => {
  it('pone CPU, RAM y Disco en una sola lista, con el porcentaje redondeado', async () => {
    await montar(<ResumenSistema stats={stats({ cpu_percent: 12.6 })} />)
    expect(document.querySelectorAll('ul')).toHaveLength(1)
    expect(resumen()).toEqual(['CPU 13%', 'RAM 1%', 'Disco 6%'])
  })

  it('acota a 0-100 lo que se sale de rango', async () => {
    await montar(<ResumenSistema stats={stats({ cpu_percent: 140, ram_percent: -3 })} />)
    expect(resumen()).toEqual(['CPU 100%', 'RAM 0%', 'Disco 6%'])
  })

  it('un valor ausente o no finito sale como un guion, no como 0 %', async () => {
    await montar(<ResumenSistema stats={stats({ cpu_percent: NaN, ram_percent: undefined as unknown as number })} />)
    expect(resumen()).toEqual(['CPU —', 'RAM —', 'Disco 6%'])
    expect(medidas()[0].getAttribute('aria-label')).toBe('CPU sin datos')
  })

  it('con el disco sin medir (total 0) sale un guion y el tooltip lo explica', async () => {
    await montar(<ResumenSistema stats={stats({ disk_total_gb: 0, disk_used_gb: 0, disk_percent: 0 })} />)
    const disco = medidas()[2]
    expect(disco.textContent).toContain('—')
    expect(await detalle(disco)).toBe('No se pudo medir el disco')
  })

  it('el aria-label lleva nombre y valor, y la descripción el detalle', async () => {
    await montar(<ResumenSistema stats={stats()} />)
    const [cpu, ram, disco] = medidas()
    expect(document.querySelector('ul')?.getAttribute('aria-label')).toBe('Uso de recursos')
    expect(cpu.getAttribute('aria-label')).toBe('CPU 0%')
    expect(await detalle(cpu)).toBe('AMD Ryzen 5 5600G')
    expect(ram.getAttribute('aria-label')).toBe('RAM 1%')
    expect(await detalle(ram)).toBe('512,0 MB / 32,0 GB')
    expect(disco.getAttribute('aria-label')).toBe('Disco 6%')
    expect(await detalle(disco)).toContain('60,0 GB / 1000,0 GB')
    expect(await detalle(disco)).toContain('/data/uploads')
  })

  it('todas se alcanzan con el teclado', async () => {
    await montar(<ResumenSistema stats={stats()} />)
    expect(medidas().every(m => m.getAttribute('tabindex') === '0')).toBe(true)
  })

  it('la GPU y la VRAM solo salen si hay GPU', async () => {
    await montar(<ResumenSistema stats={stats({ gpu: { name: 'RTX 3060', percent: 7, vram_used_gb: 1, vram_total_gb: 12, vram_percent: 8.3 } })} />)
    expect(resumen()).toEqual(['CPU 0%', 'RAM 1%', 'Disco 6%', 'GPU 7%', 'VRAM 8%'])
    expect(await detalle(medidas()[3])).toBe('RTX 3060')
  })

  it('colapsada lleva la clase que apila las medidas', async () => {
    await montar(<ResumenSistema stats={stats()} collapsed />)
    expect(document.querySelector('.sys-status')?.classList.contains('collapsed')).toBe(true)
  })

  it('sigue habiendo velocidad de red debajo', async () => {
    await montar(<ResumenSistema stats={stats({ net_down_bps: 2048, net_up_bps: 1024 })} />)
    expect(document.querySelector('.sys-net-row')?.textContent).toContain('2,0 KB/s')
    expect(document.querySelector('.sys-net-row')?.textContent).toContain('1,0 KB/s')
  })
})
