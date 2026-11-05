// @vitest-environment jsdom
/**
 * Marcar películas para «Subir por lotes»: el tope del lote, que la casilla no abra la ficha ni despliegue la fila,
 * que solo las películas la lleven, que la lista siga con siete columnas y lo que dice la barra.
 */
import { act } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'

vi.mock('../../api/library', () => ({ getLibrary: vi.fn() }))

import { getLibrary } from '../../api/library'
import { useSeleccionLote } from '../../hooks/useSeleccionLote'
import type { LibraryItemResponse } from '../../types/api'
import { LargePosterCard } from '../LargePosterCard'
import { LibraryTreeRow } from '../LibraryTreeRow'
import { BarraLote } from '../lote/BarraLote'
import { boton, desmontar, montar, pulsar, texto } from './dom'

afterEach(async () => {
  await desmontar()
  vi.clearAllMocks()
})

const elemento = (id: number, parcial: Partial<LibraryItemResponse> = {}) =>
  ({ id, item_type: 'movie', title: `Peli ${id}`, local_status: 'Disponible', has_spanish_ok: 1, ...parcial }) as LibraryItemResponse

const casilla = (titulo: string) => document.querySelector<HTMLInputElement>(`input[aria-label="Seleccionar «${titulo}»"]`)

describe('useSeleccionLote', () => {
  let api: ReturnType<typeof useSeleccionLote>
  const vistos: ReturnType<typeof useSeleccionLote>[] = []
  function Prueba({ maximo }: { maximo: number }) {
    api = useSeleccionLote(maximo)
    vistos.push(api)
    return null
  }

  it('marca y desmarca, sin pasar del tope, con funciones estables', async () => {
    await montar(<Prueba maximo={2} />)
    await act(async () => { api.alternar(elemento(1)) })
    await act(async () => { api.alternar(elemento(2)) })
    expect(api.total).toBe(2)
    expect(api.lleno).toBe(true)
    // Lleno: la tercera no entra.
    await act(async () => { api.alternar(elemento(3)) })
    expect([...api.seleccion.keys()]).toEqual([1, 2])
    expect(api.tiene(3)).toBe(false)
    // Desmarcar deja sitio otra vez.
    await act(async () => { api.alternar(elemento(1)) })
    await act(async () => { api.alternar(elemento(3)) })
    expect([...api.seleccion.keys()]).toEqual([2, 3])
    // Guarda el elemento entero: sobrevive aunque la fila desaparezca de la lista.
    expect(api.seleccion.get(3)!.title).toBe('Peli 3')
    expect(new Set(vistos.map(v => v.alternar)).size).toBe(1)
    expect(new Set(vistos.map(v => v.limpiar)).size).toBe(1)
    await act(async () => { api.limpiar() })
    expect(api.total).toBe(0)
  })
})

describe('la casilla en la lista', () => {
  async function fila(item: LibraryItemResponse, props: Partial<Parameters<typeof LibraryTreeRow>[0]> = {}) {
    const onSelect = vi.fn()
    const onAlternar = vi.fn()
    await montar(
      <table><tbody>
        <LibraryTreeRow item={item} depth={0} instances={[]} onSelect={onSelect} onAction={() => {}} onAlternar={onAlternar} {...props} />
      </tbody></table>,
    )
    return { onSelect, onAlternar }
  }

  it('va dentro de la celda del título: la fila sigue con siete celdas', async () => {
    await fila(elemento(1))
    expect(document.querySelector('td.bib-celda-titulo input[type="checkbox"]')).not.toBeNull()
    expect(document.querySelectorAll('tr.bib-fila > td')).toHaveLength(7)
  })

  it('marcarla avisa con la película y no abre su ficha', async () => {
    const { onSelect, onAlternar } = await fila(elemento(1))
    await pulsar(casilla('Peli 1')!)
    expect(onAlternar).toHaveBeenCalledWith(expect.objectContaining({ id: 1 }))
    expect(onSelect).not.toHaveBeenCalled()
  })

  it('refleja si está marcada y, con el lote lleno, no deja marcar otra', async () => {
    await fila(elemento(1), { seleccionado: true, loteLleno: true })
    expect(casilla('Peli 1')!.checked).toBe(true)
    expect(casilla('Peli 1')!.disabled).toBe(false)
    await desmontar()
    await fila(elemento(2), { loteLleno: true })
    expect(casilla('Peli 2')!.disabled).toBe(true)
  })

  it('una serie no la lleva, así que un clic en su fila solo la despliega', async () => {
    vi.mocked(getLibrary).mockResolvedValue({ items: [], total: 0 } as never)
    const { onAlternar } = await fila(elemento(5, { item_type: 'series', title: 'Serie' }))
    expect(document.querySelector('input[type="checkbox"]')).toBeNull()
    await pulsar(document.querySelector('tr.bib-fila')!)
    expect(getLibrary).toHaveBeenCalled()
    expect(onAlternar).not.toHaveBeenCalled()
  })

  it('sin modo selección no hay casilla', async () => {
    await fila(elemento(1), { onAlternar: undefined })
    expect(document.querySelector('input[type="checkbox"]')).toBeNull()
  })
})

describe('la casilla en los pósters grandes', () => {
  it('marca sin abrir la ficha, y la tarjeta marcada se distingue', async () => {
    const onSelect = vi.fn()
    const onToggle = vi.fn()
    await montar(<LargePosterCard item={elemento(1)} onSelect={onSelect} onToggle={onToggle} seleccionado />)
    expect(document.querySelector('.poster-grande-marco > .lote-casilla-poster')).not.toBeNull()
    expect(document.querySelector('.poster-grande-tarjeta.lote-marcada')).not.toBeNull()
    await pulsar(casilla('Peli 1')!)
    expect(onToggle).toHaveBeenCalledTimes(1)
    expect(onSelect).not.toHaveBeenCalled()
    // Fuera de la casilla, la tarjeta abre la ficha como siempre.
    await pulsar(document.querySelector('.poster-grande-tarjeta')!)
    expect(onSelect).toHaveBeenCalledTimes(1)
  })
})

describe('la barra de la selección', () => {
  it('cuenta las marcadas y las que el filtro esconde', async () => {
    const onSubir = vi.fn()
    await montar(<BarraLote total={3} ocultas={1} onSubir={onSubir} onLimpiar={() => {}} />)
    expect(texto()).toContain('3 seleccionadas (1 oculta por el filtro)')
    await pulsar(boton('Subir por lotes'))
    expect(onSubir).toHaveBeenCalled()
  })

  it('sin nada marcado lo explica y no deja subir', async () => {
    await montar(<BarraLote total={0} ocultas={0} onSubir={() => {}} onLimpiar={() => {}} />)
    expect(texto()).toContain('Marca las películas que quieras subir juntas')
    expect(boton('Subir por lotes')!.disabled).toBe(true)
  })
})
