// @vitest-environment jsdom
/**
 * La paleta Ctrl+K: filtra secciones, busca en la Biblioteca con el servidor simulado y elige con teclado o ratón.
 */
import { act } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../../api/library', () => ({ getLibrary: vi.fn(), TOP_LEVEL_PARENT_FILTER: 0 }))

import { getLibrary } from '../../api/library'
import type { LibraryItemResponse, LibraryListResponse } from '../../types/api'
import { CommandPalette } from '../CommandPalette'
import { desmontar, escribir, esperar, montar, texto } from './dom'

const m = vi.mocked(getLibrary)
const SECCIONES = [{ id: 'dashboard', titulo: 'Panel' }, { id: 'library', titulo: 'Biblioteca' }, { id: 'stats', titulo: 'Estadísticas' }]

const lista = (items: Partial<LibraryItemResponse>[]): LibraryListResponse =>
  ({ items: items as LibraryItemResponse[], total: items.length, archivos: 0, limit: 8, offset: 0 })

function montarPaleta() {
  const llamadas = { seccion: vi.fn(), elemento: vi.fn(), cerrar: vi.fn() }
  return montar(
    <CommandPalette secciones={SECCIONES} onSeccion={llamadas.seccion} onElemento={llamadas.elemento} onClose={llamadas.cerrar} />,
  ).then(() => llamadas)
}

const entrada = () => document.querySelector<HTMLInputElement>('input[aria-label="Buscar"]')!
const tecla = (key: string) => act(async () => {
  entrada().dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true }))
})

beforeEach(() => { m.mockReset(); m.mockResolvedValue(lista([])) })
afterEach(desmontar)

describe('CommandPalette', () => {
  it('sin texto enseña todas las secciones y no busca en la Biblioteca', async () => {
    await montarPaleta()
    expect(document.querySelectorAll('[role="option"]')).toHaveLength(3)
    expect(m).not.toHaveBeenCalled()
  })

  it('filtra las secciones sin acentos y Intro abre la elegida', async () => {
    const f = await montarPaleta()
    await escribir(entrada(), 'estadis')
    expect(document.querySelectorAll('[role="option"]')).toHaveLength(1)
    await tecla('Enter')
    expect(f.seccion).toHaveBeenCalledWith('stats')
    expect(f.cerrar).toHaveBeenCalled()
  })

  it('busca en la Biblioteca (solo el nivel de arriba) y abre la ficha de la elegida', async () => {
    m.mockResolvedValue(lista([{ id: 42, title: 'Dune', year: 2021, item_type: 'movie' }]))
    const f = await montarPaleta()
    await escribir(entrada(), 'dun')
    await esperar(() => texto().includes('Dune (2021)'))
    expect(m).toHaveBeenCalledWith({ search: 'dun', parent_id: 0, limit: 8 })
    expect(texto()).toContain('Película')
    // Las secciones no coinciden con «dun»: la única opción es la película.
    await tecla('Enter')
    expect(f.elemento).toHaveBeenCalledWith(42)
  })

  it('las flechas mueven la selección y dan la vuelta', async () => {
    const f = await montarPaleta()
    await tecla('ArrowUp')   // desde la primera, a la última
    await tecla('Enter')
    expect(f.seccion).toHaveBeenCalledWith('stats')
  })

  it('un fallo de la búsqueda no rompe la paleta', async () => {
    m.mockRejectedValue(new Error('caído'))
    await montarPaleta()
    await escribir(entrada(), 'zzz')
    await esperar(() => texto().includes('Nada que coincida con «zzz»'))
  })
})
