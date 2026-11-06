// @vitest-environment jsdom
/**
 * El modal compartido es un diálogo de verdad: título anunciado, foco dentro, Tab atrapado, Escape y velo lo
 * cierran (el velo solo si el gesto entero fue sobre él) y el foco vuelve a quien lo abrió.
 */
import { act, useState } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { Modal } from '../Modal'
import { desmontar, montar, pulsar } from './dom'

function Arnes({ alCerrar = vi.fn(), conAutofoco = false }: { alCerrar?: () => void; conAutofoco?: boolean }) {
  const [abierto, setAbierto] = useState(false)
  return (
    <>
      <button id="abrir" onClick={() => setAbierto(true)}>Abrir</button>
      {abierto && (
        <Modal titulo="Mi modal" onClose={() => { alCerrar(); setAbierto(false) }}>
          <input id="a" aria-label="Primero" autoFocus={conAutofoco} />
          <button id="b">Segundo</button>
        </Modal>
      )}
    </>
  )
}

const panel = () => document.querySelector<HTMLElement>('.modal-panel')
const velo = () => document.querySelector<HTMLElement>('.modal-overlay')!
const tecla = (key: string, opciones: KeyboardEventInit = {}) =>
  act(async () => { document.dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true, ...opciones })) })
const evento = (el: Element, tipo: string, init: MouseEventInit = {}) =>
  act(async () => { el.dispatchEvent(new MouseEvent(tipo, { bubbles: true, button: 0, ...init })) })

async function abrir(props: Parameters<typeof Arnes>[0] = {}) {
  await montar(<Arnes {...props} />)
  const opener = document.getElementById('abrir') as HTMLButtonElement
  opener.focus()
  await pulsar(opener)
  return opener
}

// jsdom no hace layout: sin esto ningún elemento «se ve» y la lista de enfocables del modal sale vacía.
beforeEach(() => {
  vi.spyOn(HTMLElement.prototype, 'getClientRects').mockReturnValue([{}] as unknown as DOMRectList)
  // El tooltip del botón Cerrar mide su texto con un Range, que jsdom tampoco trae.
  Range.prototype.getClientRects = () => [] as unknown as DOMRectList
})
afterEach(async () => { await desmontar(); vi.restoreAllMocks() })

describe('Modal', () => {
  it('es un diálogo modal con el título como nombre accesible', async () => {
    await abrir()
    const p = panel()!
    expect(p.getAttribute('role')).toBe('dialog')
    expect(p.getAttribute('aria-modal')).toBe('true')
    expect(document.getElementById(p.getAttribute('aria-labelledby')!)?.textContent).toBe('Mi modal')
  })

  it('el foco entra en el panel, o se queda en el hijo que ya lo pedía', async () => {
    await abrir()
    expect(document.activeElement).toBe(panel())
    await desmontar()
    await abrir({ conAutofoco: true })
    expect(document.activeElement).toBe(document.getElementById('a'))
  })

  it('Tab no se sale del modal: del último pasa al primero y Mayús+Tab al revés', async () => {
    await abrir()
    const cerrar = document.querySelector<HTMLElement>('.modal-close')!
    const ultimo = document.getElementById('b')!
    ultimo.focus()
    await tecla('Tab')
    expect(document.activeElement).toBe(cerrar)
    await tecla('Tab', { shiftKey: true })
    expect(document.activeElement).toBe(ultimo)
  })

  it('Escape lo cierra y el foco vuelve al botón que lo abrió', async () => {
    const alCerrar = vi.fn()
    const opener = await abrir({ alCerrar })
    await tecla('Escape')
    expect(alCerrar).toHaveBeenCalledTimes(1)
    expect(panel()).toBeNull()
    expect(document.activeElement).toBe(opener)
  })

  it('el velo lo cierra al pulsar y soltar sobre él, pero no si el gesto empezó dentro del panel', async () => {
    const alCerrar = vi.fn()
    await abrir({ alCerrar })

    // Seleccionar texto: se pulsa dentro y se suelta fuera. El «click» cae en el velo (ancestro común) y no debe cerrar.
    await evento(panel()!, 'pointerdown')
    await evento(velo(), 'click')
    expect(alCerrar).not.toHaveBeenCalled()

    // Un clic dentro del panel tampoco.
    await evento(panel()!, 'click')
    expect(alCerrar).not.toHaveBeenCalled()

    // Pulsar y soltar sobre el velo, sí.
    await evento(velo(), 'pointerdown')
    await evento(velo(), 'click')
    expect(alCerrar).toHaveBeenCalledTimes(1)
  })

  it('con dos modales abiertos, Escape cierra solo el de encima', async () => {
    const cierres: string[] = []
    // El segundo se abre después, desde dentro del primero (como MediaInfo sobre el asistente de subida).
    function Dos() {
      const [segundo, setSegundo] = useState(false)
      return (
        <>
          <Modal titulo="Primero" onClose={() => cierres.push('primero')}>
            <button id="abrir-segundo" onClick={() => setSegundo(true)}>Abrir el segundo</button>
          </Modal>
          {segundo && <Modal titulo="Segundo" onClose={() => { cierres.push('segundo'); setSegundo(false) }}><button>x</button></Modal>}
        </>
      )
    }
    await montar(<Dos />)
    await pulsar(document.getElementById('abrir-segundo')!)
    await tecla('Escape')
    expect(cierres).toEqual(['segundo'])
    await tecla('Escape')
    expect(cierres).toEqual(['segundo', 'primero'])
  })
})
