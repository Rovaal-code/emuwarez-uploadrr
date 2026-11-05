// @vitest-environment jsdom
// Peticiones con servidor simulado: grupos por estado, orden por recompensa y columna Autor. Y «Subir seleccionadas»:
// marcar las peticiones que se pueden subir y subirlas juntas con el modal de «Subir por lotes» (el de verdad), cada
// una con su petición, como en «Listo para subir» del Panel.
import { act, useState } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../../api/requests', () => ({ getRequests: vi.fn(), getRequestDetail: vi.fn() }))
vi.mock('../../api/requestReadiness', () => ({ getCandidates: vi.fn(), getReadiness: vi.fn() }))
vi.mock('../../api/library', () => ({
  getLibraryItem: vi.fn(), getLibrary: vi.fn(), getEmuComparison: vi.fn(), suggestProvider: vi.fn(),
}))
vi.mock('../../api/instances', () => ({ getInstances: vi.fn() }))
vi.mock('../../api/uploads', () => ({ queueLote: vi.fn(), runUploadChecks: vi.fn(), getUploadChecksProgress: vi.fn() }))
vi.mock('../../api/nomenclature', () => ({ getNomenclatureFields: vi.fn(), previewNomenclatureFields: vi.fn() }))
vi.mock('../../api/settings', () => ({ fetchSettings: vi.fn() }))
vi.mock('../../api/eventos', () => ({ seguirProgreso: vi.fn(() => () => {}) }))
vi.mock('../../components/UploadWizardModal', () => ({ UploadWizardModal: () => null }))

import { getRequestDetail, getRequests } from '../../api/requests'
import { getInstances } from '../../api/instances'
import { getEmuComparison, getLibraryItem } from '../../api/library'
import { getNomenclatureFields } from '../../api/nomenclature'
import { fetchSettings } from '../../api/settings'
import { queueLote, runUploadChecks } from '../../api/uploads'
import { SeccionVisible } from '../../context/SeccionVisible'
import { SyncContext } from '../../context/SyncContext'
import type { LibraryItemResponse, RequestDetailResponse, RequestItemResponse } from '../../types/api'
import { boton, campo, desmontar, elegir, escribir, esperar, montar, pulsar, texto } from '../../components/__tests__/dom'
import { MAX_ELEMENTOS_LOTE } from '../../utils/lote'
import { RequestsPage } from '../RequestsPage'

const peticion = (id: number, extra: Partial<RequestItemResponse>): RequestItemResponse => ({
  id, emu_id: String(id), title: `Petición ${id}`, category: 'Películas', requested_source: null, requested_resolution: null,
  emu_status: 'unfilled', points: null, comments: null, votes: null, author: 'pedidor', is_mine: false, req_scope: null,
  req_season: null, req_episode: null, created_at: '2026-10-01T00:00:00Z', tmdb_id: null, imdb_id: null, tvdb_id: null,
  mal_id: null, url: null, compatibility_status: null, compatibility_confidence: null, library_item_id: null,
  library_title: null, library_year: null, instance_type: null, instance_name: null, instance_id: null, title_slug: null,
  library_tmdb_id: null, display_title: null, local_status: null, poster_url: null, backdrop_url: null, reviewed_at: null,
  updated_at: null, readiness_status: null, readiness_action: null, readiness_best_library_item_id: null, ...extra,
}) as RequestItemResponse

const DATOS = [
  peticion(1, { readiness_status: 'no_local_match', compatibility_status: 'Sin coincidencia', points: 500 }),
  peticion(2, { readiness_status: 'ready_to_upload', compatibility_status: 'Compatible', points: 40 }),
  peticion(3, { readiness_status: 'no_castellano', compatibility_status: 'Compatible', points: 90 }),
  peticion(4, { readiness_status: 'ready_to_upload', compatibility_status: 'Compatible', points: 300 }),
  peticion(5, { readiness_status: 'filled', compatibility_status: 'Llena', points: 999 }),
  peticion(6, { readiness_status: 'no_local_match', compatibility_status: 'Sin coincidencia', points: 20 }),
]

