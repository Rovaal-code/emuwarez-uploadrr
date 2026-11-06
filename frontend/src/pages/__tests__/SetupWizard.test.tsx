// @vitest-environment jsdom
// El asistente de primera configuración: la key de eMuwarez va oculta, el aviso de «prueba la key» no es un error
// hasta que la prueba falla, y desde el paso siguiente a eMuwarez se puede volver atrás sin perder lo escrito.
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { SetupStatusResponse } from '../../types/api'

vi.mock('../../api/setup', () => ({
  setupAdmin: vi.fn(), setupTmdb: vi.fn(), setupEmu: vi.fn(), setupInstance: vi.fn(),
  setupQbit: vi.fn(), setupImghosts: vi.fn(), setupComplete: vi.fn(),
}))
vi.mock('../../api/auth', () => ({ login: vi.fn() }))
vi.mock('../../api/library', () => ({ startLibrarySync: vi.fn() }))
vi.mock('../../api/settings', () => ({ fetchSettings: vi.fn(), updateSettings: vi.fn() }))
vi.mock('../../api/integrationTests', () => ({
  testTmdbConnection: vi.fn(), testEmuwarezConnection: vi.fn(), testArrConnection: vi.fn(),
  testQbitConnection: vi.fn(), testImghostConnection: vi.fn(),
}))

import { setupEmu } from '../../api/setup'
import { fetchSettings, updateSettings } from '../../api/settings'
import { testEmuwarezConnection } from '../../api/integrationTests'
import { SetupWizard } from '../SetupWizard'

;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

const ESTADO: SetupStatusResponse = {
  initialized: false, admin_configured: true, tmdb_configured: false, emu_configured: false,
  radarr_instances: 0, sonarr_instances: 0, next_step: 'emu',
}

let raiz: Root
let contenedor: HTMLDivElement

async function esperar() {
  await act(async () => { await new Promise(r => setTimeout(r, 0)) })
}

async function montar(estado: SetupStatusResponse = ESTADO) {
  contenedor = document.createElement('div')
  document.body.appendChild(contenedor)
  raiz = createRoot(contenedor)
  await act(async () => { raiz.render(<SetupWizard setupStatus={estado} onComplete={() => {}} />) })
  await esperar()
}

function boton(texto: string): HTMLButtonElement | undefined {
  return [...contenedor.querySelectorAll('button')].find(b => b.textContent?.trim() === texto)
}

async function pulsar(el: HTMLElement) {
  await act(async () => { el.dispatchEvent(new MouseEvent('click', { bubbles: true })) })
  await esperar()
}

async function escribir(el: HTMLInputElement, valor: string) {
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(el, valor)
    el.dispatchEvent(new Event('input', { bubbles: true }))
  })
}

const titulo = () => contenedor.querySelector('h2')?.textContent ?? ''
const alertas = () => [...contenedor.querySelectorAll('[role="alert"]')].map(a => a.textContent ?? '')

beforeEach(() => {
  vi.mocked(fetchSettings).mockResolvedValue({ provider_priority_order: [], image_hosts_available: [] } as unknown as Awaited<ReturnType<typeof fetchSettings>>)
  vi.mocked(updateSettings).mockResolvedValue({} as Awaited<ReturnType<typeof updateSettings>>)
  vi.mocked(setupEmu).mockResolvedValue(undefined as unknown as Awaited<ReturnType<typeof setupEmu>>)
})

afterEach(async () => {
  await act(async () => { raiz.unmount() })
  contenedor.remove()
  vi.clearAllMocks()
})

describe('Asistente de primera configuración', () => {
  it('el título del paso dice cuántos hay', async () => {
    await montar()
    expect(titulo()).toBe('eMuwarez · paso 3 de 9')
  })

  it('la key de eMuwarez va oculta y se puede mostrar; lo que se envía no cambia', async () => {
    vi.mocked(testEmuwarezConnection).mockResolvedValue({ ok: true, service: 'emuwarez', status: 'ok', message: '' })
    await montar()
    const key = contenedor.querySelector<HTMLInputElement>('#setup-campo-4')!
    expect(key.type).toBe('password')
    await pulsar(contenedor.querySelector<HTMLButtonElement>('button[aria-label="Mostrar la key"]')!)
    expect(key.type).toBe('text')
    expect(contenedor.querySelector('button[aria-label="Ocultar la key"]')?.getAttribute('aria-pressed')).toBe('true')
    await escribir(key, 'clave-123')
    await pulsar(boton('Probar conexión')!)
    expect(testEmuwarezConnection).toHaveBeenCalledWith({ api_key: 'clave-123' })
    await pulsar(boton('Continuar')!)
    expect(setupEmu).toHaveBeenCalledWith('clave-123')
  })

  it('antes de probar la key no hay ningún error; si la prueba falla, sí', async () => {
    vi.mocked(testEmuwarezConnection).mockResolvedValue({ ok: false, service: 'emuwarez', status: 'invalid_key', message: '' })
    await montar()
    expect(alertas()).toEqual([])
    expect(contenedor.textContent).toContain('Pulsa «Probar conexión»: hace falta una key de eMuwarez válida para seguir.')
    expect(boton('Continuar')!.disabled).toBe(true)
    await escribir(contenedor.querySelector<HTMLInputElement>('#setup-campo-4')!, 'mala')
    await pulsar(boton('Probar conexión')!)
    expect(alertas().join(' ')).toContain('La key no ha pasado la prueba.')
    // El resultado de la prueba lleva su tono por clase, no por un color en línea.
    expect(contenedor.querySelector('.aj-resultado--error')?.textContent).toBe('✗ API key inválida')
  })

  it('desde Instancias se vuelve a eMuwarez con lo escrito; desde eMuwarez no hay «Atrás»', async () => {
    vi.mocked(testEmuwarezConnection).mockResolvedValue({ ok: true, service: 'emuwarez', status: 'ok', message: '' })
    await montar()
    expect(boton('Atrás')).toBeUndefined()
    await escribir(contenedor.querySelector<HTMLInputElement>('#setup-campo-4')!, 'clave-123')
    await pulsar(boton('Probar conexión')!)
    await pulsar(boton('Continuar')!)
    expect(titulo()).toContain('Instancias')
    await pulsar(boton('Atrás')!)
    expect(titulo()).toContain('eMuwarez')
    expect(contenedor.querySelector<HTMLInputElement>('#setup-campo-4')!.value).toBe('clave-123')
    // La prueba ya hecha sigue valiendo: se puede continuar sin repetirla.
    expect(boton('Continuar')!.disabled).toBe(false)
  })

  it('tras recargar en un paso posterior no ofrece volver a uno sin su prueba hecha', async () => {
    await montar({ ...ESTADO, emu_configured: true, next_step: 'tmdb' })
    expect(titulo()).toContain('TMDb')
    expect(boton('Atrás')).toBeUndefined()
  })
})
