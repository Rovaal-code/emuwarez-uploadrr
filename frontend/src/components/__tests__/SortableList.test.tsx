// @vitest-environment jsdom
/**
 * Con el dedo no hay arrastre (el mousedown de compatibilidad llega tras el touchend), así que cada fila trae subir y
 * bajar: mueven como las flechas del teclado, anuncian la posición, se apagan en el borde y no pierden el foco.
 */
import { act, useState } from 'react'
import { afterEach, describe, expect, it } from 'vitest'

import { SortableList } from '../SortableList'
import { desmontar, montar } from './dom'

function Arnes() {
  const [ids, setIds] = useState(['AMZN', 'NF', 'DSNP'])
  return (
    <>
      <output id="orden">{ids.join(',')}</output>
      <SortableList ids={ids} onChange={setIds} renderRow={(id, _i, { botones }) => <div>{id}{botones}</div>} />
    </>
  )
}

const orden = () => document.getElementById('orden')!.textContent
const btn = (etiqueta: string) => document.querySelector<HTMLButtonElement>(`button[aria-label="${etiqueta}"]`)!
const pulsar = (b: HTMLButtonElement) => act(async () => { b.click() })

afterEach(desmontar)

describe('SortableList con el dedo', () => {
  it('bajar y subir reordenan la lista y anuncian la nueva posición', async () => {
    await montar(<Arnes />)
    await pulsar(btn('Bajar AMZN'))
    expect(orden()).toBe('NF,AMZN,DSNP')
    expect(document.querySelector('[role="status"]')!.textContent).toBe('AMZN: posición 2 de 3')
    await pulsar(btn('Subir DSNP'))
    expect(orden()).toBe('NF,DSNP,AMZN')
  })

  it('en el borde el botón se apaga, y el foco pasa al otro', async () => {
    await montar(<Arnes />)
    expect(btn('Subir AMZN').disabled).toBe(true)
    expect(btn('Bajar DSNP').disabled).toBe(true)
    btn('Subir NF').focus()
    await pulsar(btn('Subir NF'))
    expect(orden()).toBe('NF,AMZN,DSNP')
    expect(document.activeElement).toBe(btn('Bajar NF'))
    btn('Bajar AMZN').focus()
    await pulsar(btn('Bajar AMZN'))
    expect(orden()).toBe('NF,DSNP,AMZN')
    expect(document.activeElement).toBe(btn('Subir AMZN'))
    btn('Subir AMZN').focus()
    await pulsar(btn('Subir AMZN'))
    expect(document.activeElement).toBe(btn('Subir AMZN'))
  })
})
