// @vitest-environment jsdom
// Instancias: editar dice qué se edita y no pierde el foco; el botón de añadir no cambia de significado.
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { InstanceSafeResponse } from '../../types/api'

vi.mock('../../api/instances', () => ({
  getInstances: vi.fn(), addInstance: vi.fn(), updateInstance: vi.fn(), testInstance: vi.fn(),
  syncInstance: vi.fn(), deleteInstance: vi.fn(),
}))
vi.mock('../../api/dashboard', () => ({ getDashboardSummary: vi.fn() }))
vi.mock('../../api/integrationTests', () => ({ testArrConnection: vi.fn() }))
vi.mock('../../hooks/useRefrescoPorAvisos', () => ({ useRefrescoPorAvisos: () => {} }))

import { getInstances } from '../../api/instances'
import { getDashboardSummary } from '../../api/dashboard'
import { InstancesPage } from '../InstancesPage'

;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

const INSTANCIA: InstanceSafeResponse = {
  id: 7, type: 'radarr', name: 'Radarr HD', url: 'http://radarr:7878', api_key_masked: 'abcd****', enabled: true,
  is_4k: false, is_anime: false, last_test_status: null, last_test_at: null, created_at: '2026-11-01T10:00:00', updated_at: null,
}

let raiz: Root
let contenedor: HTMLDivElement

async function esperar() {
  await act(async () => { await new Promise(r => setTimeout(r, 0)) })
}
// Lo que el componente deja para el siguiente fotograma (mover el foco).
async function fotograma() {
  await act(async () => { await new Promise(r => requestAnimationFrame(() => r(null))) })
}

async function montar() {
  contenedor = document.createElement('div')
  document.body.appendChild(contenedor)
  raiz = createRoot(contenedor)
  await act(async () => { raiz.render(<InstancesPage />) })
  await esperar()
}

function boton(texto: string): HTMLButtonElement {
  const b = [...contenedor.querySelectorAll('button')].find(x => x.textContent?.trim() === texto)
  if (!b) throw new Error(`No hay botón «${texto}»`)
  return b
}

async function pulsar(el: HTMLElement) {
  await act(async () => { el.dispatchEvent(new MouseEvent('click', { bubbles: true })) })
  await esperar()
}

beforeEach(() => {
  vi.mocked(getInstances).mockResolvedValue([structuredClone(INSTANCIA)])
  vi.mocked(getDashboardSummary).mockResolvedValue({ instancias_caidas: [] } as unknown as Awaited<ReturnType<typeof getDashboardSummary>>)
})

afterEach(async () => {
  await act(async () => { raiz.unmount() })
  contenedor.remove()
  vi.clearAllMocks()
})

describe('Instancias', () => {
  it('«Editar» enseña qué instancia se edita, lleva el foco al primer campo y «Cancelar» lo devuelve a «Editar»', async () => {
    await montar()
    await pulsar(contenedor.querySelector<HTMLButtonElement>('button[aria-label="Editar Radarr HD"]')!)
    await fotograma()
    expect(contenedor.querySelector('.inst-titulo-edicion')?.textContent).toBe('Editar «Radarr HD»')
    const nombre = contenedor.querySelector<HTMLInputElement>('#inst-edicion-7 input')!
    expect(nombre.value).toBe('Radarr HD')
    expect(document.activeElement).toBe(nombre)
    expect(nombre.labels?.[0]?.textContent).toContain('máx. 15')
    await pulsar(boton('Cancelar'))
    await fotograma()
    expect(document.activeElement).toBe(contenedor.querySelector('button[aria-label="Editar Radarr HD"]'))
  })

  it('el botón de la cabecera no se convierte en «Cancelar»: se desactiva y el formulario lleva su propio «Cancelar»', async () => {
    await montar()
    const anadir = boton('+ Añadir instancia')
    await pulsar(anadir)
    await fotograma()
    expect(anadir.textContent).toBe('+ Añadir instancia')
    expect(anadir.disabled).toBe(true)
    expect(anadir.getAttribute('aria-expanded')).toBe('true')
    expect(contenedor.querySelector('#inst-nueva')!.contains(document.activeElement)).toBe(true)
    await pulsar(boton('Cancelar'))
    await fotograma()
    expect(contenedor.querySelector('#inst-nueva')).toBeNull()
    expect(anadir.disabled).toBe(false)
    expect(document.activeElement).toBe(anadir)
  })
})
