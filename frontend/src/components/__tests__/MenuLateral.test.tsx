// @vitest-environment jsdom
/**
 * La barra lateral en ventanas estrechas: un cajón que se abre con el botón de la cabecera, se cierra con Escape,
 * con el velo o al elegir una sección, y devuelve el foco al botón.
 */
import { act } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../../api/system', () => ({ getSystemStats: vi.fn(() => new Promise(() => { /* sin datos */ })) }))

import { useMenuMovil } from '../../hooks/useMenuMovil'
import { BotonMenu } from '../BotonMenu'
import { Sidebar } from '../Sidebar'
import { desmontar, montar, pulsar } from './dom'

const onNavigate = vi.fn()
const onTour = vi.fn()

// El mismo cableado que AppShell: el hook, el botón de la cabecera, el velo y la barra.
function Arnes() {
  const menu = useMenuMovil()
  return (
    <>
      <BotonMenu abierto={menu.abierto} onAlternar={menu.alternar} botonRef={menu.botonRef} />
      {menu.abierto && <div className="sidebar-velo" onClick={menu.cerrar} />}
      <Sidebar active="library" onNavigate={onNavigate} movil={menu.movil} abierta={menu.abierto} onCerrar={menu.cerrar} onTour={onTour} />
    </>
  )
}

function ventana(estrecha: boolean) {
  window.matchMedia = vi.fn(() => ({
    matches: estrecha, addEventListener: vi.fn(), removeEventListener: vi.fn(),
  })) as unknown as typeof window.matchMedia
}

const menu = () => document.querySelector<HTMLButtonElement>('.boton-menu')!
const barra = () => document.querySelector<HTMLElement>('.sidebar')!
const escape = () => act(async () => { document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true })) })

beforeEach(() => { onNavigate.mockReset(); onTour.mockReset(); localStorage.clear() })
afterEach(desmontar)

describe('barra lateral en ventanas estrechas', () => {
  beforeEach(() => ventana(true))

  it('empieza cerrada y el botón la abre: aria-expanded, textos visibles y el foco en la sección actual', async () => {
    await montar(<Arnes />)
    expect(menu().getAttribute('aria-expanded')).toBe('false')
    expect(barra().classList.contains('abierta')).toBe(false)

    await pulsar(menu())
    expect(menu().getAttribute('aria-expanded')).toBe('true')
    expect(barra().classList.contains('abierta')).toBe(true)
    expect(barra().textContent).toContain('Biblioteca')
    expect(document.activeElement?.textContent).toContain('Biblioteca')
    expect(document.querySelector('.sidebar-velo')).not.toBeNull()
  })

  it('Escape la cierra y el foco vuelve al botón', async () => {
    await montar(<Arnes />)
    await pulsar(menu())
    await escape()
    expect(menu().getAttribute('aria-expanded')).toBe('false')
    expect(barra().classList.contains('abierta')).toBe(false)
    expect(document.activeElement).toBe(menu())
  })

  it('el velo y el logo también la cierran', async () => {
    await montar(<Arnes />)
    await pulsar(menu())
    await pulsar(document.querySelector('.sidebar-velo')!)
    expect(barra().classList.contains('abierta')).toBe(false)

    await pulsar(menu())
    await pulsar(document.querySelector('.sidebar-logo')!)
    expect(barra().classList.contains('abierta')).toBe(false)
    expect(document.activeElement).toBe(menu())
  })

  it('elegir una sección navega y cierra el cajón', async () => {
    await montar(<Arnes />)
    await pulsar(menu())
    await pulsar([...barra().querySelectorAll('.nav-item')].find(b => b.textContent === 'Subidas'))
    expect(onNavigate).toHaveBeenCalledWith('uploads')
    expect(barra().classList.contains('abierta')).toBe(false)
  })

  it('el cajón ofrece volver a ver el tour', async () => {
    await montar(<Arnes />)
    await pulsar(menu())
    const boton = [...barra().querySelectorAll('button')].find(b => b.textContent === 'Ver el tour guiado')!
    await pulsar(boton)
    expect(onTour).toHaveBeenCalledTimes(1)
  })

  it('aunque la barra esté contraída en escritorio, en el cajón enseña los textos', async () => {
    localStorage.setItem('emuwarez_uploadrr_sidebar_collapsed', 'true')
    await montar(<Arnes />)
    expect(barra().classList.contains('collapsed')).toBe(false)
    expect(barra().textContent).toContain('Estadísticas')
  })
})

describe('barra lateral en escritorio', () => {
  it('el logo contrae y expande la barra, y nada la trata como cajón', async () => {
    ventana(false)
    await montar(<Arnes />)
    const logo = document.querySelector<HTMLButtonElement>('.sidebar-logo')!
    expect(logo.getAttribute('aria-expanded')).toBe('true')
    await pulsar(logo)
    expect(barra().classList.contains('collapsed')).toBe(true)
    expect(logo.getAttribute('aria-expanded')).toBe('false')
    expect(barra().classList.contains('abierta')).toBe(false)
  })
})
