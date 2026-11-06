// @vitest-environment jsdom
/**
 * Los tooltips con el dedo (sin hover): un toque en una ayuda la abre y otro la cierra, y también se cierra al tocar
 * fuera o con Escape. Un toque en un botón con acción propia no abre nada, y con ratón todo sigue como antes.
 */
import { act } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { InfoIcon } from '../InfoIcon'
import { StatCard } from '../StatCard'
import { Tooltip } from '../Tooltip'
import { desmontar, montar } from './dom'

function sinHover(valor: boolean) {
  window.matchMedia = vi.fn((q: string) => ({
    matches: q.includes('hover: none') ? valor : false, addEventListener: vi.fn(), removeEventListener: vi.fn(),
  })) as unknown as typeof window.matchMedia
}

const globo = () => document.querySelector('[role="tooltip"]')
async function evento(el: EventTarget, tipo: string, init: EventInit & { key?: string } = {}) {
  const e = tipo === 'keydown'
    ? new KeyboardEvent(tipo, { bubbles: true, ...init })
    : new MouseEvent(tipo, { bubbles: true, cancelable: true, ...init })
  await act(async () => { el.dispatchEvent(e) })
}
const tocar = async (el: Element) => { await evento(el, 'pointerdown'); await evento(el, 'pointerup') }

// jsdom no mide el texto: el tooltip ajusta su ancho a la línea más larga con Range.getClientRects.
if (!Range.prototype.getClientRects) {
  Range.prototype.getClientRects = () => [] as unknown as DOMRectList
}

afterEach(async () => { await desmontar() })

describe('Tooltip con el dedo', () => {
  it('un toque en el «?» abre la explicación y otro la cierra', async () => {
    sinHover(true)
    await montar(<InfoIcon text="De dónde sale este dato" />)
    const ayuda = document.querySelector('.menores-info')!
    await tocar(ayuda)
    expect(globo()?.textContent).toBe('De dónde sale este dato')
    await tocar(ayuda)
    expect(globo()).toBeNull()
  })

  it('se cierra al tocar fuera y con Escape', async () => {
    sinHover(true)
    await montar(<div><StatCard label="En disco" value={3} info="Contenido presente en disco" /><p id="fuera">otra cosa</p></div>)
    const tarjeta = document.querySelector('.stat-card')!
    await tocar(tarjeta)
    expect(globo()?.textContent).toBe('Contenido presente en disco')
    await evento(document.getElementById('fuera')!, 'pointerdown')
    expect(globo()).toBeNull()

    await tocar(tarjeta)
    expect(globo()).not.toBeNull()
    await evento(document, 'keydown', { key: 'Escape' })
    expect(globo()).toBeNull()
  })

  it('un botón con acción propia hace lo suyo y no abre su tooltip', async () => {
    sinHover(true)
    const accion = vi.fn()
    await montar(<Tooltip content="Actualizar ahora"><button type="button" onClick={accion}>↻</button></Tooltip>)
    const b = document.querySelector('button')!
    await tocar(b)
    await evento(b, 'click')
    expect(accion).toHaveBeenCalledTimes(1)
    expect(globo()).toBeNull()
  })

  it('con ratón, el toque no abre nada (el tooltip sigue siendo del hover)', async () => {
    sinHover(false)
    await montar(<InfoIcon text="Explicación" />)
    await tocar(document.querySelector('.menores-info')!)
    expect(globo()).toBeNull()
  })
})
