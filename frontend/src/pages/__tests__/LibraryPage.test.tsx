// @vitest-environment jsdom
/**
 * Biblioteca y «Subir por lotes»: el botón «Seleccionar» pone casillas en películas y series, lo marcado sobrevive a
 * filtrar, a aplicar una vista guardada y a cambiar de vista, la barra dice cuántas esconde el filtro, «Subir por
 * lotes» abre el modal con lo marcado, y salir de la sección lo limpia todo.
 */
import { useState } from 'react'
import { act } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../../api/library', () => ({
  getLibrary: vi.fn(), getLibraryFilterOptions: vi.fn(async () => ({})), getLibraryItem: vi.fn(async () => ({})),
  TOP_LEVEL_PARENT_FILTER: 0,
}))
vi.mock('../../api/instances', () => ({ getInstances: vi.fn(async () => []) }))
vi.mock('../../api/settings', () => ({ fetchSettings: vi.fn(async () => ({ upload_max_concurrent: 1 })) }))

import { getLibrary } from '../../api/library'
import { SeccionVisible } from '../../context/SeccionVisible'
import { SyncContext } from '../../context/SyncContext'
import type { LibraryItemResponse } from '../../types/api'
import { boton, desmontar, esperar, montar, pulsar, texto } from '../../components/__tests__/dom'
import { LibraryPage } from '../LibraryPage'

const item = (id: number, title: string, extra: Partial<LibraryItemResponse> = {}) => ({
  id, item_type: 'movie', title, year: 2021, local_status: 'Disponible', has_spanish_ok: 1, parent_id: null,
  ...extra,
}) as LibraryItemResponse

const DUNE = item(1, 'Dune')
const ALIEN = item(2, 'Alien')
const SERIE = item(3, 'Serie', { item_type: 'series' })

const SYNC = {
  lastInvalidatedAt: 0, libSyncing: false, startLibrarySync: vi.fn(), isAnySyncing: false,
  catalogSyncing: false, catalogStatus: null, startCatalogSync: vi.fn(),
}

let fijarVisible: (v: boolean) => void = () => {}
function Envoltorio() {
  const [visible, setVisible] = useState(true)
  fijarVisible = setVisible
  return (
    <SyncContext.Provider value={SYNC as never}>
      <SeccionVisible visible={visible}><LibraryPage onNavigate={vi.fn()} /></SeccionVisible>
    </SyncContext.Provider>
  )
}

const casilla = (titulo: string) => document.querySelector<HTMLInputElement>(`input[aria-label="Seleccionar «${titulo}»"]`)
const barra = () => document.querySelector('.lote-barra')

async function pagina(vista: 'list' | 'grid' = 'list') {
  localStorage.setItem('emuwarez_uploadrr_library_view', vista)
  await montar(<Envoltorio />)
  await esperar(() => texto().includes('Alien'))
}

beforeEach(() => {
  // Con búsqueda, solo lo que la cumple; sin ella, todo.
  vi.mocked(getLibrary).mockImplementation(async q => {
    const todos = [DUNE, ALIEN, SERIE]
    const items = q?.search ? todos.filter(i => i.title.toLowerCase().includes(String(q.search).toLowerCase())) : todos
    return { items, total: items.length, archivos: 2 } as never
  })
})
afterEach(async () => {
  await desmontar()
  vi.clearAllMocks()
  localStorage.clear()
})

