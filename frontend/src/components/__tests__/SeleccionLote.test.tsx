// @vitest-environment jsdom
/**
 * Marcar películas, series y temporadas para «Subir por lotes»: el tope del lote, que la casilla no abra la ficha ni
 * despliegue la fila, que los capítulos no la lleven, que una serie desplegada se la pase a sus temporadas, que la
 * lista siga con siete columnas y lo que dice la barra.
 */
import { act } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'

vi.mock('../../api/library', () => ({ getLibrary: vi.fn() }))

import { getLibrary } from '../../api/library'
import type { DashboardRecommendationItem } from '../../api/dashboard'
import { useSeleccionLote } from '../../hooks/useSeleccionLote'
import { claveDelPanel } from '../../utils/lote'
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
  let api: ReturnType<typeof useSeleccionLote<LibraryItemResponse>>
  const vistos: ReturnType<typeof useSeleccionLote<LibraryItemResponse>>[] = []
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

  it('con otra clave (la del Panel), dos filas del mismo elemento son dos marcas', async () => {
    let panel!: ReturnType<typeof useSeleccionLote<DashboardRecommendationItem, string>>
    function PruebaPanel() {
      panel = useSeleccionLote<DashboardRecommendationItem, string>(50, claveDelPanel)
      return null
    }
    const fila = (rec: number | null, objetivo: number | null) =>
      ({ id: 5, rec_request_id: rec, library_target_id: objetivo, title: 'Serie' }) as DashboardRecommendationItem
    await montar(<PruebaPanel />)
    await act(async () => { panel.alternar(fila(77, 55)) })
    await act(async () => { panel.alternar(fila(78, 55)) })
    await act(async () => { panel.alternar(fila(null, null)) })
    expect([...panel.seleccion.keys()]).toEqual(['77-55', '78-55', 'u-5'])
    expect(panel.tiene('78-55')).toBe(true)
    await act(async () => { panel.alternar(fila(78, 55)) })
    expect(panel.tiene('78-55')).toBe(false)
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

  it('va dentro de la celda del título: la fila sigue con doce celdas', async () => {
    await fila(elemento(1))
    expect(document.querySelector('td.bib-celda-titulo input[type="checkbox"]')).not.toBeNull()
    expect(document.querySelectorAll('tr.bib-fila > td')).toHaveLength(12)
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

  it('una serie la lleva: marcarla no la despliega, y un clic en la fila sí', async () => {
    vi.mocked(getLibrary).mockResolvedValue({ items: [], total: 0 } as never)
    const { onAlternar } = await fila(elemento(5, { item_type: 'series', title: 'Serie' }))
    await pulsar(casilla('Serie')!)
    expect(onAlternar).toHaveBeenCalledWith(expect.objectContaining({ id: 5 }))
    expect(getLibrary).not.toHaveBeenCalled()
    await pulsar(document.querySelector('tr.bib-fila')!)
    expect(getLibrary).toHaveBeenCalled()
    expect(onAlternar).toHaveBeenCalledTimes(1)
  })

  it('una serie desplegada pasa la casilla a sus temporadas, marcadas según la lista; un capítulo no la lleva', async () => {
    vi.mocked(getLibrary).mockImplementation(async q => ({
      items: q?.type === 'season'
        ? [elemento(51, { item_type: 'season', title: 'Serie - Temporada 1', parent_id: 5 }),
           elemento(52, { item_type: 'season', title: 'Serie - Temporada 2', parent_id: 5 })]
        : [elemento(511, { item_type: 'episode', title: 'Serie S01E01', parent_id: 51 })],
      total: 2,
    }) as never)
    const { onAlternar } = await fila(elemento(5, { item_type: 'series', title: 'Serie' }), { temporadasMarcadas: '52' })
    await pulsar(document.querySelector('tr.bib-fila')!)
    expect(casilla('Serie - Temporada 1')!.checked).toBe(false)
    expect(casilla('Serie - Temporada 2')!.checked).toBe(true)
    await pulsar(casilla('Serie - Temporada 1')!)
    expect(onAlternar).toHaveBeenCalledWith(expect.objectContaining({ id: 51 }))
    // Desplegar la temporada enseña sus capítulos, sin casilla.
    const filaTemporada = [...document.querySelectorAll('tr.bib-fila')].find(tr => tr.textContent?.includes('Temporada 1'))!
    await pulsar(filaTemporada)
    expect(texto()).toContain('S01E01')
    expect(document.querySelectorAll('input[type="checkbox"]')).toHaveLength(3)
  })

  it('un capítulo no la lleva', async () => {
    await fila(elemento(7, { item_type: 'episode', title: 'Serie S01E01' }))
    expect(document.querySelector('input[type="checkbox"]')).toBeNull()
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
    expect(texto()).toContain('Marca las películas, series o temporadas que quieras subir juntas')
    expect(boton('Subir por lotes')!.disabled).toBe(true)
  })

  it('el Panel le pone su texto', async () => {
    await montar(<BarraLote total={2} vacia="Marca las peticiones" textoSubir="Subir seleccionadas (2)" onSubir={() => {}} onLimpiar={() => {}} />)
    expect(texto()).toContain('2 seleccionadas')
    expect(texto()).not.toContain('oculta')
    expect(boton('Subir seleccionadas (2)')!.disabled).toBe(false)
  })
})
