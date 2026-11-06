// @vitest-environment jsdom
/**
 * El menú de filtro de columna se cierra al tocar fuera. Lo hace con `pointerdown`, no con `mousedown`: en iOS
 * tocar fuera no genera eventos de ratón, así que con `mousedown` el menú se quedaba abierto.
 */
import { act, useState } from 'react'
import { afterEach, describe, expect, it } from 'vitest'

import { HeaderFilter } from '../HeaderFilter'
import { desmontar, montar, pulsar } from './dom'

const OPCIONES = [{ value: '', label: 'Todos' }, { value: 'a', label: 'Alfa' }, { value: 'b', label: 'Beta' }]

function Arnes() {
  const [valor, setValor] = useState<string[]>([])
  return (
    <>
      <HeaderFilter label="Estado" value={valor} options={OPCIONES} onChange={setValor} />
      <p id="fuera">Fuera</p>
    </>
  )
}

const menu = () => document.querySelector('[role="dialog"]')
const disparar = (el: Element, tipo: string) =>
  act(async () => { el.dispatchEvent(new Event(tipo, { bubbles: true })) })

async function abrir() {
  await montar(<Arnes />)
  await pulsar(document.querySelector('.hf-trigger') ?? undefined)
  expect(menu()).not.toBeNull()
}

describe('HeaderFilter', () => {
  afterEach(desmontar)

  it('se cierra con un toque fuera (pointerdown)', async () => {
    await abrir()
    await disparar(document.getElementById('fuera')!, 'pointerdown')
    expect(menu()).toBeNull()
  })

  it('no se cierra con un toque dentro del menú', async () => {
    await abrir()
    await disparar(menu()!, 'pointerdown')
    expect(menu()).not.toBeNull()
  })

  it('ya no escucha mousedown: lo cierra el pointerdown que lo precede', async () => {
    await abrir()
    await disparar(document.getElementById('fuera')!, 'mousedown')
    expect(menu()).not.toBeNull()
  })
})
