// @vitest-environment jsdom
// Guía: la sección abierta va en la URL, para poder enlazar a una sección concreta.
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, describe, expect, it } from 'vitest'
import { GuidePage } from '../GuidePage'

;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

let raiz: Root
let contenedor: HTMLDivElement

async function montar() {
  contenedor = document.createElement('div')
  document.body.appendChild(contenedor)
  raiz = createRoot(contenedor)
  await act(async () => { raiz.render(<GuidePage />) })
}

const activa = () => contenedor.querySelector('[role="tab"][aria-selected="true"]')?.id

afterEach(async () => {
  await act(async () => { raiz.unmount() })
  contenedor.remove()
  window.history.replaceState(null, '', '/')
})

describe('Guía', () => {
  it('abre la sección que pide ?seccion= y, si no existe, la de partida', async () => {
    window.history.replaceState(null, '', '/guide?seccion=rules')
    await montar()
    expect(activa()).toBe('guia-pestana-rules')
    await act(async () => { raiz.unmount() })
    contenedor.remove()

    window.history.replaceState(null, '', '/guide?seccion=no-existe')
    await montar()
    expect(activa()).toBe('guia-pestana-formula')
  })

  it('elegir una sección la apunta en la URL sin añadir una entrada al historial', async () => {
    window.history.replaceState(null, '', '/guide')
    const antes = window.history.length
    await montar()
    await act(async () => { contenedor.querySelector<HTMLButtonElement>('#guia-pestana-upload')!.click() })
    expect(activa()).toBe('guia-pestana-upload')
    expect(window.location.search).toBe('?seccion=upload')
    expect(window.history.length).toBe(antes)
  })
})
