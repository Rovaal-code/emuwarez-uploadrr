// @vitest-environment jsdom
/**
 * HoverTitle con onClick es un enlace de verdad: un <a href> con la ruta (clic central y Ctrl/⌘+clic abren otra pestaña,
 * el clic normal navega dentro de la aplicación) o, sin ruta, un <button>. Sin onClick es solo el tooltip.
 */
import { act } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { HoverTitle } from '../Tooltip'
import { desmontar, montar } from './dom'

afterEach(async () => { await desmontar() })

async function clic(el: Element, opciones: MouseEventInit = {}) {
  const evento = new MouseEvent('click', { bubbles: true, cancelable: true, ...opciones })
  await act(async () => { el.dispatchEvent(evento) })
  return evento
}

describe('HoverTitle', () => {
  it('con href y onClick es un <a href>: el clic normal navega en la aplicación y no sigue el enlace', async () => {
    const abrir = vi.fn()
    await montar(<HoverTitle as="span" className="hover-link" href="/uploads/7" onClick={abrir} tip="Abrir">Ver motivo</HoverTitle>)
    const enlace = document.querySelector('a')!
    expect(enlace.getAttribute('href')).toBe('/uploads/7')
    expect(enlace.getAttribute('role')).toBeNull()
    expect(enlace.className).toBe('enlace-titulo hover-link')
    const evento = await clic(enlace)
    expect(abrir).toHaveBeenCalledTimes(1)
    expect(evento.defaultPrevented).toBe(true)
  })

  it('Ctrl/⌘/Mayús+clic se lo deja al navegador (otra pestaña o ventana)', async () => {
    const abrir = vi.fn()
    await montar(<HoverTitle href="/requests/3" onClick={abrir} tip="Abrir">Título</HoverTitle>)
    const enlace = document.querySelector('a')!
    for (const mod of [{ ctrlKey: true }, { metaKey: true }, { shiftKey: true }]) {
      const evento = await clic(enlace, mod)
      expect(evento.defaultPrevented).toBe(false)
    }
    expect(abrir).not.toHaveBeenCalled()
    // as="div" (por defecto): el enlace ocupa su línea, como el div de antes.
    expect(enlace.classList.contains('titulo-bloque')).toBe(true)
  })

  it('con onClick y sin href es un <button type="button">; sin onClick, el elemento de siempre', async () => {
    const accion = vi.fn()
    await montar(<>
      <HoverTitle onClick={accion} tip="Hacer">Acción</HoverTitle>
      <HoverTitle as="span" tip="Solo tooltip">Texto</HoverTitle>
    </>)
    const boton = document.querySelector('button')!
    expect(boton.getAttribute('type')).toBe('button')
    await clic(boton)
    expect(accion).toHaveBeenCalledTimes(1)
    expect(document.querySelector('a')).toBeNull()
    expect(document.querySelector('span')!.textContent).toBe('Texto')
  })
})