describe('Seleccionar en Biblioteca', () => {
  it('sin el modo selección no hay casillas ni barra; con él, en películas y series', async () => {
    await pagina()
    expect(casilla('Dune')).toBeNull()
    expect(barra()).toBeNull()
    await pulsar(boton('Seleccionar'))
    expect(casilla('Dune')).not.toBeNull()
    expect(casilla('Alien')).not.toBeNull()
    expect(casilla('Serie')).not.toBeNull()
    expect(barra()!.textContent).toContain('Marca las películas, series o temporadas que quieras subir juntas')
  })

  it('lo marcado sobrevive a filtrar, a una vista guardada y a cambiar de vista', async () => {
    localStorage.setItem('emuwarez_uploadrr_library_views', JSON.stringify([
      { id: 'v1', nombre: 'Solo Alien', filtros: { search: 'ali' } },
    ]))
    await pagina()
    await pulsar(boton('Seleccionar'))
    await pulsar(casilla('Dune')!)
    expect(barra()!.textContent).toContain('1 seleccionada')

    // La vista guardada filtra: Dune ya no se ve, pero sigue marcada.
    await pulsar(boton('Solo Alien'))
    await esperar(() => !texto().includes('Dune'))
    expect(barra()!.textContent).toContain('1 seleccionada (1 oculta por el filtro)')

    // En pósters también se marca, y la cuenta sigue.
    await pulsar(document.querySelector('button[aria-label="Vista de pósters"]')!)
    await pulsar(await esperar(() => casilla('Alien')))
    expect(casilla('Alien')!.checked).toBe(true)
    expect(barra()!.textContent).toContain('2 seleccionadas (1 oculta por el filtro)')

    // «Subir por lotes» abre el modal con las dos, en el orden en que se marcaron.
    await pulsar(boton('Subir por lotes'))
    const dialogo = document.querySelector('[role="dialog"]')!
    expect(dialogo.textContent).toContain('Subir por lotes')
    expect([...dialogo.querySelectorAll('.lote-fila-titulo')].map(e => e.textContent)).toEqual(['Dune (2021)', 'Alien (2021)'])
  })

  it('una serie marcada entra en el modal como sus temporadas', async () => {
    vi.mocked(getLibrary).mockImplementation(async q => {
      if (q?.parent_id === 3) {
        const temporadas = [1, 2].map(n => item(30 + n, `Serie - Temporada ${n}`, {
          item_type: 'season', parent_id: 3, season_number: n, resolution: '1080p', video_codec: 'x264',
        }))
        return { items: temporadas, total: 2 } as never
      }
      return { items: [DUNE, ALIEN, SERIE], total: 3, archivos: 2 } as never
    })
    await pagina()
    await pulsar(boton('Seleccionar'))
    await pulsar(casilla('Serie')!)
    await pulsar(casilla('Dune')!)
    await pulsar(boton('Subir por lotes'))
    const dialogo = document.querySelector('[role="dialog"]')!
    await esperar(() => dialogo.querySelectorAll('.lote-fila-titulo').length === 3)
    expect([...dialogo.querySelectorAll('.lote-fila-titulo')].map(e => e.textContent))
      .toEqual(['Serie (2021) - Temporada 1', 'Serie (2021) - Temporada 2', 'Dune (2021)'])
    expect(getLibrary).toHaveBeenCalledWith({ parent_id: 3, type: 'season', limit: 500 })
  })

  it('una temporada se marca desde su serie desplegada, y no cuenta como oculta por el filtro', async () => {
    vi.mocked(getLibrary).mockImplementation(async q => (q?.parent_id === 3
      ? { items: [item(31, 'Serie - Temporada 1', { item_type: 'season', parent_id: 3, season_number: 1 })], total: 1 }
      : { items: [DUNE, ALIEN, SERIE], total: 3, archivos: 2 }) as never)
    await pagina()
    await pulsar(boton('Seleccionar'))
    const filaSerie = [...document.querySelectorAll('tr.bib-fila')].find(tr => tr.textContent?.includes('Serie'))!
    await pulsar(filaSerie)
    await pulsar(await esperar(() => casilla('Serie - Temporada 1')))
    expect(casilla('Serie - Temporada 1')!.checked).toBe(true)
    expect(barra()!.textContent).toContain('1 seleccionada')
    expect(barra()!.textContent).not.toContain('oculta')
  })

  it('«Limpiar» desmarca todo y apagar «Seleccionar» también', async () => {
    await pagina()
    await pulsar(boton('Seleccionar'))
    await pulsar(casilla('Dune')!)
    await pulsar(boton('Limpiar'))
    expect(casilla('Dune')!.checked).toBe(false)
    await pulsar(casilla('Alien')!)
    await pulsar(boton('Seleccionar'))
    expect(barra()).toBeNull()
    await pulsar(boton('Seleccionar'))
    expect(casilla('Alien')!.checked).toBe(false)
  })

  it('salir de Biblioteca limpia la selección y quita el modo', async () => {
    await pagina()
    await pulsar(boton('Seleccionar'))
    await pulsar(casilla('Dune')!)
    await act(async () => { fijarVisible(false) })
    await act(async () => { fijarVisible(true) })
    expect(barra()).toBeNull()
    await pulsar(boton('Seleccionar'))
    expect(casilla('Dune')!.checked).toBe(false)
    expect(barra()!.textContent).not.toContain('seleccionada')
  })
})

describe('Columnas de la lista', () => {
  const cabeceras = () => [...document.querySelectorAll('thead th')]

  it('cada dato filtrable tiene su columna con su filtro en la cabecera, alineada con las celdas', async () => {
    await pagina()
    const nombres = cabeceras().map(th => th.textContent?.replace(/[▾▼▲]/g, '').trim())
    expect(nombres).toEqual([
      'TítuloTipo', 'Origen', 'Estado', 'Petición', 'Resolución', 'Proveedor', 'Fuente', 'Grupo',
      'Español', 'EMuwarez', 'Tamaño', 'Acciones',
    ])
    for (const col of ['Origen', 'Resolución', 'Proveedor', 'Fuente', 'Grupo']) {
      const th = cabeceras().find(c => c.textContent?.includes(col))!
      expect(th.querySelectorAll('.hf-trigger')).toHaveLength(1)
    }
    // El tipo no es columna: su filtro acompaña al nombre del título.
    expect(cabeceras()[0].querySelector('.hf-trigger')!.textContent).toContain('Tipo')
    expect(document.querySelectorAll('tr.bib-fila')[0].querySelectorAll(':scope > td')).toHaveLength(cabeceras().length)
  })

  it('el menú de la columna Grupo se abre desde su propia cabecera', async () => {
    await pagina()
    const th = cabeceras()[7]
    await pulsar(th.querySelector('.hf-trigger')!)
    expect(document.body.textContent).toContain('Desmarcar todo')
    expect(cabeceras()[0].querySelectorAll('.hf-trigger')).toHaveLength(1)
  })
})