async function pagina() {
  await montar(
    <SyncContext.Provider value={{
      requestsSyncing: false, requestsStatus: null, startRequestsSync: vi.fn(), lastInvalidatedAt: 0, isAnySyncing: false,
    } as never}>
      <SeccionVisible visible><RequestsPage /></SeccionVisible>
    </SyncContext.Provider>,
  )
  await esperar(() => document.querySelector('table.data-table tbody tr'))
}

const cabeceras = () => [...document.querySelectorAll('thead th')].map(th => th.textContent?.trim())
const grupos = () => [...document.querySelectorAll('tbody.pet-bloque')].map(b => ({
  titulo: b.querySelector('.pet-grupo-titulo')!.textContent,
  n: b.querySelector('.pet-grupo-n')!.textContent,
  filas: [...b.querySelectorAll('tr.clickable')].map(tr => tr.querySelector('.lib-title-link')!.textContent),
}))
const casillaAutor = () => campo<HTMLInputElement>('Mostrar autor')
const ultimaLlamada = () => { const l = vi.mocked(getRequests).mock.calls; return l[l.length - 1][0] }

beforeEach(() => {
  localStorage.clear()
  vi.mocked(getRequests).mockResolvedValue({ items: DATOS, total: DATOS.length } as never)
  vi.mocked(getInstances).mockResolvedValue([])
})
afterEach(desmontar)

describe('Peticiones', () => {
  it('sin orden elegido agrupa por lo que se puede hacer y ordena cada grupo por recompensa', async () => {
    await pagina()
    expect(grupos()).toEqual([
      { titulo: 'Lista para subir', n: '2', filas: ['Petición 4', 'Petición 2'] },
      { titulo: 'Parcial', n: '1', filas: ['Petición 3'] },
      { titulo: 'No la tienes', n: '2', filas: ['Petición 1', 'Petición 6'] },
      { titulo: 'Cerradas', n: '1', filas: ['Petición 5'] },
    ])
    // Al servidor se le pide por recompensa: es el orden de dentro de cada grupo.
    expect(vi.mocked(getRequests).mock.calls[0][0]).toMatchObject({ sort: 'points_desc' })
  })

  it('elegir otro orden quita los grupos y deja la lista plana', async () => {
    await pagina()
    await elegir(document.querySelector('select.form-select') as HTMLSelectElement, 'created_desc')
    await esperar(() => document.querySelectorAll('tbody.pet-bloque').length === 0)
    expect(document.querySelectorAll('tr.clickable')).toHaveLength(DATOS.length)
    expect(document.querySelector('.pet-grupo-cab')).toBeNull()
    expect(ultimaLlamada()).toMatchObject({ sort: 'created_desc' })
  })

  it('ordenar desde la cabecera de Puntos también quita los grupos', async () => {
    await pagina()
    await pulsar(document.querySelector('button[aria-label="Puntos / recompensa"]')!)
    await esperar(() => document.querySelectorAll('tbody.pet-bloque').length === 0)
    expect(ultimaLlamada()).toMatchObject({ sort: 'points_desc' })
  })

  it('la columna Autor está oculta por defecto', async () => {
    await pagina()
    expect(cabeceras().some(c => c?.startsWith('Autor'))).toBe(false)
    expect(document.body.textContent).not.toContain('pedidor')
    expect(casillaAutor()!.checked).toBe(false)
  })

  it('la casilla muestra la columna Autor y lo recuerda', async () => {
    await pagina()
    await pulsar(casillaAutor())
    expect(cabeceras().some(c => c?.startsWith('Autor'))).toBe(true)
    expect(document.body.textContent).toContain('pedidor')
    expect(localStorage.getItem('emuwarez_peticiones_mostrar_autor')).toBe('1')
    // Las cabeceras de grupo ocupan todo el ancho, con la columna de más.
    const th = document.querySelector('th.pet-grupo-th')!
    expect(th.getAttribute('colspan')).toBe(String(document.querySelectorAll('thead th').length))
  })

  it('con la preferencia guardada arranca con el autor a la vista', async () => {
    localStorage.setItem('emuwarez_peticiones_mostrar_autor', '1')
    await pagina()
    expect(casillaAutor()!.checked).toBe(true)
    expect(cabeceras().some(c => c?.startsWith('Autor'))).toBe(true)
  })
})

// ── «Subir seleccionadas» ───────────────────────────────────────────────────────────────────────────────────────

