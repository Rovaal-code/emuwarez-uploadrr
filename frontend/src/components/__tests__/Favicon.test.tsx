// @vitest-environment jsdom
/**
 * Favicon: el icono del sitio sale de los ficheros del proyecto (assets/iconos), sin pedir nada fuera; si el sitio
 * no tiene, o el fichero no carga, se enseña el icono de reserva.
 */
import { useState } from 'react'
import { afterEach, describe, expect, it } from 'vitest'
import { Favicon, domainOf } from '../Favicon'
import { iconoDe } from '../../utils/iconosSitios'
import { boton, desmontar, montar, pulsar } from './dom'

afterEach(desmontar)

describe('iconoDe', () => {
  it('conoce los sitios de la lista y no distingue mayúsculas', () => {
    expect(iconoDe('netflix.com')).toBeTruthy()
    expect(iconoDe('Netflix.COM')).toBe(iconoDe('netflix.com'))
    expect(iconoDe('www.imdb.com')).toBeTruthy()
  })

  it('devuelve null para un sitio que no está', () => {
    expect(iconoDe('no-existe.example')).toBeNull()
  })
})

describe('Favicon', () => {
  it('pinta el icono del proyecto, de este mismo servidor', async () => {
    await montar(<Favicon domain="netflix.com" size={16} fallback={<b>reserva</b>} />)
    const img = document.querySelector('img')!
    expect(img).not.toBeNull()
    expect(img.getAttribute('src')).toBe(iconoDe('netflix.com'))
    expect(img.getAttribute('src')).not.toMatch(/^https?:\/\//)  // nada de fuera
    expect(document.body.textContent).not.toContain('reserva')
  })

  it('con fondo, lo pinta dentro de la caja', async () => {
    await montar(<Favicon domain="imgbb.com" background="white" fallback={<b>reserva</b>} />)
    expect(document.querySelector('.menores-icono-caja img')).not.toBeNull()
  })

  it.each([['un sitio sin icono', 'no-existe.example'], ['sin dominio', ''], ['dominio nulo', null]])(
    'enseña el de reserva con %s', async (_caso, domain) => {
      await montar(<Favicon domain={domain} fallback={<b>reserva</b>} />)
      expect(document.querySelector('img')).toBeNull()
      expect(document.body.textContent).toContain('reserva')
    })

  it('si el fichero no carga, enseña el de reserva', async () => {
    await montar(<Favicon domain="netflix.com" fallback={<b>reserva</b>} />)
    const { act } = await import('react')
    await act(async () => { document.querySelector('img')!.dispatchEvent(new Event('error')) })
    expect(document.querySelector('img')).toBeNull()
    expect(document.body.textContent).toContain('reserva')
  })
})

describe('Favicon con otro dominio', () => {
  it('tras un fallo, el dominio nuevo vuelve a intentar su icono', async () => {
    function Cambia() {
      const [d, setD] = useState('netflix.com')
      return <><button onClick={() => setD('imgbb.com')}>cambiar</button><Favicon domain={d} fallback={<b>reserva</b>} /></>
    }
    await montar(<Cambia />)
    const { act } = await import('react')
    await act(async () => { document.querySelector('img')!.dispatchEvent(new Event('error')) })
    expect(document.body.textContent).toContain('reserva')
    await pulsar(boton('cambiar'))
    expect(document.querySelector('img')?.getAttribute('src')).toBe(iconoDe('imgbb.com'))
    expect(document.body.textContent).not.toContain('reserva')
  })
})

describe('domainOf', () => {
  it('saca el nombre de una URL', () => {
    expect(domainOf('https://imgbox.com/x')).toBe('imgbox.com')
    expect(domainOf('no es una url')).toBe('')
    expect(domainOf(null)).toBe('')
  })
})
