// @vitest-environment jsdom
/**
 * Los tooltips con el dedo (sin hover): un toque en una ayuda la abre y otro la cierra, y también se cierra al tocar
 * fuera o con Escape. Un toque en un botón con acción propia no abre nada, y con ratón todo sigue como antes.
 */
import { act } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { InfoIcon } from '../InfoIcon'
import { StatCard } from '../StatCard'
import { HoverTitle, Tooltip } from '../Tooltip'
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

  it('un HoverTitle informativo (sin onClick) se abre al tocarlo: el identificador entero solo está en el tooltip', async () => {
    sinHover(true)
    await montar(<HoverTitle as="span" tip="0123456789abcdef0123456789abcdef01234567"><code>0123456</code></HoverTitle>)
    await tocar(document.querySelector('code')!)
    expect(globo()?.textContent).toBe('0123456789abcdef0123456789abcdef01234567')
  })

  it('no se abre en un enlace HoverTitle, en un asa de arrastre ni dentro de una fila que se abre al tocarla', async () => {
    sinHover(true)
    const abrir = vi.fn()
    await montar(
      <div>
        <HoverTitle href="/requests/3" onClick={abrir} tip="Abrir ficha">Título</HoverTitle>
        <HoverTitle as="span" tip="Arrastra para reordenar" role="button" tabIndex={0}>≡</HoverTitle>
        <table><tbody><tr className="clickable"><td><HoverTitle as="span" tip="Título entero">Títu…</HoverTitle></td></tr></tbody></table>
      </div>,
    )
    for (const sel of ['a', '[role="button"]', 'td span']) {
      await tocar(document.querySelector(sel)!)
      expect(globo()).toBeNull()
    }
  })
})