describe('«Subir seleccionadas» en Peticiones', () => {
  const ficha = (id: number, extra: Partial<LibraryItemResponse>) => ({
    id, item_type: 'movie', title: `Ficha ${id}`, year: 2016, local_status: 'Disponible', has_spanish_ok: 1,
    resolution: '1080p', source: 'WEB-DL', video_codec: 'x264', ...extra,
  }) as LibraryItemResponse
  // La serie 5 (Lost) con su temporada 55 y su capítulo 66; la película 20.
  const FICHAS: Record<number, LibraryItemResponse> = {
    5: ficha(5, { item_type: 'series', title: 'Lost' }),
    55: ficha(55, { item_type: 'season', title: 'Lost - Temporada 2', parent_id: 5, season_number: 2 }),
    66: ficha(66, { item_type: 'episode', title: 'Lost S01E12', season_number: 1, episode_number: 12 }),
    20: ficha(20, { title: 'Única', source: 'BluRay' }),
  }
  // Lo que da la ficha de la petición: la fila a la que se refiere (la temporada o el capítulo, no la serie).
  const DESTINO: Record<number, number> = { 71: 55, 72: 66 }
  const ENTORNO = { ready: true, checks: [{ id: 'emuwarez', label: 'eMuwarez responde', status: 'ok' as const, message: '' }] }

  const lista = (extra: Partial<RequestItemResponse>): Partial<RequestItemResponse> =>
    ({ compatibility_status: 'Compatible', readiness_status: 'ready_to_upload', ...extra })
  const PELICULA = peticion(70, lista({ title: 'Única', library_item_id: 20, points: 900 }))
  const TEMPORADA = peticion(71, lista({
    title: 'Lost', category: 'TV', library_item_id: 5, req_scope: 'season', req_season: 2, points: 800,
  }))
  const CAPITULO = peticion(72, lista({
    title: 'Lost', category: 'TV', library_item_id: 5, req_scope: 'episode', req_season: 1, req_episode: 12, points: 700,
  }))
  const SIN_CASTELLANO = peticion(73, lista({ title: 'Muda', library_item_id: 20, readiness_status: 'no_castellano' }))
  const SIN_FILA = peticion(74, lista({ title: 'Sin fila', library_item_id: null }))
  const PARCIAL = peticion(75, { title: 'A medias', compatibility_status: 'Parcial', library_item_id: 20 })

  let fijarVisible: (v: boolean) => void = () => {}
  const navegar = vi.fn()
  function Envoltorio() {
    const [visible, setVisible] = useState(true)
    fijarVisible = setVisible
    return (
      <SyncContext.Provider value={{
        requestsSyncing: false, requestsStatus: null, startRequestsSync: vi.fn(), lastInvalidatedAt: 0, isAnySyncing: false,
      } as never}>
        <SeccionVisible visible={visible}><RequestsPage onNavigate={navegar} /></SeccionVisible>
      </SyncContext.Provider>
    )
  }
  async function paginaConSeleccion(items: RequestItemResponse[]) {
    // Con búsqueda, solo las que la contienen en el título (para ver lo marcado que el filtro esconde).
    vi.mocked(getRequests).mockImplementation(async q => {
      const quedan = q?.search ? items.filter(i => i.title.includes(q.search!)) : items
      return { items: quedan, total: quedan.length } as never
    })
    await montar(<Envoltorio />)
    await esperar(() => document.querySelector('table.data-table tbody tr'))
  }

  const casillas = () => [...document.querySelectorAll<HTMLInputElement>('tbody input[type="checkbox"]')]
  const casilla = (titulo: string) => document.querySelector<HTMLInputElement>(`input[aria-label="Seleccionar «${titulo}»"]`)!
  const seleccionar = () => pulsar(boton('Seleccionar'))
  const titulosLote = () => [...document.querySelectorAll('.lote-fila-titulo')].map(e => e.textContent)
  const peticionesLote = () => [...document.querySelectorAll('.lote-fila-peticion')].map(e => e.textContent)

  beforeEach(() => {
    vi.mocked(getLibraryItem).mockImplementation(async id => FICHAS[id])
    vi.mocked(getRequestDetail).mockImplementation(async id => ({
      id, match: { library_item_id: 5, library_target_id: DESTINO[id] },
    }) as unknown as RequestDetailResponse)
    vi.mocked(fetchSettings).mockResolvedValue({ upload_max_concurrent: 1 } as never)
    vi.mocked(runUploadChecks).mockImplementation(async (id, scope) => (scope === 'environment'
      ? ENTORNO
      : { ready: true, nombre: `Pack ${id}`, checks: [{ id: 'accesible', label: 'Fichero accesible', status: 'ok' as const, message: '' }] }))
    vi.mocked(getNomenclatureFields).mockImplementation(async id => ({
      fields: { source: 'BluRay', provider: null }, torrent_name: `Nombre ${id}`, internal_mkv_title: '', blocked: false,
    }) as never)
    vi.mocked(getEmuComparison).mockResolvedValue({ available: true, message: null, matches: [] })
    vi.mocked(queueLote).mockImplementation(async elementos => ({
      lote_id: '0123456789ab', encolados: elementos.length, saltados: 0,
      resultados: elementos.map((e, i) => ({ item_id: e.item_id, status: 'queued' as const, job_id: 100 + i, errors: [] })),
    }))
  })

  it('sin nada que se pueda subir no hay «Seleccionar»', async () => {
    await paginaConSeleccion([SIN_CASTELLANO, SIN_FILA, PARCIAL])
    expect(boton('Seleccionar')).toBeUndefined()
  })

  it('«Seleccionar» pone casillas solo en las que el Panel tiene en «Listo para subir»', async () => {
    await paginaConSeleccion([PELICULA, TEMPORADA, SIN_CASTELLANO, SIN_FILA, PARCIAL])
    expect(casillas()).toHaveLength(0)
    expect(document.querySelector('.lote-barra')).toBeNull()
    await seleccionar()
    expect(boton('Seleccionar')!.getAttribute('aria-pressed')).toBe('true')
    expect(casillas().map(c => c.getAttribute('aria-label'))).toEqual([
      'Seleccionar «Única»', 'Seleccionar «Lost - Temporada 2»',
    ])
    // La casilla va en la celda Título: la tabla no gana columnas.
    expect(document.querySelector('th.pet-grupo-th')!.getAttribute('colspan'))
      .toBe(String(document.querySelectorAll('thead th').length))
    expect(texto()).toContain('Marca las peticiones listas que quieras subir juntas')
    expect(boton('Subir seleccionadas (0)')!.disabled).toBe(true)
    await pulsar(casilla('Única'))
    // Marcar no abre la ficha de la petición.
    expect(getRequestDetail).not.toHaveBeenCalled()
    expect(document.querySelector('.pet-detalle')).toBeNull()
    await pulsar(casilla('Lost - Temporada 2'))
    expect(texto()).toContain('2 seleccionadas')
    expect(boton('Subir seleccionadas (2)')!.disabled).toBe(false)
    // Apagarlo quita las casillas y lo marcado.
    await seleccionar()
    expect(casillas()).toHaveLength(0)
    await seleccionar()
    expect(casillas().filter(c => c.checked)).toHaveLength(0)
  })

  it('sube lo marcado como un lote: cada una con su petición, la de temporada o capítulo sobre esa fila', async () => {
    await paginaConSeleccion([PELICULA, TEMPORADA, CAPITULO])
    await seleccionar()
    await pulsar(casilla('Única'))
    await pulsar(casilla('Lost - Temporada 2'))
    await pulsar(casilla('Lost - S01E12'))
    const cargasAntes = vi.mocked(getRequests).mock.calls.length
    await pulsar(boton('Subir seleccionadas (3)'))
    await esperar(() => document.querySelector('.lote-lista'))
    // La película va derecha a su fila; la temporada y el capítulo, a la que da la ficha de la petición (no la serie).
    expect(vi.mocked(getRequestDetail).mock.calls.map(c => c[0])).toEqual([71, 72])
    expect(vi.mocked(getLibraryItem).mock.calls.map(c => c[0])).toEqual([20, 55, 66])
    expect(titulosLote()).toEqual(['Única (2016)', 'Lost (2016) - Temporada 2', 'Lost (2016) - S01E12'])
    expect(peticionesLote()).toEqual(['Petición #70', 'Petición #71', 'Petición #72'])

    await pulsar(boton('Continuar (3)'))
    await esperar(() => boton('Subir 3') && !boton('Subir 3')!.disabled)
    await pulsar(boton('Subir 3'))
    await esperar(() => texto().includes('3 de 3 encoladas'))
    expect(vi.mocked(queueLote).mock.calls[0][0].map(e => [e.item_id, e.request_item_id])).toEqual([
      [20, 70], [55, 71], [66, 72],
    ])
    // Encolado: la selección se limpia, el modo se apaga y la lista se recarga.
    expect(document.querySelector('.lote-barra')).toBeNull()
    expect(casillas()).toHaveLength(0)
    expect(vi.mocked(getRequests).mock.calls.length).toBeGreaterThan(cargasAntes)
    await seleccionar()
    expect(casillas().filter(c => c.checked)).toHaveLength(0)
  })

  it('si alguna ya no está, lo dice y abre el lote con el resto', async () => {
    vi.mocked(getRequestDetail).mockRejectedValue(new Error('404'))
    await paginaConSeleccion([PELICULA, TEMPORADA])
    await seleccionar()
    await pulsar(casilla('Única'))
    await pulsar(casilla('Lost - Temporada 2'))
    await pulsar(boton('Subir seleccionadas (2)'))
    await esperar(() => document.querySelector('.lote-lista'))
    expect(document.querySelector('[role="alert"]')!.textContent).toContain('No se pudo abrir «Lost - Temporada 2»')
    expect(titulosLote()).toEqual(['Única (2016)'])
  })

  it('lo marcado sobrevive al filtro y la barra cuenta lo que esconde', async () => {
    await paginaConSeleccion([PELICULA, TEMPORADA])
    await seleccionar()
    await pulsar(casilla('Única'))
    await pulsar(casilla('Lost - Temporada 2'))
    await escribir(document.querySelector<HTMLInputElement>('input.pet-buscar')!, 'Lost')
    await esperar(() => document.querySelectorAll('tbody tr.clickable').length === 1)
    expect(texto()).toContain('2 seleccionadas (1 oculta por el filtro)')
    expect(casilla('Lost - Temporada 2').checked).toBe(true)
  })

  it(`no deja marcar más de ${MAX_ELEMENTOS_LOTE}`, async () => {
    const muchas = Array.from({ length: MAX_ELEMENTOS_LOTE + 1 }, (_, i) =>
      peticion(200 + i, lista({ title: `Película ${200 + i}`, library_item_id: 20 })))
    await paginaConSeleccion(muchas)
    await seleccionar()
    for (const c of casillas().slice(0, MAX_ELEMENTOS_LOTE)) await pulsar(c)
    expect(texto()).toContain(`${MAX_ELEMENTOS_LOTE} seleccionadas`)
    expect(texto()).toContain(`tope de ${MAX_ELEMENTOS_LOTE} por lote`)
    const ultima = casillas()[MAX_ELEMENTOS_LOTE]
    expect(ultima.checked).toBe(false)
    expect(ultima.disabled).toBe(true)
    // Cincuenta clics, cada uno repintando la tabla entera: con otros ficheros a la vez pasa de los 5 s por defecto.
  }, 30_000)

  it('salir de Peticiones limpia la selección y quita el modo', async () => {
    await paginaConSeleccion([PELICULA])
    await seleccionar()
    await pulsar(casilla('Única'))
    expect(texto()).toContain('1 seleccionada')
    await act(async () => { fijarVisible(false) })
    await act(async () => { fijarVisible(true) })
    await esperar(() => document.querySelector('table.data-table tbody tr'))
    expect(casillas()).toHaveLength(0)
    expect(document.querySelector('.lote-barra')).toBeNull()
    await seleccionar()
    expect(casilla('Única').checked).toBe(false)
  })

  it('salir mientras se piden las fichas no abre el lote al volver', async () => {
    let soltar: () => void = () => {}
    vi.mocked(getLibraryItem).mockImplementation(id => new Promise(resolve => { soltar = () => resolve(FICHAS[id]) }))
    await paginaConSeleccion([PELICULA])
    await seleccionar()
    await pulsar(casilla('Única'))
    await pulsar(boton('Subir seleccionadas (1)'))
    await act(async () => { fijarVisible(false) })
    await act(async () => { soltar() })
    await act(async () => { fijarVisible(true) })
    expect(document.querySelector('.lote-lista')).toBeNull()
  })
})
