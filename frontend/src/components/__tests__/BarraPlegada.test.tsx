// @vitest-environment jsdom
/**
 * Entre el cajón y unos 1100 px la barra lateral arranca plegada mientras el usuario no haya elegido; lo que elija con
 * el logo se guarda y manda en cualquier ancho, y sin preferencia la barra sigue los cambios de tamaño de la ventana.
 */
import { act } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../../api/system', () => ({ getSystemStats: vi.fn(() => new Promise(() => { /* sin datos */ })) }))

import { CONSULTA_PLEGADA, Sidebar } from '../Sidebar'
import { desmontar, montar, pulsar } from './dom'

const CLAVE = 'emuwarez_uploadrr_sidebar_collapsed'
let estrecha = false
let alCambiar: (() => void) | null = null

// Solo la consulta de la barra plegada responde según `estrecha`; las demás (cajón, hover) no casan.
function ventana(v: boolean) {
  estrecha = v
  window.matchMedia = vi.fn((q: string) => ({
    get matches() { return q === CONSULTA_PLEGADA && estrecha },
    addEventListener: (_: string, fn: () => void) => { if (q === CONSULTA_PLEGADA) alCambiar = fn },
    removeEventListener: vi.fn(),
  })) as unknown as typeof window.matchMedia
}

const barra = () => document.querySelector<HTMLElement>('.sidebar')!
const logo = () => document.querySelector<HTMLButtonElement>('.sidebar-logo')!
const plegada = () => barra().classList.contains('collapsed')

beforeEach(() => { localStorage.clear(); alCambiar = null })
afterEach(desmontar)

describe('barra lateral plegada por defecto en tableta', () => {
  it('sin preferencia guardada, arranca plegada en una ventana de tableta y abierta en una ancha', async () => {
    ventana(true)
    await montar(<Sidebar active="library" onNavigate={() => {}} />)
    expect(plegada()).toBe(true)
    expect(logo().getAttribute('aria-expanded')).toBe('false')
    expect(document.querySelector('.sidebar-expandir')).not.toBeNull()
    await desmontar()

    ventana(false)
    await montar(<Sidebar active="library" onNavigate={() => {}} />)
    expect(plegada()).toBe(false)
    expect(document.querySelector('.sidebar-expandir')).toBeNull()
  })

  it('sin preferencia, sigue a la ventana al cambiar de tamaño', async () => {
    ventana(false)
    await montar(<Sidebar active="library" onNavigate={() => {}} />)
    expect(plegada()).toBe(false)
    estrecha = true
    await act(async () => { alCambiar?.() })
    expect(plegada()).toBe(true)
  })

  it('abrirla con el logo en una ventana de tableta se guarda y manda aunque cambie el ancho', async () => {
    ventana(true)
    await montar(<Sidebar active="library" onNavigate={() => {}} />)
    await pulsar(logo())
    expect(plegada()).toBe(false)
    expect(localStorage.getItem(CLAVE)).toBe('false')

    estrecha = false
    await act(async () => { alCambiar?.() })
    estrecha = true
    await act(async () => { alCambiar?.() })
    expect(plegada()).toBe(false)
  })

  it('una barra plegada a mano sigue plegada en una ventana ancha', async () => {
    localStorage.setItem(CLAVE, 'true')
    ventana(false)
    await montar(<Sidebar active="library" onNavigate={() => {}} />)
    expect(plegada()).toBe(true)
    await pulsar(logo())
    expect(plegada()).toBe(false)
    expect(localStorage.getItem(CLAVE)).toBe('false')
  })
})
