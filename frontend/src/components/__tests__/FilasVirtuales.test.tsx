// @vitest-environment jsdom
/**
 * La estimación de alto de FilasVirtuales con medidas simuladas (jsdom no maqueta): la media sale solo de las filas
 * ordinarias que siguen en la lista, y un cambio de ancho del contenedor (el corte tabla ↔ tarjeta por fila de
 * Peticiones y Subidas) olvida lo medido con el ancho anterior.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

// Un ResizeObserver que se dispara a mano. Va antes de importar dom.ts, que pondría uno vacío.
const observadores = vi.hoisted(() => {
  const lista: { cb: (e: { target: Element }[]) => void; objetivos: Set<Element> }[] = []
  ;(globalThis as { ResizeObserver?: unknown }).ResizeObserver = class {
    o: { cb: (e: { target: Element }[]) => void; objetivos: Set<Element> }
    constructor(cb: (e: { target: Element }[]) => void) { this.o = { cb, objetivos: new Set() }; lista.push(this.o) }
    observe(el: Element) { this.o.objetivos.add(el) }
    unobserve(el: Element) { this.o.objetivos.delete(el) }
    disconnect() { this.o.objetivos.clear() }
  }
  return lista
})

import { act, useRef } from 'react'
import { FilasVirtuales } from '../FilasVirtuales'
import { desmontar, montar } from './dom'

// Lo que «mide» cada fila: por clave, y el ancho del contenedor.
let alto: (clave: number) => number = () => 60
let ancho = 1000
const prototipo = Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'offsetHeight')!
beforeEach(() => {
  observadores.length = 0
  alto = () => 60
  ancho = 1000
  Object.defineProperty(HTMLElement.prototype, 'offsetHeight', {
    configurable: true,
    get(this: HTMLElement) { return this.dataset.clave != null ? alto(Number(this.dataset.clave)) : 0 },
  })
})
let otraRaiz: { unmount: () => void } | null = null
afterEach(async () => {
  if (otraRaiz) await act(async () => { otraRaiz!.unmount() })
  otraRaiz = null
  await desmontar()
  Object.defineProperty(HTMLElement.prototype, 'offsetHeight', prototipo)
})

function Lista({ items, dobles = [], fijas }: { items: number[]; dobles?: number[]; fijas?: ReadonlySet<number> }) {
  const contenedor = useRef<HTMLDivElement>(null)
  const cabecera = useRef<HTMLTableSectionElement>(null)
  const medidas = (el: HTMLDivElement | null) => {
    contenedor.current = el
    if (!el) return
    Object.defineProperty(el, 'clientHeight', { configurable: true, get: () => 300 })
    Object.defineProperty(el, 'clientWidth', { configurable: true, get: () => ancho })
  }
  return (
    <div ref={medidas}>
      <table>
        <thead ref={cabecera}><tr><th>Título</th></tr></thead>
        <FilasVirtuales
          items={items} clave={k => k} alturaEstimada={50} columnas={1} contenedor={contenedor} cabecera={cabecera} fijas={fijas}
          pintar={k => dobles.includes(k)
            ? [<tr key="a"><td>{k}</td></tr>, <tr key="b"><td>intento anterior</td></tr>]
            : <tr><td>{k}</td></tr>}
        />
      </table>
    </div>
  )
}

const deFilas = () => observadores[0]
const delContenedor = () => observadores.find(o => [...o.objetivos].some(el => el.tagName === 'DIV'))!
async function disparar(o: { cb: (e: { target: Element }[]) => void; objetivos: Set<Element> }) {
  await act(async () => { o.cb([...o.objetivos].map(target => ({ target }))) })
}
const pintadas = () => document.querySelectorAll('tbody[data-clave]').length
// Lo que suma el hueco del final: las filas sin pintar por su alto estimado.
const huecoFinal = () => {
  const huecos = [...document.querySelectorAll<HTMLElement>('tr.fila-hueco td')]
  const h = huecos[huecos.length - 1]
  return parseFloat(h!.style.height)
}
const claves = (n: number, desde = 0) => Array.from({ length: n }, (_, i) => desde + i)

describe('FilasVirtuales: la estimación de alto', () => {
  it('una cadena desplegada (varias <tr>) no infla la media de las demás', async () => {
    alto = k => (k === 0 ? 300 : 60)
    await montar(<Lista items={claves(200)} dobles={[0]} />)
    await disparar(deFilas())
    expect(huecoFinal()).toBe((200 - pintadas()) * 60)
  })

  it('una fila que pasa a fija sin cambiar de alto deja de contar para la media', async () => {
    // Una serie de Biblioteca que se abre sin capítulos aún: sigue siendo una sola <tr> y mide lo mismo.
    alto = k => (k === 0 ? 300 : 60)
    const { rerender } = await montarConRerender(<Lista items={claves(200)} />)
    await disparar(deFilas())
    expect(huecoFinal()).toBeGreaterThan((200 - pintadas()) * 60)
    await rerender(<Lista items={claves(200)} fijas={new Set([0])} />)
    expect(huecoFinal()).toBe((200 - pintadas()) * 60)
  })

  it('con otro filtro, las filas que ya no están no cuentan para la media', async () => {
    alto = k => (k < 100 ? 120 : 60)
    const { rerender } = await montarConRerender(<Lista items={claves(200)} />)
    await disparar(deFilas())
    // Otra lista sin ninguna de las medidas a 120: sus filas se estiman con lo que miden las suyas.
    await rerender(<Lista items={claves(100, 100)} />)
    await disparar(deFilas())
    expect(huecoFinal()).toBe((100 - pintadas()) * 60)
  })

  it('al cambiar el ancho del contenedor se olvida lo medido y se vuelven a medir las pintadas', async () => {
    await montar(<Lista items={claves(200)} />)
    await disparar(deFilas())
    expect(huecoFinal()).toBe((200 - pintadas()) * 60)
    // Cruza el corte: cada fila es ahora una tarjeta de 120 px. El observador de las filas no se dispara.
    ancho = 500
    alto = () => 120
    await disparar(delContenedor())
    expect(huecoFinal()).toBe((200 - pintadas()) * 120)
  })
})

// montar() de dom.ts no devuelve la raíz: aquí hace falta repintar con otras props.
async function montarConRerender(el: React.ReactElement) {
  const { createRoot } = await import('react-dom/client')
  const caja = document.createElement('div')
  document.body.appendChild(caja)
  const raiz = createRoot(caja)
  otraRaiz = raiz
  await act(async () => { raiz.render(el) })
  return { rerender: async (otro: React.ReactElement) => { await act(async () => { raiz.render(otro) }) } }
}
