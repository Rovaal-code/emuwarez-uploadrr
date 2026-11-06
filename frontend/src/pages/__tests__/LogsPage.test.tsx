// @vitest-environment jsdom
// Logs: copiar una línea lo confirma, y el teclado entra a la lista por una sola línea y se mueve con las flechas.
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { LogEntry } from '../../api/logs'

vi.mock('../../api/logs', () => ({ getLogs: vi.fn() }))
// Sin la sección a la vista no corre el refresco de cada 3 segundos.
vi.mock('../../context/SeccionVisible', () => ({ useSeccionVisible: () => false }))

import { getLogs } from '../../api/logs'
import { LogsPage } from '../LogsPage'

;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

const LINEAS: LogEntry[] = [
  { ts: 3, time: '2026-11-06 11:00:03', level: 'ERROR', logger: 'app', message: 'tercera' },
  { ts: 2, time: '2026-11-06 11:00:02', level: 'INFO', logger: 'app', message: 'segunda' },
  { ts: 1, time: '2026-11-06 11:00:01', level: 'INFO', logger: 'app', message: 'primera' },
]

let raiz: Root
let contenedor: HTMLDivElement
const escribirPortapapeles = vi.fn()

async function esperar() {
  await act(async () => { await new Promise(r => setTimeout(r, 0)) })
}

async function montar() {
  contenedor = document.createElement('div')
  document.body.appendChild(contenedor)
  raiz = createRoot(contenedor)
  await act(async () => { raiz.render(<LogsPage />) })
  await esperar()
}

const lineas = () => [...contenedor.querySelectorAll<HTMLButtonElement>('.lg-linea__cuerpo')]
async function tecla(el: HTMLElement, key: string) {
  await act(async () => { el.dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true })) })
  await esperar()
}

beforeEach(() => {
  vi.mocked(getLogs).mockResolvedValue({ items: structuredClone(LINEAS), count: 3 } as Awaited<ReturnType<typeof getLogs>>)
  escribirPortapapeles.mockResolvedValue(undefined)
  Object.defineProperty(navigator, 'clipboard', { value: { writeText: escribirPortapapeles }, configurable: true })
})

afterEach(async () => {
  await act(async () => { raiz.unmount() })
  contenedor.remove()
  vi.clearAllMocks()
})

describe('Logs', () => {
  it('copiar una línea lo dice en el contador', async () => {
    await montar()
    const contador = () => contenedor.querySelector('.lg-contador')?.textContent
    expect(contador()).toBe('3 líneas')
    await act(async () => { contenedor.querySelector<HTMLButtonElement>('.lg-copiar')!.click() })
    await esperar()
    expect(escribirPortapapeles).toHaveBeenCalledTimes(1)
    expect(contador()).toBe('Línea copiada')
  })

  it('solo una línea está en el orden del tabulador, los botones de copiar no, y las flechas mueven el foco', async () => {
    await montar()
    expect(lineas().map(b => b.tabIndex)).toEqual([0, -1, -1])
    // La lista no es otra parada: el primer Tab llega directo a la línea, donde funcionan las flechas y C.
    expect(contenedor.querySelector('.lg-lista')!.hasAttribute('tabindex')).toBe(false)
    expect([...contenedor.querySelectorAll<HTMLButtonElement>('.lg-copiar')].every(b => b.tabIndex === -1)).toBe(true)
    await act(async () => { lineas()[0].focus() })
    await tecla(lineas()[0], 'ArrowDown')
    expect(document.activeElement).toBe(lineas()[1])
    // La que tiene el foco pasa a ser la que entra con Tab.
    expect(lineas().map(b => b.tabIndex)).toEqual([-1, 0, -1])
    await tecla(lineas()[1], 'End')
    expect(document.activeElement).toBe(lineas()[2])
    await tecla(lineas()[2], 'Home')
    expect(document.activeElement).toBe(lineas()[0])
  })

  it('si un refresco se lleva la línea enfocada, el foco vuelve a la lista', async () => {
    await montar()
    await act(async () => { lineas()[2].focus() })
    expect(document.activeElement).toBe(lineas()[2])
    // Llega una línea nueva y la más vieja (la enfocada) sale de las que se enseñan.
    vi.mocked(getLogs).mockResolvedValue({
      items: [{ ts: 4, time: '2026-11-06 11:00:04', level: 'INFO', logger: 'app', message: 'cuarta' }, ...structuredClone(LINEAS).slice(0, 2)],
      count: 3,
    } as Awaited<ReturnType<typeof getLogs>>)
    const refrescar = [...contenedor.querySelectorAll('button')].find(b => b.textContent === 'Refrescar')!
    // Como el refresco automático: el foco sigue en la línea, que desaparece; sin el arreglo cae al body.
    await act(async () => { refrescar.dispatchEvent(new MouseEvent('click', { bubbles: true })) })
    await esperar()
    expect(lineas().map(l => l.textContent).join(' ')).not.toContain('primera')
    expect(contenedor.querySelector('.lg-lista')!.contains(document.activeElement)).toBe(true)
  })

  it('la tecla C copia la línea enfocada', async () => {
    await montar()
    await act(async () => { lineas()[1].focus() })
    await tecla(lineas()[1], 'c')
    expect(escribirPortapapeles).toHaveBeenCalledTimes(1)
    expect(escribirPortapapeles.mock.calls[0][0]).toContain('segunda')
  })
})
